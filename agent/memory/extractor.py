"""MemoryExtractor — LLM-based structured fact extraction from conversation turns."""

import json
import logging

from core.llm import get_llm_client_from_settings

from agent.memory.models import Memory, MemoryType
from core.config import settings

logger = logging.getLogger(__name__)

EXTRACTION_PROMPT = """You are a memory extraction system. Extract structured facts from the conversation below.

Output a JSON array of facts. Each fact has:
- type: "user_profile" | "preference" | "session" | "feedback"
- key: short label for this fact
- value: the fact content
- confidence: 0.0 to 1.0 (how certain you are)

Rules:
- user_profile: concrete facts about the user (skills, education, work history, job target, etc.)
- preference: user's expressed preferences (style, format, industry, approach)
- session: temporary context for the current conversation (current resume being edited, recent JD, etc.)
- feedback: user's reactions to suggestions (accepted/rejected, preferred style, etc.)
- Only extract NEW facts that haven't been stated before
- Don't make up facts — only extract what the user actually said
- If the user corrects a previous fact, extract the correction with high confidence

Conversation:
{conversation}

Output ONLY the JSON array, no other text:"""


class MemoryExtractor:
    """Extracts structured memory facts from conversation turns using LLM."""

    def __init__(self, llm_client=None):
        self._client = llm_client

    @property
    def client(self):
        if self._client is None:
            self._client = get_llm_client_from_settings()
        return self._client

    async def extract(
        self,
        user_message: str,
        agent_response: str,
        existing_memories: list[Memory] | None = None,
    ) -> list[Memory]:
        """Extract candidate memories from a conversation turn."""
        conversation = f"User: {user_message}\nAssistant: {agent_response}"

        try:
            response = self.client.messages.create(
                model=settings.llm_model,
                max_tokens=1024,
                temperature=0.0,
                messages=[{
                    "role": "user",
                    "content": EXTRACTION_PROMPT.format(conversation=conversation),
                }],
            )

            content = response.content[0].text
            facts = json.loads(content)
            return [
                Memory(
                    type=MemoryType(f["type"]),
                    key=f["key"],
                    value=f["value"],
                    confidence=f.get("confidence", 1.0),
                )
                for f in facts
                if isinstance(f, dict) and "type" in f and "key" in f and "value" in f
            ]
        except Exception as e:
            logger.warning(f"Memory extraction failed: {e}")
            return []
