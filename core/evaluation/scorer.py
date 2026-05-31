"""Scorer — weighted aggregation of rule, LLM, and ATS evaluation results."""

from dataclasses import dataclass, field

from core.evaluation.rules import RuleResult, Violation, Severity
from core.evaluation.ats_simulator import ATSResult


@dataclass
class QualityReport:
    overall_score: float = 0.0
    rule_score: float = 0.0
    llm_score: float = 0.0
    ats_score: float = 0.0

    # LLM dimensional scores
    star_completeness: float = 0.0
    quantitative_density: float = 0.0
    terminology_accuracy: float = 0.0
    conciseness: float = 0.0
    narrative_coherence: float = 0.0

    # Prioritized issues
    critical: list[Violation] = field(default_factory=list)
    errors: list[Violation] = field(default_factory=list)
    warnings: list[Violation] = field(default_factory=list)
    info: list[Violation] = field(default_factory=list)

    # LLM suggestions
    suggestions: list[str] = field(default_factory=list)
    strengths: list[str] = field(default_factory=list)

    # ATS
    ats_fields: list = field(default_factory=list)
    ats_format_issues: list[str] = field(default_factory=list)
    keyword_coverage: float = 0.0


class Scorer:
    """Aggregate rule-based, LLM-based, and ATS evaluation into a unified QualityReport."""

    def score(
        self,
        rule_result: RuleResult,
        llm_result: dict,
        ats_result: ATSResult,
    ) -> QualityReport:
        # LLM dimensional scores
        dims = llm_result.get("dimensions", {})
        llm_overall = float(llm_result.get("overall_score", 5.0))

        # Weighted aggregation: 0.4 * rules + 0.5 * LLM + 0.1 * ATS
        ats_score = ats_result.score
        overall = round(
            0.4 * rule_result.score +
            0.5 * (llm_overall or 5.0) +
            0.1 * ats_score,
            1,
        )

        # Classify violations by severity
        critical = [v for v in rule_result.violations if v.severity == Severity.CRITICAL]
        errors = [v for v in rule_result.violations if v.severity == Severity.ERROR]
        warnings = [v for v in rule_result.violations if v.severity == Severity.WARNING]
        info = [v for v in rule_result.violations if v.severity == Severity.INFO]

        return QualityReport(
            overall_score=overall,
            rule_score=rule_result.score,
            llm_score=llm_overall,
            ats_score=ats_score,
            star_completeness=float(dims.get("star_completeness", 0)),
            quantitative_density=float(dims.get("quantitative_density", 0)),
            terminology_accuracy=float(dims.get("terminology_accuracy", 0)),
            conciseness=float(dims.get("conciseness", 0)),
            narrative_coherence=float(dims.get("narrative_coherence", 0)),
            critical=critical,
            errors=errors,
            warnings=warnings,
            info=info,
            suggestions=llm_result.get("suggestions", []),
            strengths=llm_result.get("strengths", []),
            ats_fields=ats_result.fields,
            ats_format_issues=ats_result.format_issues,
            keyword_coverage=ats_result.keyword_coverage_pct,
        )
