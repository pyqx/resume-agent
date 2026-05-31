"""Agent main loop — Plan → Act → Observe → Replan (LangGraph StateGraph)."""

import json
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, AsyncIterator
from uuid import uuid4

from agent.checkpoint import CheckpointManager, Checkpoint
from agent.context import ContextAssembler
from agent.planner import Planner, StrategicPlan, TacticalStep, MilestoneStatus
from agent.tools.registry import ToolRegistry
from agent.tools.base import ToolResult
from core.config import settings

logger = logging.getLogger(__name__)


class LoopState(str, Enum):
    PLAN = "plan"
    ACT = "act"
    OBSERVE = "observe"
    END = "end"
    NEED_USER = "need_user"


@dataclass
class LoopContext:
    """Mutable state that flows through the Agent loop."""
    session_id: str = field(default_factory=lambda: str(uuid4()))
    user_id: str = "default"
    user_message: str = ""
    agent_response: str = ""
    state: LoopState = LoopState.PLAN
    iteration: int = 0
    max_iterations: int = 15
    consecutive_failures: int = 0
    max_failures: int = 3

    # Planning
    strategic_plan: StrategicPlan | None = None
    current_tactical_step: TacticalStep | None = None

    # Tool execution
    tool_queue: list[dict] = field(default_factory=list)
    tool_results: list[ToolResult] = field(default_factory=list)
    tool_call_history: list[dict] = field(default_factory=list)

    # Working state
    working_state: dict = field(default_factory=dict)

    # Conversation history for multi-turn context
    conversation_history: list[dict] = field(default_factory=list)

    # Checkpoint
    last_checkpoint_id: str = ""

    # Events for SSE streaming
    events: list[dict] = field(default_factory=list)

    def emit_event(self, event_type: str, data: Any):
        self.events.append({
            "type": event_type,
            "data": data,
            "timestamp": time.time(),
        })

    def tool_call_history_summary(self) -> str:
        """Summarize all previous tool calls and their results for the LLM."""
        if not self.tool_call_history:
            return "No previous attempts."
        lines = []
        for entry in self.tool_call_history:
            status = "OK" if entry.get("success") else f"FAILED: {entry.get('error', 'unknown')}"
            lines.append(f"- {entry['tool']}({json.dumps(entry.get('params', {}))}) → {status}")
        return "\n".join(lines)

    def needs_user_input(self) -> bool:
        return self.state == LoopState.NEED_USER

    def is_terminal(self) -> bool:
        return self.state in (LoopState.END, LoopState.NEED_USER)


