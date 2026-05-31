"""IssueAnalyzer — scan repo issues for contribution opportunities."""

import logging
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


class IssueAnalyzer:
    """Analyze GitHub Issues to find good contribution entry points.

    Uses GitHub API with optional token for higher rate limits.
    """

    def __init__(self, github_token: str = ""):
        self._token = github_token

    async def analyze(self, repo_url: str, max_issues: int = 30) -> dict:
        """Fetch and classify recent issues from a GitHub repo.

        Returns:
            Dict with categorized issues by difficulty and value.
        """
        owner, repo = self._parse_repo_url(repo_url)
        if not owner or not repo:
            return {"error": "Could not parse repo URL", "issues": []}

        # Try GitHub API
        import httpx
        headers = {"Accept": "application/vnd.github.v3+json"}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"

        issues = []

        try:
            async with httpx.AsyncClient() as client:
                # Fetch issues with "good first issue" label
                for label in ["good first issue", "help wanted", "bug", "enhancement"]:
                    resp = await client.get(
                        f"https://api.github.com/repos/{owner}/{repo}/issues",
                        params={
                            "labels": label,
                            "state": "open",
                            "sort": "reactions",
                            "per_page": 10,
                        },
                        headers=headers,
                        timeout=15.0,
                    )
                    if resp.status_code == 200:
                        for item in resp.json():
                            issues.append({
                                "number": item["number"],
                                "title": item["title"],
                                "labels": [l["name"] for l in item.get("labels", [])],
                                "reactions": item.get("reactions", {}).get("total_count", 0),
                                "comments": item.get("comments", 0),
                                "url": item["html_url"],
                                "category": label,
                            })

                # Deduplicate
                seen = set()
                unique_issues = []
                for issue in issues:
                    if issue["number"] not in seen:
                        seen.add(issue["number"])
                        unique_issues.append(issue)

                # Classify
                good_first = [i for i in unique_issues if "good first issue" in i.get("labels", [])]
                valuable = sorted(unique_issues, key=lambda i: i["reactions"], reverse=True)[:10]

                return {
                    "total_open_issues_found": len(unique_issues),
                    "good_first_issues": good_first[:10],
                    "high_engagement_issues": valuable[:10],
                    "categorized": {
                        "beginner": len(good_first),
                        "intermediate": sum(1 for i in unique_issues if "help wanted" in i.get("labels", [])),
                        "advanced": sum(1 for i in unique_issues if i.get("labels") and "enhancement" in i.get("labels", [])),
                    },
                }

        except Exception as e:
            logger.warning(f"GitHub API error for {owner}/{repo}: {e}")
            return {
                "error": str(e),
                "issues": [],
                "note": "GitHub API unavailable. Consider providing a token for higher rate limits.",
            }

    @staticmethod
    def _parse_repo_url(url: str) -> tuple[str, str]:
        """Extract owner and repo from GitHub URL."""
        parsed = urlparse(url)
        parts = parsed.path.strip("/").split("/")
        if len(parts) >= 2:
            return parts[0], parts[1]
        return "", ""
