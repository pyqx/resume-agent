"""Tests for the resume data contract (core/resume/schema.py)."""

from core.resume.schema import (
    MatchLevel,
    ResumeData,
    Skill,
    WorkExperience,
)


class TestAllSections:
    def test_includes_skills(self):
        # Historical bug: skills were missing, so skill entries could never
        # be found or deleted by id.
        resume = ResumeData(skills=[Skill(name="Python")])
        assert "skills" in resume.all_sections

    def test_skill_lookup_and_removal_by_id(self):
        skill = Skill(name="Python")
        resume = ResumeData(skills=[skill])
        assert resume.get_entry_by_id(skill.id) is skill
        assert resume.remove_entry(skill.id) is True
        assert resume.skills == []

    def test_remove_bumps_version(self):
        work = WorkExperience(company="Acme")
        resume = ResumeData(work_experience=[work])
        v = resume.version
        assert resume.remove_entry(work.id)
        assert resume.version == v + 1


class TestSchemaFields:
    def test_match_level_has_error(self):
        assert MatchLevel.ERROR.value == "error"

    def test_dates_approximate_default_false(self):
        assert WorkExperience().dates_approximate is False

    def test_skill_has_confidence(self):
        assert Skill().confidence == 1.0
