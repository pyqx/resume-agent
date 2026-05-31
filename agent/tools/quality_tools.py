"""Quality evaluation tools — rule checks + LLM judge + ATS simulation."""

import logging

from agent.tools.base import BaseTool, ToolMetadata, ToolResult, ToolCategory, Difficulty

logger = logging.getLogger(__name__)


class EvaluateStarCompletenessTool(BaseTool):
    def __init__(self, rule_evaluator, llm_judge, get_resume_fn=None):
        self._rules = rule_evaluator
        self._llm = llm_judge
        self._get_resume = get_resume_fn

    @property
    def metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="evaluate_star_completeness",
            category=ToolCategory.QUALITY,
            description="Evaluate how complete the STAR (Situation/Task/Action/Result) structure is in each experience entry. Auto-fetches resume data.",
            usage_guide="Use when analyzing whether resume entries are descriptive enough. No parameters needed — automatically evaluates all work and project entries.",
            preconditions=["resume_loaded"],
            estimated_time=Difficulty.MEDIUM,
        )

    async def execute(self, **kwargs) -> ToolResult:
        try:
            # Auto-extract entry texts from current resume
            if self._get_resume:
                resume = self._get_resume()
                if resume:
                    entry_texts = []
                    for w in resume.work_experience:
                        bullets_text = " ".join(w.bullets) if w.bullets else ""
                        entry_texts.append(f"{w.position} at {w.company}: {w.description} {bullets_text}")
                    for p in resume.project_experience:
                        bullets_text = " ".join(p.bullets) if p.bullets else ""
                        entry_texts.append(f"{p.name}: {p.description} {bullets_text}")
                else:
                    entry_texts = []
            else:
                entry_texts = []

            if not entry_texts:
                return ToolResult.ok({"message": "No experience entries found in the current resume", "results": []})

            results = []
            for text in entry_texts:
                star_elements = {
                    "situation": any(w in text.lower() for w in ["背景", "当时", "context", "situation", "facing"]),
                    "task": any(w in text.lower() for w in ["任务", "负责", "task", "goal", "objective", "需要"]),
                    "action": any(w in text.lower() for w in ["使用", "通过", "设计", "开发", "实现", "采用", "built", "implemented", "designed", "developed", "used"]),
                    "result": any(w in text.lower() for w in ["提升", "降低", "增长", "节省", "达到", "实现", "increased", "reduced", "improved", "achieved", "resulted", "grew"]),
                }
                completeness = sum(1 for v in star_elements.values() if v)
                results.append({
                    "text": text[:100],
                    "star_elements": star_elements,
                    "completeness": completeness,
                    "max_score": 4,
                    "missing": [k for k, v in star_elements.items() if not v],
                })

            return ToolResult.ok(results)
        except Exception as e:
            return ToolResult.fail("STAR_EVAL_ERROR", str(e))


class EvaluateEntryQualityTool(BaseTool):
    def __init__(self, llm_judge, get_resume_fn):
        self._llm = llm_judge
        self._get_resume = get_resume_fn

    @property
    def metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="evaluate_entry_quality",
            category=ToolCategory.QUALITY,
            description="Comprehensive quality score for a single resume entry (0-10 scale with dimensional breakdown)",
            usage_guide="Use for deep analysis of a specific entry. Returns dimensional scores and specific improvement suggestions.",
            preconditions=["resume_loaded"],
            estimated_time=Difficulty.MEDIUM,
        )

    async def execute(self, entry_id: str = "", **kwargs) -> ToolResult:
        try:
            resume = self._get_resume()
            if not resume:
                return ToolResult.fail("NO_RESUME", "No resume loaded")

            if entry_id:
                entry = resume.get_entry_by_id(entry_id)
                if not entry:
                    return ToolResult.fail("NOT_FOUND", f"Entry {entry_id} not found")
                entries = [entry]
            else:
                entries = list(resume.work_experience) + list(resume.project_experience) + list(resume.education)

            result = await self._llm.evaluate(resume)
            return ToolResult.ok({
                "entry_count": len(entries),
                "evaluation": result,
            })
        except Exception as e:
            return ToolResult.fail("QUALITY_ERROR", str(e))


