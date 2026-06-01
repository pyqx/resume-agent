"""SSE streaming chat endpoint."""

import json
import logging
import re

from fastapi import APIRouter, Depends, Request
from sse_starlette.sse import EventSourceResponse

from api.deps import get_agent_loop
from agent.loop import AgentLoop

logger = logging.getLogger(__name__)

router = APIRouter()


def _build_resume_summary(resume) -> str:
    """Build a concise text summary of a resume for inclusion in the system prompt."""
    pi = resume.personal_info
    lines = []
    if pi.full_name:
        lines.append(f"Name: {pi.full_name}")
    if pi.email:
        lines.append(f"Email: {pi.email}")
    if pi.phone:
        lines.append(f"Phone: {pi.phone}")

    edu = resume.education
    if edu:
        lines.append(f"Education ({len(edu)} entries):")
        for e in edu[:4]:
            lines.append(f"  - {e.degree or ''} {e.major or ''} at {e.school or ''}")

    work = resume.work_experience
    if work:
        lines.append(f"Work Experience ({len(work)} entries):")
        for w in work[:6]:
            bullets_preview = ", ".join(w.bullets[:2]) if w.bullets else w.description or ""
            lines.append(f"  - {w.position or ''} at {w.company or ''}: {bullets_preview}")

    projects = resume.project_experience
    if projects:
        lines.append(f"Projects ({len(projects)} entries):")
        for p in projects[:4]:
            lines.append(f"  - {p.name or ''}: {p.description or ''}")

    skills = resume.skills
    if skills:
        names = [s.name for s in skills if s.name]
        lines.append(f"Skills ({len(names)}): {', '.join(names[:30])}")

    if resume.target_position:
        lines.append(f"Target Position: {resume.target_position}")
    if resume.target_industry:
        lines.append(f"Target Industry: {resume.target_industry}")

    return "\n".join(lines)


_GITHUB_RE = re.compile(r'https?://github\.com/[\w.-]+/[\w.-]+')


def _detect_github_urls(body: dict, ws: dict) -> dict:
    """Extract GitHub URLs from the message body and set in working_state."""
    message = body.get("message", "")
    if not message:
        return ws
    match = _GITHUB_RE.search(message)
    if match:
        ws["github_url"] = match.group().rstrip("/")
        ws["github_url_provided"] = True
        logger.info("GitHub URL detected: %s", ws["github_url"])
    return ws


def _enrich_working_state(working_state: dict | None, body: dict) -> dict:
    """Load resume data into working_state if resume_id is provided."""
    import api.routes.resume as resume_mod
    ws = dict(working_state) if working_state else {}
    resume_id = body.get("resume_id")
    if not resume_id:
        resume_id = resume_mod.get_current_resume_id()
    if not resume_id and resume_mod._resume_store:
        resume_id = next(iter(resume_mod._resume_store.keys()))
    if resume_id:
        resume = resume_mod._resume_store.get(resume_id)
        if resume:
            resume_mod.set_current_resume_id(resume_id)
            ws["resume_loaded"] = True
            ws["resume_id"] = resume_id
            ws["resume_summary"] = _build_resume_summary(resume)
            logger.info("Resume loaded: id=%s name=%s", resume_id, resume.personal_info.full_name or resume.source_filename)
        else:
            logger.warning("Resume not found in store: id=%s", resume_id)
            ws["resume_loaded"] = False
    return ws


