"""Memory tools — search, read, and manage the Agent's memory."""

from agent.tools.base import BaseTool, ToolMetadata, ToolResult, ToolCategory, Difficulty
from agent.memory.store import MemoryStore
from agent.memory.models import MemoryType


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
            estimated_time=Difficulty.LIGHT,
        )

    async def execute(self, query: str = "", user_id: str = "default", top_k: int = 5, **kwargs) -> ToolResult:
        if not query:
            return ToolResult.fail("PARAM_ERROR", "query is required")
        try:
            results = await self._store.search(query=query, user_id=user_id, top_k=top_k)
            return ToolResult.ok([{
                "id": m.id, "type": m.type.value, "key": m.key, "value": m.value
            } for m in results])
        except Exception as e:
            return ToolResult.fail("MEMORY_SEARCH_ERROR", str(e), is_retryable=True)


class GetUserProfileTool(BaseTool):
    def __init__(self, store: MemoryStore):
        self._store = store

    @property
    def metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="get_user_profile",
            category=ToolCategory.MEMORY,
            description="Get the user's complete profile (skills, education, work history)",
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
            return ToolResult.fail("PROFILE_ERROR", str(e), is_retryable=True)


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
            return ToolResult.fail("PREFERENCES_ERROR", str(e), is_retryable=True)


class ForgetMemoryTool(BaseTool):
    def __init__(self, store: MemoryStore):
        self._store = store

    @property
    def metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="forget_memory",
            category=ToolCategory.MEMORY,
            description="Delete a specific memory (user-requested)",
            usage_guide="Use ONLY when the user explicitly asks to delete or forget something",
            preconditions=["user_confirmed"],
            estimated_time=Difficulty.LIGHT,
            is_idempotent=True,
            requires_user_confirmation=True,
        )

    async def execute(self, memory_id: str = "", **kwargs) -> ToolResult:
        if not memory_id:
            return ToolResult.fail("PARAM_ERROR", "memory_id is required")
        try:
            await self._store.soft_delete(memory_id)
            return ToolResult.ok({"deleted": memory_id})
        except Exception as e:
            return ToolResult.fail("FORGET_ERROR", str(e), is_retryable=True)
