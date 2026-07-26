"""JDParser — structured extraction of job description requirements."""

import logging

from core.llm import (
    UNTRUSTED_NOTE,
    get_llm_client_from_settings,
    parse_json_response,
    render_prompt,
    wrap_untrusted,
)
from core.resume.schema import JDRequirements, JDSignal, Requirement, RequirementType

logger = logging.getLogger(__name__)

# JD text longer than this is truncated before being sent to the LLM.
MAX_JD_CHARS = 8000

JD_SYSTEM_PROMPT = (
    "You are a job description analyzer. Extract structured requirements "
    "from the job description supplied by the user. " + UNTRUSTED_NOTE
)

JD_EXTRACTION_PROMPT = """Extract structured requirements from the JD text below.

Output a JSON object with:
{"position_title": "", "company": "", "hard_requirements": [{"criterion": "", "type": "must_have"}], "nice_to_have": [{"criterion": "", "type": "plus"}], "soft_signals": [{"phrase": "", "interpretation": "", "risk_level": "info|warning|caution"}], "keyword_frequency": {"keyword": count}}

Rules:
- hard_requirements: explicit must-haves (years of experience, degree, specific technologies, certifications)
- nice_to_have: "bonus points", "preferred", "nice to have" items
- soft_signals: detect subtext in phrases like "fast-paced" (may mean overtime), "wear many hats" (may mean understaffed), "rockstar/ninja" (immature culture), "competitive salary" (likely below market), "unlimited PTO" (may mean no structured time off)
- keyword_frequency: count key technical/business terms

JD Text:
{jd_text}

Output ONLY valid JSON:"""


class JDParser:
    """Parse job description text into structured JDRequirements."""

    def __init__(self, llm_client=None):
        self._llm = llm_client

    @property
    def llm(self):
        if self._llm is None:
            self._llm = get_llm_client_from_settings()
        return self._llm

    async def parse(self, jd_text: str) -> JDRequirements:
        """Parse JD text into structured requirements.

        Raises RuntimeError when the LLM call or JSON parsing fails, so
        callers surface a real error instead of silently receiving zero
        requirements (which rendered as "0% match" with no explanation).
        """
        text = jd_text[:MAX_JD_CHARS]
        if len(jd_text) > MAX_JD_CHARS:
            logger.warning(
                "JD text truncated from %d to %d chars before LLM parsing",
                len(jd_text), MAX_JD_CHARS,
            )

        prompt = render_prompt(
            JD_EXTRACTION_PROMPT,
            jd_text=wrap_untrusted(text, "job_description"),
        )

        try:
            # 4096: a long JD's structured output (requirements + signals +
            # Chinese keyword table) can exceed 2048 tokens and truncate.
            response = await self.llm.messages.create(
                max_tokens=4096,
                temperature=0.0,
                expect_json=True,
                system=JD_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )
            data = parse_json_response(response)
        except Exception as e:
            logger.error("JD parsing failed: %s", e)
            raise RuntimeError(f"JD 解析失败: {e}") from e

        if not isinstance(data, dict):
            raise RuntimeError(
                f"JD 解析失败: LLM 返回的不是 JSON 对象 ({type(data).__name__})"
            )

        result = JDRequirements(
            raw_text=jd_text,
            position_title=str(data.get("position_title") or ""),
            company=str(data.get("company") or ""),
            hard_requirements=self._build_requirements(
                data.get("hard_requirements"), RequirementType.MUST_HAVE
            ),
            nice_to_have=self._build_requirements(
                data.get("nice_to_have"), RequirementType.PLUS
            ),
            soft_signals=self._build_signals(data.get("soft_signals")),
            keyword_frequency=self._build_keyword_frequency(
                data.get("keyword_frequency")
            ),
        )
        logger.info(
            "JD parsed: title=%r hard=%d nice=%d signals=%d keywords=%d",
            result.position_title, len(result.hard_requirements),
            len(result.nice_to_have), len(result.soft_signals),
            len(result.keyword_frequency),
        )
        return result

    @staticmethod
    def _build_requirements(raw, req_type: RequirementType) -> list[Requirement]:
        """Build Requirement entries from LLM output.

        Models sometimes emit "requirement" instead of "criterion" (or bare
        strings) — accept both; entries with an empty criterion are skipped.
        """
        requirements: list[Requirement] = []
        for r in raw or []:
            if isinstance(r, dict):
                criterion = str(r.get("criterion") or r.get("requirement") or "").strip()
            elif isinstance(r, str):
                criterion = r.strip()
            else:
                continue
            if not criterion:
                continue
            requirements.append(Requirement(criterion=criterion, type=req_type))
        return requirements

    @staticmethod
    def _build_signals(raw) -> list[JDSignal]:
        signals: list[JDSignal] = []
        for s in raw or []:
            if not isinstance(s, dict):
                continue
            phrase = str(s.get("phrase") or "")
            interpretation = str(s.get("interpretation") or "")
            if not phrase and not interpretation:
                continue
            signals.append(JDSignal(
                phrase=phrase,
                interpretation=interpretation,
                risk_level=str(s.get("risk_level") or "info"),
            ))
        return signals

    @staticmethod
    def _build_keyword_frequency(raw) -> dict[str, int]:
        if not isinstance(raw, dict):
            return {}
        freq: dict[str, int] = {}
        for k, v in raw.items():
            key = str(k).strip()
            if not key:
                continue
            try:
                freq[key] = int(v)
            except (TypeError, ValueError):
                freq[key] = 1
        return freq
