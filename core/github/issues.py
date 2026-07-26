"""IssueAnalyzer — scan repo issues for contribution opportunities."""

import asyncio
import logging
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

_LABELS = ["good first issue", "help wanted", "bug", "enhancement"]


class IssueAnalyzer:
    """Analyze GitHub Issues to find good contribution entry points.

    Uses the GitHub API with an optional token for higher rate limits.
    Difficulty buckets are derived directly from labels (a heuristic,
    not an actual difficulty estimate).
    """

    def __init__(self, github_token: str = ""):
        self._token = github_token

    async def analyze(self, repo_url: str, max_issues: int = 30) -> dict:
        """Fetch and classify recent open issues from a GitHub repo."""
        owner, repo = self._parse_repo_url(repo_url)
        if not owner or not repo:
            return {"error": "Could not parse repo URL", "issues": []}

        import httpx
        headers = {"Accept": "application/vnd.github+json"}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"

        async def fetch_label(client: httpx.AsyncClient, label: str) -> tuple[str, list | str]:
            try:
                resp = await client.get(
                    f"https://api.github.com/repos/{owner}/{repo}/issues",
                    params={
                        "labels": label,
                        "state": "open",
                        # "reactions" is not a valid sort for this endpoint;
                        # sort by comments, re-rank by reactions client-side.
                        "sort": "comments",
                        "per_page": 10,
                    },
                    headers=headers,
                    timeout=15.0,
                )
            except Exception as e:
                return label, f"network error: {e}"
            if resp.status_code in (403, 429):
                return label, "rate_limited"
            if resp.status_code != 200:
                return label, f"http {resp.status_code}"
            items = []
            for item in resp.json():
                # The /issues endpoint also returns pull requests — skip them.
                if "pull_request" in item:
                    continue
                items.append({
                    "number": item["number"],
                    "title": str(item.get("title", ""))[:200],
                    "labels": [l["name"] for l in item.get("labels", [])],
                    "reactions": item.get("reactions", {}).get("total_count", 0),
                    "comments": item.get("comments", 0),
                    "url": item.get("html_url", ""),
                    "category": label,
                })
            return label, items

        issues: list[dict] = []
        errors: dict[str, str] = {}
        try:
            async with httpx.AsyncClient() as client:
                results = await asyncio.gather(
                    *(fetch_label(client, label) for label in _LABELS)
                )
        except Exception as e:
            logger.warning("GitHub API error for %s/%s: %s", owner, repo, e)
            return {
                "error": str(e),
                "issues": [],
                "note": "GitHub API unavailable. Consider providing a token for higher rate limits.",
            }

        for label, result in results:
            if isinstance(result, str):
                errors[label] = result
            else:
                issues.extend(result)

        if errors and not issues:
            rate_limited = any(v == "rate_limited" for v in errors.values())
            return {
                "error": "rate limited" if rate_limited else "; ".join(
                    f"{k}: {v}" for k, v in errors.items()
                ),
                "issues": [],
                "note": (
                    "GitHub API rate limit reached — set GITHUB_TOKEN for 5000 req/h."
                    if rate_limited
                    else "GitHub API unavailable."
                ),
            }

        # Deduplicate across labels
        seen = set()
        unique_issues = []
        for issue in issues:
            if issue["number"] not in seen:
                seen.add(issue["number"])
                unique_issues.append(issue)

        good_first = [i for i in unique_issues if "good first issue" in i.get("labels", [])]
        valuable = sorted(unique_issues, key=lambda i: i["reactions"], reverse=True)[:10]

        result = {
            "total_open_issues_found": len(unique_issues),
            "good_first_issues": good_first[:10],
            "high_engagement_issues": valuable,
            "categorized": {
                "beginner": len(good_first),
                "intermediate": sum(1 for i in unique_issues if "help wanted" in i.get("labels", [])),
                "advanced": sum(1 for i in unique_issues if "enhancement" in i.get("labels", [])),
            },
            "note": "Difficulty buckets are derived from issue labels only.",
        }
        if errors:
            result["partial_errors"] = errors
        return result

    @staticmethod
    def _parse_repo_url(url: str) -> tuple[str, str]:
        """Extract owner and repo from GitHub URL."""
        parsed = urlparse(url)
        parts = parsed.path.strip("/").split("/")
        if len(parts) >= 2:
            return parts[0], parts[1]
        return "", ""
