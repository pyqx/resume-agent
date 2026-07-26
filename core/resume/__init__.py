"""core.resume — resume data contract and processing.

Only the (dependency-light) schema is re-exported here. Import submodules
directly for heavier components, e.g.:

    from core.resume.parser import ResumeParser
    from core.resume.exporter import ResumeExporter
    from core.resume.sanitizer import PIIMasker, sanitize_text

Keeping this package __init__ light avoids import cycles (core.llm imports
core.resume.sanitizer; parser imports core.llm).
"""

from core.resume.schema import (
    ResumeData, PersonalInfo, Education, WorkExperience,
    ProjectExperience, Skill, EducationLevel, EntryType,
    JDRequirements, Requirement, MatchReport, JDSignal,
    RequirementType, MatchLevel, ResumeVersion, VersionDiff,
    EntryDiff, DiffType,
)

__all__ = [
    "ResumeData", "PersonalInfo", "Education", "WorkExperience",
    "ProjectExperience", "Skill", "EducationLevel", "EntryType",
    "JDRequirements", "Requirement", "MatchReport", "JDSignal",
    "RequirementType", "MatchLevel", "ResumeVersion", "VersionDiff",
    "EntryDiff", "DiffType",
]
