"""Resume tools — read, update resume entries, manage versions."""

import logging

from pydantic import ValidationError

from agent.tools.base import BaseTool, ToolMetadata, ToolResult, ToolCategory, Difficulty
from core.resume.schema import Education, ProjectExperience, Skill, WorkExperience
from core.resume.version_manager import VersionManager

logger = logging.getLogger(__name__)

# Fields tools may never overwrite on an entry.
_PROTECTED_ENTRY_FIELDS = {"id", "entry_type"}

_SECTION_MODELS = {
    "education": Education,
    "work_experience": WorkExperience,
    "project_experience": ProjectExperience,
    "skills": Skill,
}


class ReadResumeSectionTool(BaseTool):
    def __init__(self, get_resume_fn):
        self._get_resume = get_resume_fn

    @property
    def metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="read_resume_section",
            category=ToolCategory.RESUME,
            description="Read a specific section of the current resume",
            usage_guide="Use when you need to inspect one section of the current resume",
            parameters={
                "section": "string, one of: personal_info | education | work_experience | project_experience | skills",
            },
            preconditions=["resume_loaded"],
            estimated_time=Difficulty.LIGHT,
        )

    async def execute(self, section: str = "", resume_id: str = "", **kwargs) -> ToolResult:
        if not section:
            return ToolResult.fail("PARAM_ERROR", "section is required", is_retryable=False)
        try:
            resume = self._get_resume(resume_id) if resume_id else self._get_resume()
            if not resume:
                return ToolResult.fail("NO_RESUME", "No resume is currently loaded", is_retryable=False)

            sections = {
                "personal_info": resume.personal_info.model_dump(mode="json"),
                "education": [e.model_dump(mode="json") for e in resume.education],
                "work_experience": [w.model_dump(mode="json") for w in resume.work_experience],
                "project_experience": [p.model_dump(mode="json") for p in resume.project_experience],
                "skills": [s.model_dump(mode="json") for s in resume.skills],
            }
            if section not in sections:
                return ToolResult.fail(
                    "PARAM_ERROR",
                    f"Unknown section: {section}. Available: {list(sections.keys())}",
                    is_retryable=False,
                )
            return ToolResult.ok(sections[section])
        except Exception as e:
            logger.exception("read_resume_section failed")
            return ToolResult.fail("READ_ERROR", str(e), is_retryable=False)


class UpdateResumeEntryTool(BaseTool):
    def __init__(self, get_resume_fn, save_resume_fn):
        self._get_resume = get_resume_fn
        self._save_resume = save_resume_fn

    @property
    def metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="update_resume_entry",
            category=ToolCategory.RESUME,
            description="Update a specific entry in the resume (validated fields only)",
            usage_guide="Use to modify an existing entry (education, work experience, project, skill).",
            parameters={
                "entry_id": "string, the entry's id (get it from read_resume_section)",
                "updates": "object mapping field name to new value, e.g. {\"position\": \"高级工程师\"}",
            },
            preconditions=["resume_loaded"],
            estimated_time=Difficulty.LIGHT,
            is_idempotent=False,
        )

    async def execute(self, entry_id: str = "", updates: dict | None = None, **kwargs) -> ToolResult:
        if not entry_id:
            return ToolResult.fail("PARAM_ERROR", "entry_id is required", is_retryable=False)
        if not isinstance(updates, dict) or not updates:
            return ToolResult.fail("PARAM_ERROR", "updates must be a non-empty object", is_retryable=False)
        try:
            resume = self._get_resume()
            if not resume:
                return ToolResult.fail("NO_RESUME", "No resume is currently loaded", is_retryable=False)

            entry = resume.get_entry_by_id(entry_id)
            if not entry:
                return ToolResult.fail("NOT_FOUND", f"No entry found with id: {entry_id}", is_retryable=False)

            allowed = set(type(entry).model_fields.keys()) - _PROTECTED_ENTRY_FIELDS
            unknown = set(updates) - allowed
            if unknown:
                return ToolResult.fail(
                    "PARAM_ERROR",
                    f"Unknown or protected fields: {sorted(unknown)}. Allowed: {sorted(allowed)}",
                    is_retryable=False,
                )

            merged = entry.model_dump()
            merged.update(updates)
            try:
                validated = type(entry).model_validate(merged)
            except ValidationError as e:
                return ToolResult.fail(
                    "VALIDATION_ERROR",
                    f"Invalid values: {e.errors()[:3]}",
                    is_retryable=False,
                )
            for key in updates:
                setattr(entry, key, getattr(validated, key))

            resume.bump_version()
            self._save_resume(resume)
            return ToolResult.ok({"entry_id": entry_id, "updated": sorted(updates.keys())})
        except Exception as e:
            logger.exception("update_resume_entry failed")
            return ToolResult.fail("UPDATE_ERROR", str(e), is_retryable=False)


