"""GitHubAnalyzer — orchestrates the 5-stage progressive disclosure analysis pipeline."""

import hashlib
import json
import logging

from diskcache import Cache
from core.llm import get_llm_client_from_settings

from core.config import settings
from core.github.cloner import RepoCloner
from core.github.structure import StructureAnalyzer
from core.github.dependencies import DependencyAnalyzer
from core.github.issues import IssueAnalyzer
from core.github.suggestion import SuggestionGenerator
from core.github.resume_entry import ResumeEntryComposer

logger = logging.getLogger(__name__)


class GitHubAnalyzer:
    """5-stage progressive disclosure analysis for GitHub repositories.

    Each stage is evaluated by the Agent before proceeding to the next.
    Results are cached by (repo_url, commit_sha) for instant re-analysis.
    """

    def __init__(
        self,
        llm_client=None,
        cache: Cache | None = None,
        github_token: str = "",
    ):
        self._llm = llm_client
        self._cache = cache
        self._cloner = RepoCloner()
        self._structure = StructureAnalyzer()
        self._deps = DependencyAnalyzer()
        self._issues = IssueAnalyzer(github_token=github_token)
        self._suggestions = SuggestionGenerator(llm_client=llm_client)
        self._composer = ResumeEntryComposer(llm_client=llm_client)

    @property
    def llm(self):
        if self._llm is None:
            self._llm = get_llm_client_from_settings()
        return self._llm

    # ── Stage methods (each returns a dict for progressive streaming) ──

    async def stage1_metadata(self, repo_url: str) -> dict:
        """Stage 1: Quick overview — parse URL, get repo identity."""
        from urllib.parse import urlparse
        parsed = urlparse(repo_url)
        parts = parsed.path.strip("/").split("/")

        # Try GitHub API for metadata
        meta = {"url": repo_url, "owner": "", "repo": "", "stars": 0, "language": "", "description": ""}

        if len(parts) >= 2 and "github.com" in parsed.netloc:
            meta["owner"] = parts[0]
            meta["repo"] = parts[1]

            try:
                import httpx
                async with httpx.AsyncClient() as client:
                    resp = await client.get(
                        f"https://api.github.com/repos/{parts[0]}/{parts[1]}",
                        timeout=10.0,
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        meta["stars"] = data.get("stargazers_count", 0)
                        meta["language"] = data.get("language", "")
                        meta["description"] = data.get("description", "")
                        meta["topics"] = data.get("topics", [])
                        meta["updated_at"] = data.get("updated_at", "")
                        meta["open_issues"] = data.get("open_issues_count", 0)
                        meta["forks"] = data.get("forks_count", 0)
            except Exception:
                pass  # Non-critical — proceed with partial data

        return meta

    async def stage2_structure(self, repo_url: str) -> dict:
        """Stage 2: Clone and analyze directory structure."""
        repo_path = None
        try:
            repo_path = self._cloner.shallow_clone(repo_url)
            return self._structure.analyze(repo_path)
        except Exception as e:
            return {"error": str(e), "structure_available": False}
        finally:
            if repo_path:
                self._cloner.cleanup(repo_path)

    async def stage3_deep_analysis(self, repo_url: str) -> dict:
        """Stage 3: Dependencies + Issues (parallel)."""
        repo_path = None
        results = {"dependencies": {}, "issues": {}}

        try:
            repo_path = self._cloner.shallow_clone(repo_url)
            results["dependencies"] = self._deps.analyze(repo_path)
        except Exception as e:
            results["dependencies"] = {"error": str(e)}
        finally:
            if repo_path:
                self._cloner.cleanup(repo_path)

        results["issues"] = await self._issues.analyze(repo_url)

        return results

    async def stage4_suggestions(
        self,
        repo_analysis: dict,
        career_direction: str = "",
        skill_level: str = "intermediate",
    ) -> dict:
        """Stage 4: Generate personalized improvement suggestions."""
        return await self._suggestions.generate(
            repo_analysis=repo_analysis,
            career_direction=career_direction,
            skill_level=skill_level,
        )

    async def stage5_resume_entry(
        self,
        selected_suggestion: dict,
        repo_context: dict,
    ) -> dict:
        """Stage 5: Compose a STAR-formatted resume entry."""
        return await self._composer.compose(
            suggestion=selected_suggestion,
            repo_context=repo_context,
        )

    # ── Cache helpers ────────────────────────────────────────

    def _cache_key(self, repo_url: str, stage: str) -> str:
        url_hash = hashlib.sha256(repo_url.encode()).hexdigest()[:16]
        return f"github_{stage}_{url_hash}"

    def _get_cached(self, repo_url: str, stage: str) -> dict | None:
        if not self._cache:
            return None
        return self._cache.get(self._cache_key(repo_url, stage))

    def _set_cache(self, repo_url: str, stage: str, data: dict, expire: int = 3600):
        if self._cache:
            self._cache.set(self._cache_key(repo_url, stage), data, expire=expire)
