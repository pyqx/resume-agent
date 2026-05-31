"""GitHub analysis tools — progressive disclosure pipeline."""

import logging

from agent.tools.base import BaseTool, ToolMetadata, ToolResult, ToolCategory, Difficulty

logger = logging.getLogger(__name__)


class FetchRepoMetadataTool(BaseTool):
    def __init__(self, analyzer):
        self._analyzer = analyzer

    @property
    def metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="fetch_repo_metadata",
            category=ToolCategory.GITHUB,
            description="Stage 1: Fetch basic metadata (stars, language, description) for a GitHub repo",
            usage_guide="Use first when a user provides a GitHub URL. Quick overview before deciding to do deeper analysis.",
            preconditions=["github_url_provided"],
            estimated_time=Difficulty.LIGHT,
            is_idempotent=True,
        )

    async def execute(self, repo_url: str = "", **kwargs) -> ToolResult:
        if not repo_url:
            return ToolResult.fail("PARAM_ERROR", "repo_url is required")
        try:
            result = await self._analyzer.stage1_metadata(repo_url)
            return ToolResult.ok(result)
        except Exception as e:
            return ToolResult.fail("METADATA_ERROR", str(e), is_retryable=True,
                                    fallback_suggestion="Check the URL and try again")


class AnalyzeRepoStructureTool(BaseTool):
    def __init__(self, analyzer):
        self._analyzer = analyzer

    @property
    def metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="analyze_repo_structure",
            category=ToolCategory.GITHUB,
            description="Stage 2: Clone repo and analyze directory structure, modules, and tech stack",
            usage_guide="Use after metadata looks promising. Provides module map and tech stack details.",
            preconditions=["github_url_provided"],
            estimated_time=Difficulty.MEDIUM,
            is_idempotent=True,
        )

    async def execute(self, repo_url: str = "", **kwargs) -> ToolResult:
        if not repo_url:
            return ToolResult.fail("PARAM_ERROR", "repo_url is required")
        try:
            result = await self._analyzer.stage2_structure(repo_url)
            return ToolResult.ok(result)
        except Exception as e:
            return ToolResult.fail("STRUCTURE_ERROR", str(e), is_retryable=True,
                                    fallback_suggestion="Repository may be too large. Try analyzing a specific subdirectory.")


class AnalyzeRepoDependenciesTool(BaseTool):
    def __init__(self, analyzer):
        self._analyzer = analyzer

    @property
    def metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="analyze_repo_dependencies",
            category=ToolCategory.GITHUB,
            description="Stage 3a: Analyze project dependencies for outdated packages and issues",
            usage_guide="Use after structure analysis to identify dependency upgrade opportunities.",
            preconditions=["github_url_provided"],
            estimated_time=Difficulty.MEDIUM,
            is_idempotent=False,
        )

    async def execute(self, repo_url: str = "", **kwargs) -> ToolResult:
        if not repo_url:
            return ToolResult.fail("PARAM_ERROR", "repo_url is required")
        try:
            results = await self._analyzer.stage3_deep_analysis(repo_url)
            return ToolResult.ok(results.get("dependencies", {}))
        except Exception as e:
            return ToolResult.fail("DEPS_ERROR", str(e), is_retryable=True)


class ScanIssuesForOpportunitiesTool(BaseTool):
    def __init__(self, analyzer):
        self._analyzer = analyzer

    @property
    def metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="scan_issues_for_opportunities",
            category=ToolCategory.GITHUB,
            description="Stage 3b: Scan open issues to find contribution entry points categorized by difficulty",
            usage_guide="Use to find 'good first issue' and high-engagement issues that make good starting points.",
            preconditions=["github_url_provided"],
            estimated_time=Difficulty.MEDIUM,
            is_idempotent=False,
        )

    async def execute(self, repo_url: str = "", **kwargs) -> ToolResult:
        if not repo_url:
            return ToolResult.fail("PARAM_ERROR", "repo_url is required")
        try:
            results = await self._analyzer.stage3_deep_analysis(repo_url)
            return ToolResult.ok(results.get("issues", {}))
        except Exception as e:
            return ToolResult.fail("ISSUES_ERROR", str(e), is_retryable=True)


class GenerateDevSuggestionsTool(BaseTool):
    def __init__(self, analyzer, get_user_profile_fn):
        self._analyzer = analyzer
        self._get_profile = get_user_profile_fn

    @property
    def metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="generate_dev_suggestions",
            category=ToolCategory.GITHUB,
            description="Stage 4: Generate 3-5 personalized improvement directions aligning repo opportunities with user's career",
            usage_guide="Use after all analysis stages. Combines repo analysis with user's career direction to suggest specific contributions.",
            preconditions=["github_url_provided"],
            estimated_time=Difficulty.HEAVY,
            is_idempotent=False,
        )

    async def execute(self, repo_url: str = "", repo_analysis: dict | None = None, **kwargs) -> ToolResult:
        if not repo_url:
            return ToolResult.fail("PARAM_ERROR", "repo_url is required")
        try:
            analysis = repo_analysis or {}
            career = ""
            try:
                profile = self._get_profile()
                career = getattr(profile, "target_position", "") if profile else ""
            except Exception:
                pass

            result = await self._analyzer.stage4_suggestions(
                repo_analysis=analysis,
                career_direction=career or "general software development",
            )
            return ToolResult.ok(result)
        except Exception as e:
            return ToolResult.fail("SUGGESTION_ERROR", str(e), is_retryable=True)


class ComposeResumeEntryFromGitHubTool(BaseTool):
    def __init__(self, analyzer):
        self._analyzer = analyzer

    @property
    def metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="compose_resume_entry_from_github",
            category=ToolCategory.GITHUB,
            description="Stage 5: Generate a STAR-format resume entry from a selected contribution plan",
            usage_guide="Use as the final step — converts a selected suggestion into professional resume content.",
            preconditions=["github_url_provided"],
            estimated_time=Difficulty.LIGHT,
            is_idempotent=False,
        )

    async def execute(self, suggestion: dict | None = None, repo_context: dict | None = None, **kwargs) -> ToolResult:
        if not suggestion:
            return ToolResult.fail("PARAM_ERROR", "suggestion is required")
        try:
            result = await self._analyzer.stage5_resume_entry(
                selected_suggestion=suggestion,
                repo_context=repo_context or {},
            )
            return ToolResult.ok(result)
        except Exception as e:
            return ToolResult.fail("COMPOSE_ERROR", str(e))
