"""VersionManager — create, fork, diff, and manage resume versions.

Each version stores a full deep-copied snapshot as JSON under
settings.versions_path (one file per version). Simple and robust for a
single-user tool; no copy-on-write.
"""

import json
import logging
from datetime import datetime
from pathlib import Path

from core.config import settings
from core.resume.schema import (
    ResumeData, ResumeVersion, VersionDiff, EntryDiff, DiffType,
)

logger = logging.getLogger(__name__)


def _parse_dt(value) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str) and value:
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            pass
    return datetime.now()


class VersionManager:
    """Manage multiple resume versions with forking and diffing."""

    def __init__(self, storage_dir: Path | None = None):
        self._storage_dir = storage_dir or settings.versions_path
        self._storage_dir.mkdir(parents=True, exist_ok=True)
        self._index: dict[str, ResumeVersion] = {}
        self._migrate_legacy_files()
        self._load_index()

    # ── Public API ──────────────────────────────────────────

    def create_version(
        self,
        resume_data: ResumeData,
        name: str = "master",
        notes: str = "",
        parent_id: str | None = None,
    ) -> ResumeVersion:
        """Create a new version snapshot from resume data."""
        version = ResumeVersion(
            parent_id=parent_id,
            name=name,
            notes=notes,
            resume_data=resume_data.model_copy(deep=True),
        )
        self._index[version.id] = version
        self._persist(version)
        logger.info("Resume version created: %s (%s)", version.name, version.id)
        return version

    def fork_version(self, source_id: str, new_name: str, notes: str = "") -> ResumeVersion:
        """Fork an existing version into an independent copy."""
        source = self._get(source_id)
        return self.create_version(
            resume_data=source.resume_data,
            name=new_name,
            notes=notes,
            parent_id=source.id,
        )

    def get_version(self, version_id: str) -> ResumeVersion:
        """Get a specific version by ID."""
        return self._get(version_id)

    def list_versions(self) -> list[dict]:
        """List all versions with summary info, newest first."""
        versions = sorted(
            self._index.values(), key=lambda v: str(v.created_at), reverse=True
        )
        return [
            {
                "id": v.id,
                "parent_id": v.parent_id,
                "name": v.name,
                "notes": v.notes,
                "created_at": str(v.created_at),
                "updated_at": str(v.updated_at),
                "entry_counts": {
                    "education": len(v.resume_data.education),
                    "work_experience": len(v.resume_data.work_experience),
                    "project_experience": len(v.resume_data.project_experience),
                    "skills": len(v.resume_data.skills),
                },
            }
            for v in versions
        ]

    def update_version(self, version_id: str, resume_data: ResumeData) -> ResumeVersion:
        """Update the resume data of an existing version."""
        version = self._get(version_id)
        version.resume_data = resume_data.model_copy(deep=True)
        version.updated_at = datetime.now()
        self._persist(version)
        return version

    def delete_version(self, version_id: str) -> bool:
        """Delete a version; children keep existing but lose the parent link."""
        if version_id not in self._index:
            return False
        del self._index[version_id]
        self._version_path(version_id).unlink(missing_ok=True)
        for child in self._index.values():
            if child.parent_id == version_id:
                child.parent_id = None
                self._persist(child)
        return True

    def diff_versions(self, version_a_id: str, version_b_id: str) -> VersionDiff:
        """Compute structural (entry-level) diff between two versions."""
        a = self._get(version_a_id).resume_data
        b = self._get(version_b_id).resume_data

        diffs: list[EntryDiff] = []
        for section_key in ("education", "work_experience", "project_experience"):
            a_entries = {e.id: e for e in getattr(a, section_key)}
            b_entries = {e.id: e for e in getattr(b, section_key)}

            for eid, entry in b_entries.items():
                if eid not in a_entries:
                    diffs.append(EntryDiff(
                        diff_type=DiffType.ADDED,
                        entry_id=eid,
                        section=section_key,
                        new_entry=entry.model_dump(mode="json"),
                    ))

            for eid, entry in a_entries.items():
                if eid not in b_entries:
                    diffs.append(EntryDiff(
                        diff_type=DiffType.REMOVED,
                        entry_id=eid,
                        section=section_key,
                        old_entry=entry.model_dump(mode="json"),
                    ))

            for eid in set(a_entries) & set(b_entries):
                changed_fields = self._compare_entries(
                    a_entries[eid].model_dump(),
                    b_entries[eid].model_dump(),
                )
                if changed_fields:
                    diffs.append(EntryDiff(
                        diff_type=DiffType.MODIFIED,
                        entry_id=eid,
                        section=section_key,
                        old_entry=a_entries[eid].model_dump(mode="json"),
                        new_entry=b_entries[eid].model_dump(mode="json"),
                        changed_fields=changed_fields,
                    ))

        # Skills diff by (name, category); level/years changes count as
        # modified via the tuple including them would over-report — keep
        # simple add/remove semantics, sorted for stable rendering.
        a_skills = {(s.name, s.category) for s in a.skills}
        b_skills = {(s.name, s.category) for s in b.skills}
        added_skills = sorted(b_skills - a_skills)
        removed_skills = sorted(a_skills - b_skills)

        if added_skills:
            diffs.append(EntryDiff(
                diff_type=DiffType.ADDED,
                section="skills",
                new_entry={"skills": [{"name": n, "category": c} for n, c in added_skills]},
            ))
        if removed_skills:
            diffs.append(EntryDiff(
                diff_type=DiffType.REMOVED,
                section="skills",
                old_entry={"skills": [{"name": n, "category": c} for n, c in removed_skills]},
            ))

        return VersionDiff(
            version_a_id=version_a_id,
            version_b_id=version_b_id,
            diffs=diffs,
        )

    # ── Internal helpers ────────────────────────────────────

    def _get(self, version_id: str) -> ResumeVersion:
        if version_id not in self._index:
            raise KeyError(f"Version not found: {version_id}")
        return self._index[version_id]

    def _version_path(self, version_id: str) -> Path:
        return self._storage_dir / f"version_{version_id}.json"

    def _persist(self, version: ResumeVersion):
        file_path = self._version_path(version.id)
        data = {
            "id": version.id,
            "parent_id": version.parent_id,
            "name": version.name,
            "notes": version.notes,
            "resume_data": version.resume_data.model_dump(mode="json"),
            "created_at": str(version.created_at),
            "updated_at": str(version.updated_at),
        }
        tmp_path = file_path.with_suffix(".json.tmp")
        tmp_path.write_text(
            json.dumps(data, indent=2, default=str), encoding="utf-8"
        )
        tmp_path.replace(file_path)

    def _migrate_legacy_files(self):
        """Move version_*.json out of uploads_path (they used to share it,
        and the resume loader would mis-read them)."""
        legacy_dir = settings.uploads_path
        if not legacy_dir or legacy_dir == self._storage_dir or not legacy_dir.exists():
            return
        for old in legacy_dir.glob("version_*.json"):
            target = self._storage_dir / old.name
            try:
                if not target.exists():
                    old.replace(target)
                else:
                    old.unlink()
                logger.info("Migrated legacy version file: %s", old.name)
            except OSError as e:
                logger.warning("Could not migrate %s: %s", old.name, e)

    def _load_index(self):
        """Load all persisted versions from disk."""
        for file_path in self._storage_dir.glob("version_*.json"):
            try:
                data = json.loads(file_path.read_text(encoding="utf-8"))
                version = ResumeVersion(
                    id=data["id"],
                    parent_id=data.get("parent_id"),
                    name=data["name"],
                    notes=data.get("notes", ""),
                    resume_data=ResumeData(**data["resume_data"]),
                    created_at=_parse_dt(data.get("created_at")),
                    updated_at=_parse_dt(data.get("updated_at")),
                )
                self._index[version.id] = version
            except Exception as e:
                logger.warning("Failed to load version %s: %s", file_path, e)

    @staticmethod
    def _compare_entries(a: dict, b: dict) -> list[str]:
        """Compare two entry dicts and return changed field names."""
        changed = []
        skip_keys = {"id", "entry_type", "confidence"}
        for key in set(a) | set(b):
            if key in skip_keys:
                continue
            if json.dumps(a.get(key), default=str) != json.dumps(b.get(key), default=str):
                changed.append(key)
        return sorted(changed)
