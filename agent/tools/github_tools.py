"""GitHub analysis tools — progressive disclosure pipeline."""

import logging

from agent.tools.base import BaseTool, ToolMetadata, ToolResult, ToolCategory, Difficulty

logger = logging.getLogger(__name__)

_URL_PARAM = {
    "repo_url": "string, the repository URL (e.g. https://github.com/owner/repo). "
                "Omit to use the URL from the conversation."
}


class _GitHubToolBase(BaseTool):
    """Shared repo_url resolution: explicit param -> conversation context."""

    def __init__(self, analyzer):
        self._analyzer = analyzer

    @staticmethod
    def _resolve_url(repo_url: str, kwargs: dict) -> str:
        return repo_url or kwargs.get("github_url", "") or ""


class FetchRepoMetadataTool(_GitHubToolBase):
    @property
    def metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="fetch_repo_metadata",
            category=ToolCategory.GITHUB,
            description="Fetch basic metadata (stars, language, description) for a GitHub repo",
            usage_guide="Use when the user provides a GitHub URL. Returns stars, language, description, topics.",
            parameters=_URL_PARAM,
            preconditions=["github_url_provided"],
            estimated_time=Difficulty.LIGHT,
            is_idempotent=True,
        )

    async def execute(self, repo_url: str = "", **kwargs) -> ToolResult:
        repo_url = self._resolve_url(repo_url, kwargs)
        if not repo_url:
            return ToolResult.fail("PARAM_ERROR", "repo_url is required", is_retryable=False)
        try:
            result = await self._analyzer.stage1_metadata(repo_url)
            return ToolResult.ok(result)
        except Exception as e:
            logger.warning("fetch_repo_metadata failed: %s", e)
            return ToolResult.fail("METADATA_ERROR", str(e), is_retryable=True,
                                    fallback_suggestion="Check the URL and try again")


class AnalyzeRepoStructureTool(_GitHubToolBase):
    @property
    def metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="analyze_repo_structure",
            category=ToolCategory.GITHUB,
            description="Clone repo and analyze directory structure, modules, and tech stack",
            usage_guide="Provides module map, tech stack, and directory structure of the repo.",
            parameters=_URL_PARAM,
            preconditions=["github_url_provided"],
            estimated_time=Difficulty.MEDIUM,
            is_idempotent=True,
        )

    async def execute(self, repo_url: str = "", **kwargs) -> ToolResult:
        repo_url = self._resolve_url(repo_url, kwargs)
        if not repo_url:
            return ToolResult.fail("PARAM_ERROR", "repo_url is required", is_retryable=False)
        try:
            result = await self._analyzer.stage2_structure(repo_url)
            if result.get("error"):
                return ToolResult.fail("STRUCTURE_ERROR", str(result["error"]), is_retryable=False)
            return ToolResult.ok(result)
        except Exception as e:
            logger.warning("analyze_repo_structure failed: %s", e)
            return ToolResult.fail("STRUCTURE_ERROR", str(e), is_retryable=False,
                                    fallback_suggestion="Repository may be private or too large.")


class AnalyzeRepoDependenciesTool(_GitHubToolBase):
    @property
    def metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="analyze_repo_dependencies",
            category=ToolCategory.GITHUB,
            description="Inventory project dependencies from manifest files",
            usage_guide="Use after structure analysis to understand the dependency landscape.",
            parameters=_URL_PARAM,
            preconditions=["github_url_provided"],
            estimated_time=Difficulty.MEDIUM,
            is_idempotent=True,
        )

    async def execute(self, repo_url: str = "", **kwargs) -> ToolResult:
        repo_url = self._resolve_url(repo_url, kwargs)
        if not repo_url:
            return ToolResult.fail("PARAM_ERROR", "repo_url is required", is_retryable=False)
        try:
            results = await self._analyzer.stage3_deep_analysis(repo_url)
            return ToolResult.ok(results.get("dependencies", {}))
        except Exception as e:
            logger.warning("analyze_repo_dependencies failed: %s", e)
            return ToolResult.fail("DEPS_ERROR", str(e), is_retryable=False)


