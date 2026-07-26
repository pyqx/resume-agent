"""WeaknessStrategist — detect resume vulnerabilities and generate honest-but-optimized narratives."""

import logging
from datetime import date

from core.interview.lang import detect_language
from core.llm import (
    UNTRUSTED_NOTE,
    get_llm_client_from_settings,
    parse_json_response,
    render_prompt,
    wrap_untrusted,
)
from core.resume.schema import ResumeData

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are a career strategist helping a candidate prepare for tough "
    "interview questions about resume weaknesses. You NEVER suggest lying "
    "or fabricating experience.\n\n" + UNTRUSTED_NOTE
)

_OUTPUT_SPEC = """For each concern, provide:
- concern: what the interviewer might notice
- risk_level: "high" | "medium" | "low" — how likely it is to be questioned
- honest_narrative: a truthful, positive way to frame this (MUST NOT suggest lying or fabricating)
- sample_response: a sample answer the candidate can use (2-3 sentences)
- resume_fix: optional suggestion for how to adjust the resume to mitigate this concern

General principles:
- NEVER suggest lying or fabricating experiences
- Frame gaps as learning/growth periods
- For frequent job changes: focus on skill progression rather than tenure

Output JSON array:
[
  {
    "concern": "...",
    "risk_level": "high|medium|low",
    "honest_narrative": "...",
    "sample_response": "...",
    "resume_fix": "..."
  }
]

Output ONLY valid JSON array:"""

WEAKNESS_PROMPT = (
    """Analyze the detected resume concerns below and build response strategies.

{language_instruction}

## Resume
{resume_text}

## Detected Potential Concerns
{detected_concerns}

"""
    + _OUTPUT_SPEC
)

# Used when rule-based detection finds nothing: a weak resume must still get a
# substantive review instead of a free pass ("no weaknesses").
CONTENT_REVIEW_PROMPT = (
    """Review the candidate's resume below for substantive interview vulnerabilities.

{language_instruction}

## Resume
{resume_text}

No rule-based concerns (employment gaps, job hopping, missing education) were detected.
Look deeper and identify AT MOST 3 substantive weaknesses an interviewer would probe, focusing on:
- content quality: vague bullets, responsibilities listed without outcomes
- missing quantification: achievements without metrics or numbers to back them
- skill match: gaps between the skills/experience shown and the stated target position

Only report weaknesses with real interview risk. If the resume genuinely has none, return an empty array [].

"""
    + _OUTPUT_SPEC
)