class CheckVerbStrengthTool(BaseTool):
    def __init__(self, rule_evaluator, get_resume_fn):
        self._rules = rule_evaluator
        self._get_resume = get_resume_fn

    @property
    def metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="check_verb_strength",
            category=ToolCategory.QUALITY,
            description="Scan for weak verbs (负责/参与/协助) and suggest stronger alternatives",
            usage_guide="Use when tightening the language of experience bullets.",
            preconditions=["resume_loaded"],
            estimated_time=Difficulty.LIGHT,
        )

    async def execute(self, **kwargs) -> ToolResult:
        try:
            resume = self._get_resume()
            if not resume:
                return ToolResult.fail("NO_RESUME", "No resume loaded")

            rule_result = self._rules.evaluate(resume)
            weak_verb_violations = [
                v for v in rule_result.violations
                if v.rule == "weak_verb"
            ]
            return ToolResult.ok({
                "count": len(weak_verb_violations),
                "violations": [
                    {"location": v.location, "message": v.message, "suggestion": v.suggestion}
                    for v in weak_verb_violations
                ],
            })
        except Exception as e:
            return ToolResult.fail("VERB_CHECK_ERROR", str(e))


class CheckSensitiveInfoTool(BaseTool):
    def __init__(self, rule_evaluator, get_resume_fn):
        self._rules = rule_evaluator
        self._get_resume = get_resume_fn

    @property
    def metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="check_sensitive_info",
            category=ToolCategory.QUALITY,
            description="Scan resume for sensitive information (ID numbers, salary, full addresses, phone numbers)",
            usage_guide="Use before exporting or sharing a resume to detect privacy risks.",
            estimated_time=Difficulty.LIGHT,
        )

    async def execute(self, **kwargs) -> ToolResult:
        try:
            resume = self._get_resume()
            if not resume:
                return ToolResult.fail("NO_RESUME", "No resume loaded")

            rule_result = self._rules.evaluate(resume)
            sensitive = [
                v for v in rule_result.violations
                if v.rule == "sensitive_info"
            ]
            return ToolResult.ok({
                "has_sensitive_info": len(sensitive) > 0,
                "count": len(sensitive),
                "violations": [
                    {"severity": v.severity, "message": v.message, "suggestion": v.suggestion}
                    for v in sensitive
                ],
            })
        except Exception as e:
            return ToolResult.fail("SENSITIVE_CHECK_ERROR", str(e))


class RunFullQualityAuditTool(BaseTool):
    def __init__(self, rule_evaluator, llm_judge, ats_simulator, scorer, get_resume_fn):
        self._rules = rule_evaluator
        self._llm = llm_judge
        self._ats = ats_simulator
        self._scorer = scorer
        self._get_resume = get_resume_fn

    @property
    def metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="run_full_quality_audit",
            category=ToolCategory.QUALITY,
            description="Run complete quality audit: rule checks + LLM evaluation + ATS simulation. Returns prioritized improvement list.",
            usage_guide="Use when the user wants a comprehensive quality report. Best used before finalizing a resume for submission.",
            preconditions=["resume_loaded"],
            estimated_time=Difficulty.MEDIUM,
            is_idempotent=False,
        )

    async def execute(self, **kwargs) -> ToolResult:
        try:
            resume = self._get_resume()
            if not resume:
                return ToolResult.fail("NO_RESUME", "No resume loaded")

            # Run all three evaluators
            rule_result = self._rules.evaluate(resume)
            llm_result = await self._llm.evaluate(resume)

            resume_text = str(resume.model_dump())
            ats_result = self._ats.simulate(resume_text)

            # Aggregate
            report = self._scorer.score(rule_result, llm_result, ats_result)

            return ToolResult.ok({
                "overall_score": report.overall_score,
                "breakdown": {
                    "rule_score": report.rule_score,
                    "llm_score": report.llm_score,
                    "ats_score": report.ats_score,
                },
                "dimensions": {
                    "star_completeness": report.star_completeness,
                    "quantitative_density": report.quantitative_density,
                    "terminology_accuracy": report.terminology_accuracy,
                    "conciseness": report.conciseness,
                    "narrative_coherence": report.narrative_coherence,
                },
                "critical_issues": [
                    {"rule": v.rule, "message": v.message, "suggestion": v.suggestion}
                    for v in report.critical
                ],
                "errors": [
                    {"rule": v.rule, "message": v.message, "suggestion": v.suggestion}
                    for v in report.errors
                ],
                "warnings": [
                    {"rule": v.rule, "message": v.message, "suggestion": v.suggestion}
                    for v in report.warnings
                ],
                "info": [
                    {"rule": v.rule, "message": v.message, "suggestion": v.suggestion}
                    for v in report.info
                ],
                "suggestions": report.suggestions,
                "strengths": report.strengths,
                "ats": {
                    "fields": [
                        {"field": f.field, "found": f.found, "issues": f.issues}
                        for f in report.ats_fields
                    ],
                    "format_issues": report.ats_format_issues,
                    "keyword_coverage_pct": report.keyword_coverage,
                },
            })
        except Exception as e:
            return ToolResult.fail("AUDIT_ERROR", str(e), is_retryable=True)
