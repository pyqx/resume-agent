"""SelfIntroGenerator — generate 1-minute and 3-minute self-introduction scripts."""

import json
import logging

from core.llm import get_llm_client_from_settings

from core.config import settings
from core.resume.schema import ResumeData

logger = logging.getLogger(__name__)

INTRO_PROMPT = """You are a career coach helping a candidate prepare their self-introduction.

## Candidate Resume
{resume_text}

Generate two versions of a self-introduction:

1. **short_version** (~200 Chinese characters or ~100 English words): Suitable for "Tell me about yourself" in a phone screen. Hook + key skills + one achievement + why this role.

2. **long_version** (~500 Chinese characters or ~250 English words): Suitable for on-site interview opening. Hook + career arc + 2-3 key achievements with context + relevant skills + why this role/company.

Rules:
- Lead with impact, not biography
- Quantify achievements where possible
- Match the tone to the industry (tech = direct, consulting = structured, creative = engaging)
- End with a bridge to "why I'm interested in this role"
- {language_preference}

Output JSON:
{{
  "short_version": "text",
  "short_duration_seconds": 0,
  "long_version": "text",
  "long_duration_seconds": 0,
  "key_messages": ["message 1", "message 2", "message 3"],
  "delivery_tips": ["tip 1", "tip 2"]
}}

Output ONLY valid JSON:"""


class SelfIntroGenerator:
    """Generate self-introduction scripts calibrated to duration targets."""

    def __init__(self, llm_client=None):
        self._llm = llm_client

    @property
    def llm(self):
        if self._llm is None:
            self._llm = get_llm_client_from_settings()
        return self._llm

    async def generate(self, resume: ResumeData, target_language: str = "auto") -> dict:
        """Generate 1-min and 3-min self-introduction scripts."""
        resume_text = self._resume_to_text(resume)

        lang_pref = "Write in English." if self._is_english(resume_text) else "Write in Chinese."

        try:
            response = self.llm.messages.create(
                model=settings.llm_model,
                max_tokens=2048,
                temperature=0.4,
                messages=[{
                    "role": "user",
                    "content": INTRO_PROMPT.format(
                        resume_text=resume_text[:4000],
                        language_preference=lang_pref,
                    ),
                }],
            )

            content = self._extract_text(response)
            return json.loads(self._clean_json(content))

        except Exception as e:
            logger.warning(f"Intro generation failed: {e}")
            return {
                "short_version": "Self-introduction generation unavailable.",
                "long_version": "Self-introduction generation unavailable.",
                "key_messages": [],
                "delivery_tips": [],
                "error": str(e),
            }

    def _resume_to_text(self, resume: ResumeData) -> str:
        parts = [f"Name: {resume.personal_info.full_name}"]
        parts.append(f"Target: {resume.target_position or 'Not specified'}")
        for w in resume.work_experience:
            parts.append(f"{w.position} @ {w.company}: {'; '.join(w.bullets)}")
        for p in resume.project_experience:
            parts.append(f"Project {p.name}: {'; '.join(p.bullets)}")
        if resume.skills:
            parts.append("Skills: " + ", ".join(s.name for s in resume.skills[:8]))
        return "\n".join(parts)

    @staticmethod
    def _is_english(text: str) -> bool:
        ascii_chars = sum(1 for c in text if ord(c) < 128)
        return ascii_chars / max(len(text), 1) > 0.7

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
