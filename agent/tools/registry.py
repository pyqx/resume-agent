"""Tool registry — dynamic tool discovery, filtering, and permission control."""

from agent.tools.base import BaseTool, ToolResult


class ToolRegistry:
    """Central registry for all tools. Filters tools by context to enforce permissions."""

    def __init__(self):
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool):
        """Register a tool instance."""
        self._tools[tool.metadata.name] = tool

    def register_many(self, tools: list[BaseTool]):
        """Register multiple tool instances."""
        for tool in tools:
            self.register(tool)

    def get(self, name: str) -> BaseTool | None:
        """Get a tool by name."""
        return self._tools.get(name)

    def get_manifest(self, context: dict) -> list[BaseTool]:
        """Return tools applicable to the current context.

        Dynamic filtering ensures the Agent never sees tools it shouldn't use:
        - No resume uploaded → no resume-editing tools (except parser)
        - No GitHub URL → no GitHub tools
        - Sanitization not configured → no tools that send sensitive data to LLM
        """
        available = []
        for tool in self._tools.values():
            if self._is_applicable(tool, context):
                available.append(tool)
        return available

    def get_llm_manifest_text(self, context: dict) -> str:
        """Generate LLM-readable tool manifest for the system prompt."""
        tools = self.get_manifest(context)
        if not tools:
            return "No tools currently available."
        return "\n\n".join(t.to_llm_description() for t in tools)

    def list_all(self) -> list[str]:
        """List all registered tool names."""
        return list(self._tools.keys())

    async def execute(self, name: str, **kwargs) -> ToolResult:
        """Execute a tool by name with retry logic moved to the Agent loop."""
        tool = self._tools.get(name)
        if tool is None:
            return ToolResult.fail(
                error_code="TOOL_NOT_FOUND",
                error_message=f"Tool '{name}' is not registered. Available: {', '.join(self.list_all()[:10])}",
                is_retryable=True,
                fallback_suggestion="Try a different tool or respond directly to the user.",
            )
        try:
            return await tool.execute(**kwargs)
        except Exception as e:
            return ToolResult.fail(
                error_code="TOOL_EXECUTION_ERROR",
                error_message=str(e),
                is_retryable=True,
            )

    def _is_applicable(self, tool: BaseTool, context: dict) -> bool:
        """Check if a tool is applicable in the given context."""
        preconditions = tool.metadata.preconditions
        if not preconditions:
            return True

        for condition in preconditions:
            if condition == "resume_loaded":
                if not context.get("resume_loaded", False):
                    return False
            elif condition == "github_url_provided":
                if not context.get("github_url"):
                    return False
            elif condition == "jd_loaded":
                if not context.get("jd_loaded", False):
                    return False
            elif condition == "sanitization_configured":
                if not context.get("sanitization_configured", False):
                    return False
            elif condition == "user_confirmed":
                if not context.get("user_confirmed", False):
                    return False
        return True
