"""Session history API routes."""

from fastapi import APIRouter, HTTPException, Query

from api.deps import get_session_manager

router = APIRouter()


@router.get("/")
async def list_sessions(
    user_id: str = Query(default="default"),
    limit: int = Query(default=50, ge=1, le=200),
):
    sm = await get_session_manager()
    sessions = await sm.list_sessions(user_id=user_id, limit=limit)
    return {"sessions": sessions}


@router.get("/{session_id}")
async def get_session(session_id: str):
    sm = await get_session_manager()
    session = await sm.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    messages = await sm.get_messages(session_id)
    return {
        "session_id": session_id,
        "title": session.get("title", ""),
        "resume_id": session.get("resume_id") or "",
        "created_at": session.get("created_at", ""),
        "messages": messages,
    }


@router.delete("/{session_id}")
async def delete_session(session_id: str):
    sm = await get_session_manager()
    deleted = await sm.delete_session(session_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="会话不存在")
    return {"deleted": session_id}
