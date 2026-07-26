"""Tests for JD keyword coverage (core/jd/keywords.py)."""

from core.jd.keywords import compute_keyword_coverage
from core.resume.schema import PersonalInfo, ResumeData, Skill, WorkExperience


def _resume() -> ResumeData:
    return ResumeData(
        personal_info=PersonalInfo(full_name="张三", summary="资深后端工程师"),
        work_experience=[
            WorkExperience(
                company="Google", position="Backend Engineer",
                bullets=["使用 Python 与 Django 构建微服务", "优化 MySQL 查询性能"],
            )
        ],
        skills=[Skill(name="Python"), Skill(name="Docker")],
    )


class TestKeywordCoverage:
    def test_ascii_word_boundary(self):
        # "go" must NOT match inside "Google" / "Django".
        result = compute_keyword_coverage(["go"], _resume())
        assert "go" in [m.lower() for m in result["missing"]]

    def test_exact_ascii_match(self):
        result = compute_keyword_coverage(["python", "docker"], _resume())
        matched_lower = [m.lower() for m in result["matched"]]
        assert "python" in matched_lower
        assert "docker" in matched_lower

    def test_cjk_substring_match(self):
        result = compute_keyword_coverage(["微服务", "高并发"], _resume())
        assert "微服务" in result["matched"]
        assert "高并发" in result["missing"]

    def test_field_names_not_matched(self):
        # Historical bug: coverage ran over model_dump JSON, so schema field
        # names like "skills"/"company" counted as hits.
        result = compute_keyword_coverage(["skills", "entry_type"], _resume())
        assert "entry_type" in result["missing"]

    def test_coverage_rate_bounds(self):
        result = compute_keyword_coverage(["python", "kubernetes"], _resume())
        assert 0 <= result["coverage_rate"] <= 100
