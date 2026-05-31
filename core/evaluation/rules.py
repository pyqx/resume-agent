"""RuleEvaluator — local, millisecond-level quality checks on resume content."""

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum

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

    @property
    def critical_count(self) -> int:
        return sum(1 for v in self.violations if v.severity == Severity.CRITICAL)

    @property
    def error_count(self) -> int:
        return sum(1 for v in self.violations if v.severity == Severity.ERROR)

    @property
    def warning_count(self) -> int:
        return sum(1 for v in self.violations if v.severity == Severity.WARNING)


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

# Common tech stack casing fixes
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


class RuleEvaluator:
    """Run all rule-based quality checks on a resume."""

    def evaluate(self, resume: ResumeData) -> RuleResult:
        violations: list[Violation] = []

        violations.extend(self._check_weak_verbs(resume))
        violations.extend(self._check_sensitive_info(resume))
        violations.extend(self._check_page_length(resume))
        violations.extend(self._check_cjk_spacing(resume))
        violations.extend(self._check_date_consistency(resume))
        violations.extend(self._check_tech_casing(resume))

        # Deduct points: critical=-2, error=-1, warning=-0.5, info=-0.2
        deductions = (
            sum(2.0 for v in violations if v.severity == Severity.CRITICAL) +
            sum(1.0 for v in violations if v.severity == Severity.ERROR) +
            sum(0.5 for v in violations if v.severity == Severity.WARNING) +
            sum(0.2 for v in violations if v.severity == Severity.INFO)
        )
        score = max(0.0, min(10.0, 10.0 - deductions))

        return RuleResult(violations=violations, score=round(score, 1))

    def _check_weak_verbs(self, resume: ResumeData) -> list[Violation]:
        violations = []
        for work in resume.work_experience:
            for bullet in work.bullets:
                for weak in WEAK_VERBS_CN:
                    if weak in bullet:
                        suggestion = STRONG_VERBS_MAP.get(weak, "更强的动词")
                        violations.append(Violation(
                            rule="weak_verb",
                            severity=Severity.WARNING,
                            location=f"工作经历/{work.company}/{work.position}",
                            message=f"弱动词 '{weak}' 在: '{bullet[:40]}...'",
                            suggestion=f"建议替换为: {suggestion}",
                        ))
                for weak in WEAK_VERBS_EN:
                    if weak.lower() in bullet.lower():
                        suggestion = STRONG_VERBS_MAP.get(weak, "stronger verb")
                        violations.append(Violation(
                            rule="weak_verb",
                            severity=Severity.WARNING,
                            location=f"Work/{work.company}/{work.position}",
                            message=f"Weak verb '{weak}' in: '{bullet[:40]}...'",
                            suggestion=f"Consider replacing with: {suggestion}",
                        ))
        return violations

    def _check_sensitive_info(self, resume: ResumeData) -> list[Violation]:
        violations = []
        all_text = str(resume.model_dump())

        for pattern, label, severity in SENSITIVE_PATTERNS:
            matches = re.findall(pattern, all_text)
            for match in matches:
                violations.append(Violation(
                    rule="sensitive_info",
                    severity=severity,
                    location="简历全文",
                    message=f"检测到可能的{label}: {match[:20]}...",
                    suggestion=f"建议移除{label}，仅保留必要联系方式（如邮箱、LinkedIn）",
                ))
        return violations

    def _check_page_length(self, resume: ResumeData) -> list[Violation]:
        violations = []
        # Estimate length: ~800 chars per page for Chinese
        total_chars = len(str(resume.model_dump()))
        estimated_pages = total_chars / 800

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

    def _check_cjk_spacing(self, resume: ResumeData) -> list[Violation]:
        violations = []
        all_text = str(resume.model_dump())

        # Chinese immediately followed by Latin characters without space
        cjk_latin_no_space = re.finditer(
            r'[一-鿿぀-ゟ゠-ヿ](?=[a-zA-Z0-9])',
            all_text,
        )
        count = 0
        for _ in cjk_latin_no_space:
            count += 1

        if count > 3:
            violations.append(Violation(
                rule="cjk_spacing",
                severity=Severity.INFO,
                location="全文",
                message=f"检测到 {count} 处中英文之间缺少空格",
                suggestion="中英文混排时，中文字符和英文字母/数字之间应加一个空格",
            ))

        return violations

    def _check_date_consistency(self, resume: ResumeData) -> list[Violation]:
        violations = []
        today = date.today()

        for i, work in enumerate(resume.work_experience):
            if work.start_date and work.end_date:
                if work.start_date > work.end_date:
                    violations.append(Violation(
                        rule="date_consistency",
                        severity=Severity.ERROR,
                        location=f"工作经历/{work.company}",
                        message=f"开始日期 ({work.start_date}) 晚于结束日期 ({work.end_date})",
                        suggestion="请检查并修正日期",
                    ))
                span_days = (work.end_date - work.start_date).days
                if span_days < 30 and not work.is_current:
                    violations.append(Violation(
                        rule="date_consistency",
                        severity=Severity.WARNING,
                        location=f"工作经历/{work.company}",
                        message=f"工作时间不足1个月 ({span_days}天)",
                        suggestion="如果是实习/试用期，建议注明",
                    ))

            # Check for future dates
            if work.start_date and work.start_date > today:
                violations.append(Violation(
                    rule="date_consistency",
                    severity=Severity.ERROR,
                    location=f"工作经历/{work.company}",
                    message=f"开始日期 ({work.start_date}) 是未来日期",
                    suggestion="请修正为实际日期",
                ))

        # Check for overlapping periods
        periods = []
        for work in resume.work_experience:
            if work.start_date:
                periods.append((work.start_date, work.end_date or today, work.company))
        periods.sort(key=lambda x: x[0])

        for i in range(len(periods) - 1):
            if periods[i][1] and periods[i+1][0] and periods[i][1] > periods[i+1][0]:
                violations.append(Violation(
                    rule="date_overlap",
                    severity=Severity.WARNING,
                    location=f"工作经历/{periods[i][2]} 与 {periods[i+1][2]}",
                    message="两段工作经历的时间有重叠",
                    suggestion="请检查是否为同时做两份工作，或修正日期",
                ))

        return violations

    def _check_tech_casing(self, resume: ResumeData) -> list[Violation]:
        violations = []
        all_text = str(resume.model_dump())

        for wrong, correct in TECH_CASING.items():
            pattern = re.compile(re.escape(wrong), re.IGNORECASE)
            if pattern.search(all_text):
                # Check if the correctly cased version is already present
                if correct.lower() != wrong.lower() and correct not in all_text:
                    violations.append(Violation(
                        rule="tech_casing",
                        severity=Severity.INFO,
                        location="全文",
                        message=f"'{wrong}' 应写作 '{correct}'",
                        suggestion=f"技术名词大小写规范: {correct}",
                    ))

        return violations
