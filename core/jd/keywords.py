"""Keyword coverage between JD keywords and resume content.

Shared by core.jd.matcher and the JD API routes. The resume is rendered to
plain text (field values only) before matching, so schema field names like
"skills"/"description" can never count as keyword hits (the old
implementation matched against a model_dump JSON string and had that bug).
"""

import re

from core.resume.schema import ResumeData


def _render_resume_text(resume: ResumeData) -> str:
    """Render resume content (values, not field names) as plain text."""
    parts: list[str] = []

    if resume.personal_info.summary:
        parts.append(resume.personal_info.summary)
    if resume.target_position:
        parts.append(resume.target_position)
    if resume.target_industry:
        parts.append(resume.target_industry)

    for w in resume.work_experience:
        parts.extend(v for v in (w.position, w.company, w.description) if v)
        parts.extend(b for b in w.bullets if b)

    for p in resume.project_experience:
        parts.extend(v for v in (p.name, p.role, p.description) if v)
        parts.extend(t for t in p.technologies if t)
        parts.extend(b for b in p.bullets if b)

    for s in resume.skills:
        if s.name:
            parts.append(s.name)

    for e in resume.education:
        parts.extend(v for v in (e.school, e.degree, e.major, e.description) if v)

    return "\n".join(parts)


def _ascii_pattern(keyword: str) -> re.Pattern:
    r"""\b-bounded regex for an ASCII keyword.

    - A boundary is only added on sides where the keyword edge is a word
      character, so symbol-edged keywords like "c++" or ".net" still match
      ("\bc\+\+\b" would never match "c++" at end of text).
    - Compiled with re.ASCII so \b treats CJK characters as non-word:
      "java" must match inside "精通Java开发" while still not matching
      "javascript" (under Unicode \b, the CJK neighbour would suppress the
      boundary and cause a false miss).
    """
    prefix = r"\b" if re.match(r"\w", keyword[0], re.ASCII) else ""
    suffix = r"\b" if re.match(r"\w", keyword[-1], re.ASCII) else ""
    return re.compile(prefix + re.escape(keyword) + suffix, re.ASCII)


def compute_keyword_coverage(jd_keywords: list[str], resume: ResumeData) -> dict:
    """返回 {"coverage_rate": float, "matched": list[str], "missing": list[str]}

    - coverage_rate 为 0-100 的百分比(保留 1 位小数)。
    - ASCII 关键词用词边界正则匹配(避免 "java" 命中 "javascript");
      含中文等非 ASCII 字符的关键词用子串匹配。
    - 大小写不敏感;关键词先去空白、去重(不区分大小写)。
    """
    seen: set[str] = set()
    keywords: list[str] = []
    for raw in jd_keywords or []:
        kw = str(raw).strip()
        if not kw or kw.lower() in seen:
            continue
        seen.add(kw.lower())
        keywords.append(kw)

    if not keywords:
        return {"coverage_rate": 0.0, "matched": [], "missing": []}

    resume_text = _render_resume_text(resume).lower()

    matched: list[str] = []
    missing: list[str] = []
    for kw in keywords:
        low = kw.lower()
        if low.isascii():
            hit = _ascii_pattern(low).search(resume_text) is not None
        else:
            hit = low in resume_text
        (matched if hit else missing).append(kw)

    return {
        "coverage_rate": round(len(matched) / len(keywords) * 100, 1),
        "matched": matched,
        "missing": missing,
    }
