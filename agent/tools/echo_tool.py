"""Echo tool — for integration testing of the Agent loop."""

from agent.tools.base import BaseTool, ToolMetadata, ToolResult, ToolCategory, Difficulty


class EchoTool(BaseTool):
    @property
    def metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="echo",
            category=ToolCategory.UTILITY,
            description="Echo back the input — for testing",
            usage_guide="Use for testing the tool execution pipeline",
            estimated_time=Difficulty.LIGHT,
        )

    async def execute(self, message: str = "", **kwargs) -> ToolResult:
        return ToolResult.ok({"echo": message})
