"""Agent tool base classes — ToolMetadata, ToolResult, BaseTool."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ToolCategory(Enum):
    RESUME = "resume"
    JD = "jd"
    GITHUB = "github"
    QUALITY = "quality"
    MEMORY = "memory"
    INTERVIEW = "interview"
    WEB = "web"
    UTILITY = "utility"


class Difficulty(Enum):
    LIGHT = "light"
    MEDIUM = "medium"
    HEAVY = "heavy"


@dataclass
class ToolMetadata:
    """Declarative metadata that the Agent reads to decide when/how to use a tool."""
    name: str
    category: ToolCategory
    description: str
    usage_guide: str
    # Parameter name -> human-readable description (type + meaning). Rendered
    # into the LLM manifest so the model doesn't have to guess param names.
    parameters: dict[str, str] = field(default_factory=dict)
    preconditions: list[str] = field(default_factory=list)
    estimated_time: Difficulty = Difficulty.LIGHT
    is_idempotent: bool = True
    requires_user_confirmation: bool = False


@dataclass
class ToolResult:
    """Structured result from a tool execution. Agent loop uses this for OBSERVE/REPLAN."""
    success: bool
    data: Any = None
    error_code: str | None = None
    error_message: str | None = None
    is_retryable: bool = False
    fallback_suggestion: str | None = None

    @classmethod
    def ok(cls, data: Any = None) -> "ToolResult":
        return cls(success=True, data=data)

    @classmethod
    def fail(
        cls,
        error_code: str,
        error_message: str = "",
        is_retryable: bool = False,
        fallback_suggestion: str | None = None,
    ) -> "ToolResult":
        return cls(
            success=False,
            error_code=error_code,
            error_message=error_message,
            is_retryable=is_retryable,
            fallback_suggestion=fallback_suggestion,
        )


class BaseTool(ABC):
    """Base class for all Agent tools."""

    @property
    @abstractmethod
    def metadata(self) -> ToolMetadata:
        ...

    @abstractmethod
    async def execute(self, **kwargs) -> ToolResult:
        ...

    def to_llm_description(self) -> str:
        """Generate a text description for the LLM's system prompt."""
        m = self.metadata
        lines = [
            f"Tool: {m.name}",
            f"When to use: {m.usage_guide}",
        ]
        if m.parameters:
            lines.append("Parameters:")
            lines.extend(f"  - {name}: {desc}" for name, desc in m.parameters.items())
        else:
            lines.append("Parameters: none")
        if m.requires_user_confirmation:
            lines.append(
                "NOTE: destructive — requires explicit user confirmation; "
                "call with confirm=true only AFTER the user has agreed."
            )
        return "\n".join(lines)
