"""Resume version management REST routes (mounted at /resume/versions).

Registered BEFORE the resume router so /resume/versions/* is not swallowed
by /resume/{resume_id}.
"""

import logging

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field, ValidationError
from starlette.requests import Request

logger = logging.getLogger(__name__)

router = APIRouter()


def _vm():
    import api.deps as deps
    if deps._version_manager is None:
        from core.resume.version_manager import VersionManager
        deps._version_manager = VersionManager()
    return deps._version_manager


@router.get("/")
async def list_versions():
    return {"versions": _vm().list_versions()}


class CreateVersionRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    notes: str = Field(default="", max_length=500)
    resume_id: str = ""


@router.post("/")
async def create_version(request: Request):
    try:
        req = CreateVersionRequest.model_validate(await request.json())
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=e.errors()[:3])
    except Exception:
        raise HTTPException(status_code=400, detail="请求体不是合法的 JSON")

    from api.routes.resume import resolve_resume
    resume = resolve_resume(req.resume_id)
    if not resume:
        raise HTTPException(status_code=404, detail="未找到简历,请先上传或选择简历")

    version = _vm().create_version(resume, name=req.name, notes=req.notes)
    return {"version_id": version.id, "name": version.name}


class ForkVersionRequest(BaseModel):
    new_name: str = Field(min_length=1, max_length=100)
    notes: str = Field(default="", max_length=500)


@router.post("/{version_id}/fork")
async def fork_version(version_id: str, request: Request):
    try:
        req = ForkVersionRequest.model_validate(await request.json())
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=e.errors()[:3])
    except Exception:
        raise HTTPException(status_code=400, detail="请求体不是合法的 JSON")
    try:
        version = _vm().fork_version(version_id, req.new_name, req.notes)
    except KeyError:
        raise HTTPException(status_code=404, detail="版本不存在")
    return {"version_id": version.id, "name": version.name}


@router.get("/{version_id}")
async def get_version(version_id: str):
    try:
        version = _vm().get_version(version_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="版本不存在")
    return {
        "id": version.id,
        "parent_id": version.parent_id,
        "name": version.name,
        "notes": version.notes,
        "created_at": str(version.created_at),
        "updated_at": str(version.updated_at),
        "resume_data": version.resume_data.model_dump(mode="json"),
    }


@router.get("/{version_id}/diff")
async def diff_versions(version_id: str, against: str = Query(min_length=1)):
    """Diff `against` (A, older) -> version_id (B, newer)."""
    try:
        diff = _vm().diff_versions(against, version_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=f"版本不存在: {e}")
    return diff.model_dump(mode="json")


@router.delete("/{version_id}")
async def delete_version(version_id: str):
    if not _vm().delete_version(version_id):
        raise HTTPException(status_code=404, detail="版本不存在")
    return {"deleted": version_id}
