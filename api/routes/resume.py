"""Resume CRUD API routes."""

import json
import logging
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool

from core.config import settings
from core.resume.schema import ResumeData

logger = logging.getLogger(__name__)

router = APIRouter()

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".doc", ".md", ".txt", ".markdown"}

# In-memory cache of parsed resumes, backed by JSON files in uploads_path.
# Single-user deployment: one process, one owner.
_resume_store: dict[str, ResumeData] = {}
_current_resume_id: str = ""

_CURRENT_ID_FILE = "current_resume.txt"


def get_current_resume_id() -> str:
    return _current_resume_id


def set_current_resume_id(resume_id: str):
    """Set the currently-selected resume and persist the selection."""
    global _current_resume_id
    _current_resume_id = resume_id
    try:
        (settings.data_dir / _CURRENT_ID_FILE).write_text(resume_id, encoding="utf-8")
    except Exception as e:
        logger.warning("Failed to persist current resume id: %s", e)


def resolve_resume(resume_id: str = "") -> ResumeData | None:
    """Single canonical resume resolver used by all routes and tools.

    Priority: explicit id -> current selection. Never falls back to an
    arbitrary resume — callers must handle None with a clear error.
    """
    if resume_id:
        return _resume_store.get(resume_id)
    if _current_resume_id:
        return _resume_store.get(_current_resume_id)
    return None


# Backward-compatible alias (older modules imported the underscored name).
_get_resume = resolve_resume


def _save_resume(resume: ResumeData):
    """Save a resume to the in-memory store and persist to disk."""
    _resume_store[resume.id] = resume
    try:
        _persist_resume(resume)
    except Exception as e:
        # Surface persistence failures instead of silently "succeeding":
        # callers treat this as an error so the user knows data may be lost.
        logger.error("Failed to persist resume %s to disk: %s", resume.id, e)
        raise


def _persist_resume(resume: ResumeData):
    Path(settings.uploads_path).mkdir(parents=True, exist_ok=True)
    file_path = settings.uploads_path / f"{resume.id}.json"
    tmp_path = file_path.with_suffix(".json.tmp")
    tmp_path.write_text(
        json.dumps(resume.model_dump(mode="json"), indent=2, default=str),
        encoding="utf-8",
    )
    tmp_path.replace(file_path)


def _load_persisted_resumes():
    """Load all persisted resumes on startup."""
    global _current_resume_id
    Path(settings.uploads_path).mkdir(parents=True, exist_ok=True)
    for file_path in Path(settings.uploads_path).glob("*.json"):
        name = file_path.name
        # Skip non-resume artifacts (uploaded originals, legacy version files)
        if name.startswith("upload_") or name.startswith("version_"):
            continue
        try:
            data = json.loads(file_path.read_text(encoding="utf-8"))
            resume = ResumeData(**data)
            _resume_store[resume.id] = resume
        except Exception as e:
            logger.warning("Failed to load resume %s: %s", file_path, e)
    # Restore last selection; fall back to empty (user picks explicitly).
    try:
        saved = (settings.data_dir / _CURRENT_ID_FILE).read_text(encoding="utf-8").strip()
        if saved in _resume_store:
            _current_resume_id = saved
    except FileNotFoundError:
        pass
    except Exception as e:
        logger.warning("Failed to restore current resume id: %s", e)


def _original_upload_path(resume_id: str, suffix: str) -> Path:
    return settings.uploads_path / f"upload_{resume_id}{suffix}"


async def _receive_upload(file: UploadFile, dest: Path) -> int:
    """Stream an upload to dest with a size cap. Returns bytes written."""
    max_bytes = settings.max_upload_size_mb * 1024 * 1024
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(1024 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise HTTPException(
                status_code=413,
                detail=f"File too large (max {settings.max_upload_size_mb} MB)",
            )
        chunks.append(chunk)
    if total == 0:
        raise HTTPException(status_code=400, detail="Empty file")
    data = b"".join(chunks)
    await run_in_threadpool(dest.write_bytes, data)
    return total


def _validated_suffix(filename: str | None) -> str:
    # Basename first: the client controls filename and may include ../ or \.
    safe_name = Path(filename or "").name
    suffix = Path(safe_name).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        allowed = ", ".join(sorted(ALLOWED_EXTENSIONS))
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported format: {suffix or '(none)'}. Allowed: {allowed}",
        )
    return suffix


