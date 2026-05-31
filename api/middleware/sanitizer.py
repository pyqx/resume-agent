"""Privacy sanitization middleware — mask sensitive data before LLM calls, re-identify after."""

import json
import logging
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from core.resume.sanitizer import ResumeSanitizer, SanitizerConfig

logger = logging.getLogger(__name__)


# Per-session sanitizer instances
_sanitizers: dict[str, ResumeSanitizer] = {}


def get_sanitizer(session_id: str, config: SanitizerConfig | None = None) -> ResumeSanitizer:
    """Get or create a sanitizer for a session."""
    if session_id not in _sanitizers:
        _sanitizers[session_id] = ResumeSanitizer(config=config or SanitizerConfig())
    return _sanitizers[session_id]


def clear_sanitizer(session_id: str):
    """Remove sanitizer state for a session (for cleanup)."""
    if session_id in _sanitizers:
        _sanitizers[session_id].clear()
        del _sanitizers[session_id]


class SanitizationContext:
    """Context manager that wraps LLM calls with sanitization.

    Usage:
        ctx = SanitizationContext(session_id)
        safe_text = ctx.sanitize_before_llm(original_text)
        # ... send safe_text to LLM ...
        restored_text = ctx.sanitize_after_llm(llm_response)
    """

    def __init__(self, session_id: str):
        self.session_id = session_id
        self.sanitizer = get_sanitizer(session_id)

    def sanitize_before_llm(self, text: str) -> str:
        """Apply sanitization before sending to LLM."""
        return self.sanitizer.resanitize(text, reverse=False)

    def sanitize_after_llm(self, text: str) -> str:
        """Restore original values in LLM response."""
        return self.sanitizer.resanitize(text, reverse=True)

    def get_mapping(self) -> dict[str, str]:
        return self.sanitizer.get_mapping()


def sanitize_resume_data(data: dict) -> dict:
    """Sanitize a resume data dict before sending to LLM.

    Masks: phone, salary, ID numbers, full addresses.
    Preserves: email (needed for format checking), name, skills.
    """
    config = SanitizerConfig(
        mask_phone=True,
        mask_email=False,
        mask_address=True,
        mask_salary=True,
        mask_id_number=True,
    )
    sanitizer = ResumeSanitizer(config=config)

    text = json.dumps(data, default=str)
    safe_text = ResumeSanitizer.sanitize_text(text)
    return json.loads(safe_text) if safe_text else data


class PrivacyLoggingMiddleware(BaseHTTPMiddleware):
    """Middleware that logs when sensitive data is being sent to external services.

    This does NOT block requests — it only logs and adds a privacy notice header.
    """

    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)

        # Add privacy notice for any endpoint that may interact with LLM
        if request.url.path in ("/chat/stream", "/chat/send", "/resume/upload", "/jd/match"):
            response.headers["X-Privacy-Notice"] = "LLM"

        return response