class ScanIssuesForOpportunitiesTool(_GitHubToolBase):
    @property
    def metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="scan_issues_for_opportunities",
            category=ToolCategory.GITHUB,
            description="Scan open issues to find contribution entry points (grouped by label)",
            usage_guide="Use to find 'good first issue' and high-engagement issues that make good starting points.",
            parameters=_URL_PARAM,
            preconditions=["github_url_provided"],
            estimated_time=Difficulty.MEDIUM,
            is_idempotent=True,
        )

    async def execute(self, repo_url: str = "", **kwargs) -> ToolResult:
        repo_url = self._resolve_url(repo_url, kwargs)
        if not repo_url:
            return ToolResult.fail("PARAM_ERROR", "repo_url is required", is_retryable=False)
        try:
            results = await self._analyzer.stage3_deep_analysis(repo_url)
            issues = results.get("issues", {})
            if issues.get("error"):
                return ToolResult.fail(
                    "ISSUES_ERROR",
                    f"{issues['error']} — {issues.get('note', '')}",
                    is_retryable=False,
                )
            return ToolResult.ok(issues)
        except Exception as e:
            logger.warning("scan_issues_for_opportunities failed: %s", e)
            return ToolResult.fail("ISSUES_ERROR", str(e), is_retryable=False)


class GenerateDevSuggestionsTool(_GitHubToolBase):
    def __init__(self, analyzer, get_resume_fn=None):
        super().__init__(analyzer)
        self._get_resume = get_resume_fn

    @property
    def metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="generate_dev_suggestions",
            category=ToolCategory.GITHUB,
            description="Generate 3-5 personalized improvement directions aligning repo opportunities with the user's career",
            usage_guide="Use after all analysis stages. Combines repo analysis with the user's career direction to suggest specific contributions.",
            parameters={
                **_URL_PARAM,
                "repo_analysis": "object, optional — combined analysis from earlier stages (auto-fetched when omitted)",
            },
            preconditions=["github_url_provided"],
            estimated_time=Difficulty.HEAVY,
            is_idempotent=True,
        )

    async def execute(self, repo_url: str = "", repo_analysis: dict | None = None, **kwargs) -> ToolResult:
        repo_url = self._resolve_url(repo_url, kwargs)
        if not repo_url:
            return ToolResult.fail("PARAM_ERROR", "repo_url is required", is_retryable=False)
        try:
            if not isinstance(repo_analysis, dict) or not repo_analysis:
                logger.info("Auto-running analysis stages for suggestions: %s", repo_url)
                repo_analysis = await self._analyzer.full_analysis(repo_url)

            career = ""
            try:
                resume = self._get_resume() if self._get_resume else None
                if resume:
                    career = resume.target_position or ""
                    if not career and resume.work_experience:
                        career = resume.work_experience[0].position or ""
            except Exception as e:
                logger.warning("Could not derive career direction from resume: %s", e)

            result = await self._analyzer.stage4_suggestions(
                repo_analysis=repo_analysis,
                career_direction=career,
            )
            return ToolResult.ok(result)
        except Exception as e:
            logger.warning("generate_dev_suggestions failed: %s", e)
            return ToolResult.fail("SUGGESTION_ERROR", str(e), is_retryable=False)


class ComposeResumeEntryFromGitHubTool(_GitHubToolBase):
    @property
    def metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="compose_resume_entry_from_github",
            category=ToolCategory.GITHUB,
            description="Generate a STAR-format resume entry from a selected contribution plan",
            usage_guide="Use as the final step — converts a selected suggestion into professional resume content.",
            parameters={
                "suggestion": "object, one suggestion from generate_dev_suggestions",
                "repo_context": "object, optional — repo metadata for context",
            },
            preconditions=["github_url_provided"],
            estimated_time=Difficulty.MEDIUM,
            is_idempotent=True,
        )

    async def execute(self, suggestion: dict | None = None, repo_context: dict | None = None, **kwargs) -> ToolResult:
        if not isinstance(suggestion, dict) or not suggestion:
            return ToolResult.fail("PARAM_ERROR", "suggestion is required", is_retryable=False)
        try:
            result = await self._analyzer.stage5_resume_entry(
                selected_suggestion=suggestion,
                repo_context=repo_context if isinstance(repo_context, dict) else {},
            )
            return ToolResult.ok(result)
        except Exception as e:
            logger.warning("compose_resume_entry_from_github failed: %s", e)
            return ToolResult.fail("COMPOSE_ERROR", str(e), is_retryable=False)
