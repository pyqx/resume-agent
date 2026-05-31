"""Resume CRUD API routes."""

import json
import logging
import shutil
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Request, UploadFile, File, Form, HTTPException
from fastapi.responses import JSONResponse

from core.config import settings
from core.resume.schema import ResumeData
from api.deps import get_db, get_memory_store

logger = logging.getLogger(__name__)

router = APIRouter()

# In-memory store for parsed resumes (will move to SQLite/disk in production)
_resume_store: dict[str, ResumeData] = {}
_current_resume_id: str = ""


def get_current_resume_id() -> str:
    return _current_resume_id


def set_current_resume_id(resume_id: str):
    global _current_resume_id
    _current_resume_id = resume_id


def _get_resume(resume_id: str = "") -> ResumeData | None:
    """Helper to retrieve a resume from the in-memory store."""
    if not resume_id:
        resume_id = _current_resume_id
    if not resume_id and _resume_store:
        resume_id = next(iter(_resume_store.keys()))
    return _resume_store.get(resume_id)


def _save_resume(resume: ResumeData):
    """Helper to save a resume to the in-memory store."""
    _resume_store[resume.id] = resume
    # Persist to disk (best-effort, don't fail the request)
    try:
        _persist_resume(resume)
    except Exception as e:
        logger.warning(f"Failed to persist resume to disk: {e}")


def _persist_resume(resume: ResumeData):
    """Persist resume to disk as JSON."""
    Path(settings.uploads_path).mkdir(parents=True, exist_ok=True)
    file_path = settings.uploads_path / f"{resume.id}.json"
    file_path.write_text(
        json.dumps(resume.model_dump(mode="json"), indent=2, default=str),
        encoding="utf-8",
    )


def _load_persisted_resumes():
    """Load all persisted resumes on startup."""
    Path(settings.uploads_path).mkdir(parents=True, exist_ok=True)
    for file_path in Path(settings.uploads_path).glob("*.json"):
        try:
            data = json.loads(file_path.read_text(encoding="utf-8"))
            resume = ResumeData(**data)
            _resume_store[resume.id] = resume
        except Exception as e:
            logger.warning(f"Failed to load resume {file_path}: {e}")


