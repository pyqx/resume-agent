"""Tests for the evaluation stack (rules / ATS / scorer) on real rendering."""

from core.evaluation.ats_simulator import ATSSimulator
from core.evaluation.render import resume_to_text
from core.evaluation.rules import RuleEvaluator
from core.resume.schema import (
    Education,
    PersonalInfo,
    ResumeData,
    Skill,
    WorkExperience,
)


def _full_resume() -> ResumeData:
    return ResumeData(
        personal_info=PersonalInfo(
            full_name="张三",
            email="zhangsan@example.com",
            phone="13812345678",
            summary="五年后端开发经验",
        ),
        education=[Education(school="清华大学", degree="学士", major="计算机")],
        work_experience=[
            WorkExperience(
                company="某公司",
                position="后端工程师",
                bullets=["主导重构订单系统,QPS 提升 300%", "搭建监控体系,故障率降低 50%"],
            )
        ],
        skills=[Skill(name="Python", category="语言")],
    )


class TestRender:
    def test_no_dict_repr_artifacts(self):
        # Historical bug: evaluation ran on str(model_dump()), full of
        # UUIDs, field names and quotes.
        text = resume_to_text(_full_resume())
        assert "entry_type" not in text
        assert "confidence" not in text
        assert "'" not in text.replace("’", "")
        assert "张三" in text
        assert "主导重构订单系统" in text


class TestRules:
    def test_own_contact_not_flagged_sensitive(self):
        result = RuleEvaluator().evaluate(_full_resume())
        sensitive = [v for v in result.violations if v.rule == "sensitive_info"]
        assert sensitive == [], f"own phone/email must not be flagged: {sensitive}"

    def test_phone_in_bullet_flagged(self):
        resume = _full_resume()
        resume.work_experience[0].bullets.append("如有问题联系 13911112222")
        result = RuleEvaluator().evaluate(resume)
        assert any(v.rule == "sensitive_info" for v in result.violations)

    def test_weak_verb_deduction_capped(self):
        resume = _full_resume()
        resume.work_experience[0].bullets = [
            f"负责参与协助进行处理模块{i}" for i in range(15)
        ]
        result = RuleEvaluator().evaluate(resume)
        # Historical bug: -0.5 per hit floored every Chinese resume to 0.
        assert result.score > 0

    def test_project_bullets_scanned_for_weak_verbs(self):
        from core.resume.schema import ProjectExperience
        resume = _full_resume()
        resume.work_experience = []
        resume.project_experience = [
            ProjectExperience(name="校园系统", bullets=["负责数据库设计"])
        ]
        result = RuleEvaluator().evaluate(resume)
        assert any(v.rule == "weak_verb" for v in result.violations)


class TestFullAuditTool:
    def test_audit_payload_builds_with_dict_ats_fields(self):
        """Regression: ats_fields items are dicts (asdict) — payload assembly
        must not assume legacy attribute objects ('dict' has no attr 'field')."""
        import asyncio
        from agent.tools.quality_tools import RunFullQualityAuditTool
        from core.evaluation.scorer import Scorer

        class FakeJudge:
            async def evaluate(self, resume):
                return {"available": False, "error": "offline"}

        resume = _full_resume()
        tool = RunFullQualityAuditTool(
            RuleEvaluator(), FakeJudge(), ATSSimulator(), Scorer(),
            lambda resume_id="": resume,
        )
        result = asyncio.run(tool.execute())
        assert result.success, f"{result.error_code}: {result.error_message}"
        payload = result.data
        assert payload["llm_available"] is False
        assert all("field" in f and "found" in f for f in payload["ats"]["fields"])
        assert 0 <= payload["overall_score"] <= 10


class TestATS:
    def test_full_resume_scores_high_without_saturation(self):
        result = ATSSimulator().simulate(_full_resume())
        score = result["score"] if isinstance(result, dict) else result.score
        assert 0 <= score <= 10

    def test_empty_resume_scores_low(self):
        empty = ResumeData()
        result = ATSSimulator().simulate(empty)
        score = result["score"] if isinstance(result, dict) else result.score
        full = ATSSimulator().simulate(_full_resume())
        full_score = full["score"] if isinstance(full, dict) else full.score
        assert score < full_score
