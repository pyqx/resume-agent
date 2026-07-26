"""Quality evaluation tools — rule checks + LLM judge + ATS simulation."""

import logging

from agent.tools.base import BaseTool, ToolMetadata, ToolResult, ToolCategory, Difficulty

logger = logging.getLogger(__name__)

# STAR keyword tables. A word may appear in ONE category only — "实现" used to
# sit in both action and result, double-counting a single occurrence.
_STAR_KEYWORDS = {
    "situation": ["背景", "当时", "面对", "针对", "context", "situation", "facing"],
    "task": ["任务", "目标", "需要", "task", "goal", "objective"],
    "action": ["使用", "通过", "设计", "开发", "搭建", "采用", "重构", "优化",
               "built", "implemented", "designed", "developed", "used", "refactored"],
    "result": ["提升", "降低", "增长", "节省", "达到", "缩短", "%", "倍",
               "increased", "reduced", "improved", "achieved", "resulted", "grew"],
}


class EvaluateStarCompletenessTool(BaseTool):
    """Fast keyword-heuristic STAR check (no LLM call).

    This is a heuristic screen — for semantic judgment use
    evaluate_entry_quality (LLM-based).
    """

    def __init__(self, get_resume_fn=None):
        self._get_resume = get_resume_fn

    @property
    def metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="evaluate_star_completeness",
            category=ToolCategory.QUALITY,
            description="Quick keyword-based check of STAR (Situation/Task/Action/Result) coverage per experience entry",
            usage_guide="Use as a fast screen for which entries lack STAR elements. For deep semantic evaluation use evaluate_entry_quality.",
            preconditions=["resume_loaded"],
            estimated_time=Difficulty.LIGHT,
        )

    async def execute(self, **kwargs) -> ToolResult:
        try:
            resume = self._get_resume() if self._get_resume else None
            if not resume:
                return ToolResult.fail("NO_RESUME", "No resume loaded", is_retryable=False)

            entries = []
            for w in resume.work_experience:
                text = " ".join([w.description or ""] + list(w.bullets or []))
                entries.append((f"{w.position} @ {w.company}", w.id, text))
            for p in resume.project_experience:
                text = " ".join([p.description or ""] + list(p.bullets or []))
                entries.append((p.name, p.id, text))

            if not entries:
                return ToolResult.fail(
                    "NO_ENTRIES", "简历中没有工作/项目经历条目", is_retryable=False
                )

            results = []
            for label, entry_id, text in entries:
                lowered = text.lower()
                star_elements = {
                    element: any(w in lowered for w in words)
                    for element, words in _STAR_KEYWORDS.items()
                }
                results.append({
                    "entry": label,
                    "entry_id": entry_id,
                    "star_elements": star_elements,
                    "completeness": sum(star_elements.values()),
                    "max_score": 4,
                    "missing": [k for k, v in star_elements.items() if not v],
                })
            return ToolResult.ok(results)
        except Exception as e:
            logger.exception("evaluate_star_completeness failed")
            return ToolResult.fail("STAR_EVAL_ERROR", str(e), is_retryable=False)


class EvaluateEntryQualityTool(BaseTool):
    def __init__(self, llm_judge, get_resume_fn):
        self._llm = llm_judge
        self._get_resume = get_resume_fn

    @property
    def metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="evaluate_entry_quality",
            category=ToolCategory.QUALITY,
            description="LLM quality evaluation of the resume (0-10 with dimensional breakdown and suggestions)",
            usage_guide="Use for deep quality analysis. Returns dimensional scores and specific improvement suggestions.",
            preconditions=["resume_loaded"],
            estimated_time=Difficulty.MEDIUM,
        )

    async def execute(self, **kwargs) -> ToolResult:
        try:
            resume = self._get_resume()
            if not resume:
                return ToolResult.fail("NO_RESUME", "No resume loaded", is_retryable=False)

            result = await self._llm.evaluate(resume)
            if isinstance(result, dict) and result.get("available") is False:
                return ToolResult.fail(
                    "LLM_UNAVAILABLE",
                    f"LLM 评估不可用: {result.get('error', 'unknown')}",
                    is_retryable=False,
                )
            return ToolResult.ok({"evaluation": result})
        except Exception as e:
            logger.exception("evaluate_entry_quality failed")
            return ToolResult.fail("QUALITY_ERROR", str(e), is_retryable=False)


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
                return ToolResult.fail("NO_RESUME", "No resume loaded", is_retryable=False)

            rule_result = self._rules.evaluate(resume)
            weak_verb_violations = [v for v in rule_result.violations if v.rule == "weak_verb"]
            return ToolResult.ok({
                "count": len(weak_verb_violations),
                "violations": [
                    {"location": v.location, "message": v.message, "suggestion": v.suggestion}
                    for v in weak_verb_violations
                ],
            })
        except Exception as e:
            logger.exception("check_verb_strength failed")
            return ToolResult.fail("VERB_CHECK_ERROR", str(e), is_retryable=False)


class CheckSensitiveInfoTool(BaseTool):
    def __init__(self, rule_evaluator, get_resume_fn):
        self._rules = rule_evaluator
        self._get_resume = get_resume_fn

    @property
    def metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="check_sensitive_info",
            category=ToolCategory.QUALITY,
            description="Scan resume content for sensitive information (ID numbers, salary, addresses in bullets)",
            usage_guide="Use before exporting or sharing a resume to detect privacy risks.",
            preconditions=["resume_loaded"],
            estimated_time=Difficulty.LIGHT,
        )

    async def execute(self, **kwargs) -> ToolResult:
        try:
            resume = self._get_resume()
            if not resume:
                return ToolResult.fail("NO_RESUME", "No resume loaded", is_retryable=False)

            rule_result = self._rules.evaluate(resume)
            sensitive = [v for v in rule_result.violations if v.rule == "sensitive_info"]
            return ToolResult.ok({
                "has_sensitive_info": len(sensitive) > 0,
                "count": len(sensitive),
                "violations": [
                    {"severity": v.severity, "message": v.message, "suggestion": v.suggestion}
                    for v in sensitive
                ],
            })
        except Exception as e:
            logger.exception("check_sensitive_info failed")
            return ToolResult.fail("SENSITIVE_CHECK_ERROR", str(e), is_retryable=False)


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
            estimated_time=Difficulty.HEAVY,
        )

    async def execute(self, **kwargs) -> ToolResult:
        try:
            resume = self._get_resume()
            if not resume:
                return ToolResult.fail("NO_RESUME", "No resume loaded", is_retryable=False)

            rule_result = self._rules.evaluate(resume)
            llm_result = await self._llm.evaluate(resume)
            # New contract: ATS simulates against the actual ResumeData
            # (rendered text internally), not a dict repr.
            ats_result = self._ats.simulate(resume)

            report = self._scorer.score(rule_result, llm_result, ats_result)

            payload = {
                "overall_score": report.overall_score,
                "llm_available": not (
                    isinstance(llm_result, dict) and llm_result.get("available") is False
                ),
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
            }
            return ToolResult.ok(payload)
        except Exception as e:
            logger.exception("run_full_quality_audit failed")
            return ToolResult.fail("AUDIT_ERROR", str(e), is_retryable=False)
