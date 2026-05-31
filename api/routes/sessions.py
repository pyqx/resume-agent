"""Session history API routes."""

from fastapi import APIRouter, HTTPException
from api.session_manager import SessionManager
from api.deps import get_db

router = APIRouter()


@router.get("/")
async def list_sessions():
    db = await get_db()
    sm = SessionManager(db)
    sessions = await sm.list_sessions()
    return {"sessions": sessions}


@router.get("/{session_id}")
async def get_session(session_id: str):
    db = await get_db()
    sm = SessionManager(db)
    messages = await sm.get_messages(session_id)
    if not messages:
        raise HTTPException(status_code=404, detail="Session not found")
    # Get resume_id from sessions table
    sessions_list = await sm.list_sessions()
    resume_id = ""
    for s in sessions_list:
        if s["id"] == session_id:
            resume_id = s.get("resume_id") or ""
            break
    return {"session_id": session_id, "messages": messages, "resume_id": resume_id}


@router.delete("/{session_id}")
async def delete_session(session_id: str):
    db = await get_db()
    sm = SessionManager(db)
    await sm.delete_session(session_id)
    return {"deleted": session_id}
