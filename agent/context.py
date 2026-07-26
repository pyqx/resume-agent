"""ContextAssembler — builds the full reasoning context for each Agent planning round."""

import logging

from agent.memory.retriever import MemoryRetriever
from agent.tools.registry import ToolRegistry
from core.llm import render_prompt, UNTRUSTED_NOTE

logger = logging.getLogger(__name__)

# Length caps keep the system prompt bounded as memories/resumes grow.
_RESUME_CONTEXT_MAX = 3000
_MEMORY_SECTION_MAX = 1500

SYSTEM_PROMPT = """You are a senior resume consultant with deep expertise in recruitment across industries.

## Your Role
Help users create, optimize, and tailor their resumes. You are NOT a simple form-filler —
you are a career narrative advisor who understands how recruiters and ATS systems evaluate resumes.

## Core Principles
1. **Ask, don't assume**: When information is missing, ask targeted follow-up questions rather than guessing.
2. **Evidence over claims**: Every improvement you suggest should be backed by JD analysis, industry standards, or ATS requirements.
3. **User has final say**: You suggest, the user decides. Never change facts, only optimize presentation.
4. **STAR completeness**: Every experience entry should cover Situation, Task, Action, Result.
5. **Quantify when possible**: Numbers, percentages, scales — they make claims credible.
6. **Respond in the user's language** (Chinese users get Chinese responses).

## Security
{untrusted_note}

## Working Context
- User Profile from Memory: {user_profile}
- User Preferences: {preferences}
- Session Context: {session_context}
- Feedback History: {feedback_history}
- Current Resume: {resume_context}

## Available Tools
{tool_manifest}

## Response Format
Plan your approach before responding. If you need to use tools, explain briefly what you're doing and why.
Always end your turn by either asking the user a question or presenting a result for their confirmation.
"""


class ContextAssembler:
    """Assembles the complete context for each Agent planning round.

    assemble() is called before every PLAN phase (not once per request), so
    tool availability and memory reflect state changes made by earlier
    rounds in the same request.
    """

    def __init__(self, retriever: MemoryRetriever, tool_registry: ToolRegistry):
        self._retriever = retriever
        self._tool_registry = tool_registry

    async def assemble(
        self,
        user_message: str,
        session_id: str = "default",
        user_id: str = "default",
        working_state: dict | None = None,
    ) -> dict:
        """Build the full context dict for the current planning round."""
        working_state = working_state or {}

        # Memory is auxiliary context — a broken/absent vector store must
        # never take down the chat endpoint.
        try:
            memory_context = await self._retriever.get_relevant_context(
                user_message=user_message,
                user_id=user_id,
                session_id=session_id,
            )
        except TypeError:
            # Older retriever signature without session_id
            try:
                memory_context = await self._retriever.get_relevant_context(
                    user_message=user_message, user_id=user_id
                )
            except Exception as e:
                logger.warning("Memory retrieval failed: %s", e)
                memory_context = {}
        except Exception as e:
            logger.warning("Memory retrieval failed: %s", e)
            memory_context = {}

        context_for_tools = {
            "resume_loaded": working_state.get("resume_loaded", False),
            "github_url": working_state.get("github_url"),
            "jd_loaded": working_state.get("jd_loaded", False),
        }
        tool_manifest_text = self._tool_registry.get_llm_manifest_text(context_for_tools)
        available_tools = self._tool_registry.get_manifest(context_for_tools)

        def _mem_lines(key: str, fallback: str, with_confidence: bool = False) -> str:
            items = memory_context.get(key, [])
            if not items:
                return fallback
            if with_confidence:
                lines = [f"- {m.key}: {m.value} (confidence: {m.confidence:.1f})" for m in items]
            else:
                lines = [f"- {m.key}: {m.value}" for m in items]
            return "\n".join(lines)[:_MEMORY_SECTION_MAX]

        resume_context = working_state.get(
            "resume_summary",
            "No resume loaded. Ask the user to upload one if needed.",
        )[:_RESUME_CONTEXT_MAX]

        system_prompt = render_prompt(
            SYSTEM_PROMPT,
            untrusted_note=UNTRUSTED_NOTE,
            user_profile=_mem_lines("user_profile", "No profile data yet."),
            preferences=_mem_lines("preference", "No preferences recorded.", with_confidence=True),
            session_context=_mem_lines("session", "No session context."),
            feedback_history=_mem_lines("feedback", "No feedback history."),
            resume_context=resume_context,
            tool_manifest=tool_manifest_text,
        )

        return {
            "system_prompt": system_prompt,
            "available_tools": available_tools,
        }
