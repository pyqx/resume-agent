"""InterviewQuestionGenerator — generate targeted questions from resume + JD."""

import logging

from core.interview.lang import detect_language
from core.llm import (
    UNTRUSTED_NOTE,
    get_llm_client_from_settings,
    parse_json_response,
    render_prompt,
    wrap_untrusted,
)
from core.resume.schema import JDRequirements, ResumeData

logger = logging.getLogger(__name__)

_RESULT_KEYS = (
    "star_deep_dives",
    "technical_follow_ups",
    "behavioral",
    "pressure_tests",
    "company_specific_tips",
    "most_likely_questions",
)


def _as_string_list(raw) -> list[str]:
    """Coerce list items to plain strings; {"question"/"tip": ...} objects unwrap."""
    if not isinstance(raw, list):
        return []
    items = []
    for it in raw:
        if isinstance(it, str) and it.strip():
            items.append(it.strip())
        elif isinstance(it, dict):
            text = it.get("question") or it.get("tip") or it.get("text") or ""
            if isinstance(text, str) and text.strip():
                items.append(text.strip())
    return items


def _as_question_list(raw) -> list[dict]:
    """Coerce list items to {"question": ...} dicts; plain strings get wrapped."""
    if not isinstance(raw, list):
        return []
    items = []
    for it in raw:
        if isinstance(it, dict):
            q = it.get("question")
            if isinstance(q, str) and q.strip():
                items.append(it)
        elif isinstance(it, str) and it.strip():
            items.append({"question": it.strip()})
    return items

SYSTEM_PROMPT = (
    "You are an experienced technical interviewer. You generate realistic, "
    "targeted interview questions from a candidate's resume and, when "
    "available, the job description.\n\n" + UNTRUSTED_NOTE
)

QUESTIONS_PROMPT = """Generate interview questions based on the candidate's resume and job description below.

{language_instruction}

## Resume
{resume_text}

## Job Description
{jd_text}

{jd_instruction}

Generate questions in four categories:

1. **star_deep_dives** (3-5 questions): For each significant experience, ask detailed STAR follow-ups.
   Format: {"question": "...", "targets_entry": "company or project name", "dimension": "situation|task|action|result"}

2. **technical_follow_ups** (4-6 questions): For each major technology mentioned, generate a common interview question.
   Format: {"question": "...", "technology": "tech name", "topic": "specific concept"}

3. **behavioral** (3-4 questions): Infer soft skills from experience patterns and generate situational questions.
   Format: {"question": "...", "skill_targeted": "skill name", "scenario": "..."}

4. **pressure_tests** (2-3 questions): Challenge the candidate's most impressive claims to verify depth.
   Format: {"question": "...", "targets_claim": "...", "challenge_angle": "..."}

Also provide:
- company_specific_tips: {company_tips_instruction}
- most_likely_questions: top 3 questions you would ask if you were the interviewer

Output JSON:
{
  "star_deep_dives": [...],
  "technical_follow_ups": [...],
  "behavioral": [...],
  "pressure_tests": [...],
  "company_specific_tips": [...],
  "most_likely_questions": [...]
}

Output ONLY valid JSON:"""


