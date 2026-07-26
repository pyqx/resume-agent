"""MemoryExtractor — LLM-based structured fact extraction from conversation turns."""

import logging

from core.llm import (
    UNTRUSTED_NOTE,
    get_llm_client_from_settings,
    parse_json_response,
    render_prompt,
    wrap_untrusted,
)

from agent.memory.models import Memory, MemoryType

logger = logging.getLogger(__name__)

# Longest fact value we persist; anything longer is truncated.
MAX_VALUE_LENGTH = 500
# How many known facts to show the model so "only NEW facts" is enforceable.
MAX_EXISTING_FACTS = 30

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
- Only extract NEW facts that are not already in the known facts list below; never repeat a known fact
- If the user corrects a known fact, extract the correction with high confidence
- Don't make up facts — only extract what the user actually said
- If there are no new facts, output an empty array: []

{untrusted_note}

Known facts (already stored — do NOT re-extract these):
{existing_facts}

{conversation}

Output ONLY the JSON array, no other text:"""


class MemoryExtractor:
    """Extracts structured memory facts from conversation turns using an LLM."""

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
        """Extract candidate memories from a conversation turn.

        ``existing_memories`` are injected into the prompt so the model can
        skip already-known facts and flag corrections.
        """
        conversation = f"User: {user_message}\nAssistant: {agent_response}"
        existing_facts = "\n".join(
            f"- {m.key}: {m.value}"
            for m in (existing_memories or [])[:MAX_EXISTING_FACTS]
        ) or "(none)"

        prompt = render_prompt(
            EXTRACTION_PROMPT,
            untrusted_note=UNTRUSTED_NOTE,
            existing_facts=existing_facts,
            conversation=wrap_untrusted(conversation, "conversation"),
        )

        try:
            response = await self.client.messages.create(
                max_tokens=1024,
                temperature=0.0,
                messages=[{"role": "user", "content": prompt}],
                expect_json=True,
            )
            facts = parse_json_response(response)
        except Exception as e:
            logger.warning("Memory extraction failed: %s", e)
            return []

        if isinstance(facts, dict):
            # Some models wrap the array in an object despite instructions.
            facts = facts.get("facts", facts.get("memories", []))
        if not isinstance(facts, list):
            logger.warning(
                "Memory extraction returned non-list JSON (%s); ignoring",
                type(facts).__name__,
            )
            return []

        memories: list[Memory] = []
        for fact in facts:
            memory = self._fact_to_memory(fact)
            if memory is not None:
                memories.append(memory)
        return memories

    async def extract_and_store(
        self,
        conversation: list[dict],
        user_id: str,
        session_id: str,
        store,
    ) -> int:
        """Extract facts from a conversation and persist them via ``store``.

        Returns the number of memories successfully written. Never raises —
        memory capture must not break the main agent flow.
        """
        try:
            user_message = ""
            agent_response = ""
            for msg in conversation:
                role = str(msg.get("role", ""))
                content = msg.get("content", "")
                if not isinstance(content, str):
                    continue
                if role == "user":
                    user_message = content
                elif role in ("assistant", "agent"):
                    agent_response = content
            if not user_message and not agent_response:
                return 0

            existing = await store.get_all_for_user(user_id=user_id)
            facts = await self.extract(
                user_message, agent_response, existing_memories=existing
            )

            stored = 0
            for memory in facts:
                memory.user_id = user_id
                memory.metadata = {**(memory.metadata or {}), "session_id": session_id}
                try:
                    await store.add(memory)
                    stored += 1
                except Exception as e:
                    logger.warning("Failed to store memory %r: %s", memory.key, e)
            if stored:
                logger.info("Stored %d new memories for user %s", stored, user_id)
            return stored
        except Exception as e:
            logger.warning("extract_and_store failed: %s", e)
            return 0

    def _fact_to_memory(self, fact) -> Memory | None:
        """Validate a single raw fact. Invalid facts are logged and skipped
        individually — one bad item must not discard the whole batch."""
        if not isinstance(fact, dict):
            logger.warning("Skipping non-dict fact: %r", fact)
            return None

        try:
            mem_type = MemoryType(str(fact.get("type", "")).strip().lower())
        except ValueError:
            logger.warning("Skipping fact with invalid type: %r", fact.get("type"))
            return None

        # Normalize keys: strip + lower + whitespace -> underscores.
        key = "_".join(str(fact.get("key", "")).strip().lower().split())
        value = str(fact.get("value", "")).strip()[:MAX_VALUE_LENGTH]
        if not key or not value:
            logger.warning("Skipping fact with empty key/value: %r", fact)
            return None

        try:
            confidence = float(fact.get("confidence", 1.0))
        except (TypeError, ValueError):
            logger.warning(
                "Fact %r has invalid confidence %r; defaulting to 1.0",
                key, fact.get("confidence"),
            )
            confidence = 1.0
        confidence = max(0.0, min(1.0, confidence))

        return Memory(type=mem_type, key=key, value=value, confidence=confidence)
