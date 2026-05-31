"""ResumeSanitizer — mask sensitive information before sending to LLM."""

import re
import hashlib
import logging
from dataclasses import dataclass, field
from copy import deepcopy

from core.resume.schema import ResumeData, PersonalInfo

logger = logging.getLogger(__name__)

# Default sensitive field patterns
DEFAULT_PATTERNS = {
    "phone": r'(?:\+?86[\s-]?)?1[3-9]\d{9}',
    "email": r'[\w.+-]+@[\w-]+\.[\w.-]+',
    "id_number": r'\d{17}[\dXx]',
    "salary": r'(?:月薪|年薪|薪资|工资|salary)[：:\s]*[\d,.]+[万kwK]?',
    "full_address": r'(?:地址|住址)[：:\s]*.{5,}',
    "wechat": r'(?:微信|WeChat|wx)[：:\s]*[\w-]+',
}


@dataclass
class SanitizerConfig:
    """Which fields to sanitize and how."""
    mask_phone: bool = True
    mask_email: bool = False  # Often needed for format checking
    mask_address: bool = True
    mask_salary: bool = True
    mask_id_number: bool = True
    mask_company_names: bool = False  # Optionally mask current employer
    custom_masks: dict[str, str] = field(default_factory=dict)


class ResumeSanitizer:
    """Sanitize resume data before sending to external services.

    Maintains a mapping table that enables re-identification after LLM processing.
    """

    def __init__(self, config: SanitizerConfig | None = None):
        self.config = config or SanitizerConfig()
        self._mapping: dict[str, str] = {}

    def sanitize(self, resume: ResumeData) -> tuple[ResumeData, dict[str, str]]:
        """Sanitize a ResumeData object, returning sanitized copy + mapping table.

        The mapping table maps placeholder → original value for re-identification.
        """
        self._mapping = {}
        resume_copy = deepcopy(resume)
        pi = resume_copy.personal_info

        if self.config.mask_phone and pi.phone:
            placeholder = self._make_placeholder("phone")
            self._mapping[placeholder] = pi.phone
            pi.phone = placeholder

        if self.config.mask_email and pi.email:
            placeholder = self._make_placeholder("email")
            self._mapping[placeholder] = pi.email
            pi.email = placeholder

        if self.config.mask_address and pi.location:
            placeholder = self._make_placeholder("location")
            self._mapping[placeholder] = pi.location
            pi.location = placeholder

        # Apply custom masks
        for field_name, pattern in self.config.custom_masks.items():
            if hasattr(pi, field_name):
                value = getattr(pi, field_name)
                if value:
                    placeholder = self._make_placeholder(field_name)
                    self._mapping[placeholder] = value
                    setattr(pi, field_name, placeholder)

        return resume_copy, self._mapping

    @staticmethod
    def sanitize_text(text: str) -> str:
        """Sanitize plain text by masking common sensitive patterns."""
        result = text
        for pattern_name, pattern in DEFAULT_PATTERNS.items():
            result = re.sub(
                pattern,
                lambda m: f"[REDACTED:{pattern_name}]",
                result,
                flags=re.IGNORECASE,
            )
        return result

    def resanitize(self, text: str, reverse: bool = True) -> str:
        """Replace placeholders with original values (or vice versa)."""
        result = text
        if reverse:
            for placeholder, original in self._mapping.items():
                result = result.replace(placeholder, original)
        else:
            for original, placeholder in self._mapping.items():
                result = result.replace(original, placeholder)
        return result

    def get_mapping(self) -> dict[str, str]:
        return dict(self._mapping)

    def clear(self):
        """Clear the mapping table (for cleanup)."""
        self._mapping.clear()

    @staticmethod
    def _make_placeholder(field: str) -> str:
        """Generate a consistent placeholder for a field."""
        suffix = hashlib.md5(field.encode()).hexdigest()[:8]
        return f"[REDACTED_{field}_{suffix}]"
