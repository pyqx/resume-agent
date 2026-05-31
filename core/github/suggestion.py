"""SuggestionGenerator — generate personalized improvement directions for a repo."""

import json
import logging

from core.llm import get_llm_client_from_settings

from core.config import settings

logger = logging.getLogger(__name__)

SUGGESTION_PROMPT = """You are a senior software engineer helping a developer find meaningful open-source contribution opportunities.

## Repository Analysis
{repo_analysis}

## Developer Profile
- Career direction: {career_direction}
- Skill level: {skill_level}

Generate 3-5 improvement directions for this repository. Each direction should be:

1. **Aligned with the developer's career direction** — prioritize changes that use skills relevant to their target role
2. **Feasible** — based on the repo's actual tech stack and codebase
3. **Impactful** — valuable to the project and impressive on a resume

For each direction, provide:
- title: short name
- what_to_do: concrete description of the change
- why_valuable: why this is a worthwhile contribution
- technical_challenges: what makes this non-trivial
- estimated_hours: rough time estimate
- difficulty: "beginner" | "intermediate" | "advanced"
- prerequisite_knowledge: what to learn first
- resume_impact: which job requirements this addresses
- recommended: true/false (mark false if you would NOT recommend this)

Also include:
- learning_path: 2-3 resources (docs, papers, tutorials) for necessary prerequisite knowledge
- avoid: 1-2 directions to AVOID and why

Output JSON:
{{
  "suggestions": [...],
  "learning_path": ["resource 1", "resource 2"],
  "avoid": [{{"direction": "...", "reason": "..."}}],
  "overall_assessment": "brief assessment of this repo as a resume-building opportunity"
}}

Output ONLY valid JSON:"""


class SuggestionGenerator:
    """Generate personalized open-source contribution suggestions."""

    def __init__(self, llm_client=None):
        self._llm = llm_client

    @property
    def llm(self):
        if self._llm is None:
            self._llm = get_llm_client_from_settings()
        return self._llm

    async def generate(
        self,
        repo_analysis: dict,
        career_direction: str = "",
        skill_level: str = "intermediate",
    ) -> dict:
        """Generate personalized contribution suggestions."""
        try:
            analysis_text = json.dumps(repo_analysis, indent=2, default=str)[:6000]

            response = self.llm.messages.create(
                model=settings.llm_model,
                max_tokens=4096,
                temperature=0.3,
                messages=[{
                    "role": "user",
                    "content": SUGGESTION_PROMPT.format(
                        repo_analysis=analysis_text,
                        career_direction=career_direction or "general software development",
                        skill_level=skill_level,
                    ),
                }],
            )

            content = self._extract_text(response)
            return json.loads(self._clean_json(content))

        except Exception as e:
            logger.warning(f"Suggestion generation failed: {e}")
            return {
                "suggestions": [],
                "learning_path": [],
                "avoid": [],
                "overall_assessment": "Unable to generate suggestions due to an error.",
                "error": str(e),
            }

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
