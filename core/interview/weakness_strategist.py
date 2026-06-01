"""WeaknessStrategist — detect resume vulnerabilities and generate honest-but-optimized narratives."""

import logging

from core.llm import get_llm_client_from_settings

from core.config import settings
from core.resume.schema import ResumeData

logger = logging.getLogger(__name__)

WEAKNESS_PROMPT = """You are a career strategist helping a candidate prepare for tough interview questions about resume weaknesses.

## Resume
{resume_text}

## Detected Potential Concerns
{detected_concerns}

For each concern, provide:
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
  {{
    "concern": "...",
    "risk_level": "high|medium|low",
    "honest_narrative": "...",
    "sample_response": "...",
    "resume_fix": "..."
  }}
]

Output ONLY valid JSON array:"""


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
        """Analyze resume for potential interview vulnerabilities."""
        concerns = self._detect_concerns(resume)
        if not concerns:
            return []

        resume_text = self._resume_to_text(resume)

        try:
            response = self.llm.messages.create(
                model=settings.llm_model,
                max_tokens=3072,
                temperature=0.3,
                messages=[{
                    "role": "user",
                    "content": WEAKNESS_PROMPT.format(
                        resume_text=resume_text[:4000].replace("{", "{{").replace("}", "}}"),
                        detected_concerns="\n".join(f"- {c}" for c in concerns).replace("{", "{{").replace("}", "}}"),
                    ),
                }],
            )

            import json
            content = self._extract_text(response)
            return json.loads(self._clean_json(content))

        except Exception as e:
            logger.warning(f"Weakness analysis failed: {e}")
            return [{"concern": c, "risk_level": "medium", "honest_narrative": "", "sample_response": "", "error": str(e)} for c in concerns]

    def _detect_concerns(self, resume: ResumeData) -> list[str]:
        """Rule-based detection of resume concerns."""
        from datetime import date, timedelta
        today = date.today()
        concerns = []

        works = sorted(
            [w for w in resume.work_experience if w.start_date],
            key=lambda w: w.start_date or date.min,
        )

        # Employment gap check
        for i in range(len(works) - 1):
            if works[i].end_date and works[i+1].start_date:
                gap = (works[i+1].start_date - works[i].end_date).days
                if gap > 90:
                    concerns.append(f"{gap}天职业空窗期 ({works[i].company} → {works[i+1].company})")

        # Job hopping
        if len(works) >= 3:
            tenures = []
            for w in works:
                if w.start_date:
                    end = w.end_date or today
                    tenure_days = (end - w.start_date).days
                    tenures.append(tenure_days)
            if tenures:
                avg_tenure = sum(tenures) / len(tenures)
                if avg_tenure < 547:  # < 1.5 years
                    concerns.append(f"平均在岗时间不足1.5年 ({avg_tenure/365:.1f}年)")

        # Education not in top tier
        has_education = any(resume.education)
        has_experience = any(resume.work_experience)
        if not has_education and has_experience:
            concerns.append("简历中未体现教育经历")

        return concerns

    def _resume_to_text(self, resume: ResumeData) -> str:
        parts = []
        for w in resume.work_experience:
            start = str(w.start_date) if w.start_date else "?"
            end = "至今" if w.is_current else str(w.end_date) if w.end_date else "?"
            parts.append(f"{start}→{end}: {w.position} @ {w.company}")
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