@router.post("/upload")
async def upload_resume(file: UploadFile = File(...)):
    """Upload and parse a resume file (PDF/DOCX/MD).

    Returns structured ResumeData with per-field confidence scores.
    """
    allowed_extensions = {".pdf", ".docx", ".doc", ".md", ".txt", ".markdown"}
    suffix = Path(file.filename or "").suffix.lower()

    if suffix not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported format: {suffix}. Allowed: {allowed_extensions}",
        )

    # Save uploaded file
    Path(settings.uploads_path).mkdir(parents=True, exist_ok=True)
    upload_path = settings.uploads_path / f"upload_{file.filename}"
    with open(upload_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    try:
        from core.resume.parser import ResumeParser
        parser = ResumeParser()
        logger.info("Parsing resume: file=%s", file.filename)
        resume_data, metadata = await parser.parse(upload_path)
        resume_data.source_filename = file.filename or "unknown"
        _save_resume(resume_data)
        logger.info("Resume parsed: id=%s name=%s sections(edu=%d work=%d proj=%d skills=%d)",
                    resume_data.id, resume_data.personal_info.full_name,
                    len(resume_data.education), len(resume_data.work_experience),
                    len(resume_data.project_experience), len(resume_data.skills))

        return JSONResponse({
            "resume_id": resume_data.id,
            "resume": resume_data.model_dump(mode="json"),
            "metadata": metadata,
        })
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception(f"Resume upload failed: {e}")
        raise HTTPException(status_code=500, detail=f"Parsing failed: {e}")


@router.post("/debug-parse")
async def debug_parse_resume(file: UploadFile = File(...)):
    """Debug endpoint: trace resume parsing step by step.

    Returns each intermediate result so you can see exactly where parsing fails.
    """
    allowed_extensions = {".pdf", ".docx", ".doc", ".md", ".txt", ".markdown"}
    suffix = Path(file.filename or "").suffix.lower()

    if suffix not in allowed_extensions:
        raise HTTPException(status_code=400, detail=f"Unsupported format: {suffix}")

    Path(settings.uploads_path).mkdir(parents=True, exist_ok=True)
    upload_path = settings.uploads_path / f"debug_{file.filename}"
    with open(upload_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    debug_info = {"steps": []}

    # Step 1: Text extraction
    from core.resume.parser import ResumeParser
    parser = ResumeParser()

    try:
        if suffix == ".pdf":
            raw_text, warnings = parser._parse_pdf(upload_path)
        elif suffix in (".docx", ".doc"):
            raw_text, warnings = parser._parse_docx(upload_path)
        else:
            raw_text = upload_path.read_text(encoding="utf-8")
            warnings = []

        debug_info["steps"].append({
            "step": 1,
            "name": "text_extraction",
            "success": bool(raw_text.strip()),
            "text_length": len(raw_text),
            "text_preview": raw_text[:2000],
            "warnings": warnings,
        })

        if not raw_text.strip():
            debug_info["error"] = "No text could be extracted"
            return debug_info

    except Exception as e:
        debug_info["steps"].append({
            "step": 1, "name": "text_extraction", "success": False, "error": str(e)
        })
        debug_info["error"] = f"Text extraction failed: {e}"
        return debug_info

    # Step 2: LLM structured extraction
    try:
        structured = await parser._extract_structured(raw_text)
        is_fallback = (
            len(structured.education) == 0
            and len(structured.work_experience) == 0
            and len(structured.project_experience) == 0
            and len(structured.skills) == 0
        )
        step2 = {
            "step": 2,
            "name": "llm_extraction",
            "success": not is_fallback,
            "fell_back_to_rules": is_fallback,
            "raw_llm_response": parser.last_raw_response[:2000] if parser.last_raw_response else "(empty)",
            "cleaned_json": parser.last_cleaned_json[:2000] if parser.last_cleaned_json else "(empty)",
            "parse_error": parser.last_parse_error or "(none)",
            "resume_preview": {
                "personal_info": structured.personal_info.model_dump(mode="json"),
                "education_count": len(structured.education),
                "work_experience_count": len(structured.work_experience),
                "project_experience_count": len(structured.project_experience),
                "skills_count": len(structured.skills),
            },
        }
    except Exception as e:
        step2 = {
            "step": 2,
            "name": "llm_extraction",
            "success": False,
            "error": str(e),
            "error_type": type(e).__name__,
        }
        debug_info["error"] = f"LLM extraction failed: {e}"

    debug_info["steps"].append(step2)
    if "result" not in debug_info:
        debug_info["result"] = structured.model_dump(mode="json") if 'structured' in dir() else None
    return debug_info


@router.get("/{resume_id}")
async def get_resume(resume_id: str):
    """Get a parsed resume by ID."""
    resume = _resume_store.get(resume_id)
    if not resume:
        raise HTTPException(status_code=404, detail="Resume not found")
    return resume.model_dump(mode="json")


@router.get("/")
async def list_resumes():
    """List all stored resumes."""
    return {
        "resumes": [
            {
                "id": r.id,
                "version": r.version,
                "updated_at": str(r.updated_at),
                "filename": r.source_filename,
                "name": r.personal_info.full_name,
            }
            for r in _resume_store.values()
        ],
    }


@router.put("/{resume_id}/entry/{entry_id}")
async def update_resume_entry(resume_id: str, entry_id: str, updates: dict[str, Any]):
    """Update a specific entry in a resume."""
    resume = _resume_store.get(resume_id)
    if not resume:
        raise HTTPException(status_code=404, detail="Resume not found")

    entry = resume.get_entry_by_id(entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail=f"Entry {entry_id} not found")

    for key, value in updates.items():
        if hasattr(entry, key):
            setattr(entry, key, value)

    resume.bump_version()
    _save_resume(resume)
    return {"entry_id": entry_id, "updated_fields": list(updates.keys())}


@router.delete("/{resume_id}/entry/{entry_id}")
async def delete_resume_entry(resume_id: str, entry_id: str):
    """Delete an entry from a resume."""
    resume = _resume_store.get(resume_id)
    if not resume:
        raise HTTPException(status_code=404, detail="Resume not found")

    removed = resume.remove_entry(entry_id)
    if not removed:
        raise HTTPException(status_code=404, detail=f"Entry {entry_id} not found")

    _save_resume(resume)
    return {"deleted": entry_id}


# ── Version Management ─────────────────────────────────────

from core.resume.version_manager import VersionManager

_version_manager = VersionManager()


def _sync_store_to_versions():
    """Sync the in-memory _resume_store to VersionManager versions.
    Called after a resume is parsed/uploaded to create an initial version.
    """
    for resume_id, resume in _resume_store.items():
        existing = [v for v in _version_manager.list_versions()
                    if v["id"] == resume_id]
        if not existing:
            _version_manager.create_version(
                resume_data=resume,
                name="Initial Import",
                notes="Created from uploaded resume",
            )


@router.post("/versions")
async def create_version(request: Request):
    """Create a new version or fork from an existing one."""
    body = await request.json()
    action = body.get("action", "create")
    name = body.get("name", "Untitled")
    notes = body.get("notes", "")
    parent_id = body.get("parent_id")
    resume_id = body.get("resume_id")

    if action == "fork":
        if not parent_id:
            raise HTTPException(status_code=400, detail="parent_id required for fork")
        try:
            version = _version_manager.fork_version(parent_id, name, notes)
        except KeyError:
            raise HTTPException(status_code=404, detail=f"Parent version {parent_id} not found")
    else:
        resume = _get_resume(resume_id) if resume_id else None
        if not resume:
            raise HTTPException(status_code=404, detail="Resume not found")
        version = _version_manager.create_version(resume, name, notes)

    return {
        "version_id": version.id,
        "name": version.name,
        "created_at": str(version.created_at),
    }


@router.get("/versions")
async def list_versions():
    """List all resume versions."""
    return {"versions": _version_manager.list_versions()}


@router.get("/versions/{version_id}")
async def get_version(version_id: str):
    """Get a specific version's full resume data."""
    try:
        version = _version_manager.get_version(version_id)
        return {
            "version": {
                "id": version.id,
                "parent_id": version.parent_id,
                "name": version.name,
                "notes": version.notes,
                "created_at": str(version.created_at),
                "updated_at": str(version.updated_at),
            },
            "resume": version.resume_data.model_dump(mode="json"),
        }
    except KeyError:
        raise HTTPException(status_code=404, detail="Version not found")


@router.get("/versions/{version_id}/diff")
async def diff_versions(version_id: str, against: str = ""):
    """Get the diff between two versions."""
    if not against:
        # Diff against parent by default
        try:
            v = _version_manager.get_version(version_id)
            if v.parent_id:
                against = v.parent_id
            else:
                raise HTTPException(status_code=400, detail="No parent to diff against. Specify 'against' query param.")
        except KeyError:
            raise HTTPException(status_code=404, detail="Version not found")

    try:
        diff = _version_manager.diff_versions(against, version_id)
        return diff.model_dump(mode="json")
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/versions/{version_id}")
async def delete_version(version_id: str):
    """Delete a version."""
    deleted = _version_manager.delete_version(version_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Version not found")
    return {"deleted": version_id}


# Load persisted resumes on module import
_load_persisted_resumes()
