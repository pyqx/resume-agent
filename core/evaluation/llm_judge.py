"""LLMJudge — LLM-as-Judge for semantic quality evaluation of resume content."""

import logging

from core.evaluation.render import resume_to_text
from core.llm import (
    UNTRUSTED_NOTE,
    get_llm_client_from_settings,
    parse_json_response,
    render_prompt,
    wrap_untrusted,
)
from core.resume.schema import ResumeData

logger = logging.getLogger(__name__)

# Dimension weights (mirrors prompts/evaluation/llm_judge_v1.yaml). The
# overall score is always computed in Python from these weights — a
# model-reported total is never trusted.
DIMENSION_WEIGHTS: dict[str, float] = {
    "star_completeness": 0.35,
    "quantitative_density": 0.30,
    "terminology_accuracy": 0.15,
    "conciseness": 0.10,
    "narrative_coherence": 0.10,
}

_MAX_RESUME_CHARS = 8000
_DEFAULT_DIMENSION_SCORE = 5.0

JUDGE_SYSTEM = (
    "You are a strict but constructive resume quality evaluator. "
    "Follow the scoring rubric exactly and output only JSON. " + UNTRUSTED_NOTE
)

# Rubric merged from prompts/evaluation/llm_judge_v1.yaml (v1.0).
JUDGE_PROMPT = """Score the resume below across five dimensions on a 1-10 scale.

{resume_text}

Dimensions and scoring rubric:

1. star_completeness — Do experience entries include Situation, Task, Action, and Result?
   1-3: Most entries describe only what was done (Action), missing context and results
   4-6: Some entries have STAR elements but inconsistently applied
   7-8: Most entries have 3+ STAR elements clearly present
   9-10: Every entry has full STAR with specific details in each dimension

2. quantitative_density — How many entries include specific numbers, percentages, or measurable outcomes?
   1-3: Almost no numbers or measurable outcomes
   4-6: Some numbers present but vague (e.g. 'many', 'several')
   7-8: Most entries have at least one specific metric
   9-10: Every claim is backed by a specific number or percentage

3. terminology_accuracy — Are technical terms spelled correctly and used appropriately?
   1-3: Major errors in tech stack naming or industry terminology
   4-6: Minor inconsistencies in term usage
   7-8: Terms are correct, occasionally missing context
   9-10: All terms are precisely used with correct context

4. conciseness — Is the writing tight and impactful? No filler words?
   1-3: Wordy, repetitive, or filled with meaningless phrases
   4-6: Some filler but generally readable
   7-8: Clean writing with few redundancies
   9-10: Every word pulls its weight, maximum impact per sentence

5. narrative_coherence — Does the resume tell a clear career story with logical progression?
   1-3: Disjointed experiences with no clear career narrative
   4-6: Some progression visible but not clearly articulated
   7-8: Clear career arc with logical progression between roles
   9-10: Compelling narrative that positions each experience as a stepping stone

Guidelines:
- Always include 2-3 specific, actionable suggestions targeting the lowest-scoring dimensions
- Cite specific examples from the resume text
- Be constructive — focus on what can be improved, not what's wrong

Output JSON only:
{
  "dimensions": {
    "star_completeness": 0,
    "quantitative_density": 0,
    "terminology_accuracy": 0,
    "conciseness": 0,
    "narrative_coherence": 0
  },
  "suggestions": ["suggestion 1", "suggestion 2", "suggestion 3"],
  "strengths": ["strength 1", "strength 2"]
}"""


class LLMJudge:
    """LLM-based semantic quality evaluator. Uses temperature=0 for reproducibility."""

    def __init__(self, llm_client=None):
        self._llm = llm_client

    @property
    def llm(self):
        if self._llm is None:
            self._llm = get_llm_client_from_settings()
        return self._llm

    async def evaluate(self, resume: ResumeData) -> dict:
        """Evaluate resume quality across five dimensions.

        Returns ``{"available": True, "dimensions": {...}, "overall_score": ...,
        "suggestions": [...], "strengths": [...]}`` on success, plus
        ``"parse_warnings"`` when a dimension had to be defaulted.

        On failure returns ``{"available": False, "error": "..."}`` — never a
        fabricated mid-scale score.
        """
        resume_text = resume_to_text(resume)[:_MAX_RESUME_CHARS]
        prompt = render_prompt(
            JUDGE_PROMPT,
            resume_text=wrap_untrusted(resume_text, "resume"),
        )

        try:
            response = await self.llm.messages.create(
                messages=[{"role": "user", "content": prompt}],
                system=JUDGE_SYSTEM,
                max_tokens=2048,
                temperature=0.0,
                expect_json=True,
            )
            data = parse_json_response(response)
            if not isinstance(data, dict):
                raise ValueError("judge response is not a JSON object")
        except Exception as e:
            logger.warning("LLM judge evaluation failed: %s", e)
            return {"available": False, "error": f"{type(e).__name__}: {e}"[:300]}

        return self._build_result(data)

    @staticmethod
    def _build_result(data: dict) -> dict:
        raw_dims = data.get("dimensions")
        if not isinstance(raw_dims, dict):
            raw_dims = {}

        parse_warnings: list[str] = []
        dimensions: dict[str, float] = {}
        for name in DIMENSION_WEIGHTS:
            raw = raw_dims.get(name)
            try:
                value = float(raw)
                if value != value:  # NaN
                    raise ValueError("NaN")
            except (TypeError, ValueError):
                parse_warnings.append(
                    f"dimension '{name}' was {raw!r}; defaulted to {_DEFAULT_DIMENSION_SCORE}"
                )
                value = _DEFAULT_DIMENSION_SCORE
            dimensions[name] = min(10.0, max(0.0, value))

        # Weighted total computed here, not by the model.
        overall = round(
            sum(dimensions[name] * weight for name, weight in DIMENSION_WEIGHTS.items()),
            1,
        )

        suggestions = data.get("suggestions")
        strengths = data.get("strengths")
        result = {
            "available": True,
            "dimensions": dimensions,
            "overall_score": overall,
            "suggestions": [str(s) for s in suggestions if s] if isinstance(suggestions, list) else [],
            "strengths": [str(s) for s in strengths if s] if isinstance(strengths, list) else [],
        }
        if parse_warnings:
            result["parse_warnings"] = parse_warnings
        return result
