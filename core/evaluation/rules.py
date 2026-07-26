"""RuleEvaluator — local, millisecond-level quality checks on resume content.

All text-based checks run on ``resume_to_text(resume)`` (the rendered
plain text) or directly on structured fields — never on the Python dict
repr of the model, which used to inflate page estimates and misfire the
spacing/sensitive-info/casing checks on UUIDs and field names.
"""

import re
from dataclasses import dataclass, field
from datetime import date
from enum import Enum

from core.evaluation.render import resume_to_text
from core.resume.schema import ResumeData


class Severity(str, Enum):
    CRITICAL = "critical"
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass
class Violation:
    rule: str
    severity: Severity
    location: str = ""
    message: str = ""
    suggestion: str = ""


@dataclass
class RuleResult:
    violations: list[Violation] = field(default_factory=list)
    score: float = 10.0  # 0-10 scale


# Known weak verbs in Chinese and English
WEAK_VERBS_CN = [
    "负责", "参与", "协助", "进行", "完成", "处理", "做了", "做了些",
    "担任", "承担", "从事",
]
WEAK_VERBS_EN = [
    "responsible for", "participated in", "assisted with", "helped with",
    "was involved in", "worked on", "did", "handled",
]

# Stronger alternatives
STRONG_VERBS_MAP = {
    "负责": "主导/设计/制定",
    "参与": "协同推进/牵头",
    "协助": "支持/配合",
    "进行": "执行/实施/推动",
    "完成": "交付/达成/实现",
    "做了": "构建/开发/打造",
    "处理": "优化/重构/解决",
    "responsible for": "led / architected / drove",
    "participated in": "co-led / championed",
    "assisted with": "enabled / supported",
    "worked on": "built / delivered / shipped",
}

# Canonical casing for common tech terms. Keys are matched case-insensitively
# as standalone words in the rendered text; any occurrence whose exact
# spelling differs from the canonical value is flagged.
TECH_CASING = {
    "react.js": "React",
    "reactjs": "React",
    "vue.js": "Vue.js",
    "vuejs": "Vue.js",
    "node.js": "Node.js",
    "nodejs": "Node.js",
    "github": "GitHub",
    "gitlab": "GitLab",
    "docker": "Docker",
    "kubernetes": "Kubernetes",
    "postgresql": "PostgreSQL",
    "mongodb": "MongoDB",
    "redis": "Redis",
    "typescript": "TypeScript",
    "javascript": "JavaScript",
    "python": "Python",
    "java": "Java",
    "golang": "Go",
    "next.js": "Next.js",
    "nextjs": "Next.js",
}

SENSITIVE_PATTERNS = [
    (r'\d{17}[\dXx]', "身份证号", Severity.CRITICAL),
    (r'(?:月薪|年薪|薪资|工资|salary)[：:\s]*[\d,.]+[万kwK]?', "薪资信息", Severity.CRITICAL),
    (r'(?:地址|住址)[：:\s]*.{5,}', "详细地址", Severity.WARNING),
    (r'(?:1[3-9]\d{9})', "手机号", Severity.WARNING),
]

# Deduction per violation, by severity (four-level weights preserved).
SEVERITY_DEDUCTIONS = {
    Severity.CRITICAL: 2.0,
    Severity.ERROR: 1.0,
    Severity.WARNING: 0.5,
    Severity.INFO: 0.2,
}

# Per-rule deduction caps so one noisy category cannot zero the whole score
# (e.g. a Chinese resume full of "负责" bullets). Rules absent here have no cap.
RULE_DEDUCTION_CAPS = {
    "weak_verb": 2.0,
    "sensitive_info": 2.0,
}


