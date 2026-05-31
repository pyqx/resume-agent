"""ResumeEntryComposer — generate STAR-formatted resume entries from contribution ideas."""

import json
import logging

from core.llm import get_llm_client_from_settings

from core.config import settings

logger = logging.getLogger(__name__)

COMPOSE_PROMPT = """You are a senior resume writer specializing in technical roles. Transform the following open-source contribution plan into a professional resume entry.

## Contribution Plan
{suggestion}

## Repository Context
{repo_context}

Write a STAR-format resume entry with these sections:
- **background**: One sentence setting the context (what the project is and why this matters)
- **role**: Your role (e.g., "Independent Contributor", "Core Developer")
- **technical_approach**: 3-4 bullet points describing the technical work performed
- **outcomes**: 2-3 bullet points with quantified or specific results

Rules:
- Use strong action verbs (designed, implemented, optimized, integrated)
- Include specific technology names and technical concepts
- Make results concrete — if user hasn't completed the work yet, use "Expected outcomes:" prefix
- Keep it to 5-8 bullet points total
- Match the tone of a professional senior-level resume

Output JSON:
{{
  "entry_title": "Project: Contribution Title",
  "background": "...",
  "role": "...",
  "technical_approach": ["bullet 1", "bullet 2", "bullet 3"],
  "outcomes": ["outcome 1", "outcome 2"],
  "technologies_mentioned": ["tech 1", "tech 2"],
  "is_planned": true
}}

Output ONLY valid JSON:"""


class ResumeEntryComposer:
    """Compose STAR-format resume entries from GitHub contribution plans."""

    def __init__(self, llm_client=None):
        self._llm = llm_client

    @property
    def llm(self):
        if self._llm is None:
            self._llm = get_llm_client_from_settings()
        return self._llm

    async def compose(self, suggestion: dict, repo_context: dict) -> dict:
        """Compose a resume entry from a selected contribution suggestion."""
        try:
            response = self.llm.messages.create(
                model=settings.llm_model,
                max_tokens=2048,
                temperature=0.3,
                messages=[{
                    "role": "user",
                    "content": COMPOSE_PROMPT.format(
                        suggestion=json.dumps(suggestion, indent=2, default=str)[:3000],
                        repo_context=json.dumps(repo_context, indent=2, default=str)[:2000],
                    ),
                }],
            )

            content = self._extract_text(response)
            return json.loads(self._clean_json(content))

        except Exception as e:
            logger.warning(f"Resume entry composition failed: {e}")
            return {
                "entry_title": "Contribution",
                "background": "",
                "role": "Contributor",
                "technical_approach": [],
                "outcomes": [],
                "technologies_mentioned": [],
                "is_planned": True,
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
