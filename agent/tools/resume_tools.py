"""Resume tools — parse, read, update resume entries, manage versions."""

import logging
from pathlib import Path

from agent.tools.base import BaseTool, ToolMetadata, ToolResult, ToolCategory, Difficulty
from core.resume.parser import ResumeParser
from core.resume.schema import ResumeData
from core.resume.version_manager import VersionManager

logger = logging.getLogger(__name__)


class ParseResumeFileTool(BaseTool):
    def __init__(self, parser: ResumeParser):
        self._parser = parser

    @property
    def metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="parse_resume_file",
            category=ToolCategory.RESUME,
            description="Parse an uploaded resume file (PDF/DOCX/MD) into structured data",
            usage_guide="Use when the user uploads a resume file that needs to be parsed. Returns structured ResumeData with per-field confidence scores.",
            estimated_time=Difficulty.MEDIUM,
            is_idempotent=True,
        )

    async def execute(self, file_path: str = "", **kwargs) -> ToolResult:
        if not file_path:
            return ToolResult.fail("PARAM_ERROR", "file_path is required")
        try:
            resume_data, metadata = await self._parser.parse(file_path)
            return ToolResult.ok({
                "resume": resume_data.model_dump(mode="json"),
                "metadata": metadata,
            })
        except FileNotFoundError:
            return ToolResult.fail("FILE_NOT_FOUND", f"File not found: {file_path}")
        except ValueError as e:
            return ToolResult.fail("PARSE_ERROR", str(e), fallback_suggestion="Try uploading as plain text")
        except Exception as e:
            logger.exception(f"Parse failed: {e}")
            return ToolResult.fail("PARSE_ERROR", str(e), is_retryable=True)


class ReadResumeSectionTool(BaseTool):
    def __init__(self, get_resume_fn):
        self._get_resume = get_resume_fn

    @property
    def metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="read_resume_section",
            category=ToolCategory.RESUME,
            description="Read a specific section of the current resume",
            usage_guide="Use when you need to inspect one section (education/work_experience/project_experience/skills) of the current resume",
            preconditions=["resume_loaded"],
            estimated_time=Difficulty.LIGHT,
        )

    async def execute(self, section: str = "", resume_id: str = "", **kwargs) -> ToolResult:
        if not section:
            return ToolResult.fail("PARAM_ERROR", "section is required")
        try:
            resume = self._get_resume(resume_id) if resume_id else self._get_resume()
            if not resume:
                return ToolResult.fail("NO_RESUME", "No resume is currently loaded")

            sections = {
                "personal_info": resume.personal_info.model_dump(mode="json"),
                "education": [e.model_dump(mode="json") for e in resume.education],
                "work_experience": [w.model_dump(mode="json") for w in resume.work_experience],
                "project_experience": [p.model_dump(mode="json") for p in resume.project_experience],
                "skills": [s.model_dump(mode="json") for s in resume.skills],
            }

            if section not in sections:
                return ToolResult.fail("PARAM_ERROR", f"Unknown section: {section}. Available: {list(sections.keys())}")

            return ToolResult.ok(sections[section])
        except Exception as e:
            return ToolResult.fail("READ_ERROR", str(e))


