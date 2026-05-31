"""JDSignalDetector — rule-based detection of hidden signals in job descriptions."""

import re
from core.resume.schema import JDSignal


# Known signal phrases and their interpretations
SIGNAL_PATTERNS = [
    ("fast.paced|快速迭代|节奏快", "高频度需求变更，可能需要频繁加班", "warning"),
    ("wear.many.hats|身兼多职|多面手", "团队配置不齐，一人需承担多个岗位职责", "warning"),
    ("从0到1|zero.to.one|from.scratch", "新业务线，团队/流程可能不成熟", "info"),
    ("rockstar|ninja|guru|大牛|大神", "招聘文化不专业，可能对技术有不切实际期望", "caution"),
    ("competitive.salary|薪资有竞争力", "实际薪资可能低于市场水平", "warning"),
    ("unlimited.PTO|无限休假", "可能没有结构化的休假制度", "info"),
    ("startup.mindset|创业心态", "可能需要超时工作，且不确定性高", "warning"),
    ("embrace.change|拥抱变化", "方向可能频繁调整，需要较强适应性", "info"),
    ("result.oriented|结果导向", "面试时会追问量化数据，绩效压力可能较大", "info"),
    ("fight.for|fight.for.it|狼性", "竞争激烈的内部文化", "caution"),
    ("flat.structure|扁平化", "可能晋升路径不清晰", "info"),
    ("early.employee|早期员工", "期权可能有价值，但风险也高", "info"),
    ("wearing.multiple.hats", "职责范围可能超出职位描述", "warning"),
    ("self.starter|自驱", "可能缺乏系统的新人培训和指导", "info"),
]


class SignalDetector:
    """Detect hidden signals and subtext in JD text."""

    def detect(self, jd_text: str) -> list[JDSignal]:
        """Scan JD text for known signal phrases and return interpretations."""
        signals: list[JDSignal] = []
        seen_phrases: set[str] = set()

        for pattern, interpretation, risk_level in SIGNAL_PATTERNS:
            match = re.search(pattern, jd_text, re.IGNORECASE)
            if match and match.group() not in seen_phrases:
                phrase = match.group()
                seen_phrases.add(phrase)
                signals.append(JDSignal(
                    phrase=phrase,
                    interpretation=interpretation,
                    risk_level=risk_level,
                ))

        return signals
