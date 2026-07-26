"""JDSignalDetector — rule-based detection of hidden signals in job descriptions."""

import re

from core.resume.schema import JDSignal


# Known signal phrases and their interpretations: (pattern, interpretation, risk_level).
# Word gaps use [\s\-_]? ("fast-paced" / "fast paced" / "fastpaced") instead of the
# old `.` wildcard, which matched any character ("fastXpaced" also fired).
SIGNAL_PATTERNS = [
    (r"fast[\s\-_]?paced|快速迭代|节奏快", "高频度需求变更，可能需要频繁加班", "warning"),
    (r"wear[\s\-_]?many[\s\-_]?hats|身兼多职|多面手", "团队配置不齐，一人需承担多个岗位职责", "warning"),
    (r"从0到1|zero[\s\-_]?to[\s\-_]?one|from[\s\-_]?scratch", "新业务线，团队/流程可能不成熟", "info"),
    (r"rockstar|ninja|guru|大牛|大神", "招聘文化不专业，可能对技术有不切实际期望", "caution"),
    (r"competitive[\s\-_]?salary|薪资有竞争力", "实际薪资可能低于市场水平", "warning"),
    (r"unlimited[\s\-_]?PTO|无限休假", "可能没有结构化的休假制度", "info"),
    (r"startup[\s\-_]?mindset|创业心态", "可能需要超时工作，且不确定性高", "warning"),
    (r"embrace[\s\-_]?change|拥抱变化", "方向可能频繁调整，需要较强适应性", "info"),
    (r"result[\s\-_]?oriented|结果导向", "面试时会追问量化数据，绩效压力可能较大", "info"),
    # 旧模式为 "fight.for|fight.for.it"：第二分支永不可达（第一分支已匹配其前缀），已删。
    (r"fight[\s\-_]?for|狼性", "竞争激烈的内部文化", "caution"),
    (r"flat[\s\-_]?structure|扁平化", "可能晋升路径不清晰", "info"),
    (r"early[\s\-_]?employee|早期员工", "期权可能有价值，但风险也高", "info"),
    (r"wearing[\s\-_]?multiple[\s\-_]?hats", "职责范围可能超出职位描述", "warning"),
    (r"self[\s\-_]?starter|自驱", "可能缺乏系统的新人培训和指导", "info"),
    # ── 中文工时/文化信号扩充 ──
    # (?<!\d)/(?!\d) 防止命中年份等更长数字（如 "1996 年成立"）。
    (r"(?<!\d)996(?!\d)", "996 工作制：早 9 晚 9 每周 6 天，长期高强度加班", "caution"),
    (r"大小周", "大小周排班：隔周单休，实际工作时长明显增加", "caution"),
    (r"弹性工作(制|时间)?", "弹性工作制：可能意味着实际工作时间无边界", "info"),
    (r"奋斗者", "奋斗者文化：可能默认长时间投入，加班回报未必对等", "warning"),
    (r"抗压(能力|性)?(强|好)?", "强调抗压能力强：可能是高压、高强度的工作环境", "warning"),
    (r"加班", "明确提及加班，工作强度可能较大", "warning"),
    (r"on[\s\-_]?call|随叫随到", "需要 on-call 值守，非工作时间可能仍需随时响应", "info"),
    (r"快速成长", "强调快速成长：可能人手不足，以高强度工作换取成长", "info"),
]

# 命中位置前 2 个字符内出现这些否定字则跳过该次命中（"不加班"、"无996"）。
_NEGATION_CHARS = "非不无没"
_NEGATION_WINDOW = 2


class SignalDetector:
    """Detect hidden signals and subtext in JD text."""

    def detect(self, jd_text: str) -> list[JDSignal]:
        """Scan JD text for known signal phrases and return interpretations.

        每条规则最多报告一次：phrase 取首个有效命中的原文；同一规则重复
        命中时在 interpretation 末尾附 "(出现 N 次)"；命中位置前 2 个
        字符内含否定字（非/不/无/没）的命中被忽略。
        """
        signals: list[JDSignal] = []

        for pattern, interpretation, risk_level in SIGNAL_PATTERNS:
            first_phrase = ""
            count = 0
            for m in re.finditer(pattern, jd_text, re.IGNORECASE):
                prefix = jd_text[max(0, m.start() - _NEGATION_WINDOW):m.start()]
                if any(ch in prefix for ch in _NEGATION_CHARS):
                    continue
                count += 1
                if not first_phrase:
                    first_phrase = m.group()
            if count == 0:
                continue
            text = interpretation if count == 1 else f"{interpretation}(出现 {count} 次)"
            signals.append(JDSignal(
                phrase=first_phrase,
                interpretation=text,
                risk_level=risk_level,
            ))

        return signals
