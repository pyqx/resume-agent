"""GitHub analysis API routes — progressive disclosure streaming."""

import json
import logging

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from sse_starlette.sse import EventSourceResponse

from core.github.analyzer import GitHubAnalyzer
from core.cache import get_cache

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/analyze")
async def analyze_github_repo(request: Request):
    """Progressive 5-stage GitHub repo analysis streamed via SSE."""
    body = await request.json()
    repo_url = body.get("repo_url", "")

    if not repo_url:
        raise HTTPException(status_code=400, detail="repo_url is required")

    analyzer = GitHubAnalyzer(cache=get_cache())

    async def event_generator():
        # Stage 1: Metadata
        yield {"event": "stage", "data": '{"stage": 1, "name": "metadata"}'}
        meta = await analyzer.stage1_metadata(repo_url)
        yield {"event": "metadata", "data": json.dumps(meta)}

        # Stage 2: Structure
        yield {"event": "stage", "data": '{"stage": 2, "name": "structure"}'}
        structure = await analyzer.stage2_structure(repo_url)
        yield {"event": "structure", "data": json.dumps(structure)[:5000]}

        # Stage 3: Deep analysis
        yield {"event": "stage", "data": '{"stage": 3, "name": "deep_analysis"}'}
        deep = await analyzer.stage3_deep_analysis(repo_url)
        yield {"event": "deep_analysis", "data": json.dumps(deep)[:5000]}

        # Combine all analysis for stage 4
        full_analysis = {
            "metadata": meta,
            "structure": structure,
            "dependencies": deep.get("dependencies", {}),
            "issues": deep.get("issues", {}),
        }

        # Stage 4: Suggestions
        yield {"event": "stage", "data": '{"stage": 4, "name": "suggestions"}'}
        suggestions = await analyzer.stage4_suggestions(full_analysis)
        yield {"event": "suggestions", "data": json.dumps(suggestions)[:8000]}

        # Stage 5: ready for resume entry composition (on-demand)
        yield {"event": "stage", "data": '{"stage": 5, "name": "ready"}'}
        yield {"event": "complete", "data": '{"status": "analysis_complete"}'}

    return EventSourceResponse(event_generator())


@router.post("/compose-entry")
async def compose_resume_entry(request: Request):
    """Generate a STAR-format resume entry from a selected suggestion."""
    body = await request.json()
    suggestion = body.get("suggestion", {})
    repo_context = body.get("repo_context", {})

    if not suggestion:
        raise HTTPException(status_code=400, detail="suggestion is required")

    analyzer = GitHubAnalyzer()
    result = await analyzer.stage5_resume_entry(suggestion, repo_context)
    return result
