"""Shared resume-language detection for the interview generators.

Replaces the two divergent heuristics that previously lived in
question_generator (CJK >= 5 chars) and intro_generator (ASCII ratio > 0.7)
with a single implementation all three generators use.
"""

import logging
import re

from core.resume.schema import ResumeData

logger = logging.getLogger(__name__)

# CJK Unified Ideographs (U+4E00–U+9FFF).
_CJK_RE = re.compile(r"[一-鿿]")
_ASCII_LETTER_RE = re.compile(r"[A-Za-z]")


def detect_language(resume: ResumeData) -> str:
    """Detect the resume's dominant language: ``"zh"`` or ``"en"``.

    Concatenates summary + all bullets + company/school/position names,
    then counts CJK characters vs. English letters. Chinese wins when CJK
    makes up more than 15% of letter-class characters, or exceeds 30
    characters in absolute terms.
    """
    parts: list[str] = [resume.personal_info.summary]
    for w in resume.work_experience:
        parts.extend(w.bullets)
        parts.append(w.company)
        parts.append(w.position)
    for p in resume.project_experience:
        parts.extend(p.bullets)
    for e in resume.education:
        parts.append(e.school)
    text = " ".join(p for p in parts if p)

    cjk = len(_CJK_RE.findall(text))
    ascii_letters = len(_ASCII_LETTER_RE.findall(text))
    letter_like = cjk + ascii_letters
    ratio = (cjk / letter_like) if letter_like else 0.0

    lang = "zh" if (ratio > 0.15 or cjk > 30) else "en"
    logger.debug(
        "detect_language: cjk=%d ascii_letters=%d ratio=%.3f -> %s",
        cjk, ascii_letters, ratio, lang,
    )
    return lang
