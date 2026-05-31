"""JDParser — structured extraction of job description requirements."""

import json
import re
import logging

from core.llm import get_llm_client_from_settings

from core.config import settings
from core.resume.schema import JDRequirements, Requirement, JDSignal, RequirementType

logger = logging.getLogger(__name__)

JD_EXTRACTION_PROMPT = """You are a job description analyzer. Extract structured requirements from the JD text below.

Output a JSON object with:
{
  "position_title": "",
  "company": "",
  "hard_requirements": [{"criterion": "", "type": "must_have"}],
  "nice_to_have": [{"criterion": "", "type": "plus"}],
  "soft_signals": [{"phrase": "", "interpretation": "", "risk_level": "info|warning|caution"}],
  "keyword_frequency": {"keyword": count}
}

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
        """Parse JD text into structured requirements."""
        # Quick regex pre-extraction
        years_pattern = re.findall(r'(\d+)[\s-]*年[\s\w]*经验|(\d+)\+?\s*years?\s*(of\s*)?experience', jd_text, re.IGNORECASE)
        degree_pattern = re.findall(r'(本科|硕士|博士|大专|bachelor|master|phd|associate)', jd_text, re.IGNORECASE)

        try:
            response = self.llm.messages.create(
                model=settings.llm_model,
                max_tokens=2048,
                temperature=0.0,
                messages=[{
                    "role": "user",
                    "content": JD_EXTRACTION_PROMPT.format(jd_text=jd_text[:8000]),
                }],
            )

            content = self._extract_text(response)
            data = json.loads(self._clean_json(content))

            return JDRequirements(
                raw_text=jd_text,
                position_title=data.get("position_title", ""),
                company=data.get("company", ""),
                hard_requirements=[
                    Requirement(criterion=r["criterion"], type=RequirementType.MUST_HAVE)
                    for r in data.get("hard_requirements", [])
                ],
                nice_to_have=[
                    Requirement(criterion=r["criterion"], type=RequirementType.PLUS)
                    for r in data.get("nice_to_have", [])
                ],
                soft_signals=[
                    JDSignal(
                        phrase=s.get("phrase", ""),
                        interpretation=s.get("interpretation", ""),
                        risk_level=s.get("risk_level", "info"),
                    )
                    for s in data.get("soft_signals", [])
                ],
                keyword_frequency=data.get("keyword_frequency", {}),
            )
        except Exception as e:
            logger.warning(f"JD parsing failed: {e}. Using rule-based fallback.")
            return self._rule_based_parse(jd_text)

    def _rule_based_parse(self, jd_text: str) -> JDRequirements:
        """Rule-based JD parsing fallback."""
        reqs = JDRequirements(raw_text=jd_text)

        # Simple keyword extraction
        tech_keywords = re.findall(
            r'\b(Java|Python|Go|Rust|JavaScript|TypeScript|React|Vue|Angular|'
            r'Spring|Django|Flask|K8s|Kubernetes|Docker|AWS|Azure|GCP|'
            r'MySQL|PostgreSQL|MongoDB|Redis|Kafka|Elasticsearch)\b',
            jd_text, re.IGNORECASE
        )

        for kw in set(tech_keywords):
            reqs.keyword_frequency[kw] = tech_keywords.count(kw)

        return reqs

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
