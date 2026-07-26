"""Tests for tool registry permission enforcement (agent/tools/registry.py)."""

import asyncio

from agent.tools.base import BaseTool, ToolMetadata, ToolResult, ToolCategory
from agent.tools.registry import ToolRegistry


class _StubTool(BaseTool):
    def __init__(self, name="stub", preconditions=None, requires_confirmation=False):
        self._name = name
        self._preconditions = preconditions or []
        self._requires_confirmation = requires_confirmation
        self.executed = False

    @property
    def metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name=self._name,
            category=ToolCategory.UTILITY,
            description="stub",
            usage_guide="stub",
            preconditions=self._preconditions,
            requires_user_confirmation=self._requires_confirmation,
        )

    async def execute(self, **kwargs) -> ToolResult:
        self.executed = True
        return ToolResult.ok({"kwargs": kwargs})


def _run(coro):
    return asyncio.run(coro)


class TestPreconditionEnforcement:
    def test_execute_blocks_unmet_precondition(self):
        # Historical bug: execute() never checked preconditions — the model
        # could invoke any tool by name.
        registry = ToolRegistry()
        tool = _StubTool(preconditions=["resume_loaded"])
        registry.register(tool)
        result = _run(registry.execute("stub", _context={"resume_loaded": False}))
        assert not result.success
        assert result.error_code == "PRECONDITION_NOT_MET"
        assert not tool.executed

    def test_execute_allows_met_precondition(self):
        registry = ToolRegistry()
        registry.register(_StubTool(preconditions=["resume_loaded"]))
        result = _run(registry.execute("stub", _context={"resume_loaded": True}))
        assert result.success

    def test_unknown_precondition_fails_closed(self):
        registry = ToolRegistry()
        tool = _StubTool(preconditions=["totally_made_up"])
        registry.register(tool)
        assert registry.get_manifest({"resume_loaded": True}) == []
        result = _run(registry.execute("stub", _context={}))
        assert not result.success


class TestConfirmationEnforcement:
    def test_destructive_requires_confirm(self):
        registry = ToolRegistry()
        tool = _StubTool(requires_confirmation=True)
        registry.register(tool)
        result = _run(registry.execute("stub", _context={}))
        assert not result.success
        assert result.error_code == "CONFIRMATION_REQUIRED"
        assert not tool.executed

    def test_confirm_true_passes_and_is_stripped(self):
        registry = ToolRegistry()
        tool = _StubTool(requires_confirmation=True)
        registry.register(tool)
        result = _run(registry.execute("stub", _context={}, confirm=True))
        assert result.success
        assert "confirm" not in result.data["kwargs"]


class TestErrorHandling:
    def test_unknown_tool(self):
        registry = ToolRegistry()
        result = _run(registry.execute("nope"))
        assert not result.success
        assert result.error_code == "TOOL_NOT_FOUND"
        assert not result.is_retryable

    def test_exception_not_retryable(self):
        class _Boom(_StubTool):
            async def execute(self, **kwargs):
                raise RuntimeError("boom")

        registry = ToolRegistry()
        registry.register(_Boom())
        result = _run(registry.execute("stub"))
        assert not result.success
        assert result.error_code == "TOOL_EXECUTION_ERROR"
        assert not result.is_retryable
