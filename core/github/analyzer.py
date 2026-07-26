"""GitHubAnalyzer — orchestrates the 5-stage progressive disclosure analysis pipeline."""

import asyncio
import hashlib
import logging
from pathlib import Path

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

    A repo is cloned at most once per analyzer instance and reused across
    stages; call release_clones() when the analysis flow is done. Stage
    results are cached in diskcache keyed by repo URL.
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
        self._issues = IssueAnalyzer(github_token=github_token or settings.github_token)
        self._suggestions = SuggestionGenerator(llm_client=llm_client)
        self._composer = ResumeEntryComposer(llm_client=llm_client)
        # url -> cloned path; bounded to one repo at a time.
        self._clones: dict[str, Path] = {}
        self._clone_lock = asyncio.Lock()

    @property
    def llm(self):
        if self._llm is None:
            self._llm = get_llm_client_from_settings()
        return self._llm

    # ── Clone management ─────────────────────────────────────

    async def _ensure_clone(self, repo_url: str) -> Path:
        """Clone the repo once and reuse it across stages."""
        async with self._clone_lock:
            existing = self._clones.get(repo_url)
            if existing and existing.exists():
                return existing
            # Bound disk usage: keep at most one repo checked out.
            for url in list(self._clones):
                await self._cloner.remove(self._clones.pop(url))
            path = await self._cloner.shallow_clone(repo_url)
            self._clones[repo_url] = path
            return path

    async def release_clones(self):
        """Remove all cached clones. Call when an analysis flow completes."""
        async with self._clone_lock:
            for url in list(self._clones):
                await self._cloner.remove(self._clones.pop(url))

    # ── Stage methods (each returns a dict for progressive streaming) ──

    async def stage1_metadata(self, repo_url: str) -> dict:
        """Stage 1: Quick overview — parse URL, get repo identity."""
        from urllib.parse import urlparse
        parsed = urlparse(repo_url)
        parts = parsed.path.strip("/").split("/")

        meta = {
            "url": repo_url, "owner": "", "repo": "",
            "stars": 0, "language": "", "description": "",
            "api_status": "unavailable",
        }

        if len(parts) >= 2 and "github.com" in parsed.netloc:
            meta["owner"] = parts[0]
            meta["repo"] = parts[1]

            cached = await self._get_cached(repo_url, "metadata")
            if cached:
                return cached

            try:
                import httpx
                headers = {"Accept": "application/vnd.github+json"}
                token = settings.github_token
                if token:
                    headers["Authorization"] = f"Bearer {token}"
                async with httpx.AsyncClient() as client:
                    resp = await client.get(
                        f"https://api.github.com/repos/{parts[0]}/{parts[1]}",
                        headers=headers,
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
                    meta["api_status"] = "ok"
                    await self._set_cache(repo_url, "metadata", meta, expire=600)
                elif resp.status_code in (403, 429):
                    meta["api_status"] = "rate_limited"
                    meta["error"] = (
                        "GitHub API rate limit reached (60 req/h unauthenticated). "
                        "Set GITHUB_TOKEN to raise the limit. Stats are unavailable, "
                        "not zero."
                    )
                    logger.warning("GitHub API rate limited for %s", repo_url)
                elif resp.status_code == 404:
                    meta["api_status"] = "not_found"
                    meta["error"] = "Repository not found (it may be private or deleted)."
                else:
                    meta["api_status"] = f"http_{resp.status_code}"
                    meta["error"] = f"GitHub API returned HTTP {resp.status_code}"
            except Exception as e:
                meta["api_status"] = "network_error"
                meta["error"] = "Could not reach the GitHub API"
                logger.warning("GitHub metadata fetch failed: %s", e)

        return meta

    async def full_analysis(self, repo_url: str) -> dict:
        """Run all analysis stages and return combined results for suggestions."""
        metadata = await self.stage1_metadata(repo_url)
        structure = await self.stage2_structure(repo_url)
        deep = await self.stage3_deep_analysis(repo_url)
        return {
            "metadata": metadata,
            "structure": structure,
            "dependencies": deep.get("dependencies", {}),
            "issues": deep.get("issues", {}),
        }

    async def stage2_structure(self, repo_url: str) -> dict:
        """Stage 2: Clone and analyze directory structure."""
        cached = await self._get_cached(repo_url, "structure")
        if cached:
            return cached
        try:
            repo_path = await self._ensure_clone(repo_url)
            result = await asyncio.to_thread(self._structure.analyze, repo_path)
            await self._set_cache(repo_url, "structure", result)
            return result
        except Exception as e:
            logger.warning("Structure analysis failed for %s: %s", repo_url, e)
            return {"error": str(e), "structure_available": False}

    async def stage3_deep_analysis(self, repo_url: str) -> dict:
        """Stage 3: Dependencies + Issues."""
        cached = await self._get_cached(repo_url, "deep")
        if cached:
            return cached

        results = {"dependencies": {}, "issues": {}}
        try:
            repo_path = await self._ensure_clone(repo_url)
            results["dependencies"] = await asyncio.to_thread(
                self._deps.analyze, repo_path
            )
        except Exception as e:
            logger.warning("Dependency analysis failed for %s: %s", repo_url, e)
            results["dependencies"] = {"error": str(e)}

        results["issues"] = await self._issues.analyze(repo_url)

        if "error" not in results["dependencies"] and "error" not in results["issues"]:
            await self._set_cache(repo_url, "deep", results)
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

    async def _get_cached(self, repo_url: str, stage: str) -> dict | None:
        if not self._cache:
            return None
        try:
            return await asyncio.to_thread(
                self._cache.get, self._cache_key(repo_url, stage)
            )
        except Exception as e:
            logger.warning("Cache read failed: %s", e)
            return None

    async def _set_cache(self, repo_url: str, stage: str, data: dict, expire: int = 3600):
        if not self._cache:
            return
        try:
            await asyncio.to_thread(
                self._cache.set, self._cache_key(repo_url, stage), data, expire=expire
            )
        except Exception as e:
            logger.warning("Cache write failed: %s", e)
