"""ContextAssembler — builds the full reasoning context for each Agent loop iteration."""

import json
import logging

from agent.memory.retriever import MemoryRetriever
from agent.tools.registry import ToolRegistry
from core.config import settings

logger = logging.getLogger(__name__)

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
    """Assembles the complete context for each Agent planning cycle."""

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
        """Build the full context dict for the current Agent turn.

        Returns:
            dict with keys: system_prompt, user_message, memory_context,
                           working_state, tool_manifest, available_tools
        """
        # Retrieve relevant memories
        memory_context = await self._retriever.get_relevant_context(
            user_message=user_message,
            user_id=user_id,
        )

        # Build tool manifest
        context_for_tools = {
            "resume_loaded": (working_state or {}).get("resume_loaded", False),
            "github_url": (working_state or {}).get("github_url"),
            "jd_loaded": (working_state or {}).get("jd_loaded", False),
            "sanitization_configured": (working_state or {}).get("sanitization_configured", False),
        }
        tool_manifest_text = self._tool_registry.get_llm_manifest_text(context_for_tools)
        available_tools = self._tool_registry.get_manifest(context_for_tools)

        # Format memory context for prompt
        user_profile = "\n".join(
            f"- {m.key}: {m.value}"
            for m in memory_context.get("user_profile", [])
        ) or "No profile data yet."

        preferences = "\n".join(
            f"- {m.key}: {m.value} (confidence: {m.confidence:.1f})"
            for m in memory_context.get("preference", [])
        ) or "No preferences recorded."

        session_ctx = "\n".join(
            f"- {m.key}: {m.value}"
            for m in memory_context.get("session", [])
        ) or "No session context."

        feedback = "\n".join(
            f"- {m.key}: {m.value}"
            for m in memory_context.get("feedback", [])
        ) or "No feedback history."

        # Extract resume context from working_state
        resume_context = (working_state or {}).get(
            "resume_summary",
            "No resume loaded. Ask the user to upload one if needed."
        )

        # Assemble system prompt
        system_prompt = SYSTEM_PROMPT.format(
            user_profile=user_profile,
            preferences=preferences,
            session_context=session_ctx,
            feedback_history=feedback,
            resume_context=resume_context,
            tool_manifest=tool_manifest_text,
        )

        return {
            "system_prompt": system_prompt,
            "user_message": user_message,
            "memory_context": memory_context,
            "working_state": working_state or {},
            "tool_manifest_text": tool_manifest_text,
            "available_tools": available_tools,
            "session_id": session_id,
            "user_id": user_id,
        }