@router.post("/stream")
async def chat_stream(
    request: Request,
    agent: AgentLoop = Depends(get_agent_loop),
):
    """SSE endpoint for real-time Agent interaction.

    Accepts JSON body: {"message": "...", "session_id": "...", "user_id": "...", "resume_id": "..."}
    Returns SSE events: plan_start, plan_decision, tool_call, tool_result, observe, final
    """
    body = await request.json()
    message = body.get("message", "")
    session_id = body.get("session_id")
    user_id = body.get("user_id", "default")
    working_state = _enrich_working_state(body.get("working_state"), body)
    working_state = _detect_github_urls(body, working_state)

    if not message:
        return EventSourceResponse(_error_stream("message is required"))

    # Session management: create session if needed, save user message
    from api.deps import get_db
    from api.session_manager import SessionManager
    db = await get_db()
    sm = SessionManager(db)
    history_messages = []
    if not session_id:
        session_id = await sm.create_session(
            user_id=user_id,
            resume_id=body.get("resume_id", ""),
        )
        logger.info("Session created: id=%s", session_id)
    else:
        # Load conversation history and restore resume association
        history_messages = await sm.get_messages(session_id)
        logger.info("Session resumed: id=%s history_turns=%d", session_id, len(history_messages))
        # Restore resume_id from session if not provided
        sessions_list = await sm.list_sessions(user_id=user_id)
        for s in sessions_list:
            if s["id"] == session_id and s.get("resume_id"):
                if not body.get("resume_id") and s["resume_id"]:
                    logger.info("Restoring resume from session: resume_id=%s", s["resume_id"])
                    working_state = _enrich_working_state(
                        working_state,
                        {"resume_id": s["resume_id"]},
                    )
                break

    await sm.save_message(session_id, "user", message)
    title = message[:50] + ("..." if len(message) > 50 else "")
    await sm.update_title(session_id, title)

    async def event_generator():
        # Emit session_id to frontend
        yield {
            "event": "session_created",
            "data": json.dumps({"session_id": session_id}),
        }
        agent_response = ""
        try:
            async for event in agent.run(
                user_message=message,
                session_id=session_id,
                user_id=user_id,
                working_state=working_state,
                history=history_messages,
            ):
                yield {
                    "event": event["type"],
                    "data": json.dumps(event["data"], default=str),
                }
                if event["type"] == "final":
                    agent_response = event["data"].get("response", "")
        except Exception as e:
            logger.exception(f"Agent loop error: {e}")
            yield {
                "event": "error",
                "data": json.dumps({"error": str(e)}),
            }
        finally:
            if agent_response:
                await sm.save_message(session_id, "agent", agent_response)

    return EventSourceResponse(event_generator())


@router.post("/send")
async def chat_send(
    request: Request,
    agent: AgentLoop = Depends(get_agent_loop),
):
    """Non-streaming endpoint for simple requests."""
    body = await request.json()
    message = body.get("message", "")
    session_id = body.get("session_id")
    user_id = body.get("user_id", "default")
    working_state = _enrich_working_state(body.get("working_state"), body)
    working_state = _detect_github_urls(body, working_state)

    if not message:
        return {"error": "message is required"}

    # Session management
    from api.deps import get_db
    from api.session_manager import SessionManager
    db = await get_db()
    sm = SessionManager(db)
    history_messages = []
    if not session_id:
        session_id = await sm.create_session(
            user_id=user_id,
            resume_id=body.get("resume_id", ""),
        )
    else:
        history_messages = await sm.get_messages(session_id)
        sessions_list = await sm.list_sessions(user_id=user_id)
        for s in sessions_list:
            if s["id"] == session_id and s.get("resume_id"):
                if not body.get("resume_id") and s["resume_id"]:
                    working_state = _enrich_working_state(
                        working_state,
                        {"resume_id": s["resume_id"]},
                    )
                break

    await sm.save_message(session_id, "user", message)
    title = message[:50] + ("..." if len(message) > 50 else "")
    await sm.update_title(session_id, title)

    responses = []
    agent_response = ""
    async for event in agent.run(
        user_message=message,
        session_id=session_id,
        user_id=user_id,
        working_state=working_state,
        history=history_messages,
    ):
        responses.append(event)
        if event["type"] == "final":
            agent_response = event["data"].get("response", "")

    if agent_response:
        await sm.save_message(session_id, "agent", agent_response)

    return {"events": responses, "session_id": session_id}


async def _error_stream(message: str):
    yield {
        "event": "error",
        "data": json.dumps({"error": message}),
    }
