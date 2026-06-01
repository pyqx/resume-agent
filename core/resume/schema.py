"""Pydantic ResumeData model — universal data contract for the entire system."""

from datetime import date, datetime
from enum import Enum
from uuid import UUID, uuid4
from pydantic import BaseModel, Field


# ── Enums ──────────────────────────────────────────────────

class EducationLevel(str, Enum):
    HIGH_SCHOOL = "high_school"
    ASSOCIATE = "associate"
    BACHELOR = "bachelor"
    MASTER = "master"
    PHD = "phd"
    OTHER = "other"


# Chinese-to-English education level mapping for LLM compatibility
EDUCATION_LEVEL_CN_MAP: dict[str, str] = {
    "高中": "high_school",
    "中专": "high_school",
    "大专": "associate",
    "专科": "associate",
    "本科": "bachelor",
    "学士": "bachelor",
    "硕士": "master",
    "研究生": "master",
    "博士": "phd",
    "博士学位": "phd",
    "其他": "other",
}


class EntryType(str, Enum):
    WORK = "work"
    PROJECT = "project"
    EDUCATION = "education"


# ── Sub-models ─────────────────────────────────────────────

class PersonalInfo(BaseModel):
    full_name: str = ""
    email: str = ""
    phone: str = ""
    location: str = ""
    linkedin: str = ""
    github: str = ""
    website: str = ""
    summary: str = ""


class Education(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    entry_type: EntryType = EntryType.EDUCATION
    school: str = ""
    degree: str = ""
    major: str = ""
    level: EducationLevel = EducationLevel.BACHELOR
    start_date: date | None = None
    end_date: date | None = None
    gpa: str = ""
    description: str = ""
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class WorkExperience(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    entry_type: EntryType = EntryType.WORK
    company: str = ""
    position: str = ""
    start_date: date | None = None
    end_date: date | None = None
    is_current: bool = False
    location: str = ""
    bullets: list[str] = Field(default_factory=list)
    description: str = ""
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class ProjectExperience(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    entry_type: EntryType = EntryType.PROJECT
    name: str = ""
    role: str = ""
    url: str = ""
    start_date: date | None = None
    end_date: date | None = None
    technologies: list[str] = Field(default_factory=list)
    bullets: list[str] = Field(default_factory=list)
    description: str = ""
    is_planned: bool = False
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class Skill(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    name: str = ""
    category: str = ""
    level: str = ""
    years: float = 0.0


# ── Top-level Resume Model ─────────────────────────────────

class ResumeData(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    version: int = 1
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

    personal_info: PersonalInfo = Field(default_factory=PersonalInfo)
    education: list[Education] = Field(default_factory=list)
    work_experience: list[WorkExperience] = Field(default_factory=list)
    project_experience: list[ProjectExperience] = Field(default_factory=list)
    skills: list[Skill] = Field(default_factory=list)

    target_position: str = ""
    target_industry: str = ""
    source_filename: str = ""

    def bump_version(self):
        self.version += 1
        self.updated_at = datetime.now()

    @property
    def all_sections(self) -> dict[str, list]:
        return {
            "education": self.education,
            "work_experience": self.work_experience,
            "project_experience": self.project_experience,
        }

    def get_entry_by_id(self, entry_id: str):
        for section in self.all_sections.values():
            for entry in section:
                if entry.id == entry_id:
                    return entry
        return None

    def remove_entry(self, entry_id: str) -> bool:
        for section_name, entries in self.all_sections.items():
            for i, entry in enumerate(entries):
                if entry.id == entry_id:
                    entries.pop(i)
                    self.bump_version()
                    return True
        return False


# ── JD Models ──────────────────────────────────────────────

class RequirementType(str, Enum):
    MUST_HAVE = "must_have"
    PLUS = "plus"


class MatchLevel(str, Enum):
    FULL = "full"
    PARTIAL = "partial"
    NONE = "none"


class Requirement(BaseModel):
    criterion: str = ""
    type: RequirementType = RequirementType.MUST_HAVE
    match_level: MatchLevel = MatchLevel.NONE
    evidence: str = ""
    suggestion: str = ""


class JDSignal(BaseModel):
    phrase: str = ""
    interpretation: str = ""
    risk_level: str = ""


class JDRequirements(BaseModel):
    raw_text: str = ""
    position_title: str = ""
    company: str = ""
    hard_requirements: list[Requirement] = Field(default_factory=list)
    nice_to_have: list[Requirement] = Field(default_factory=list)
    soft_signals: list[JDSignal] = Field(default_factory=list)
    keyword_frequency: dict[str, int] = Field(default_factory=dict)


class MatchReport(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    resume_id: str = ""
    jd_text_hash: str = ""
    overall_score: float = 0.0
    must_have_met: int = 0
    must_have_total: int = 0
    plus_met: int = 0
    plus_total: int = 0
    requirements: list[Requirement] = Field(default_factory=list)
    signals: list[JDSignal] = Field(default_factory=list)
    keyword_coverage: float = 0.0
    created_at: datetime = Field(default_factory=datetime.now)


# ── Version Management Models ──────────────────────────────

class DiffType(str, Enum):
    ADDED = "added"
    REMOVED = "removed"
    MODIFIED = "modified"


class EntryDiff(BaseModel):
    diff_type: DiffType
    entry_id: str = ""
    section: str = ""
    old_entry: dict | None = None
    new_entry: dict | None = None
    changed_fields: list[str] = Field(default_factory=list)


class VersionDiff(BaseModel):
    version_a_id: str
    version_b_id: str
    diffs: list[EntryDiff] = Field(default_factory=list)


class ResumeVersion(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    parent_id: str | None = None
    name: str = ""
    notes: str = ""
    resume_data: ResumeData = Field(default_factory=ResumeData)
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
