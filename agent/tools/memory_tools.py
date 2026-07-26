"""Memory tools — search, read, save, and manage the Agent's memory."""

import logging

from agent.tools.base import BaseTool, ToolMetadata, ToolResult, ToolCategory, Difficulty
from agent.memory.store import MemoryStore
from agent.memory.models import Memory, MemoryType

logger = logging.getLogger(__name__)

_VALID_TYPES = ", ".join(t.value for t in MemoryType)


def _result_items(results) -> list[dict]:
    """Normalize store.search output (MemorySearchResult or Memory items)."""
    items = []
    for r in results:
        memory = getattr(r, "memory", r)
        similarity = getattr(r, "similarity", None)
        item = {
            "id": memory.id,
            "type": memory.type.value,
            "key": memory.key,
            "value": memory.value,
        }
        if similarity is not None:
            item["similarity"] = round(float(similarity), 3)
        items.append(item)
    return items


class SearchMemoryTool(BaseTool):
    def __init__(self, store: MemoryStore):
        self._store = store

    @property
    def metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="search_memory",
            category=ToolCategory.MEMORY,
            description="Search the user's memory for relevant facts",
            usage_guide="Use when you need to recall user profile, preferences, or past context",
            parameters={
                "query": "string, what to search for",
                "top_k": "integer, optional, max results (default 5, max 20)",
            },
            estimated_time=Difficulty.LIGHT,
        )

    async def execute(self, query: str = "", user_id: str = "default", top_k: int = 5, **kwargs) -> ToolResult:
        if not query:
            return ToolResult.fail("PARAM_ERROR", "query is required", is_retryable=False)
        try:
            top_k = max(1, min(int(top_k), 20))
        except (TypeError, ValueError):
            top_k = 5
        try:
            results = await self._store.search(query=query, user_id=user_id, top_k=top_k)
            return ToolResult.ok(_result_items(results))
        except Exception as e:
            logger.warning("search_memory failed: %s", e)
            return ToolResult.fail("MEMORY_SEARCH_ERROR", str(e), is_retryable=False)


class SaveMemoryTool(BaseTool):
    """The write path: lets the Agent persist important user facts."""

    def __init__(self, store: MemoryStore):
        self._store = store

    @property
    def metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="save_memory",
            category=ToolCategory.MEMORY,
            description="Save an important fact about the user to long-term memory",
            usage_guide=(
                "Use when the user states a durable fact worth remembering across "
                "sessions: target position/industry, preferences (tone, format), "
                "explicit feedback on your suggestions. Do NOT save transient "
                "chit-chat or resume content (the resume itself is already stored)."
            ),
            parameters={
                "memory_type": f"string, one of: {_VALID_TYPES}",
                "key": "string, short identifier, e.g. 'target_position'",
                "value": "string, the fact, e.g. 'Java 后端,期望杭州'",
            },
            estimated_time=Difficulty.LIGHT,
            is_idempotent=False,
        )

    async def execute(
        self,
        memory_type: str = "",
        key: str = "",
        value: str = "",
        user_id: str = "default",
        **kwargs,
    ) -> ToolResult:
        if not memory_type or not key or not value:
            return ToolResult.fail(
                "PARAM_ERROR", "memory_type, key and value are required", is_retryable=False
            )
        try:
            mtype = MemoryType(memory_type)
        except ValueError:
            return ToolResult.fail(
                "PARAM_ERROR", f"Invalid memory_type: {memory_type}. Valid: {_VALID_TYPES}",
                is_retryable=False,
            )
        try:
            memory = Memory(
                user_id=user_id,
                type=mtype,
                key=str(key).strip()[:100],
                value=str(value).strip()[:500],
            )
            saved = await self._store.add(memory)
            # add() returns the stored memory's id (may differ from memory.id
            # when the fact was merged into an existing near-duplicate).
            saved_id = saved if isinstance(saved, str) else memory.id
            return ToolResult.ok({"saved": True, "memory_id": saved_id, "key": memory.key})
        except Exception as e:
            logger.warning("save_memory failed: %s", e)
            return ToolResult.fail("MEMORY_SAVE_ERROR", str(e), is_retryable=False)


class GetUserProfileTool(BaseTool):
    def __init__(self, store: MemoryStore):
        self._store = store

    @property
    def metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="get_user_profile",
            category=ToolCategory.MEMORY,
            description="Get remembered user profile facts (background, goals)",
            usage_guide="Use when starting a new task to understand the user's background",
            estimated_time=Difficulty.LIGHT,
        )

    async def execute(self, user_id: str = "default", **kwargs) -> ToolResult:
        try:
            memories = await self._store.get_all_for_user(user_id, memory_type=MemoryType.USER_PROFILE)
            return ToolResult.ok([{
                "id": m.id, "key": m.key, "value": m.value, "confidence": m.confidence,
            } for m in memories])
        except Exception as e:
            logger.warning("get_user_profile failed: %s", e)
            return ToolResult.fail("PROFILE_ERROR", str(e), is_retryable=False)


class GetUserPreferencesTool(BaseTool):
    def __init__(self, store: MemoryStore):
        self._store = store

    @property
    def metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="get_user_preferences",
            category=ToolCategory.MEMORY,
            description="Get the user's preferences (style, format, industry)",
            usage_guide="Use when making suggestions to ensure they align with user preferences",
            estimated_time=Difficulty.LIGHT,
        )

    async def execute(self, user_id: str = "default", **kwargs) -> ToolResult:
        try:
            memories = await self._store.get_all_for_user(user_id, memory_type=MemoryType.PREFERENCE)
            return ToolResult.ok([{
                "id": m.id, "key": m.key, "value": m.value, "confidence": m.confidence,
            } for m in memories])
        except Exception as e:
            logger.warning("get_user_preferences failed: %s", e)
            return ToolResult.fail("PREFERENCES_ERROR", str(e), is_retryable=False)


class ForgetMemoryTool(BaseTool):
    def __init__(self, store: MemoryStore):
        self._store = store

    @property
    def metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="forget_memory",
            category=ToolCategory.MEMORY,
            description="Delete a specific memory (user-requested)",
            usage_guide="Use ONLY when the user explicitly asks to delete or forget something. Confirm first, then call with confirm=true.",
            parameters={
                "memory_id": "string, the memory's id (from search_memory / get_user_profile)",
                "confirm": "boolean, must be true (only after the user explicitly agreed)",
            },
            estimated_time=Difficulty.LIGHT,
            is_idempotent=True,
            requires_user_confirmation=True,
        )

    async def execute(self, memory_id: str = "", **kwargs) -> ToolResult:
        if not memory_id:
            return ToolResult.fail("PARAM_ERROR", "memory_id is required", is_retryable=False)
        try:
            await self._store.soft_delete(memory_id)
            return ToolResult.ok({"deleted": memory_id})
        except Exception as e:
            logger.warning("forget_memory failed: %s", e)
            return ToolResult.fail("FORGET_ERROR", str(e), is_retryable=False)
