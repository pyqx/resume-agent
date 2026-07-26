"""Web tools — search and fetch content from the internet.

web_fetch enforces SSRF protection: only public http(s) hosts are allowed;
every redirect hop is re-validated; response bodies are size-capped.
"""

import asyncio
import html as html_lib
import ipaddress
import logging
import re
import socket
from urllib.parse import quote, urljoin, urlparse

from agent.tools.base import BaseTool, ToolMetadata, ToolResult, ToolCategory, Difficulty
from core.config import settings

logger = logging.getLogger(__name__)

_MAX_REDIRECTS = 5
_FETCH_TIMEOUT = 15
_SEARCH_TIMEOUT = 10
_ALLOWED_CONTENT_TYPES = ("text/", "application/xhtml", "application/xml", "application/json")
_USER_AGENT = "ResumeAgent/1.0 (+local resume assistant)"


async def _validate_public_url(url: str) -> str | None:
    """Return an error string if the URL must not be fetched, else None.

    Blocks non-http(s) schemes, embedded credentials, and any hostname that
    resolves to a private/loopback/link-local/reserved address (SSRF guard,
    including cloud metadata endpoints like 169.254.169.254).
    """
    try:
        parsed = urlparse(url)
    except ValueError:
        return "Invalid URL"
    if parsed.scheme not in ("http", "https"):
        return "Only http/https URLs are allowed"
    if parsed.username or parsed.password:
        return "URLs with embedded credentials are not allowed"
    host = parsed.hostname
    if not host:
        return "Invalid URL: missing host"

    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        infos = await asyncio.get_running_loop().getaddrinfo(
            host, port, proto=socket.IPPROTO_TCP
        )
    except socket.gaierror:
        return f"DNS resolution failed for {host}"

    for info in infos:
        try:
            ip = ipaddress.ip_address(info[4][0])
        except ValueError:
            return "Unresolvable address"
        if (
            ip.is_private or ip.is_loopback or ip.is_link_local
            or ip.is_reserved or ip.is_multicast or ip.is_unspecified
        ):
            return f"Blocked non-public address for {host}"
    return None


def _strip_html(raw: str) -> str:
    text = re.sub(r"<script[^>]*>.*?</script>", "", raw, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html_lib.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


class WebSearchTool(BaseTool):
    """Quick-facts lookup via the DuckDuckGo Instant Answer API."""

    @property
    def metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="web_search",
            category=ToolCategory.WEB,
            description=(
                "Quick encyclopedic lookup (DuckDuckGo Instant Answers). Works for "
                "well-known entities (companies, technologies); often returns nothing "
                "for general phrases — treat an empty result as 'not covered', not "
                "'does not exist'. Do NOT include personal data from the resume in queries."
            ),
            usage_guide="Use for looking up a company or technology by name. For GitHub repos, use fetch_repo_metadata instead.",
            estimated_time=Difficulty.MEDIUM,
        )

    async def execute(self, query: str = "", **kwargs) -> ToolResult:
        if not query:
            return ToolResult.fail("PARAM_ERROR", "query is required", is_retryable=False)
        query = str(query)[:300]

        try:
            import httpx
            logger.info("Web search: query_len=%d", len(query))

            search_url = (
                f"https://api.duckduckgo.com/?q={quote(query)}"
                "&format=json&no_html=1&skip_disambig=1"
            )
            async with httpx.AsyncClient(timeout=_SEARCH_TIMEOUT) as client:
                resp = await client.get(search_url, headers={"User-Agent": _USER_AGENT})

            if resp.status_code != 200:
                return ToolResult.fail(
                    "SEARCH_ERROR",
                    f"Search failed with status {resp.status_code}",
                    is_retryable=resp.status_code >= 500,
                )

            data = resp.json()
            results = []

            if data.get("AbstractText"):
                results.append({
                    "type": "summary",
                    "title": data.get("Heading", ""),
                    "content": data["AbstractText"],
                    "source": data.get("AbstractURL", ""),
                })

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

            note = ""
            if not results:
                note = (
                    "Instant Answer API returned no entry for this query. "
                    "This does not mean the topic doesn't exist — the API only "
                    "covers well-known entities. Consider web_fetch on a known URL."
                )

            return ToolResult.ok({
                "query": query,
                "results": results[:8],
                "result_count": len(results),
                "note": note,
            })

        except Exception as e:
            logger.warning("Web search failed: %s", e)
            return ToolResult.fail("SEARCH_ERROR", str(e), is_retryable=True)


