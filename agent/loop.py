"""Agent main loop — Plan → Act → Observe → Replan (hand-rolled state machine)."""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, AsyncIterator
from uuid import uuid4

from agent.checkpoint import CheckpointManager, Checkpoint
from agent.context import ContextAssembler
from agent.tools.registry import ToolRegistry
from agent.tools.base import ToolResult
from core.config import settings
from core.llm import extract_json_str, extract_text, parse_json_response

logger = logging.getLogger(__name__)

# Bound on tools executed in a single ACT phase.
_MAX_TOOLS_PER_ROUND = 5
# Result preview length shared by history/prompt/SSE.
_RESULT_PREVIEW_CHARS = 2000

_PLANNING_TEMPLATE = """{system_prompt}

## Current Task
User message: {user_message}

## Previous Attempts (this request)
{history_summary}

## Planning
Decide your next action.

IMPORTANT RULES:
- If you already ran tools successfully in a previous attempt, DO NOT run them again. Just respond directly with what you know.
- If all previous tool calls succeeded, output {"action": "respond", "message": "your answer", "reasoning": "why"}
- Only call NEW tools if you have NO data at all and need to gather information.
- Respond to the user in the user's language (Chinese for Chinese users).

Available actions:
1. **respond**: Reply directly to the user (answer a question, provide advice)
2. **ask**: Ask the user a clarifying question before proceeding
3. **tool**: Call one or more tools ONLY if you have no data yet

If you need to call tools, output a JSON object with:
{"action": "tool", "tools": [{"name": "tool_name", "params": {}}], "reasoning": "why"}

If you need user input, output:
{"action": "ask", "question": "your question here", "reasoning": "why"}

If you can respond directly, output:
{"action": "respond", "message": "your response", "reasoning": "why"}

Output ONLY valid JSON:"""


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
    # A "round" is one full PLAN(->ACT->OBSERVE) cycle.
    round_num: int = 0
    max_rounds: int = 15
    failed_rounds: int = 0
    max_failed_rounds: int = 3

    # Tool execution
    tool_queue: list[dict] = field(default_factory=list)
    tool_results: list[ToolResult] = field(default_factory=list)
    tool_call_history: list[dict] = field(default_factory=list)

    # Working state
    working_state: dict = field(default_factory=dict)

    # Conversation history for multi-turn context
    conversation_history: list[dict] = field(default_factory=list)

    # Events for SSE streaming
    events: list[dict] = field(default_factory=list)

    def emit_event(self, event_type: str, data: Any):
        self.events.append({
            "type": event_type,
            "data": data,
            "timestamp": time.time(),
        })

    def tool_call_history_summary(self) -> str:
        """Summarize previous tool calls and result previews for the LLM."""
        if not self.tool_call_history:
            return "No previous attempts."
        lines = []
        for entry in self.tool_call_history[-20:]:
            status = "OK" if entry.get("success") else f"FAILED: {entry.get('error', 'unknown')}"
            lines.append(f"Tool: {entry['tool']}")
            lines.append(f"  Status: {status}")
            data = entry.get("result_preview", "")
            if data:
                lines.append(f"  Result: {data[:_RESULT_PREVIEW_CHARS]}")
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
    ):
        self._llm = llm_client
        self._context_assembler = context_assembler
        self._tool_registry = tool_registry
        self._checkpoint = checkpoint_manager

    async def run(
        self,
        user_message: str,
        session_id: str | None = None,
        user_id: str = "default",
        working_state: dict | None = None,
        history: list[dict] | None = None,
    ) -> AsyncIterator[dict]:
        """Run the Agent loop, yielding SSE events at each step."""
        ctx = LoopContext(
            session_id=session_id or str(uuid4()),
            user_id=user_id,
            user_message=user_message,
            max_rounds=settings.max_loop_iterations,
            max_failed_rounds=settings.max_consecutive_failures,
            working_state=working_state or {},
            conversation_history=history or [],
        )

        # Recover from a checkpoint only if the previous run of this session
        # died mid-loop (clean completions delete their checkpoints) AND the
        # working state still matches.
        checkpoint = await self._checkpoint.load(ctx.session_id)
        if checkpoint:
            state_hash = CheckpointManager.compute_hash(ctx.working_state)
            if self._checkpoint.verify(checkpoint, state_hash) and checkpoint.tool_call_history:
                ctx.tool_call_history = list(checkpoint.tool_call_history)
                ctx.emit_event("checkpoint_restored", {
                    "recovered_tool_calls": len(ctx.tool_call_history),
                })
            else:
                await self._checkpoint.delete(ctx.session_id)

        while not ctx.is_terminal() and ctx.round_num < ctx.max_rounds:
            if ctx.state == LoopState.PLAN:
                ctx.round_num += 1
                await self._plan(ctx)
            elif ctx.state == LoopState.ACT:
                await self._act(ctx)
            elif ctx.state == LoopState.OBSERVE:
                await self._observe(ctx)

            for event in ctx.events:
                yield event
            ctx.events.clear()

        # Rounds exhausted without a response: degrade gracefully instead of
        # returning an empty string.
        if not ctx.is_terminal():
            ctx.state = LoopState.END
        if not ctx.agent_response:
            ok = sum(1 for h in ctx.tool_call_history if h.get("success"))
            total = len(ctx.tool_call_history)
            ctx.agent_response = (
                f"处理轮数已达上限,尚未得出完整结论(已执行 {total} 次工具调用,"
                f"成功 {ok} 次)。请换个说法重试,或把任务拆小一些。"
            )

        # Clean completion: checkpoints have served their purpose.
        try:
            await self._checkpoint.delete(ctx.session_id)
        except Exception as e:
            logger.warning("Checkpoint cleanup failed: %s", e)

        yield {
            "type": "final",
            "data": {
                "response": ctx.agent_response,
                "state": ctx.state.value,
                "iterations": ctx.round_num,
            },
            "timestamp": time.time(),
        }

    # ── PLAN ─────────────────────────────────────────────────

    async def _plan(self, ctx: LoopContext):
        """PLAN phase: the LLM decides respond / ask / tool."""
        ctx.emit_event("plan_start", {"iteration": ctx.round_num})

        # Re-assemble every round so tool gating and memory reflect the
        # current working state (a resume loaded by round 1's tools is
        # visible to round 2's planning).
        assembled = await self._context_assembler.assemble(
            user_message=ctx.user_message,
            session_id=ctx.session_id,
            user_id=ctx.user_id,
            working_state=ctx.working_state,
        )
        if ctx.round_num == 1:
            ctx.emit_event(
                "context_assembled", {"tool_count": len(assembled["available_tools"])}
            )

        planning_prompt = (
            _PLANNING_TEMPLATE
            .replace("{system_prompt}", assembled["system_prompt"])
            .replace("{user_message}", ctx.user_message)
            .replace("{history_summary}", ctx.tool_call_history_summary())
        )

        try:
            llm_messages = self._build_history_messages(ctx)
            response = await self._llm.messages.create(
                system=planning_prompt,
                messages=llm_messages,
                temperature=0.2,
                expect_json=True,
            )
            content = extract_text(response)
        except Exception as e:
            logger.error("Planning LLM call failed: %s", e)
            ctx.agent_response = "抱歉,AI 服务暂时不可用,请稍后重试。"
            ctx.state = LoopState.NEED_USER
            ctx.emit_event("plan_error", {"error": str(e)[:200]})
            return

        plan = self._parse_plan(content)
        action = plan.get("action", "respond")
        reasoning = str(plan.get("reasoning", ""))

        ctx.emit_event("plan_complete", {
            "action": action,
            "reasoning": reasoning[:500],
            "tools": [t.get("name", "?") for t in plan.get("tools", []) if isinstance(t, dict)],
            "raw_response": content[:500],
        })
        logger.info("Plan round %d: action=%s tools=%s", ctx.round_num, action,
                    [t.get("name") for t in plan.get("tools", []) if isinstance(t, dict)])

        if action == "tool":
            valid_tools = self._validate_tool_plan(plan.get("tools"), ctx)
            if not valid_tools:
                # Empty/invalid tool plan previously caused a livelock; ask
                # the user instead of spinning.
                ctx.agent_response = plan.get("message") or (
                    "我不确定下一步该做什么。能补充一些信息吗?"
                )
                ctx.state = LoopState.NEED_USER
                ctx.emit_event("plan_decision", {"action": "ask", "question": ctx.agent_response})
                return
            ctx.tool_queue = valid_tools
            ctx.state = LoopState.ACT
            ctx.emit_event("plan_decision", {
                "action": "tool",
                "tools": [t["name"] for t in valid_tools],
                "reasoning": reasoning,
            })
        elif action == "ask":
            ctx.agent_response = str(plan.get("question") or "能再具体描述一下你的需求吗?")
            ctx.state = LoopState.NEED_USER
            ctx.emit_event("plan_decision", {"action": "ask", "question": ctx.agent_response})
        else:  # respond
            message = plan.get("message")
            if not message:
                # Don't show raw JSON fragments to the user.
                message = content if extract_json_str(content) is None and content.strip() else (
                    "我暂时没有得到有效回复,请再试一次。"
                )
            ctx.agent_response = str(message)
            ctx.state = LoopState.END
            ctx.emit_event("plan_decision", {"action": "respond", "message": ctx.agent_response[:200]})

    def _build_history_messages(self, ctx: LoopContext) -> list[dict]:
        """Map stored history to LLM messages: filter empties, merge
        consecutive same-role turns (Anthropic requires alternation)."""
        merged: list[dict] = []
        for h in ctx.conversation_history[-20:]:
            role = h.get("role", "user")
            if role == "agent":
                role = "assistant"
            content = (h.get("content") or "").strip()
            if not content:
                continue
            if merged and merged[-1]["role"] == role:
                merged[-1]["content"] += "\n\n" + content
            else:
                merged.append({"role": role, "content": content})
        # Current user message last (and only once).
        if merged and merged[-1]["role"] == "user":
            merged[-1]["content"] += "\n\n" + ctx.user_message
        else:
            merged.append({"role": "user", "content": ctx.user_message})
        if merged[0]["role"] != "user":
            merged.insert(0, {"role": "user", "content": "(会话继续)"})
        return merged

    def _validate_tool_plan(self, tools: Any, ctx: LoopContext) -> list[dict]:
        """Keep only well-formed {name, params} entries for known tools."""
        if not isinstance(tools, list):
            return []
        valid = []
        for t in tools[:_MAX_TOOLS_PER_ROUND]:
            if not isinstance(t, dict):
                continue
            name = t.get("name")
            if not isinstance(name, str) or not self._tool_registry.get(name):
                logger.warning("Plan referenced unknown tool: %r", name)
                continue
            params = t.get("params", {})
            if not isinstance(params, dict):
                params = {}
            valid.append({"name": name, "params": params})
        return valid

    # ── ACT ──────────────────────────────────────────────────

    async def _act(self, ctx: LoopContext):
        """ACT phase: Execute tools from the queue."""
        ctx.emit_event("act_start", {"tool_count": len(ctx.tool_queue)})

        exec_context = {
            "resume_loaded": ctx.working_state.get("resume_loaded", False),
            "github_url": ctx.working_state.get("github_url"),
            "jd_loaded": ctx.working_state.get("jd_loaded", False),
        }

        aborted_at: int | None = None
        for idx, tool_def in enumerate(ctx.tool_queue):
            tool_name = tool_def["name"]
            params = dict(tool_def.get("params", {}))

            # Inject conversation context so tools operate on the active
            # resume / detected GitHub URL without the LLM re-typing them.
            resume_id = ctx.working_state.get("resume_id")
            if resume_id and "resume_id" not in params:
                params["resume_id"] = resume_id
            github_url = ctx.working_state.get("github_url")
            if github_url and "github_url" not in params:
                params["github_url"] = github_url
            if "user_id" not in params:
                params["user_id"] = ctx.user_id

            ctx.emit_event("tool_call", {"tool": tool_name, "params": params})
            logger.info("→ Tool call: %s", tool_name)

            result = await self._execute_tool_with_retry(tool_name, exec_context, **params)
            ctx.tool_results.append(result)

            data_preview = str(result.data)[:_RESULT_PREVIEW_CHARS] if (result.success and result.data) else ""
            ctx.tool_call_history.append({
                "tool": tool_name,
                "params": {k: str(v)[:200] for k, v in params.items()},
                "success": result.success,
                "error": result.error_code if not result.success else None,
                "result_preview": data_preview,
            })

            ctx.emit_event("tool_result", {
                "tool": tool_name,
                "success": result.success,
                "data": str(result.data)[:500] if result.data else None,
                "error": result.error_message,
            })

            if not result.success:
                logger.warning("← Tool FAILED: %s error=%s", tool_name, result.error_message)
                if not result.is_retryable:
                    aborted_at = idx
                    break
            else:
                logger.info("← Tool OK: %s", tool_name)

        # Record skipped tools so the next PLAN round knows they never ran.
        if aborted_at is not None:
            for skipped in ctx.tool_queue[aborted_at + 1:]:
                ctx.tool_call_history.append({
                    "tool": skipped["name"],
                    "params": {},
                    "success": False,
                    "error": "SKIPPED",
                    "result_preview": "",
                })

        ctx.state = LoopState.OBSERVE

    # ── OBSERVE ──────────────────────────────────────────────

    async def _observe(self, ctx: LoopContext):
        """OBSERVE phase: Evaluate the round's results, checkpoint, replan."""
        ctx.emit_event("observe_start", {})

        any_failure = any(not r.success for r in ctx.tool_results)
        if any_failure:
            ctx.failed_rounds += 1
            failed = [
                f"{h['tool']}: {h.get('error', 'unknown')}"
                for h in ctx.tool_call_history[-len(ctx.tool_results):]
                if not h.get("success")
            ]
            ctx.emit_event("observe_decision", {
                "decision": "partial_failure",
                "failed": failed,
            })
        else:
            ctx.failed_rounds = 0

        if ctx.failed_rounds >= ctx.max_failed_rounds:
            ctx.agent_response = (
                "连续多轮工具执行失败,我先停在这里。"
                "你可以稍后重试,或换一种方式描述需求。"
            )
            ctx.state = LoopState.NEED_USER
            ctx.emit_event("observe_decision", {"decision": "too_many_failures"})
            return

        ctx.tool_queue = []
        ctx.tool_results = []

        await self._save_checkpoint(ctx)
        ctx.state = LoopState.PLAN
        ctx.emit_event("observe_complete", {})

    # ── Helpers ──────────────────────────────────────────────

    async def _execute_tool_with_retry(
        self, tool_name: str, exec_context: dict, **kwargs
    ) -> ToolResult:
        """Execute a tool; retry only idempotent tools on retryable failures."""
        tool = self._tool_registry.get(tool_name)
        idempotent = bool(tool and tool.metadata.is_idempotent)

        last_result: ToolResult | None = None
        delay = settings.tool_retry_base_delay
        attempts = settings.tool_retry_max if idempotent else 1

        for attempt in range(attempts):
            result = await self._tool_registry.execute(tool_name, _context=exec_context, **kwargs)
            if result.success:
                return result
            last_result = result
            if not result.is_retryable or attempt == attempts - 1:
                break
            logger.warning(
                "Tool '%s' failed (attempt %d/%d), retrying in %.1fs: %s",
                tool_name, attempt + 1, attempts, delay, result.error_message,
            )
            await asyncio.sleep(delay)
            delay *= 2

        return last_result or ToolResult.fail(
            error_code="MAX_RETRIES", error_message="All retries exhausted"
        )

    async def _save_checkpoint(self, ctx: LoopContext):
        try:
            cp = Checkpoint(
                session_id=ctx.session_id,
                user_id=ctx.user_id,
                working_state_hash=CheckpointManager.compute_hash(ctx.working_state),
                tool_call_history=ctx.tool_call_history,
            )
            await self._checkpoint.save(cp)
        except Exception as e:
            logger.warning("Checkpoint save failed: %s", e)

    def _parse_plan(self, content: str) -> dict:
        """Parse the JSON plan from the LLM response, with safe fallbacks."""
        try:
            plan = parse_json_response(content)
            if isinstance(plan, dict) and plan.get("action") in ("respond", "ask", "tool"):
                return plan
            if isinstance(plan, dict):
                plan.setdefault("action", "respond")
                return plan
        except ValueError:
            pass
        if not content.strip():
            return {
                "action": "ask",
                "question": "我暂时没有得到有效回复,请再说一次你的需求。",
                "reasoning": "Empty LLM response",
            }
        # Non-JSON prose: treat as a direct response.
        return {"action": "respond", "message": content, "reasoning": "Plain-text response"}