class WeaknessStrategist:
    """Detect resume hard-to-explain points and generate honest narratives."""

    def __init__(self, llm_client=None):
        self._llm = llm_client

    @property
    def llm(self):
        if self._llm is None:
            self._llm = get_llm_client_from_settings()
        return self._llm

    async def analyze(self, resume: ResumeData) -> list[dict]:
        """Analyze resume for potential interview vulnerabilities.

        Raises RuntimeError when the LLM analysis fails.
        """
        concerns = self._detect_concerns(resume)
        resume_text = wrap_untrusted(self._resume_to_text(resume)[:4000], "RESUME")
        lang = detect_language(resume)
        language_instruction = (
            "Respond entirely in Chinese (Simplified): concern, honest_narrative, "
            "sample_response and resume_fix must all be in Chinese."
            if lang == "zh"
            else "Respond entirely in English."
        )

        if concerns:
            prompt = render_prompt(
                WEAKNESS_PROMPT,
                language_instruction=language_instruction,
                resume_text=resume_text,
                detected_concerns=wrap_untrusted(
                    "\n".join(f"- {c}" for c in concerns), "DETECTED_CONCERNS"
                ),
            )
        else:
            # No rule hits is NOT proof of a flawless resume — run one content
            # review pass; the model may still legitimately return [].
            logger.debug("No rule-based concerns detected; running LLM content review")
            prompt = render_prompt(
                CONTENT_REVIEW_PROMPT,
                language_instruction=language_instruction,
                resume_text=resume_text,
            )

        try:
            response = await self.llm.messages.create(
                messages=[{"role": "user", "content": prompt}],
                system=SYSTEM_PROMPT,
                max_tokens=3072,
                temperature=0.3,
                expect_json=True,
            )
            data = parse_json_response(response)
        except Exception as e:
            logger.warning("Weakness analysis failed: %s", e)
            raise RuntimeError(f"弱点分析失败:{e}") from e

        if not isinstance(data, list):
            logger.warning(
                "Weakness analysis returned %s instead of a JSON array",
                type(data).__name__,
            )
            raise RuntimeError("弱点分析失败:LLM 未返回 JSON 数组")

        items = [item for item in data if isinstance(item, dict)]
        if len(items) != len(data):
            logger.warning(
                "Weakness analysis dropped %d non-object item(s) from LLM output",
                len(data) - len(items),
            )
        return items

    def _detect_concerns(self, resume: ResumeData) -> list[str]:
        """Rule-based detection of resume concerns.

        Entries with dates_approximate=True or missing dates are excluded from
        gap/tenure math — the parser normalizes bare years ("2023") to
        YYYY-01-01, which would otherwise fabricate gaps.
        """
        today = date.today()
        concerns: list[str] = []

        # Only precisely dated entries participate in date arithmetic.
        precise = sorted(
            (
                w for w in resume.work_experience
                if w.start_date and not w.dates_approximate
            ),
            key=lambda w: w.start_date,
        )
        # Approximate entries with at least one (year-level) date: they cannot
        # join the math, but they can still cover a candidate gap window.
        fuzzy_dated = [
            w for w in resume.work_experience
            if w.dates_approximate and (w.start_date or w.end_date)
        ]

        def fuzzy_covers(gap_start: date, gap_end: date) -> bool:
            for w in fuzzy_dated:
                for d in (w.start_date, w.end_date):
                    if d and gap_start.year <= d.year <= gap_end.year:
                        return True
            return False

        # Employment gap check (between consecutive precisely dated jobs).
        for i in range(len(precise) - 1):
            prev, nxt = precise[i], precise[i + 1]
            if not prev.end_date or not nxt.start_date:
                continue
            gap = (nxt.start_date - prev.end_date).days
            if gap > 90 and not fuzzy_covers(prev.end_date, nxt.start_date):
                concerns.append(
                    f"{gap}天职业空窗期 ({prev.company} → {nxt.company})"
                )

        # Job hopping — average tenure over entries with a measurable span.
        tenures = []
        for w in precise:
            if w.end_date:
                end = w.end_date
            elif w.is_current:
                end = today
            else:
                continue  # end unknown and not current — cannot measure
            tenure_days = (end - w.start_date).days
            if tenure_days >= 0:
                tenures.append(tenure_days)
        if len(tenures) >= 3:
            avg_tenure = sum(tenures) / len(tenures)
            if avg_tenure < 547:  # < 1.5 years
                concerns.append(f"平均在岗时间不足1.5年 ({avg_tenure/365:.1f}年)")

        # Current tenure too short (< 6 months, precisely dated only).
        for w in resume.work_experience:
            if (
                w.is_current
                and not w.dates_approximate
                and w.start_date
                and 0 <= (today - w.start_date).days < 183
            ):
                concerns.append(f"当前任期过短({w.company or '当前公司'}入职不足6个月)")

        # No quantified achievements: no bullet contains a single digit.
        has_entries = (
            len(resume.work_experience) > 0 or len(resume.project_experience) > 0
        )
        all_bullets = [b for w in resume.work_experience for b in w.bullets]
        all_bullets += [b for p in resume.project_experience for b in p.bullets]
        if has_entries and not any(
            any(ch.isdigit() for ch in b) for b in all_bullets
        ):
            concerns.append("缺少量化成果(所有工作/项目要点均无数字支撑)")

        # 无教育经历条目
        has_education = len(resume.education) > 0
        has_experience = len(resume.work_experience) > 0
        if not has_education and has_experience:
            concerns.append("简历中未体现教育经历")

        return concerns

    def _resume_to_text(self, resume: ResumeData) -> str:
        parts = []
        if resume.target_position:
            parts.append(f"Target position: {resume.target_position}")
        for w in resume.work_experience:
            start = str(w.start_date) if w.start_date else "?"
            end = "至今" if w.is_current else str(w.end_date) if w.end_date else "?"
            approx = " (dates approximate)" if w.dates_approximate else ""
            parts.append(f"{start}→{end}{approx}: {w.position} @ {w.company}")
            parts.extend(f"  - {b}" for b in w.bullets)
        for p in resume.project_experience:
            parts.append(f"Project: {p.name}" + (f" ({p.role})" if p.role else ""))
            parts.extend(f"  - {b}" for b in p.bullets)
        for e in resume.education:
            parts.append(f"Education: {e.school} {e.degree} {e.major}".rstrip())
        if resume.skills:
            parts.append("Skills: " + ", ".join(s.name for s in resume.skills))
        return "\n".join(parts)
