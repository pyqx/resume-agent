"""Interview preparation tools — questions, self-intro, weakness analysis."""

import logging

from agent.tools.base import BaseTool, ToolMetadata, ToolResult, ToolCategory, Difficulty

logger = logging.getLogger(__name__)


class GenerateInterviewQuestionsTool(BaseTool):
    def __init__(self, question_generator, get_resume_fn, jd_parser=None):
        self._generator = question_generator
        self._get_resume = get_resume_fn
        self._jd_parser = jd_parser

    @property
    def metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="generate_interview_questions",
            category=ToolCategory.INTERVIEW,
            description="Generate targeted interview questions (STAR deep-dives, technical follow-ups, behavioral, pressure tests) from resume",
            usage_guide="Use when preparing for an interview. Pass the JD text from the conversation when available — questions become job-targeted.",
            parameters={
                "jd_text": "string, optional — the target job description for targeted questions",
            },
            preconditions=["resume_loaded"],
            estimated_time=Difficulty.MEDIUM,
        )

    async def execute(self, jd_text: str = "", **kwargs) -> ToolResult:
        try:
            resume = self._get_resume()
            if not resume:
                return ToolResult.fail("NO_RESUME", "No resume loaded", is_retryable=False)

            jd = None
            if jd_text and self._jd_parser:
                try:
                    jd = await self._jd_parser.parse(str(jd_text))
                except Exception as e:
                    logger.warning("JD parse failed for interview questions; proceeding without JD: %s", e)

            result = await self._generator.generate(resume, jd)
            return ToolResult.ok(result)
        except Exception as e:
            logger.warning("generate_interview_questions failed: %s", e)
            return ToolResult.fail("QUESTIONS_ERROR", str(e), is_retryable=False)


class GenerateSelfIntroTool(BaseTool):
    def __init__(self, intro_generator, get_resume_fn):
        self._generator = intro_generator
        self._get_resume = get_resume_fn

    @property
    def metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="generate_self_intro",
            category=ToolCategory.INTERVIEW,
            description="Generate 1-minute and 3-minute self-introduction scripts from resume",
            usage_guide="Use when the user wants to prepare their 'Tell me about yourself' answer.",
            preconditions=["resume_loaded"],
            estimated_time=Difficulty.LIGHT,
        )

    async def execute(self, **kwargs) -> ToolResult:
        try:
            resume = self._get_resume()
            if not resume:
                return ToolResult.fail("NO_RESUME", "No resume loaded", is_retryable=False)

            result = await self._generator.generate(resume)
            return ToolResult.ok(result)
        except Exception as e:
            logger.warning("generate_self_intro failed: %s", e)
            return ToolResult.fail("INTRO_ERROR", str(e), is_retryable=False)


class AnalyzeResumeWeaknessesTool(BaseTool):
    def __init__(self, strategist, get_resume_fn):
        self._strategist = strategist
        self._get_resume = get_resume_fn

    @property
    def metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="analyze_resume_weaknesses",
            category=ToolCategory.INTERVIEW,
            description="Detect resume vulnerabilities (gaps, job hopping, weak content) and generate honest narrative strategies",
            usage_guide="Use to prepare for tough interview questions about employment gaps, frequent changes, or career pivots.",
            preconditions=["resume_loaded"],
            estimated_time=Difficulty.MEDIUM,
        )

    async def execute(self, **kwargs) -> ToolResult:
        try:
            resume = self._get_resume()
            if not resume:
                return ToolResult.fail("NO_RESUME", "No resume loaded", is_retryable=False)

            result = await self._strategist.analyze(resume)
            return ToolResult.ok(result)
        except Exception as e:
            logger.warning("analyze_resume_weaknesses failed: %s", e)
            return ToolResult.fail("WEAKNESS_ERROR", str(e), is_retryable=False)
