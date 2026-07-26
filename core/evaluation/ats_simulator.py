"""ATSSimulator — simulate how common ATS systems parse a resume."""

import re
from dataclasses import asdict, dataclass, field

from core.evaluation.render import resume_to_text
from core.resume.schema import ResumeData


@dataclass
class ATSFieldResult:
    field: str
    found: bool
    value: str = ""
    issues: list[str] = field(default_factory=list)


@dataclass
class ATSResult:
    """Legacy container kept for backward-compatible imports.

    ``ATSSimulator.simulate()`` now returns a plain JSON-serializable dict
    with the same keys; this dataclass remains only because other modules
    import it from ``core.evaluation``.
    """

    fields: list[ATSFieldResult] = field(default_factory=list)
    format_issues: list[str] = field(default_factory=list)
    keyword_coverage_pct: float | None = 0.0
    score: float = 10.0  # 0-10


_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
# Chinese mobile (optionally prefixed with +86/86, separators stripped first).
_CN_PHONE_RE = re.compile(r"(?:\+?86)?1[3-9]\d{9}")
# Loose international format: +country-code and 7-15 digits/separators.
_INTL_PHONE_RE = re.compile(r"\+?\d[\d\s\-]{6,14}")
# Control characters (tab excluded — it has a dedicated check; \n \r are fine).
_CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
# Replacement char, stray BOM, private-use area — telltale mojibake.
_MOJIBAKE_RE = re.compile(r"[\ufffd\ufeff\ue000-\uf8ff]")


class ATSSimulator:
    """Simulate ATS resume parsing to detect issues before real submission.

    Checks:
    - Contact information extractability (name/email/phone, structured fields)
    - Education / latest job / skills presence (structured fields)
    - Plain-text format issues on the rendered text (tabs, control chars, mojibake)
    - Target-keyword coverage — only when target keywords are provided
    """

    FIELD_COUNT = 6

    def simulate(self, resume: ResumeData, target_keywords: list[str] | None = None) -> dict:
        """Run the ATS simulation. Returns a JSON-serializable dict.

        Score composition (total is naturally within 0-10, no clamp needed):
        - with target keywords:    fields 0-4, format 0-3, keywords 0-3
        - without target keywords: fields 0-6, format 0-4, keyword dimension
          is skipped (``keyword_coverage_pct`` is None) and its weight is
          redistributed to the other two.
        """
        text = resume_to_text(resume)

        fields = [
            self._check_name(resume),
            self._check_email(resume),
            self._check_phone(resume),
            self._check_education(resume),
            self._check_latest_job(resume),
            self._check_skills(resume),
        ]
        fields_found = sum(1 for f in fields if f.found)
        format_issues = self._check_format(text)

        keywords: list[str] = []
        if target_keywords:
            # De-duplicate, preserve order, drop blanks.
            keywords = [
                k for k in dict.fromkeys(kw.strip() for kw in target_keywords if kw and kw.strip())
            ]

        note = None
        if keywords:
            text_lower = text.lower()
            matched = [kw for kw in keywords if kw.lower() in text_lower]
            missing = [kw for kw in keywords if kw.lower() not in text_lower]
            coverage: float | None = round(len(matched) / len(keywords) * 100, 1)
            field_score = fields_found / len(fields) * 4  # 0-4
            format_score = max(0.0, 3.0 - len(format_issues))  # 0-3
            keyword_score: float | None = round(coverage / 100 * 3, 2)  # 0-3
        else:
            matched, missing = [], []
            coverage = None
            keyword_score = None
            field_score = fields_found / len(fields) * 6  # 0-6
            format_score = max(0.0, 4.0 - len(format_issues))  # 0-4
            note = "no target keywords provided"

        score = round(field_score + format_score + (keyword_score or 0.0), 1)

        result = {
            "score": score,
            "fields": [asdict(f) for f in fields],
            "fields_found": fields_found,
            "fields_total": len(fields),
            "format_issues": format_issues,
            "keyword_coverage_pct": coverage,
            "matched_keywords": matched,
            "missing_keywords": missing,
            "breakdown": {
                "field_score": round(field_score, 2),
                "format_score": round(format_score, 2),
                "keyword_score": keyword_score,
            },
        }
        if note:
            result["note"] = note
        return result

    # ── Field checks (structured data, not text regex) ─────

    def _check_name(self, resume: ResumeData) -> ATSFieldResult:
        name = resume.personal_info.full_name.strip()
        return ATSFieldResult(
            field="name",
            found=bool(name),
            value=name,
            issues=[] if name else ["未填写姓名"],
        )

    def _check_email(self, resume: ResumeData) -> ATSFieldResult:
        email = resume.personal_info.email.strip()
        if not email:
            return ATSFieldResult(field="email", found=False, issues=["未填写邮箱地址"])
        if not _EMAIL_RE.fullmatch(email):
            return ATSFieldResult(
                field="email", found=False, value=email,
                issues=["邮箱格式可能无法被ATS识别"],
            )
        return ATSFieldResult(field="email", found=True, value=email)

    def _check_phone(self, resume: ResumeData) -> ATSFieldResult:
        phone = resume.personal_info.phone.strip()
        if not phone:
            return ATSFieldResult(field="phone", found=False, issues=["未填写手机号"])
        compact = re.sub(r"[\s\-]", "", phone)
        valid = bool(_CN_PHONE_RE.fullmatch(compact)) or bool(_INTL_PHONE_RE.fullmatch(phone))
        if not valid:
            return ATSFieldResult(
                field="phone", found=False, value=phone,
                issues=["手机号格式可能无法被ATS识别"],
            )
        return ATSFieldResult(field="phone", found=True, value=phone)

    def _check_education(self, resume: ResumeData) -> ATSFieldResult:
        found = len(resume.education) > 0
        value = resume.education[0].school if found else ""
        return ATSFieldResult(
            field="education",
            found=found,
            value=value,
            issues=[] if found else ["未检测到教育经历"],
        )

    def _check_latest_job(self, resume: ResumeData) -> ATSFieldResult:
        found = len(resume.work_experience) > 0
        value = ""
        if found:
            latest = resume.work_experience[0]
            value = " ".join(x for x in (latest.company, latest.position) if x)
        return ATSFieldResult(
            field="latest_job",
            found=found,
            value=value,
            issues=[] if found else ["未检测到工作经历"],
        )

    def _check_skills(self, resume: ResumeData) -> ATSFieldResult:
        count = len(resume.skills)
        return ATSFieldResult(
            field="skills",
            found=count > 0,
            value=f"{count} skills",
            issues=[] if count > 0 else ["未检测到技能列表"],
        )

    # ── Format checks (rendered text) ──────────────────────

    def _check_format(self, text: str) -> list[str]:
        issues = []

        if "\t" in text:
            issues.append("包含制表符，可能干扰ATS解析")

        control_count = len(_CONTROL_CHARS_RE.findall(text))
        if control_count:
            issues.append(f"包含 {control_count} 个控制字符，可能干扰ATS解析")

        mojibake = sorted(set(_MOJIBAKE_RE.findall(text)))
        if mojibake:
            shown = " ".join(repr(c) for c in mojibake[:5])
            issues.append(f"包含疑似乱码字符: {shown}")

        if len(text) < 100:
            issues.append("简历内容过短，ATS可能认为不完整")

        return issues