class InterviewQuestionGenerator:
    """Generate targeted interview questions from resume content."""

    def __init__(self, llm_client=None):
        self._llm = llm_client

    @property
    def llm(self):
        if self._llm is None:
            self._llm = get_llm_client_from_settings()
        return self._llm

    async def generate(
        self,
        resume: ResumeData,
        jd: JDRequirements | None = None,
    ) -> dict:
        """Generate comprehensive interview questions, matching resume language.

        Raises RuntimeError when generation fails (no silent empty-shell result).
        """
        resume_text = self._resume_to_text(resume)[:5000]
        lang = detect_language(resume)
        has_company = bool(jd is not None and jd.company.strip())

        lang_instruction = (
            "IMPORTANT: The resume is in Chinese. Generate ALL questions and tips in Chinese (Simplified). "
            "Questions should reflect what Chinese domestic companies (互联网大厂/国企/外企 in China) typically ask "
            "for this position, in Chinese language."
            if lang == "zh"
            else "Generate ALL questions in English."
        )

        if jd is not None:
            jd_text = wrap_untrusted(self._jd_to_text(jd)[:3000], "JOB_DESCRIPTION")
            jd_instruction = (
                "A job description is provided above. Anchor technical_follow_ups and "
                "pressure_tests in its stated requirements, and prioritize experiences "
                "most relevant to the target position."
            )
        else:
            jd_text = "No job description provided."
            jd_instruction = (
                "No job description is available — base all questions on the resume alone."
            )

        company_tips_instruction = (
            f"2-3 interview preparation tips specific to the company \"{jd.company.strip()}\" "
            "(its interview style, typical process, and focus areas)"
            if has_company
            else "an empty array [] — the company is unknown, do NOT invent tips"
        )

        prompt = render_prompt(
            QUESTIONS_PROMPT,
            language_instruction=lang_instruction,
            resume_text=wrap_untrusted(resume_text, "RESUME"),
            jd_text=jd_text,
            jd_instruction=jd_instruction,
            company_tips_instruction=company_tips_instruction,
        )

        try:
            response = await self.llm.messages.create(
                messages=[{"role": "user", "content": prompt}],
                system=SYSTEM_PROMPT,
                max_tokens=4096,
                temperature=0.4,
                expect_json=True,
            )
            data = parse_json_response(response)
        except Exception as e:
            logger.warning("Interview question generation failed: %s", e)
            raise RuntimeError(f"面试问题生成失败:{e}") from e

        if not isinstance(data, dict):
            logger.warning(
                "Interview question generation returned %s instead of a JSON object",
                type(data).__name__,
            )
            raise RuntimeError("面试问题生成失败:LLM 未返回 JSON 对象")

        for key in _RESULT_KEYS:
            data.setdefault(key, [])
        if not has_company:
            # No company info — never fabricate company-specific tips.
            data["company_specific_tips"] = []

        # Normalize shapes — the LLM occasionally wraps plain-string lists in
        # {"question": ...} objects (and vice versa), which crashes the UI.
        for key in ("most_likely_questions", "company_specific_tips"):
            data[key] = _as_string_list(data.get(key))
        for key in ("star_deep_dives", "technical_follow_ups", "behavioral", "pressure_tests"):
            data[key] = _as_question_list(data.get(key))

        logger.debug(
            "Generated interview questions: %s",
            {k: len(data[k]) for k in _RESULT_KEYS if isinstance(data[k], list)},
        )
        return data

    def _resume_to_text(self, resume: ResumeData) -> str:
        parts = []
        for w in resume.work_experience:
            parts.append(f"{w.position} @ {w.company}: {'; '.join(w.bullets)}")
        for p in resume.project_experience:
            parts.append(f"{p.name}: {'; '.join(p.bullets)}")
        if resume.skills:
            parts.append("Skills: " + ", ".join(s.name for s in resume.skills))
        return "\n".join(parts)

    def _jd_to_text(self, jd: JDRequirements) -> str:
        """Render the structured JD (position, company, requirements) for the prompt."""
        parts = []
        if jd.position_title:
            parts.append(f"Position: {jd.position_title}")
        if jd.company:
            parts.append(f"Company: {jd.company}")
        if jd.hard_requirements:
            parts.append("Hard requirements:")
            parts.extend(f"- {r.criterion}" for r in jd.hard_requirements if r.criterion)
        if jd.nice_to_have:
            parts.append("Nice to have:")
            parts.extend(f"- {r.criterion}" for r in jd.nice_to_have if r.criterion)
        if jd.raw_text:
            parts.append("Full JD text:")
            parts.append(jd.raw_text[:2000])
        return "\n".join(parts)
