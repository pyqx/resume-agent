"""JD tools — parse, match, analyze job descriptions."""

from agent.tools.base import BaseTool, ToolMetadata, ToolResult, ToolCategory, Difficulty


class ParseJDTool(BaseTool):
    def __init__(self, jd_parser):
        self._parser = jd_parser

    @property
    def metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="parse_jd_text",
            category=ToolCategory.JD,
            description="Parse a job description text into structured requirements",
            usage_guide="Use when the user pastes a job description. Extracts hard requirements, nice-to-haves, and hidden signals.",
            estimated_time=Difficulty.LIGHT,
            is_idempotent=True,
        )

    async def execute(self, jd_text: str = "", **kwargs) -> ToolResult:
        if not jd_text:
            return ToolResult.fail("PARAM_ERROR", "jd_text is required")
        try:
            jd_reqs = await self._parser.parse(jd_text)
            return ToolResult.ok(jd_reqs.model_dump(mode="json"))
        except Exception as e:
            return ToolResult.fail("JD_PARSE_ERROR", str(e), is_retryable=True)


class MatchJDToResumeTool(BaseTool):
    def __init__(self, jd_matcher, get_resume_fn):
        self._matcher = jd_matcher
        self._get_resume = get_resume_fn

    @property
    def metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="match_jd_to_resume",
            category=ToolCategory.JD,
            description="Match a parsed JD against the current resume and generate a detailed match report",
            usage_guide="Use when the user wants to see how well their resume matches a job. Requires a parsed JD and a loaded resume.",
            preconditions=["resume_loaded", "jd_loaded"],
            estimated_time=Difficulty.MEDIUM,
            is_idempotent=True,
        )

    async def execute(self, jd_text: str = "", **kwargs) -> ToolResult:
        if not jd_text:
            return ToolResult.fail("PARAM_ERROR", "jd_text is required")
        try:
            resume = self._get_resume()
            if not resume:
                return ToolResult.fail("NO_RESUME", "No resume is currently loaded")

            from core.jd.parser import JDParser
            parser = JDParser()
            jd = await parser.parse(jd_text)

            report = await self._matcher.match(jd, resume)
            return ToolResult.ok(report.model_dump(mode="json"))
        except Exception as e:
            return ToolResult.fail("JD_MATCH_ERROR", str(e), is_retryable=True)


class AnalyzeKeywordCoverageTool(BaseTool):
    def __init__(self):
        pass

    @property
    def metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="analyze_keyword_coverage",
            category=ToolCategory.JD,
            description="Analyze keyword overlap between a JD and the resume for ATS optimization",
            usage_guide="Use when checking if the resume contains enough keywords from the JD to pass ATS screening.",
            preconditions=["resume_loaded"],
            estimated_time=Difficulty.LIGHT,
        )

    async def execute(self, jd_text: str = "", resume_text: str = "", **kwargs) -> ToolResult:
        if not jd_text:
            return ToolResult.fail("PARAM_ERROR", "jd_text is required")
        try:
            jd_lower = jd_text.lower()
            resume_lower = resume_text.lower()

            # Simple keyword extraction
            import re
            tech_words = set(re.findall(r'\b[a-zA-Z+#.-]{2,}\b', jd_lower))
            common_words = {'the', 'a', 'an', 'is', 'are', 'and', 'or', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'you', 'will', 'be', 'we', 'our'}
            jd_keywords = {w for w in tech_words if w not in common_words}

            matched = [kw for kw in jd_keywords if kw in resume_lower]
            missing = list(jd_keywords - set(matched))

            return ToolResult.ok({
                "coverage_rate": len(matched) / len(jd_keywords) if jd_keywords else 0,
                "matched_keywords": matched[:50],
                "missing_keywords": missing[:50],
            })
        except Exception as e:
            return ToolResult.fail("KEYWORD_ERROR", str(e))


class DetectJDSignalsTool(BaseTool):
    def __init__(self, signal_detector):
        self._detector = signal_detector

    @property
    def metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="detect_jd_signals",
            category=ToolCategory.JD,
            description="Detect hidden signals and subtext in a job description",
            usage_guide="Use to help the user understand what a JD really means between the lines.",
            estimated_time=Difficulty.LIGHT,
        )

    async def execute(self, jd_text: str = "", **kwargs) -> ToolResult:
        if not jd_text:
            return ToolResult.fail("PARAM_ERROR", "jd_text is required")
        try:
            signals = self._detector.detect(jd_text)
            return ToolResult.ok([s.model_dump(mode="json") for s in signals])
        except Exception as e:
            return ToolResult.fail("SIGNAL_ERROR", str(e))