@router.post("/upload")
async def upload_resume(file: UploadFile = File(...)):
    """Upload and parse a resume file (PDF/DOCX/MD).

    Returns structured ResumeData with per-field confidence scores.
    """
    suffix = _validated_suffix(file.filename)
    Path(settings.uploads_path).mkdir(parents=True, exist_ok=True)

    # Store under a server-generated name; never trust the client filename.
    temp_id = uuid.uuid4().hex[:12]
    upload_path = settings.uploads_path / f"upload_{temp_id}{suffix}"
    await _receive_upload(file, upload_path)

    original_name = Path(file.filename or "").name or "unknown"
    try:
        from core.resume.parser import ResumeParser
        parser = ResumeParser()
        logger.info("Parsing resume: file=%s", original_name)
        resume_data, metadata = await parser.parse(upload_path)
        resume_data.source_filename = original_name
        _save_resume(resume_data)
        # Keep the original under the resume's id so deletion can clean it up.
        final_path = _original_upload_path(resume_data.id, suffix)
        await run_in_threadpool(upload_path.replace, final_path)
        # Newly uploaded resume becomes the current selection.
        set_current_resume_id(resume_data.id)
        logger.info(
            "Resume parsed: id=%s sections(edu=%d work=%d proj=%d skills=%d)",
            resume_data.id, len(resume_data.education), len(resume_data.work_experience),
            len(resume_data.project_experience), len(resume_data.skills),
        )
        return JSONResponse({
            "resume_id": resume_data.id,
            "resume": resume_data.model_dump(mode="json"),
            "metadata": metadata,
        })
    except HTTPException:
        upload_path.unlink(missing_ok=True)
        raise
    except ValueError as e:
        upload_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=str(e))
    except Exception:
        upload_path.unlink(missing_ok=True)
        logger.exception("Resume upload failed")
        raise HTTPException(status_code=500, detail="Resume parsing failed; see server logs")


@router.post("/debug-parse")
async def debug_parse_resume(file: UploadFile = File(...)):
    """Debug endpoint: trace resume parsing step by step.

    Disabled unless DEBUG_ENDPOINTS=true — it echoes resume text and raw LLM
    responses, which must not be exposed by default.
    """
    if not settings.debug_endpoints:
        raise HTTPException(status_code=404, detail="Not found")

    suffix = _validated_suffix(file.filename)
    Path(settings.uploads_path).mkdir(parents=True, exist_ok=True)
    upload_path = settings.uploads_path / f"debug_{uuid.uuid4().hex[:12]}{suffix}"
    await _receive_upload(file, upload_path)

    debug_info: dict[str, Any] = {"steps": []}
    try:
        from core.resume.parser import ResumeParser
        parser = ResumeParser()

        # Step 1: Text extraction
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
        structured = None
        try:
            structured = await parser._extract_structured(raw_text)
            is_fallback = (
                len(structured.education) == 0
                and len(structured.work_experience) == 0
                and len(structured.project_experience) == 0
                and len(structured.skills) == 0
            )
            debug_info["steps"].append({
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
            })
        except Exception as e:
            debug_info["steps"].append({
                "step": 2,
                "name": "llm_extraction",
                "success": False,
                "error": str(e),
                "error_type": type(e).__name__,
            })
            debug_info["error"] = f"LLM extraction failed: {e}"

        debug_info["result"] = structured.model_dump(mode="json") if structured else None
        return debug_info
    finally:
        upload_path.unlink(missing_ok=True)


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
        "current_resume_id": _current_resume_id,
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


# Fields callers may never overwrite through the entry-update API.
_PROTECTED_ENTRY_FIELDS = {"id", "entry_type"}


@router.put("/{resume_id}/entry/{entry_id}")
async def update_resume_entry(resume_id: str, entry_id: str, updates: dict[str, Any]):
    """Update a specific entry in a resume (validated, whitelisted fields)."""
    resume = _resume_store.get(resume_id)
    if not resume:
        raise HTTPException(status_code=404, detail="Resume not found")

    entry = resume.get_entry_by_id(entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail=f"Entry {entry_id} not found")

    allowed = set(type(entry).model_fields.keys()) - _PROTECTED_ENTRY_FIELDS
    unknown = set(updates) - allowed
    if unknown:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown or protected fields: {sorted(unknown)}",
        )

    merged = entry.model_dump()
    merged.update(updates)
    try:
        validated = type(entry).model_validate(merged)
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=f"Invalid field values: {e.errors()}")

    for key in updates:
        setattr(entry, key, getattr(validated, key))

    resume.bump_version()
    try:
        _save_resume(resume)
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to persist resume")
    return {"entry_id": entry_id, "updated_fields": sorted(updates.keys())}


@router.delete("/{resume_id}/entry/{entry_id}")
async def delete_resume_entry(resume_id: str, entry_id: str):
    """Delete an entry from a resume."""
    resume = _resume_store.get(resume_id)
    if not resume:
        raise HTTPException(status_code=404, detail="Resume not found")

    removed = resume.remove_entry(entry_id)
    if not removed:
        raise HTTPException(status_code=404, detail=f"Entry {entry_id} not found")

    try:
        _save_resume(resume)
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to persist resume")
    return {"deleted": entry_id}


@router.delete("/{resume_id}")
async def delete_resume(resume_id: str):
    """Delete a resume from memory and disk (parsed JSON + original upload)."""
    if resume_id not in _resume_store:
        raise HTTPException(status_code=404, detail="Resume not found")

    del _resume_store[resume_id]
    if _current_resume_id == resume_id:
        set_current_resume_id("")

    file_path = settings.uploads_path / f"{resume_id}.json"
    file_path.unlink(missing_ok=True)
    for orig in settings.uploads_path.glob(f"upload_{resume_id}.*"):
        orig.unlink(missing_ok=True)

    logger.info("Resume deleted: id=%s", resume_id)
    return {"deleted": resume_id}


# Load persisted resumes on module import
_load_persisted_resumes()
