"""ATSSimulator — simulate how common ATS systems parse a resume."""

import re
from dataclasses import dataclass, field


@dataclass
class ATSFieldResult:
    field: str
    found: bool
    value: str = ""
    issues: list[str] = field(default_factory=list)


@dataclass
class ATSResult:
    parsable: bool = True
    fields: list[ATSFieldResult] = field(default_factory=list)
    format_issues: list[str] = field(default_factory=list)
    keyword_coverage_pct: float = 0.0
    score: float = 10.0  # 0-10

    @property
    def critical_fields_found(self) -> int:
        return sum(1 for f in self.fields if f.found)

    @property
    def total_critical_fields(self) -> int:
        return len(self.fields)


class ATSSimulator:
    """Simulate ATS resume parsing to detect issues before real submission.

    Checks for:
    - Contact information extractability
    - Education field detection
    - Table/image interference
    - Keyword coverage
    """

    # Fields ATS systems typically extract
    CRITICAL_FIELDS = [
        "name", "email", "phone", "education", "latest_job", "skills",
    ]

    # ATS keyword categories
    COMMON_ATS_KEYWORDS = {
        "technical": [
            "python", "java", "javascript", "typescript", "go", "rust", "c++",
            "react", "vue", "angular", "node", "django", "spring", "flask",
            "sql", "nosql", "mongodb", "postgresql", "mysql", "redis",
            "aws", "azure", "gcp", "docker", "kubernetes", "ci/cd",
            "git", "linux", "agile", "scrum", "rest", "graphql", "api",
        ],
        "soft": [
            "leadership", "communication", "teamwork", "problem-solving",
            "analytical", "project management", "mentoring",
            "领导力", "沟通能力", "沟通", "团队合作", "团队协作", "解决问题",
            "分析能力", "项目管理", "指导", "协调", "组织能力",
        ],
        "education": [
            "bachelor", "master", "phd", "mba", "degree", "university",
            "本科", "硕士", "博士", "学士", "研究生", "学位", "大学", "学院",
            "大专", "高中", "学历",
        ],
    }

    def simulate(self, resume_text: str, target_keywords: list[str] | None = None) -> ATSResult:
        """Run ATS simulation on the resume text."""
        result = ATSResult()

        # Check each critical field
        result.fields = [
            self._check_name(resume_text),
            self._check_email(resume_text),
            self._check_phone(resume_text),
            self._check_education(resume_text),
            self._check_latest_job(resume_text),
            self._check_skills(resume_text),
        ]

        # Format issues
        result.format_issues = self._check_format(resume_text)

        # Keyword coverage
        result.keyword_coverage_pct = self._check_keyword_coverage(
            resume_text.lower(), target_keywords
        )

        # Score
        field_score = sum(1 for f in result.fields if f.found) / len(result.fields) * 7
        format_score = (5 - min(5, len(result.format_issues))) * 0.6
        keyword_score = min(3, result.keyword_coverage_pct / 33)

        result.score = round(field_score + format_score + keyword_score, 1)
        result.score = max(0.0, min(10.0, result.score))

        return result

    def _check_name(self, text: str) -> ATSFieldResult:
        # Look for a name near the top (first 200 chars)
        top_section = text[:200]
        has_name = bool(re.search(r'[一-鿿]{2,4}', top_section)) or \
                   bool(re.search(r'[A-Z][a-z]+ [A-Z][a-z]+', top_section))
        return ATSFieldResult(
            field="name",
            found=has_name,
            issues=[] if has_name else ["简历开头未检测到姓名"],
        )

    def _check_email(self, text: str) -> ATSFieldResult:
        match = re.search(r'[\w.+-]+@[\w-]+\.[\w.-]+', text)
        return ATSFieldResult(
            field="email",
            found=bool(match),
            value=match.group() if match else "",
            issues=[] if match else ["未检测到邮箱地址"],
        )

    def _check_phone(self, text: str) -> ATSFieldResult:
        match = re.search(r'(?:\+86|86)?1[3-9]\d{9}', text)
        return ATSFieldResult(
            field="phone",
            found=bool(match),
            value=match.group() if match else "",
            issues=[] if match else ["未检测到手机号"],
        )

    def _check_education(self, text: str) -> ATSFieldResult:
        edu_keywords = [
            "大学", "学院", "university", "college", "本科", "硕士", "博士",
            "bachelor", "master", "phd", "degree",
        ]
        found = any(kw in text.lower() for kw in edu_keywords)
        return ATSFieldResult(
            field="education",
            found=found,
            issues=[] if found else ["未检测到教育经历"],
        )

    def _check_latest_job(self, text: str) -> ATSFieldResult:
        job_keywords = ["公司", "corporation", "inc", "ltd", "工作经历", "experience"]
        found = any(kw in text.lower() for kw in job_keywords)
        return ATSFieldResult(
            field="latest_job",
            found=found,
            issues=[] if found else ["未检测到工作经历"],
        )

    def _check_skills(self, text: str) -> ATSFieldResult:
        # Check if at least 3 technical skills are present
        text_lower = text.lower()
        found_skills = [kw for kw in self.COMMON_ATS_KEYWORDS["technical"] if kw in text_lower]
        has_skills = len(found_skills) >= 3
        return ATSFieldResult(
            field="skills",
            found=has_skills,
            value=f"{len(found_skills)} skills detected",
            issues=[f"技能关键词较少 ({len(found_skills)}个)"] if not has_skills else [],
        )

    def _check_format(self, text: str) -> list[str]:
        issues = []

        # Check for common format problems
        if "\t" in text:
            issues.append("包含制表符，可能干扰ATS解析")

        # Check for non-ASCII friendly characters
        special_chars = re.findall(r'[^\x00-\x7F一-鿿\s\w,.!?;:()\[\]@#/-]', text)
        if special_chars:
            issues.append(f"包含特殊字符可能无法被ATS识别: {special_chars[:5]}")

        # Check if there's enough text
        if len(text) < 100:
            issues.append("简历内容过短，ATS可能认为不完整")

        return issues

    def _check_keyword_coverage(self, text: str, target_keywords: list[str] | None = None) -> float:
        if target_keywords:
            keywords = set(k.lower() for k in target_keywords)
        else:
            keywords = set(self.COMMON_ATS_KEYWORDS["technical"] + self.COMMON_ATS_KEYWORDS["soft"])

        if not keywords:
            return 100.0

        matched = sum(1 for kw in keywords if kw in text)
        return round(matched / len(keywords) * 100, 1)