class RuleEvaluator:
    """Run all rule-based quality checks on a resume."""

    def evaluate(self, resume: ResumeData) -> RuleResult:
        text = resume_to_text(resume)
        violations: list[Violation] = []

        violations.extend(self._check_weak_verbs(resume))
        violations.extend(self._check_sensitive_info(resume))
        violations.extend(self._check_page_length(resume, text))
        violations.extend(self._check_cjk_spacing(text))
        violations.extend(self._check_date_consistency(resume))
        violations.extend(self._check_tech_casing(text))

        # Sum deductions per rule, apply per-rule caps, then subtract.
        deduction_by_rule: dict[str, float] = {}
        for v in violations:
            deduction_by_rule[v.rule] = (
                deduction_by_rule.get(v.rule, 0.0)
                + SEVERITY_DEDUCTIONS.get(v.severity, 0.0)
            )
        total = sum(
            min(deduction, RULE_DEDUCTION_CAPS.get(rule, deduction))
            for rule, deduction in deduction_by_rule.items()
        )
        score = max(0.0, 10.0 - total)

        return RuleResult(violations=violations, score=round(score, 1))

    # ── Shared iteration over free-text content ────────────

    @staticmethod
    def _iter_experience_texts(resume: ResumeData):
        """Yield (location, text) for every bullet/description of work and project entries."""
        for work in resume.work_experience:
            label = "/".join(x for x in ("工作经历", work.company, work.position) if x)
            for bullet in work.bullets:
                yield label, bullet
            if work.description:
                yield label, work.description
        for proj in resume.project_experience:
            label = "/".join(x for x in ("项目经历", proj.name) if x)
            for bullet in proj.bullets:
                yield label, bullet
            if proj.description:
                yield label, proj.description

    # ── Weak verbs ─────────────────────────────────────────

    @staticmethod
    def _first_weak_verb(text: str) -> str | None:
        """Earliest weak verb in the text, or None (at most one hit per unit)."""
        best: str | None = None
        best_pos = len(text) + 1
        for weak in WEAK_VERBS_CN:
            pos = text.find(weak)
            if 0 <= pos < best_pos:
                best, best_pos = weak, pos
        lower = text.lower()
        for weak in WEAK_VERBS_EN:
            m = re.search(r"\b" + re.escape(weak) + r"\b", lower)
            if m and m.start() < best_pos:
                best, best_pos = weak, m.start()
        return best

    def _check_weak_verbs(self, resume: ResumeData) -> list[Violation]:
        """Scan work AND project bullets/descriptions; max 1 violation per text unit."""
        violations = []
        for location, text in self._iter_experience_texts(resume):
            weak = self._first_weak_verb(text)
            if weak is None:
                continue
            suggestion = STRONG_VERBS_MAP.get(weak, "更强的动词 / a stronger verb")
            violations.append(Violation(
                rule="weak_verb",
                severity=Severity.WARNING,
                location=location,
                message=f"弱动词 '{weak}' 在: '{text[:40]}...'",
                suggestion=f"建议替换为: {suggestion}",
            ))
        return violations

    # ── Sensitive info ─────────────────────────────────────

    def _check_sensitive_info(self, resume: ResumeData) -> list[Violation]:
        """Scan free-text content only.

        personal_info.phone/email are expected fields and are never flagged;
        only phone numbers / ID numbers / salary figures that leak into
        bullets, descriptions or the summary are reported.
        """
        violations = []

        segments = list(self._iter_experience_texts(resume))
        if resume.personal_info.summary:
            segments.append(("个人概述", resume.personal_info.summary))
        for edu in resume.education:
            if edu.description:
                label = "/".join(x for x in ("教育经历", edu.school) if x)
                segments.append((label, edu.description))

        for location, text in segments:
            for pattern, label, severity in SENSITIVE_PATTERNS:
                for match in re.findall(pattern, text):
                    violations.append(Violation(
                        rule="sensitive_info",
                        severity=severity,
                        location=location,
                        message=f"检测到可能的{label}: {str(match)[:20]}...",
                        suggestion=f"建议移除{label}，仅保留必要联系方式（如邮箱、LinkedIn）",
                    ))
        return violations

    # ── Page length ────────────────────────────────────────

    def _check_page_length(self, resume: ResumeData, text: str) -> list[Violation]:
        violations = []
        # Estimate length on rendered text: ~800 chars per page for Chinese.
        estimated_pages = len(text) / 800

        # Count work experiences to estimate seniority
        work_count = len(resume.work_experience)
        is_new_grad = work_count <= 1 and all(not w.bullets for w in resume.work_experience)

        if is_new_grad and estimated_pages > 1.5:
            violations.append(Violation(
                rule="page_length",
                severity=Severity.WARNING,
                location="全文",
                message=f"简历约{estimated_pages:.1f}页，应届生建议控制在1页以内",
                suggestion="考虑缩减课程描述、合并相似经历、减小行间距",
            ))
        elif work_count <= 3 and estimated_pages > 2.5:
            violations.append(Violation(
                rule="page_length",
                severity=Severity.INFO,
                location="全文",
                message=f"简历约{estimated_pages:.1f}页，社招建议控制在2页以内",
                suggestion="标记低价值的早期经历，考虑裁剪",
            ))

        return violations

    # ── CJK/Latin spacing ──────────────────────────────────

    def _check_cjk_spacing(self, text: str) -> list[Violation]:
        violations = []
        # Chinese immediately followed by Latin characters without space
        count = len(re.findall(r'[一-鿿぀-ゟ゠-ヿ](?=[a-zA-Z0-9])', text))
        if count > 3:
            violations.append(Violation(
                rule="cjk_spacing",
                severity=Severity.INFO,
                location="全文",
                message=f"检测到 {count} 处中英文之间缺少空格",
                suggestion="中英文混排时，中文字符和英文字母/数字之间应加一个空格",
            ))
        return violations

    # ── Date consistency ───────────────────────────────────

    def _check_date_consistency(self, resume: ResumeData) -> list[Violation]:
        violations = []
        today = date.today()

        # Start/end inversion: work, education AND projects.
        sections = (
            [("工作经历", w, w.company) for w in resume.work_experience]
            + [("教育经历", e, e.school) for e in resume.education]
            + [("项目经历", p, p.name) for p in resume.project_experience]
        )
        for section, entry, name in sections:
            if entry.start_date and entry.end_date and entry.start_date > entry.end_date:
                violations.append(Violation(
                    rule="date_consistency",
                    severity=Severity.ERROR,
                    location=f"{section}/{name}",
                    message=f"开始日期 ({entry.start_date}) 晚于结束日期 ({entry.end_date})",
                    suggestion="请检查并修正日期",
                ))

        for work in resume.work_experience:
            # Tenure < 30 days — meaningless for year-only (approximate) dates.
            if (
                work.start_date and work.end_date
                and not work.dates_approximate
                and not work.is_current
                and work.start_date <= work.end_date
            ):
                span_days = (work.end_date - work.start_date).days
                if span_days < 30:
                    violations.append(Violation(
                        rule="date_consistency",
                        severity=Severity.WARNING,
                        location=f"工作经历/{work.company}",
                        message=f"工作时间不足1个月 ({span_days}天)",
                        suggestion="如果是实习/试用期，建议注明",
                    ))

            # Future start dates
            if work.start_date and work.start_date > today:
                violations.append(Violation(
                    rule="date_consistency",
                    severity=Severity.ERROR,
                    location=f"工作经历/{work.company}",
                    message=f"开始日期 ({work.start_date}) 是未来日期",
                    suggestion="请修正为实际日期",
                ))

        # Overlapping work periods. Skip entries whose dates were fabricated
        # from year-only sources; two concurrent (is_current) jobs are legal.
        periods = [
            (w.start_date, w.end_date or today, w.company, w.is_current)
            for w in resume.work_experience
            if w.start_date and not w.dates_approximate
        ]
        periods.sort(key=lambda p: p[0])
        for prev, nxt in zip(periods, periods[1:]):
            if prev[3] and nxt[3]:
                continue  # both current — moonlighting/part-time is legitimate
            if prev[1] > nxt[0]:
                violations.append(Violation(
                    rule="date_overlap",
                    severity=Severity.WARNING,
                    location=f"工作经历/{prev[2]} 与 {nxt[2]}",
                    message="两段工作经历的时间有重叠",
                    suggestion="请检查是否为同时做两份工作，或修正日期",
                ))

        return violations

    # ── Tech-term casing ───────────────────────────────────

    def _check_tech_casing(self, text: str) -> list[Violation]:
        """Flag standalone occurrences whose casing differs from the canonical form.

        Runs a case-insensitive standalone-word search per known term on the
        rendered text, then compares each hit case-sensitively — so
        "python" -> "Python" (same spelling, different case) is caught.
        Boundaries are ASCII-based (\\b treats CJK as word chars, which would
        miss "用docker部署"). URL/email/compound contexts (github.com,
        docker-compose) are skipped.
        """
        violations = []
        for variant, canonical in TECH_CASING.items():
            pattern = re.compile(
                r"(?<![A-Za-z0-9_])" + re.escape(variant) + r"(?![A-Za-z0-9_])",
                re.IGNORECASE,
            )
            seen_forms: set[str] = set()
            for m in pattern.finditer(text):
                found = m.group(0)
                if found == canonical or found in seen_forms:
                    continue
                start, end = m.start(), m.end()
                prev_ch = text[start - 1] if start > 0 else ""
                next_ch = text[end] if end < len(text) else ""
                next_next = text[end + 1] if end + 1 < len(text) else ""
                if prev_ch in "./@:-":
                    continue  # domain, path, mention or compound name
                if next_ch in ".-" and next_next.isalnum():
                    continue  # github.com, docker-compose, ...
                seen_forms.add(found)

                line_start = text.rfind("\n", 0, start) + 1
                line_end = text.find("\n", start)
                line = text[line_start : line_end if line_end != -1 else len(text)].strip()
                violations.append(Violation(
                    rule="tech_casing",
                    severity=Severity.INFO,
                    location=line[:40],
                    message=f"'{found}' 应写作 '{canonical}'",
                    suggestion=f"技术名词大小写规范: {canonical}",
                ))
        return violations
