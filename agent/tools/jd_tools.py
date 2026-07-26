"""JD tools — parse, match, analyze job descriptions."""

import logging

from agent.tools.base import BaseTool, ToolMetadata, ToolResult, ToolCategory, Difficulty

logger = logging.getLogger(__name__)


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
            parameters={"jd_text": "string, the full job description text"},
            estimated_time=Difficulty.LIGHT,
            is_idempotent=True,
        )

    async def execute(self, jd_text: str = "", **kwargs) -> ToolResult:
        if not jd_text:
            return ToolResult.fail("PARAM_ERROR", "jd_text is required", is_retryable=False)
        try:
            jd_reqs = await self._parser.parse(str(jd_text))
            return ToolResult.ok(jd_reqs.model_dump(mode="json"))
        except Exception as e:
            logger.warning("parse_jd_text failed: %s", e)
            return ToolResult.fail("JD_PARSE_ERROR", str(e), is_retryable=False)


class MatchJDToResumeTool(BaseTool):
    def __init__(self, jd_matcher, jd_parser, get_resume_fn):
        self._matcher = jd_matcher
        self._parser = jd_parser
        self._get_resume = get_resume_fn

    @property
    def metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="match_jd_to_resume",
            category=ToolCategory.JD,
            description="Match a JD against the current resume and generate a detailed match report",
            usage_guide="Use when the user wants to see how well their resume matches a job. Provide the JD text from the conversation.",
            parameters={"jd_text": "string, the full job description text"},
            preconditions=["resume_loaded"],
            estimated_time=Difficulty.MEDIUM,
            is_idempotent=True,
        )

    async def execute(self, jd_text: str = "", **kwargs) -> ToolResult:
        if not jd_text:
            return ToolResult.fail("PARAM_ERROR", "jd_text is required", is_retryable=False)
        try:
            resume = self._get_resume()
            if not resume:
                return ToolResult.fail("NO_RESUME", "No resume is currently loaded", is_retryable=False)

            jd = await self._parser.parse(str(jd_text))
            report = await self._matcher.match(jd, resume)
            return ToolResult.ok(report.model_dump(mode="json"))
        except Exception as e:
            logger.warning("match_jd_to_resume failed: %s", e)
            return ToolResult.fail("JD_MATCH_ERROR", str(e), is_retryable=False)


class AnalyzeKeywordCoverageTool(BaseTool):
    def __init__(self, jd_parser, get_resume_fn):
        self._parser = jd_parser
        self._get_resume = get_resume_fn

    @property
    def metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="analyze_keyword_coverage",
            category=ToolCategory.JD,
            description="Analyze keyword overlap between a JD and the current resume for ATS optimization",
            usage_guide="Use when checking if the resume contains enough keywords from the JD to pass ATS screening.",
            parameters={"jd_text": "string, the full job description text"},
            preconditions=["resume_loaded"],
            estimated_time=Difficulty.MEDIUM,
        )

    async def execute(self, jd_text: str = "", **kwargs) -> ToolResult:
        if not jd_text:
            return ToolResult.fail("PARAM_ERROR", "jd_text is required", is_retryable=False)
        try:
            resume = self._get_resume()
            if not resume:
                return ToolResult.fail("NO_RESUME", "No resume is currently loaded", is_retryable=False)

            from core.jd.keywords import compute_keyword_coverage
            jd = await self._parser.parse(str(jd_text))
            keywords = list(jd.keyword_frequency.keys())
            if not keywords:
                return ToolResult.ok({
                    "coverage_rate": None,
                    "matched": [],
                    "missing": [],
                    "note": "该 JD 未提取到关键词",
                })
            return ToolResult.ok(compute_keyword_coverage(keywords, resume))
        except Exception as e:
            logger.warning("analyze_keyword_coverage failed: %s", e)
            return ToolResult.fail("KEYWORD_ERROR", str(e), is_retryable=False)


class DetectJDSignalsTool(BaseTool):
    def __init__(self, signal_detector):
        self._detector = signal_detector

    @property
    def metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="detect_jd_signals",
            category=ToolCategory.JD,
            description="Detect hidden signals and subtext in a job description (rule-based, instant)",
            usage_guide="Use to help the user understand what a JD really means between the lines.",
            parameters={"jd_text": "string, the full job description text"},
            estimated_time=Difficulty.LIGHT,
        )

    async def execute(self, jd_text: str = "", **kwargs) -> ToolResult:
        if not jd_text:
            return ToolResult.fail("PARAM_ERROR", "jd_text is required", is_retryable=False)
        try:
            signals = self._detector.detect(str(jd_text))
            return ToolResult.ok([s.model_dump(mode="json") for s in signals])
        except Exception as e:
            logger.warning("detect_jd_signals failed: %s", e)
            return ToolResult.fail("SIGNAL_ERROR", str(e), is_retryable=False)