class AgentLoop:
    """Main Agent loop orchestrating Plan → Act → Observe → Replan."""

    def __init__(
        self,
        llm_client,
        context_assembler: ContextAssembler,
        tool_registry: ToolRegistry,
        checkpoint_manager: CheckpointManager,
        planner: Planner,
    ):
        self._llm = llm_client
        self._context_assembler = context_assembler
        self._tool_registry = tool_registry
        self._checkpoint = checkpoint_manager
        self._planner = planner

    async def run(
        self,
        user_message: str,
        session_id: str | None = None,
        user_id: str = "default",
        working_state: dict | None = None,
        history: list[dict] | None = None,
    ) -> AsyncIterator[dict]:
        """Run the Agent loop, yielding SSE events at each step.

        This is the main entry point called by the chat API endpoint.
        """
        ctx = LoopContext(
            session_id=session_id or str(uuid4()),
            user_id=user_id,
            user_message=user_message,
            max_iterations=settings.max_loop_iterations,
            max_failures=settings.max_consecutive_failures,
            working_state=working_state or {},
            conversation_history=history or [],
        )

        # Attempt checkpoint recovery
        checkpoint = await self._checkpoint.load(ctx.session_id)
        if checkpoint:
            ctx.strategic_plan = checkpoint.strategic_plan
            ctx.emit_event("checkpoint_restored", {
                "milestone": checkpoint.current_milestone_id,
                "progress": checkpoint.tactical_progress,
            })

        # Assemble initial context
        assembled = await self._context_assembler.assemble(
            user_message=user_message,
            session_id=ctx.session_id,
            user_id=ctx.user_id,
            working_state=ctx.working_state,
        )
        ctx.emit_event("context_assembled", {"tool_count": len(assembled["available_tools"])})

        # Main loop
        while not ctx.is_terminal() and ctx.iteration < ctx.max_iterations:
            ctx.iteration += 1

            if ctx.state == LoopState.PLAN:
                await self._plan(ctx, assembled)
            elif ctx.state == LoopState.ACT:
                await self._act(ctx)
            elif ctx.state == LoopState.OBSERVE:
                await self._observe(ctx)

            # Yield events accumulated in this iteration
            for event in ctx.events:
                yield event
            ctx.events.clear()

        # Emit final response
        yield {
            "type": "final",
            "data": {
                "response": ctx.agent_response,
                "state": ctx.state.value,
                "iterations": ctx.iteration,
            },
            "timestamp": time.time(),
        }

    async def _plan(self, ctx: LoopContext, assembled: dict):
        """PLAN phase: Agent reasons about what to do next.

        Uses the  API directly for planning reasoning.
        The LLM decides: respond directly, ask a clarifying question,
        or call specific tools.
        """
        ctx.emit_event("plan_start", {"iteration": ctx.iteration})

        # Build the planning prompt
        system_prompt = assembled["system_prompt"]
        tool_list = "\n".join(
            f"- {t.metadata.name}: {t.metadata.usage_guide}"
            for t in assembled["available_tools"]
        )

        planning_prompt = f"""{system_prompt}

## Current Task
User message: {ctx.user_message}

## Previous Attempts
{ctx.tool_call_history_summary()}

## Planning
Decide your next action.

IMPORTANT RULES:
- If you already ran tools successfully in a previous attempt, DO NOT run them again. Just respond directly with what you know.
- If all previous tool calls succeeded, output {{"action": "respond", "message": "your answer", "reasoning": "why"}}
- Only call NEW tools if you have NO data at all and need to gather information.

Available actions:
1. **respond**: Reply directly to the user (answer a question, provide advice)
2. **ask**: Ask the user a clarifying question before proceeding
3. **tool**: Call one or more tools ONLY if you have no data yet

If you need to call tools, output a JSON object with:
{{"action": "tool", "tools": [{{"name": "tool_name", "params": {{}}}}], "reasoning": "why"}}

If you need user input, output:
{{"action": "ask", "question": "your question here", "reasoning": "why"}}

If you can respond directly, output:
{{"action": "respond", "message": "your response", "reasoning": "why"}}

Output ONLY valid JSON:"""

        try:
            # Build messages with conversation history for multi-turn context
            llm_messages: list[dict] = []
            for h in ctx.conversation_history[-20:]:  # last 20 turns max
                llm_messages.append({"role": h.get("role", "user"), "content": h.get("content", "")})
            llm_messages.append({"role": "user", "content": ctx.user_message})

            response = self._llm.messages.create(
                model=settings.llm_model,
                max_tokens=settings.llm_max_tokens,
                temperature=settings.llm_temperature,
                system=planning_prompt,
                messages=llm_messages,
            )

            content = self._extract_text(response)
            ctx.emit_event("plan_complete", {"raw_response": content[:500]})

            # Parse the planning decision
            plan = self._parse_plan(content)
            action = plan.get("action", "respond")
            reasoning = plan.get("reasoning", "")

            logger.info("Plan: action=%s tools=%s reasoning=%s",
                         action, plan.get("tools", []), reasoning[:150])

            if action == "tool":
                tools = plan.get("tools", [])
                ctx.tool_queue = tools
                ctx.state = LoopState.ACT
                ctx.emit_event("plan_decision", {
                    "action": "tool",
                    "tools": [t["name"] for t in tools],
                    "reasoning": reasoning,
                })
            elif action == "ask":
                ctx.agent_response = plan.get("question", "")
                ctx.state = LoopState.NEED_USER
                ctx.emit_event("plan_decision", {"action": "ask", "question": ctx.agent_response})
            else:  # respond
                ctx.agent_response = plan.get("message", content)
                ctx.state = LoopState.END
                ctx.emit_event("plan_decision", {"action": "respond", "message": ctx.agent_response[:200]})

        except Exception as e:
            logger.error(f"Planning failed: {e}")
            ctx.agent_response = "I encountered an error while planning. Could you rephrase your request?"
            ctx.state = LoopState.NEED_USER
            ctx.emit_event("plan_error", {"error": str(e)})

    async def _act(self, ctx: LoopContext):
        """ACT phase: Execute tools from the queue."""
        ctx.emit_event("act_start", {"tool_count": len(ctx.tool_queue)})

        for tool_def in ctx.tool_queue:
            tool_name = tool_def["name"]
            params = dict(tool_def.get("params", {}))

            # Inject resume_id from working_state so tools operate on the active resume
            resume_id = ctx.working_state.get("resume_id")
            if resume_id and "resume_id" not in params:
                params["resume_id"] = resume_id

            ctx.emit_event("tool_call", {"tool": tool_name, "params": params})

            logger.info("→ Tool call: %s params=%s", tool_name, {k: str(v)[:100] for k, v in params.items()})

            result = await self._execute_tool_with_retry(tool_name, ctx, **params)
            ctx.tool_results.append(result)
            ctx.tool_call_history.append({
                "tool": tool_name,
                "params": params,
                "success": result.success,
                "error": result.error_code if not result.success else None,
            })

            ctx.emit_event("tool_result", {
                "tool": tool_name,
                "success": result.success,
                "data": str(result.data)[:500] if result.data else None,
                "error": result.error_message,
            })

            if not result.success:
                logger.warning("← Tool FAILED: %s error=%s retryable=%s",
                               tool_name, result.error_message, result.is_retryable)
                ctx.consecutive_failures += 1
                if not result.is_retryable:
                    break
            else:
                summary = str(result.data)[:200] if result.data else "(no data)"
                logger.info("← Tool OK: %s data=%s", tool_name, summary)
                ctx.consecutive_failures = 0

        ctx.state = LoopState.OBSERVE

    async def _observe(self, ctx: LoopContext):
        """OBSERVE phase: Evaluate tool results and decide next step."""
        ctx.emit_event("observe_start", {})

        # Check for failure conditions
        if ctx.consecutive_failures >= ctx.max_failures:
            ctx.agent_response = (
                "I've encountered repeated errors while trying to help you. "
                "You can try again, or describe what you'd like to do manually."
            )
            ctx.state = LoopState.NEED_USER
            ctx.emit_event("observe_decision", {"decision": "too_many_failures"})
            return

        # Check if all tools succeeded
        all_success = all(r.success for r in ctx.tool_results)
        if not all_success:
            failed_tools = [
                f"{h['tool']}: {h.get('error', 'unknown')}"
                for h, r in zip(ctx.tool_call_history, ctx.tool_results)
                if not r.success
            ]
            ctx.emit_event("observe_decision", {
                "decision": "partial_failure",
                "failed": failed_tools,
            })

        # Clear for next iteration
        ctx.tool_queue = []
        ctx.tool_results = []

        # Save checkpoint after observation
        await self._save_checkpoint(ctx)

        # Go back to plan for next iteration (or end)
        ctx.state = LoopState.PLAN
        ctx.emit_event("observe_complete", {})

    async def _execute_tool_with_retry(
        self,
        tool_name: str,
        ctx: LoopContext,
        **kwargs,
    ) -> ToolResult:
        """Execute a tool with exponential backoff retry."""
        last_result = None
        delay = settings.tool_retry_base_delay

        for attempt in range(settings.tool_retry_max):
            result = await self._tool_registry.execute(tool_name, **kwargs)
            if result.success:
                return result

            last_result = result
            if not result.is_retryable:
                break

            logger.warning(
                f"Tool '{tool_name}' failed (attempt {attempt+1}), "
                f"retrying in {delay}s: {result.error_message}"
            )
            await self._async_sleep(delay)
            delay *= 2

        return last_result or ToolResult.fail(error_code="MAX_RETRIES", error_message="All retries exhausted")

    async def _save_checkpoint(self, ctx: LoopContext):
        """Save a checkpoint of the current state."""
        try:
            state_hash = CheckpointManager.compute_hash(ctx.working_state)
            cp = Checkpoint(
                session_id=ctx.session_id,
                user_id=ctx.user_id,
                strategic_plan=ctx.strategic_plan,
                tactical_progress={},
                working_state_hash=state_hash,
                tool_call_history=ctx.tool_call_history,
            )
            await self._checkpoint.save(cp)
            ctx.last_checkpoint_id = cp.checkpoint_id
        except Exception as e:
            logger.warning(f"Checkpoint save failed: {e}")

    def _parse_plan(self, content: str) -> dict:
        """Parse JSON plan from LLM response, with fallback."""
        try:
            # Extract JSON from potential markdown code blocks
            content = content.strip()
            if content.startswith("```"):
                lines = content.split("\n")
                content = "\n".join(lines[1:-1])
            return json.loads(content)
        except (json.JSONDecodeError, IndexError):
            if not content.strip():
                return {"action": "ask", "question": "I didn't receive a valid response. Could you please try again?",
                        "reasoning": "Empty LLM response"}
            return {"action": "respond", "message": content, "reasoning": "Parsed from text response"}

    async def _async_sleep(self, seconds: float):
        """Async sleep."""
        import asyncio
        await asyncio.sleep(seconds)

    @staticmethod
    def _extract_text(response) -> str:
        """Extract text content from an  response, handling thinking blocks."""
        for block in response.content:
            if hasattr(block, "text"):
                return block.text
        return str(response.content)
