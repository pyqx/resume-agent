"""InterviewQuestionGenerator — generate targeted questions from resume + JD."""

import json
import logging

from core.llm import get_llm_client_from_settings

from core.config import settings
from core.resume.schema import ResumeData, JDRequirements

logger = logging.getLogger(__name__)

QUESTIONS_PROMPT = """You are an experienced technical interviewer. Generate interview questions based on the candidate's resume and job description.

## Resume
{resume_text}

## Job Description
{jd_text}

Generate questions in four categories:

1. **star_deep_dives** (3-5 questions): For each significant experience, ask detailed STAR follow-ups.
   Format: {{"question": "...", "targets_entry": "company or project name", "dimension": "situation|task|action|result"}}

2. **technical_follow_ups** (4-6 questions): For each major technology mentioned, generate a common interview question.
   Format: {{"question": "...", "technology": "tech name", "topic": "specific concept"}}

3. **behavioral** (3-4 questions): Infer soft skills from experience patterns and generate situational questions.
   Format: {{"question": "...", "skill_targeted": "skill name", "scenario": "..."}}

4. **pressure_tests** (2-3 questions): Challenge the candidate's most impressive claims to verify depth.
   Format: {{"question": "...", "targets_claim": "...", "challenge_angle": "..."}}

Also provide:
- company_specific_tips: 2-3 interview preparation tips if the company name is known
- most_likely_questions: top 3 questions you would ask if you were the interviewer

Output JSON:
{{
  "star_deep_dives": [...],
  "technical_follow_ups": [...],
  "behavioral": [...],
  "pressure_tests": [...],
  "company_specific_tips": [...],
  "most_likely_questions": [...]
}}

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
        """Generate comprehensive interview questions."""
        resume_text = self._resume_to_text(resume)
        jd_text = jd.raw_text if jd else "No job description provided."

        try:
            response = self.llm.messages.create(
                model=settings.llm_model,
                max_tokens=4096,
                temperature=0.4,
                messages=[{
                    "role": "user",
                    "content": QUESTIONS_PROMPT.format(
                        resume_text=resume_text[:5000],
                        jd_text=jd_text[:3000],
                    ),
                }],
            )

            content = self._extract_text(response)
            return json.loads(self._clean_json(content))

        except Exception as e:
            logger.warning(f"Question generation failed: {e}")
            return {
                "star_deep_dives": [],
                "technical_follow_ups": [],
                "behavioral": [],
                "pressure_tests": [],
                "company_specific_tips": [],
                "most_likely_questions": [],
                "error": str(e),
            }

    def _resume_to_text(self, resume: ResumeData) -> str:
        parts = []
        for w in resume.work_experience:
            parts.append(f"{w.position} @ {w.company}: {'; '.join(w.bullets)}")
        for p in resume.project_experience:
            parts.append(f"{p.name}: {'; '.join(p.bullets)}")
        if resume.skills:
            parts.append("Skills: " + ", ".join(s.name for s in resume.skills))
        return "\n".join(parts)

    @staticmethod
    def _extract_text(response) -> str:
        for block in response.content:
            if hasattr(block, "text"):
                return block.text
        return str(response.content)

    @staticmethod
    def _clean_json(text: str) -> str:
        text = text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1])
        return text