class UpdateResumeEntryTool(BaseTool):
    def __init__(self, get_resume_fn, save_resume_fn):
        self._get_resume = get_resume_fn
        self._save_resume = save_resume_fn

    @property
    def metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="update_resume_entry",
            category=ToolCategory.RESUME,
            description="Update a specific entry in the resume",
            usage_guide="Use to modify an existing entry (education, work experience, project, skill). The entry_id is required.",
            preconditions=["resume_loaded"],
            estimated_time=Difficulty.LIGHT,
            is_idempotent=False,
        )

    async def execute(self, entry_id: str = "", updates: dict | None = None, **kwargs) -> ToolResult:
        if not entry_id:
            return ToolResult.fail("PARAM_ERROR", "entry_id is required")
        try:
            resume = self._get_resume()
            if not resume:
                return ToolResult.fail("NO_RESUME", "No resume is currently loaded")

            entry = resume.get_entry_by_id(entry_id)
            if not entry:
                return ToolResult.fail("NOT_FOUND", f"No entry found with id: {entry_id}")

            updates = updates or {}
            for key, value in updates.items():
                if hasattr(entry, key):
                    setattr(entry, key, value)

            resume.bump_version()
            self._save_resume(resume)
            return ToolResult.ok({"entry_id": entry_id, "updated": list(updates.keys())})
        except Exception as e:
            return ToolResult.fail("UPDATE_ERROR", str(e))


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
            usage_guide="Use to add a new entry to the resume. Specify section and entry data.",
            preconditions=["resume_loaded"],
            estimated_time=Difficulty.LIGHT,
            is_idempotent=False,
        )

    async def execute(self, section: str = "", entry_data: dict | None = None, **kwargs) -> ToolResult:
        if not section:
            return ToolResult.fail("PARAM_ERROR", "section is required")
        try:
            resume = self._get_resume()
            if not resume:
                return ToolResult.fail("NO_RESUME", "No resume is currently loaded")

            entry_data = entry_data or {}

            if section == "education":
                from core.resume.schema import Education
                entry = Education(**entry_data)
                resume.education.append(entry)
            elif section == "work_experience":
                from core.resume.schema import WorkExperience
                entry = WorkExperience(**entry_data)
                resume.work_experience.append(entry)
            elif section == "project_experience":
                from core.resume.schema import ProjectExperience
                entry = ProjectExperience(**entry_data)
                resume.project_experience.append(entry)
            elif section == "skills":
                from core.resume.schema import Skill
                entry = Skill(**entry_data)
                resume.skills.append(entry)
            else:
                return ToolResult.fail("PARAM_ERROR", f"Unknown section: {section}")

            resume.bump_version()
            self._save_resume(resume)
            return ToolResult.ok({"entry_id": entry.id, "section": section})
        except Exception as e:
            return ToolResult.fail("ADD_ERROR", str(e))


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
            usage_guide="Use to remove an entry. Always confirm with the user before deleting.",
            preconditions=["resume_loaded", "user_confirmed"],
            estimated_time=Difficulty.LIGHT,
            is_idempotent=False,
            requires_user_confirmation=True,
        )

    async def execute(self, entry_id: str = "", **kwargs) -> ToolResult:
        if not entry_id:
            return ToolResult.fail("PARAM_ERROR", "entry_id is required")
        try:
            resume = self._get_resume()
            if not resume:
                return ToolResult.fail("NO_RESUME", "No resume is currently loaded")

            removed = resume.remove_entry(entry_id)
            if not removed:
                return ToolResult.fail("NOT_FOUND", f"No entry found with id: {entry_id}")

            self._save_resume(resume)
            return ToolResult.ok({"deleted": entry_id})
        except Exception as e:
            return ToolResult.fail("DELETE_ERROR", str(e))


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
            return ToolResult.fail("VERSION_ERROR", str(e))


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
            preconditions=["resume_loaded"],
            estimated_time=Difficulty.LIGHT,
            is_idempotent=False,
        )

    async def execute(self, source_version_id: str = "", new_name: str = "", notes: str = "", **kwargs) -> ToolResult:
        if not source_version_id or not new_name:
            return ToolResult.fail("PARAM_ERROR", "source_version_id and new_name are required")
        try:
            version = self._vm.fork_version(source_version_id, new_name, notes)
            return ToolResult.ok({"version_id": version.id, "name": version.name})
        except KeyError:
            return ToolResult.fail("NOT_FOUND", f"Version {source_version_id} not found")
        except Exception as e:
            return ToolResult.fail("FORK_ERROR", str(e))


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
            estimated_time=Difficulty.LIGHT,
        )

    async def execute(self, version_a: str = "", version_b: str = "", **kwargs) -> ToolResult:
        if not version_a or not version_b:
            return ToolResult.fail("PARAM_ERROR", "version_a and version_b are required")
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
            return ToolResult.fail("NOT_FOUND", str(e))
        except Exception as e:
            return ToolResult.fail("DIFF_ERROR", str(e))
