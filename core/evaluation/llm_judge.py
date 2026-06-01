"""LLMJudge — LLM-as-Judge for semantic quality evaluation of resume content."""

import json
import logging

from core.llm import get_llm_client_from_settings

from core.config import settings
from core.resume.schema import ResumeData

logger = logging.getLogger(__name__)

JUDGE_PROMPT = """You are a resume quality evaluator. Score the following resume across five dimensions on a 1-10 scale.

Resume Content:
{resume_text}

Score each dimension:
1. **star_completeness** (1-10): Do experience entries include Situation, Task, Action, and Result? Are the four elements clearly present?
2. **quantitative_density** (1-10): How many entries include specific numbers, percentages, or measurable outcomes?
3. **terminology_accuracy** (1-10): Are technical terms spelled correctly? Are industry terms used appropriately?
4. **conciseness** (1-10): Is the writing tight and impactful? No filler words or redundant statements?
5. **narrative_coherence** (1-10): Does the resume tell a clear career story? Is there a logical progression across experiences?

Also provide:
- 2-3 specific, actionable suggestions to improve the lowest-scoring dimensions
- An overall score (weighted: STAR*0.35 + Quant*0.30 + Term*0.15 + Concise*0.10 + Coherence*0.10)

Output JSON:
{{
  "dimensions": {{
    "star_completeness": 0,
    "quantitative_density": 0,
    "terminology_accuracy": 0,
    "conciseness": 0,
    "narrative_coherence": 0
  }},
  "overall_score": 0.0,
  "suggestions": ["suggestion 1", "suggestion 2", "suggestion 3"],
  "strengths": ["strength 1", "strength 2"]
}}

Output ONLY valid JSON:"""


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
        """Evaluate resume quality across five dimensions."""
        resume_text = self._resume_to_text(resume)

        try:
            response = self.llm.messages.create(
                model=settings.llm_model,
                max_tokens=2048,
                temperature=0.0,
                messages=[{
                    "role": "user",
                    "content": JUDGE_PROMPT.format(
                    resume_text=resume_text[:8000].replace("{", "{{").replace("}", "}}")
                ),
                }],
            )

            content = self._extract_text(response)
            result = json.loads(self._clean_json(content))
            return result

        except Exception as e:
            logger.warning(f"LLM judge evaluation failed: {e}")
            return {
                "dimensions": {
                    "star_completeness": 5,
                    "quantitative_density": 5,
                    "terminology_accuracy": 5,
                    "conciseness": 5,
                    "narrative_coherence": 5,
                },
                "overall_score": 5.0,
                "suggestions": ["LLM evaluation unavailable. Review resume manually."],
                "strengths": [],
                "error": str(e),
            }

    def _resume_to_text(self, resume: ResumeData) -> str:
        """Convert ResumeData to a flat text representation for evaluation."""
        parts = []

        if resume.personal_info.summary:
            parts.append(f"Summary: {resume.personal_info.summary}")

        for edu in resume.education:
            parts.append(f"Education: {edu.degree} {edu.major} @ {edu.school}")

        for work in resume.work_experience:
            parts.append(f"\nWork: {work.position} @ {work.company}")
            for bullet in work.bullets:
                parts.append(f"  - {bullet}")
            if work.description:
                parts.append(f"  {work.description}")

        for proj in resume.project_experience:
            parts.append(f"\nProject: {proj.name} ({proj.role})")
            parts.append(f"  Tech: {', '.join(proj.technologies)}")
            for bullet in proj.bullets:
                parts.append(f"  - {bullet}")

        if resume.skills:
            skills_text = ", ".join(f"{s.name}({s.years}y)" for s in resume.skills)
            parts.append(f"\nSkills: {skills_text}")

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