class AddResumeEntryTool(BaseTool):
    def __init__(self, get_resume_fn, save_resume_fn):
        self._get_resume = get_resume_fn
        self._save_resume = save_resume_fn

    @property
    def metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="add_resume_entry",
            category=ToolCategory.RESUME,
            description="Add a new entry (education, work experience, project, skill) to the resume",
            usage_guide="Use to add a new entry to the resume.",
            parameters={
                "section": "string, one of: education | work_experience | project_experience | skills",
                "entry_data": "object with the entry's fields (e.g. {\"company\": \"...\", \"position\": \"...\", \"bullets\": [...]})",
            },
            preconditions=["resume_loaded"],
            estimated_time=Difficulty.LIGHT,
            is_idempotent=False,
        )

    async def execute(self, section: str = "", entry_data: dict | None = None, **kwargs) -> ToolResult:
        if not section:
            return ToolResult.fail("PARAM_ERROR", "section is required", is_retryable=False)
        model = _SECTION_MODELS.get(section)
        if model is None:
            return ToolResult.fail(
                "PARAM_ERROR",
                f"Unknown section: {section}. Available: {list(_SECTION_MODELS.keys())}",
                is_retryable=False,
            )
        if not isinstance(entry_data, dict):
            return ToolResult.fail("PARAM_ERROR", "entry_data must be an object", is_retryable=False)
        try:
            resume = self._get_resume()
            if not resume:
                return ToolResult.fail("NO_RESUME", "No resume is currently loaded", is_retryable=False)

            entry_data = {k: v for k, v in entry_data.items() if k not in _PROTECTED_ENTRY_FIELDS}
            try:
                entry = model(**entry_data)
            except ValidationError as e:
                return ToolResult.fail(
                    "VALIDATION_ERROR", f"Invalid values: {e.errors()[:3]}", is_retryable=False
                )
            getattr(resume, section).append(entry)
            resume.bump_version()
            self._save_resume(resume)
            return ToolResult.ok({"entry_id": entry.id, "section": section})
        except Exception as e:
            logger.exception("add_resume_entry failed")
            return ToolResult.fail("ADD_ERROR", str(e), is_retryable=False)


class DeleteResumeEntryTool(BaseTool):
    def __init__(self, get_resume_fn, save_resume_fn):
        self._get_resume = get_resume_fn
        self._save_resume = save_resume_fn

    @property
    def metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="delete_resume_entry",
            category=ToolCategory.RESUME,
            description="Delete an entry from the resume (requires user confirmation)",
            usage_guide="Use to remove an entry. Ask the user to confirm first, then call with confirm=true.",
            parameters={
                "entry_id": "string, the entry's id",
                "confirm": "boolean, must be true (only after the user explicitly agreed)",
            },
            preconditions=["resume_loaded"],
            estimated_time=Difficulty.LIGHT,
            is_idempotent=False,
            requires_user_confirmation=True,
        )

    async def execute(self, entry_id: str = "", **kwargs) -> ToolResult:
        if not entry_id:
            return ToolResult.fail("PARAM_ERROR", "entry_id is required", is_retryable=False)
        try:
            resume = self._get_resume()
            if not resume:
                return ToolResult.fail("NO_RESUME", "No resume is currently loaded", is_retryable=False)

            removed = resume.remove_entry(entry_id)
            if not removed:
                return ToolResult.fail("NOT_FOUND", f"No entry found with id: {entry_id}", is_retryable=False)

            self._save_resume(resume)
            return ToolResult.ok({"deleted": entry_id})
        except Exception as e:
            logger.exception("delete_resume_entry failed")
            return ToolResult.fail("DELETE_ERROR", str(e), is_retryable=False)


