"""SelfIntroGenerator — generate short and long self-introduction scripts."""

import logging

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
    "You are a career coach helping a candidate prepare their "
    "self-introduction.\n\n" + UNTRUSTED_NOTE
)

INTRO_PROMPT = """Generate two versions of a self-introduction for the candidate below.

## Candidate Resume
{resume_text}

Generate two versions of a self-introduction:

1. **short_version** (about 200 Chinese characters, or about 100 English words): Suitable for "Tell me about yourself" in a phone screen. Hook + key skills + one achievement + why this role.

2. **long_version** (about 500 Chinese characters, or about 250 English words): Suitable for on-site interview opening. Hook + career arc + 2-3 key achievements with context + relevant skills + why this role/company.

Rules:
- Lead with impact, not biography
- Quantify achievements where possible
- Match the tone to the industry (tech = direct, consulting = structured, creative = engaging)
- End with a bridge to "why I'm interested in this role"
- {language_preference}

Output JSON:
{
  "short_version": "text",
  "short_duration_seconds": 0,
  "long_version": "text",
  "long_duration_seconds": 0,
  "key_messages": ["message 1", "message 2", "message 3"],
  "delivery_tips": ["tip 1", "tip 2"]
}

Output ONLY valid JSON:"""

_ZH_ALIASES = {"zh", "zh-cn", "zh_cn", "zh-hans", "chinese", "cn", "中文", "chinese (simplified)"}
_EN_ALIASES = {"en", "en-us", "en_us", "english"}


def _resolve_language(resume: ResumeData, target_language: str) -> str:
    """Resolve output language: explicit target overrides detection; "auto"/empty detects."""
    normalized = (target_language or "").strip().lower()
    if normalized in _ZH_ALIASES:
        return "zh"
    if normalized in _EN_ALIASES:
        return "en"
    if normalized not in ("", "auto"):
        logger.warning(
            "Unrecognized target_language %r; falling back to auto-detection",
            target_language,
        )
    return detect_language(resume)


class SelfIntroGenerator:
    """Generate short (~200 chars) and long (~500 chars) self-introduction scripts."""

    def __init__(self, llm_client=None):
        self._llm = llm_client

    @property
    def llm(self):
        if self._llm is None:
            self._llm = get_llm_client_from_settings()
        return self._llm

    async def generate(self, resume: ResumeData, target_language: str = "auto") -> dict:
        """Generate short and long self-introduction scripts.

        target_language: "zh" / "en" force the output language; "auto" (or
        empty) detects it from the resume content.

        Raises RuntimeError when generation fails.
        """
        resume_text = self._resume_to_text(resume)[:4000]
        lang = _resolve_language(resume, target_language)
        lang_pref = (
            "Write in Chinese (Simplified)." if lang == "zh" else "Write in English."
        )

        prompt = render_prompt(
            INTRO_PROMPT,
            resume_text=wrap_untrusted(resume_text, "RESUME"),
            language_preference=lang_pref,
        )

        try:
            response = await self.llm.messages.create(
                messages=[{"role": "user", "content": prompt}],
                system=SYSTEM_PROMPT,
                max_tokens=2048,
                temperature=0.4,
                expect_json=True,
            )
            data = parse_json_response(response)
        except Exception as e:
            logger.warning("Self-intro generation failed: %s", e)
            raise RuntimeError(f"自我介绍生成失败:{e}") from e

        if not isinstance(data, dict):
            logger.warning(
                "Self-intro generation returned %s instead of a JSON object",
                type(data).__name__,
            )
            raise RuntimeError("自我介绍生成失败:LLM 未返回 JSON 对象")

        data.setdefault("short_version", "")
        data.setdefault("long_version", "")
        data.setdefault("short_duration_seconds", 0)
        data.setdefault("long_duration_seconds", 0)
        data.setdefault("key_messages", [])
        data.setdefault("delivery_tips", [])

        logger.debug(
            "Generated self-intro (lang=%s): short=%d chars, long=%d chars",
            lang, len(str(data["short_version"])), len(str(data["long_version"])),
        )
        return data

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
