"""Scorer — weighted aggregation of rule, LLM, and ATS evaluation results."""

from dataclasses import dataclass, field
from typing import Any

from core.evaluation.rules import RuleResult, Severity, Violation

# Aggregation weights. When a source is unavailable (e.g. the LLM judge
# failed), its weight is dropped and the rest are renormalized — with the
# LLM missing this yields rule 0.8 / ats 0.2.
RULE_WEIGHT = 0.4
LLM_WEIGHT = 0.5
ATS_WEIGHT = 0.1


def _safe_score(value: Any) -> float | None:
    """float() with clamp to 0-10; None when the value is not a usable number."""
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number:  # NaN
        return None
    return min(10.0, max(0.0, number))


def _get(source: Any, key: str, default: Any = None) -> Any:
    """Read a key from a dict, or an attribute from a legacy result object."""
    if isinstance(source, dict):
        return source.get(key, default)
    value = getattr(source, key, default)
    return default if value is None and default is not None else value


def _str_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if item]


@dataclass
class QualityReport:
    overall_score: float = 0.0
    rule_score: float = 0.0
    llm_score: float = 0.0
    ats_score: float = 0.0

    # Whether the LLM judge actually ran (False -> llm_score is meaningless
    # and the overall score was computed from rules + ATS only).
    llm_available: bool = True

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
    # None when the ATS ran without target keywords.
    keyword_coverage: float | None = 0.0


class Scorer:
    """Aggregate rule-based, LLM-based, and ATS evaluation into a unified QualityReport."""

    def score(
        self,
        rule_result: RuleResult,
        llm_result: dict,
        ats_result: dict,
    ) -> QualityReport:
        if not isinstance(llm_result, dict):
            llm_result = {}

        rule_score = _safe_score(_get(rule_result, "score"))
        ats_score = _safe_score(_get(ats_result, "score"))

        llm_available = bool(llm_result.get("available", True))
        llm_overall = _safe_score(llm_result.get("overall_score")) if llm_available else None
        if llm_overall is None:
            llm_available = False

        # Weighted aggregation; unavailable/non-numeric sources drop out and
        # the remaining weights are renormalized.
        weighted = [
            (RULE_WEIGHT, rule_score),
            (LLM_WEIGHT, llm_overall),
            (ATS_WEIGHT, ats_score),
        ]
        active = [(weight, value) for weight, value in weighted if value is not None]
        total_weight = sum(weight for weight, _ in active)
        overall = sum(weight * value for weight, value in active) / total_weight if total_weight else 0.0
        overall = round(min(10.0, max(0.0, overall)), 1)

        # LLM dimensional scores
        dims = llm_result.get("dimensions")
        if not isinstance(dims, dict):
            dims = {}

        def dim(name: str) -> float:
            value = _safe_score(dims.get(name))
            return 0.0 if value is None else value

        # Classify violations by severity
        violations = _get(rule_result, "violations", []) or []
        critical = [v for v in violations if v.severity == Severity.CRITICAL]
        errors = [v for v in violations if v.severity == Severity.ERROR]
        warnings = [v for v in violations if v.severity == Severity.WARNING]
        info = [v for v in violations if v.severity == Severity.INFO]

        # Keyword coverage is 0-100 (or None when no target keywords given).
        raw_coverage = _get(ats_result, "keyword_coverage_pct")
        try:
            keyword_coverage = None if raw_coverage is None else float(raw_coverage)
        except (TypeError, ValueError):
            keyword_coverage = None

        return QualityReport(
            overall_score=overall,
            rule_score=rule_score if rule_score is not None else 0.0,
            llm_score=llm_overall if llm_overall is not None else 0.0,
            ats_score=ats_score if ats_score is not None else 0.0,
            llm_available=llm_available,
            star_completeness=dim("star_completeness"),
            quantitative_density=dim("quantitative_density"),
            terminology_accuracy=dim("terminology_accuracy"),
            conciseness=dim("conciseness"),
            narrative_coherence=dim("narrative_coherence"),
            critical=critical,
            errors=errors,
            warnings=warnings,
            info=info,
            suggestions=_str_list(llm_result.get("suggestions")),
            strengths=_str_list(llm_result.get("strengths")),
            ats_fields=_get(ats_result, "fields", []) or [],
            ats_format_issues=_get(ats_result, "format_issues", []) or [],
            keyword_coverage=keyword_coverage,
        )
