"""Web tools — search and fetch content from the internet."""

import json
import logging
import re
from urllib.parse import quote

from agent.tools.base import BaseTool, ToolMetadata, ToolResult, ToolCategory, Difficulty

logger = logging.getLogger(__name__)


class WebSearchTool(BaseTool):
    """Search the web for information on a given topic."""

    @property
    def metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="web_search",
            category=ToolCategory.WEB,
            description="Search the web for current information on any topic (job market trends, company info, industry news, etc.)",
            usage_guide="Use for general web research (market trends, company info, news). For GitHub repos, use fetch_repo_metadata instead.",
            estimated_time=Difficulty.MEDIUM,
        )

    async def execute(self, query: str = "", **kwargs) -> ToolResult:
        if not query:
            return ToolResult.fail("PARAM_ERROR", "query is required")

        try:
            import httpx
            logger.info("Web search: query=%s", query[:100])

            search_url = f"https://api.duckduckgo.com/?q={quote(query)}&format=json&no_html=1&skip_disambig=1"
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(search_url)

            if resp.status_code != 200:
                return ToolResult.fail("SEARCH_ERROR", f"Search failed with status {resp.status_code}")

            data = resp.json()
            results = []

            # Extract abstract
            if data.get("AbstractText"):
                results.append({
                    "type": "summary",
                    "title": data.get("Heading", ""),
                    "content": data["AbstractText"],
                    "source": data.get("AbstractURL", ""),
                })

            # Extract related topics
            for topic in data.get("RelatedTopics", []):
                if "Text" in topic:
                    results.append({
                        "type": "related",
                        "title": topic.get("Text", "")[:100],
                        "content": topic.get("Text", ""),
                        "source": topic.get("FirstURL", ""),
                    })
                elif "Topics" in topic:
                    for sub in topic["Topics"][:3]:
                        if "Text" in sub:
                            results.append({
                                "type": "related",
                                "title": sub.get("Text", "")[:100],
                                "content": sub.get("Text", ""),
                                "source": sub.get("FirstURL", ""),
                            })

            if not results:
                results.append({"type": "info", "content": f"No detailed results found for: {query}", "source": ""})

            return ToolResult.ok({
                "query": query,
                "results": results[:8],
                "result_count": len(results),
            })

        except Exception as e:
            logger.warning("Web search failed: %s", e)
            return ToolResult.fail("SEARCH_ERROR", str(e), is_retryable=True)


class WebFetchTool(BaseTool):
    """Fetch and extract readable text content from a URL."""

    @property
    def metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="web_fetch",
            category=ToolCategory.WEB,
            description="Fetch and read text content from a general web page (articles, company pages, etc.). Not for GitHub repos.",
            usage_guide="Use for reading general web pages. For GitHub repositories, use fetch_repo_metadata and other GitHub tools.",
            estimated_time=Difficulty.LIGHT,
        )

    async def execute(self, url: str = "", **kwargs) -> ToolResult:
        if not url:
            return ToolResult.fail("PARAM_ERROR", "url is required")

        try:
            import httpx
            logger.info("Web fetch: url=%s", url[:200])

            async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
                resp = await client.get(url, headers={
                    "User-Agent": "Mozilla/5.0 (compatible; ResumeAgent/1.0)",
                })

            if resp.status_code != 200:
                return ToolResult.fail("FETCH_ERROR", f"HTTP {resp.status_code}")

            content_type = resp.headers.get("content-type", "")
            text = resp.text

            # Simple text extraction: remove HTML tags, collapse whitespace
            text = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.DOTALL | re.IGNORECASE)
            text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL | re.IGNORECASE)
            text = re.sub(r'<[^>]+>', ' ', text)
            text = re.sub(r'\s+', ' ', text).strip()
            text = text[:8000]

            title_match = re.search(r'<title[^>]*>(.*?)</title>', resp.text, re.IGNORECASE | re.DOTALL)
            title = title_match.group(1).strip() if title_match else ""

            return ToolResult.ok({
                "url": url,
                "title": title,
                "content": text[:5000],
                "content_type": content_type.split(";")[0],
            })

        except Exception as e:
            logger.warning("Web fetch failed: %s", e)
            return ToolResult.fail("FETCH_ERROR", str(e), is_retryable=True)