class WebFetchTool(BaseTool):
    """Fetch and extract readable text content from a public URL."""

    @property
    def metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="web_fetch",
            category=ToolCategory.WEB,
            description="Fetch and read text content from a public web page (articles, company pages, etc.). Not for GitHub repos.",
            usage_guide="Use for reading public web pages. For GitHub repositories, use fetch_repo_metadata and other GitHub tools.",
            estimated_time=Difficulty.LIGHT,
        )

    async def execute(self, url: str = "", **kwargs) -> ToolResult:
        if not url:
            return ToolResult.fail("PARAM_ERROR", "url is required", is_retryable=False)
        url = str(url).strip()

        try:
            import httpx

            current = url
            max_bytes = settings.web_fetch_max_bytes
            async with httpx.AsyncClient(
                timeout=_FETCH_TIMEOUT, follow_redirects=False
            ) as client:
                for _ in range(_MAX_REDIRECTS + 1):
                    err = await _validate_public_url(current)
                    if err:
                        return ToolResult.fail("FETCH_BLOCKED", err, is_retryable=False)

                    logger.info("Web fetch: host=%s", urlparse(current).hostname)
                    async with client.stream(
                        "GET", current, headers={"User-Agent": _USER_AGENT}
                    ) as resp:
                        if resp.status_code in (301, 302, 303, 307, 308):
                            location = resp.headers.get("location")
                            if not location:
                                return ToolResult.fail(
                                    "FETCH_ERROR", "Redirect without Location header",
                                    is_retryable=False,
                                )
                            current = urljoin(current, location)
                            continue

                        if resp.status_code != 200:
                            return ToolResult.fail(
                                "FETCH_ERROR", f"HTTP {resp.status_code}",
                                is_retryable=resp.status_code >= 500,
                            )

                        content_type = resp.headers.get("content-type", "").lower()
                        if content_type and not content_type.startswith(_ALLOWED_CONTENT_TYPES):
                            return ToolResult.fail(
                                "FETCH_ERROR",
                                f"Unsupported content type: {content_type.split(';')[0]}",
                                is_retryable=False,
                            )

                        chunks: list[bytes] = []
                        total = 0
                        truncated = False
                        async for chunk in resp.aiter_bytes():
                            total += len(chunk)
                            if total > max_bytes:
                                chunks.append(chunk[: max_bytes - (total - len(chunk))])
                                truncated = True
                                break
                            chunks.append(chunk)
                        raw_bytes = b"".join(chunks)
                        break
                else:
                    return ToolResult.fail(
                        "FETCH_ERROR", "Too many redirects", is_retryable=False
                    )

            charset_match = re.search(r"charset=([\w\-]+)", content_type)
            encoding = charset_match.group(1) if charset_match else "utf-8"
            try:
                raw_text = raw_bytes.decode(encoding, errors="replace")
            except LookupError:
                raw_text = raw_bytes.decode("utf-8", errors="replace")

            text = _strip_html(raw_text)[:5000]

            title = ""
            title_match = re.search(
                r"<title[^>]*>(.*?)</title>", raw_text, re.IGNORECASE | re.DOTALL
            )
            if title_match:
                title = _strip_html(title_match.group(1))[:200]

            return ToolResult.ok({
                "url": url,
                "final_url": current,
                "title": title,
                "content": text,
                "content_type": content_type.split(";")[0],
                "truncated": truncated,
            })

        except Exception as e:
            logger.warning("Web fetch failed: %s", e)
            return ToolResult.fail("FETCH_ERROR", str(e), is_retryable=True)
