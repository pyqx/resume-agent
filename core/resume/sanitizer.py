"""PII sanitization — mask sensitive values before they leave the process.

Two mechanisms:
- PIIMasker: reversible, per-request masking used by the LLM client. Each
  distinct value gets its own placeholder (two phone numbers never collide),
  and placeholders are restored in the LLM's response text.
- sanitize_text / PIILogFilter: irreversible masking for log output.
"""

import logging
import re

logger = logging.getLogger(__name__)

# Sensitive value patterns. Order matters: more specific first.
DEFAULT_PATTERNS: dict[str, str] = {
    "id_number": r"\d{17}[\dXx]",
    "phone": r"(?:\+?86[\s-]?)?1[3-9]\d{9}",
    "email": r"[\w.+-]+@[\w-]+\.[\w.-]+",
    "salary": r"(?:月薪|年薪|薪资|工资|salary)[：:\s]*[\d,.]+\s*[万kwK]?",
    "wechat": r"(?:微信|WeChat|wx)[号：:\s]+[A-Za-z][\w-]{4,19}",
    "address": r"(?:地址|住址)[：:]\s*[^\s,，。;；\"']{4,30}",
}

_COMPILED = {
    name: re.compile(pattern, re.IGNORECASE) for name, pattern in DEFAULT_PATTERNS.items()
}


class PIIMasker:
    """Reversible PII masking with per-value placeholders.

    Usage (one instance per LLM request):
        masker = PIIMasker()
        safe = masker.mask(prompt_text)
        ...  # send `safe` to the LLM
        restored = masker.unmask(response_text)
    """

    def __init__(self, categories: set[str] | None = None):
        self._categories = categories or set(DEFAULT_PATTERNS)
        # original value -> placeholder
        self._forward: dict[str, str] = {}
        # placeholder -> original value
        self._reverse: dict[str, str] = {}
        self._counters: dict[str, int] = {}

    def _placeholder_for(self, category: str, value: str) -> str:
        existing = self._forward.get(value)
        if existing:
            return existing
        self._counters[category] = self._counters.get(category, 0) + 1
        placeholder = f"[PII_{category.upper()}_{self._counters[category]}]"
        self._forward[value] = placeholder
        self._reverse[placeholder] = value
        return placeholder

    def mask(self, text: str) -> str:
        if not text:
            return text
        result = text
        for category, regex in _COMPILED.items():
            if category not in self._categories:
                continue
            result = regex.sub(
                lambda m, c=category: self._placeholder_for(c, m.group(0)), result
            )
        return result

    def unmask(self, text: str) -> str:
        if not text or not self._reverse:
            return text
        result = text
        for placeholder, original in self._reverse.items():
            result = result.replace(placeholder, original)
        return result

    @property
    def masked_count(self) -> int:
        return len(self._reverse)


def sanitize_text(text: str) -> str:
    """Irreversibly mask sensitive patterns (for logs and display)."""
    result = text
    for pattern_name, regex in _COMPILED.items():
        result = regex.sub(f"[REDACTED:{pattern_name}]", result)
    return result


class PIILogFilter(logging.Filter):
    """Logging filter that masks PII in formatted log messages."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
            masked = sanitize_text(message)
            if masked != message:
                record.msg = masked
                record.args = ()
        except Exception:
            pass
        return True
