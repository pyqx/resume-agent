"""Tool registry — dynamic tool discovery, filtering, and permission control."""

import logging

from agent.tools.base import BaseTool, ToolResult

logger = logging.getLogger(__name__)

# Preconditions the registry knows how to evaluate. Unknown precondition
# strings FAIL CLOSED (tool hidden / execution refused) instead of silently
# passing.
_KNOWN_CONDITIONS = {"resume_loaded", "github_url_provided", "jd_loaded"}


class ToolRegistry:
    """Central registry for all tools.

    Permission model:
    - get_manifest() filters what the LLM *sees* by context.
    - execute() *enforces* the same preconditions plus user-confirmation for
      destructive tools — visibility filtering alone is advisory, since the
      model can name any tool.
    """

    def __init__(self):
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool):
        """Register a tool instance."""
        name = tool.metadata.name
        if name in self._tools:
            logger.warning("Tool '%s' re-registered; overwriting previous instance", name)
        self._tools[name] = tool

    def register_many(self, tools: list[BaseTool]):
        for tool in tools:
            self.register(tool)

    def get(self, name: str) -> BaseTool | None:
        return self._tools.get(name)

    def get_manifest(self, context: dict) -> list[BaseTool]:
        """Return tools applicable to the current context."""
        return [t for t in self._tools.values() if self._is_applicable(t, context)]

    def get_llm_manifest_text(self, context: dict) -> str:
        """Generate LLM-readable tool manifest for the system prompt."""
        tools = self.get_manifest(context)
        if not tools:
            return "No tools currently available."
        return "\n\n".join(t.to_llm_description() for t in tools)

    def list_all(self) -> list[str]:
        return list(self._tools.keys())

    async def execute(self, name: str, _context: dict | None = None, **kwargs) -> ToolResult:
        """Execute a tool by name, enforcing preconditions and confirmation."""
        tool = self._tools.get(name)
        if tool is None:
            return ToolResult.fail(
                error_code="TOOL_NOT_FOUND",
                error_message=f"Tool '{name}' is not available.",
                is_retryable=False,
                fallback_suggestion="Use one of the tools listed in your manifest, or respond directly.",
            )

        if _context is not None:
            missing = self._unmet_preconditions(tool, _context)
            if missing:
                return ToolResult.fail(
                    error_code="PRECONDITION_NOT_MET",
                    error_message=(
                        f"Tool '{name}' requires: {', '.join(missing)}. "
                        "Gather the missing context first (e.g. ask the user to "
                        "upload a resume or provide a GitHub URL)."
                    ),
                    is_retryable=False,
                )

        if tool.metadata.requires_user_confirmation and not _is_truthy(kwargs.get("confirm")):
            return ToolResult.fail(
                error_code="CONFIRMATION_REQUIRED",
                error_message=(
                    f"'{name}' is destructive. Ask the user to explicitly confirm, "
                    "then call again with confirm=true."
                ),
                is_retryable=False,
            )
        kwargs.pop("confirm", None)

        try:
            return await tool.execute(**kwargs)
        except Exception as e:
            logger.exception("Tool '%s' raised", name)
            # Unexpected exceptions are not known-transient: don't auto-retry.
            return ToolResult.fail(
                error_code="TOOL_EXECUTION_ERROR",
                error_message=f"{type(e).__name__}: {e}",
                is_retryable=False,
            )

    def _unmet_preconditions(self, tool: BaseTool, context: dict) -> list[str]:
        missing = []
        for condition in tool.metadata.preconditions:
            if condition not in _KNOWN_CONDITIONS:
                logger.warning(
                    "Tool '%s' declares unknown precondition '%s' — failing closed",
                    tool.metadata.name, condition,
                )
                missing.append(condition)
            elif condition == "resume_loaded" and not context.get("resume_loaded", False):
                missing.append(condition)
            elif condition == "github_url_provided" and not context.get("github_url"):
                missing.append(condition)
            elif condition == "jd_loaded" and not context.get("jd_loaded", False):
                missing.append(condition)
        return missing

    def _is_applicable(self, tool: BaseTool, context: dict) -> bool:
        return not self._unmet_preconditions(tool, context)


def _is_truthy(value) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ("true", "yes", "1", "确认", "是")
    return bool(value)
