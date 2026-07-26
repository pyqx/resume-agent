"""SSE streaming chat endpoint."""

import asyncio
import json
import logging
import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, ValidationError
from sse_starlette.sse import EventSourceResponse
from starlette.requests import Request

from api.deps import (
    get_agent_loop,
    get_memory_extractor,
    get_memory_store,
    get_session_manager,
)
from agent.loop import AgentLoop

logger = logging.getLogger(__name__)

router = APIRouter()

_GITHUB_RE = re.compile(r"https?://github\.com/[\w.-]+/[\w.-]+")


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=8000)
    session_id: str | None = None
    user_id: str = "default"
    resume_id: str = ""
    working_state: dict = Field(default_factory=dict)


def _build_resume_summary(resume) -> str:
    """Concise resume summary for the system prompt.

    Contact details are intentionally omitted — the LLM layer masks PII
    anyway, and planning never needs a phone number.
    """
    pi = resume.personal_info
    lines = []
    if pi.full_name:
        lines.append(f"Name: {pi.full_name}")

    if resume.education:
        lines.append(f"Education ({len(resume.education)} entries):")
        for e in resume.education[:4]:
            lines.append(f"  - {e.degree or ''} {e.major or ''} at {e.school or ''}")

    if resume.work_experience:
        lines.append(f"Work Experience ({len(resume.work_experience)} entries):")
        for w in resume.work_experience[:6]:
            bullets_preview = ", ".join(w.bullets[:2]) if w.bullets else (w.description or "")
            lines.append(f"  - {w.position or ''} at {w.company or ''}: {bullets_preview}")

    if resume.project_experience:
        lines.append(f"Projects ({len(resume.project_experience)} entries):")
        for p in resume.project_experience[:4]:
            lines.append(f"  - {p.name or ''}: {p.description or ''}")

    if resume.skills:
        names = [s.name for s in resume.skills if s.name]
        lines.append(f"Skills ({len(names)}): {', '.join(names[:30])}")

    if resume.target_position:
        lines.append(f"Target Position: {resume.target_position}")
    if resume.target_industry:
        lines.append(f"Target Industry: {resume.target_industry}")

    return "\n".join(lines)


async def _prepare_conversation(req: ChatRequest) -> dict:
    """Shared request preparation for /stream and /send.

    Resolves the resume (explicit id -> current selection; never an
    arbitrary one), detects GitHub URLs, creates/resumes the session and
    persists the user message.
    """
    from api.routes.resume import resolve_resume, set_current_resume_id

    sm = await get_session_manager()

    ws = dict(req.working_state)
    session_id = req.session_id
    history: list[dict] = []
    resume_id = req.resume_id

    if session_id:
        session = await sm.get_session(session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="会话不存在,可能已被删除")
        history = await sm.get_messages(session_id, limit=100)
        if not resume_id and session.get("resume_id"):
            resume_id = session["resume_id"]
            logger.info("Restoring resume from session: resume_id=%s", resume_id)
    else:
        session_id = await sm.create_session(user_id=req.user_id, resume_id=resume_id)
        logger.info("Session created: id=%s", session_id)

    resume = resolve_resume(resume_id)
    if resume:
        # An explicit selection updates the sticky "current resume".
        if req.resume_id:
            set_current_resume_id(resume.id)
            await sm.set_resume_id(session_id, resume.id)
        ws["resume_loaded"] = True
        ws["resume_id"] = resume.id
        ws["resume_summary"] = _build_resume_summary(resume)
    else:
        ws["resume_loaded"] = False
        if resume_id:
            logger.warning("Resume not found: id=%s", resume_id)

    match = _GITHUB_RE.search(req.message)
    if match:
        ws["github_url"] = match.group().rstrip("/")
        ws["github_url_provided"] = True
        logger.info("GitHub URL detected in message")

    await sm.save_message(session_id, "user", req.message)
    title = req.message[:50] + ("..." if len(req.message) > 50 else "")
    await sm.set_title_once(session_id, title)

    return {
        "session_id": session_id,
        "working_state": ws,
        "history": history,
        "session_manager": sm,
    }


def _schedule_memory_extraction(user_id: str, session_id: str, user_message: str, agent_response: str):
    """Fire-and-forget: extract durable facts from this exchange."""

    async def _run():
        try:
            extractor = await get_memory_extractor()
            store = await get_memory_store()
            saved = await extractor.extract_and_store(
                conversation=[
                    {"role": "user", "content": user_message},
                    {"role": "assistant", "content": agent_response},
                ],
                user_id=user_id,
                session_id=session_id,
                store=store,
            )
            if saved:
                logger.info("Memory extraction saved %d fact(s)", saved)
        except Exception as e:
            logger.warning("Memory extraction failed: %s", e)

    asyncio.create_task(_run())


async def _parse_request(request: Request) -> ChatRequest:
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="请求体不是合法的 JSON")
    try:
        return ChatRequest.model_validate(body)
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=e.errors()[:3])


@router.post("/stream")
async def chat_stream(
    request: Request,
    agent: AgentLoop = Depends(get_agent_loop),
):
    """SSE endpoint for real-time Agent interaction.

    Body: {"message": "...", "session_id": "...", "user_id": "...", "resume_id": "..."}
    Events: session_created, plan_*, tool_call, tool_result, observe_*, final, error
    """
    req = await _parse_request(request)
    prep = await _prepare_conversation(req)
    session_id = prep["session_id"]
    sm = prep["session_manager"]

    async def event_generator():
        yield {
            "event": "session_created",
            "data": json.dumps({"session_id": session_id}),
        }
        agent_response = ""
        try:
            async for event in agent.run(
                user_message=req.message,
                session_id=session_id,
                user_id=req.user_id,
                working_state=prep["working_state"],
                history=prep["history"],
            ):
                yield {
                    "event": event["type"],
                    "data": json.dumps(event["data"], default=str),
                }
                if event["type"] == "final":
                    agent_response = event["data"].get("response", "")
        except Exception:
            logger.exception("Agent loop error")
            yield {
                "event": "error",
                "data": json.dumps({"error": "Agent 处理出错,请稍后重试"}),
            }
        finally:
            if agent_response:
                try:
                    await sm.save_message(session_id, "agent", agent_response)
                except Exception as e:
                    logger.warning("Failed to persist agent response: %s", e)
                _schedule_memory_extraction(
                    req.user_id, session_id, req.message, agent_response
                )

    return EventSourceResponse(event_generator())


@router.post("/send")
async def chat_send(
    request: Request,
    agent: AgentLoop = Depends(get_agent_loop),
):
    """Non-streaming variant: collects all events and returns them at once."""
    req = await _parse_request(request)
    prep = await _prepare_conversation(req)
    session_id = prep["session_id"]
    sm = prep["session_manager"]

    responses = []
    agent_response = ""
    try:
        async for event in agent.run(
            user_message=req.message,
            session_id=session_id,
            user_id=req.user_id,
            working_state=prep["working_state"],
            history=prep["history"],
        ):
            responses.append(event)
            if event["type"] == "final":
                agent_response = event["data"].get("response", "")
    except Exception:
        logger.exception("Agent loop error")
        raise HTTPException(status_code=502, detail="Agent 处理出错,请稍后重试")

    if agent_response:
        await sm.save_message(session_id, "agent", agent_response)
        _schedule_memory_extraction(req.user_id, session_id, req.message, agent_response)

    return {"events": responses, "session_id": session_id}