class CreateResumeVersionTool(BaseTool):
    """Snapshot the current resume as a named version."""

    def __init__(self, version_manager: VersionManager, get_resume_fn):
        self._vm = version_manager
        self._get_resume = get_resume_fn

    @property
    def metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="save_resume_version",
            category=ToolCategory.RESUME,
            description="Save the current resume as a named version snapshot",
            usage_guide="Use before major edits, or when the user wants to keep the current state (e.g. '字节-后端-v2').",
            parameters={
                "name": "string, version name",
                "notes": "string, optional notes about this version",
            },
            preconditions=["resume_loaded"],
            estimated_time=Difficulty.LIGHT,
            is_idempotent=False,
        )

    async def execute(self, name: str = "", notes: str = "", **kwargs) -> ToolResult:
        if not name:
            return ToolResult.fail("PARAM_ERROR", "name is required", is_retryable=False)
        try:
            resume = self._get_resume()
            if not resume:
                return ToolResult.fail("NO_RESUME", "No resume is currently loaded", is_retryable=False)
            version = self._vm.create_version(resume, name=name, notes=notes)
            return ToolResult.ok({"version_id": version.id, "name": version.name})
        except Exception as e:
            logger.exception("save_resume_version failed")
            return ToolResult.fail("VERSION_ERROR", str(e), is_retryable=False)


class ListResumeVersionsTool(BaseTool):
    def __init__(self, version_manager: VersionManager):
        self._vm = version_manager

    @property
    def metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="list_resume_versions",
            category=ToolCategory.RESUME,
            description="List all saved resume versions with summary info",
            usage_guide="Use when the user wants to see their version history or select a version to work with.",
            estimated_time=Difficulty.LIGHT,
        )

    async def execute(self, **kwargs) -> ToolResult:
        try:
            versions = self._vm.list_versions()
            return ToolResult.ok(versions)
        except Exception as e:
            logger.exception("list_resume_versions failed")
            return ToolResult.fail("VERSION_ERROR", str(e), is_retryable=False)


class ForkResumeVersionTool(BaseTool):
    def __init__(self, version_manager: VersionManager):
        self._vm = version_manager

    @property
    def metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="fork_resume_version",
            category=ToolCategory.RESUME,
            description="Create a new version by forking an existing one (for job-specific tailoring)",
            usage_guide="Use when the user wants to customize their resume for a specific job without losing the original.",
            parameters={
                "source_version_id": "string, the version to fork from (see list_resume_versions)",
                "new_name": "string, name for the new version",
                "notes": "string, optional notes",
            },
            estimated_time=Difficulty.LIGHT,
            is_idempotent=False,
        )

    async def execute(self, source_version_id: str = "", new_name: str = "", notes: str = "", **kwargs) -> ToolResult:
        if not source_version_id or not new_name:
            return ToolResult.fail(
                "PARAM_ERROR", "source_version_id and new_name are required", is_retryable=False
            )
        try:
            version = self._vm.fork_version(source_version_id, new_name, notes)
            return ToolResult.ok({"version_id": version.id, "name": version.name})
        except KeyError:
            return ToolResult.fail("NOT_FOUND", f"Version {source_version_id} not found", is_retryable=False)
        except Exception as e:
            logger.exception("fork_resume_version failed")
            return ToolResult.fail("FORK_ERROR", str(e), is_retryable=False)


class DiffResumeVersionsTool(BaseTool):
    def __init__(self, version_manager: VersionManager):
        self._vm = version_manager

    @property
    def metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="diff_resume_versions",
            category=ToolCategory.RESUME,
            description="Compare two resume versions and show what changed",
            usage_guide="Use when the user wants to understand differences between versions (e.g. before/after tailoring).",
            parameters={
                "version_a": "string, older version id",
                "version_b": "string, newer version id",
            },
            estimated_time=Difficulty.LIGHT,
        )

    async def execute(self, version_a: str = "", version_b: str = "", **kwargs) -> ToolResult:
        if not version_a or not version_b:
            return ToolResult.fail("PARAM_ERROR", "version_a and version_b are required", is_retryable=False)
        try:
            diff = self._vm.diff_versions(version_a, version_b)
            return ToolResult.ok({
                "total_changes": len(diff.diffs),
                "diffs": [
                    {"type": d.diff_type, "section": d.section, "changed_fields": d.changed_fields}
                    for d in diff.diffs
                ],
            })
        except KeyError as e:
            return ToolResult.fail("NOT_FOUND", str(e), is_retryable=False)
        except Exception as e:
            logger.exception("diff_resume_versions failed")
            return ToolResult.fail("DIFF_ERROR", str(e), is_retryable=False)
