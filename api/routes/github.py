"""GitHub analysis API routes — progressive disclosure streaming."""

import json
import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, ValidationError
from sse_starlette.sse import EventSourceResponse
from starlette.requests import Request

from api.deps import get_llm_client, get_disk_cache

logger = logging.getLogger(__name__)

router = APIRouter()

_analyzer = None

# Per-event payload budget. Data is SHRUNK structurally (long strings and
# lists trimmed) and then serialized — never sliced after json.dumps, which
# used to produce unparseable JSON fragments.
_EVENT_BUDGET = 8000


def _get_analyzer():
    global _analyzer
    if _analyzer is None:
        from core.github.analyzer import GitHubAnalyzer
        _analyzer = GitHubAnalyzer(llm_client=get_llm_client(), cache=get_disk_cache())
    return _analyzer


def _shrink(obj, str_limit: int = 2000, list_limit: int = 10):
    """Recursively bound string/list sizes so the serialized JSON stays valid."""
    if isinstance(obj, str):
        return obj if len(obj) <= str_limit else obj[:str_limit] + "…(截断)"
    if isinstance(obj, list):
        trimmed = [_shrink(x, str_limit, list_limit) for x in obj[:list_limit]]
        if len(obj) > list_limit:
            trimmed.append(f"…(+{len(obj) - list_limit} more)")
        return trimmed
    if isinstance(obj, dict):
        return {k: _shrink(v, str_limit, list_limit) for k, v in obj.items()}
    return obj


def _event_json(data: dict) -> str:
    payload = json.dumps(data, ensure_ascii=False, default=str)
    if len(payload) <= _EVENT_BUDGET:
        return payload
    return json.dumps(_shrink(data), ensure_ascii=False, default=str)


class AnalyzeRequest(BaseModel):
    repo_url: str = Field(min_length=10, max_length=300)


@router.post("/analyze")
async def analyze_github_repo(request: Request):
    """Progressive 5-stage GitHub repo analysis streamed via SSE."""
    try:
        body = await request.json()
        req = AnalyzeRequest.model_validate(body)
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=e.errors()[:3])
    except Exception:
        raise HTTPException(status_code=400, detail="请求体不是合法的 JSON")

    from core.github.cloner import RepoCloner
    if RepoCloner._normalize_url(req.repo_url) is None:
        raise HTTPException(
            status_code=400,
            detail="不是有效的仓库地址(支持 github.com / gitlab.com / gitee.com)",
        )

    analyzer = _get_analyzer()
    repo_url = req.repo_url

    async def event_generator():
        try:
            yield {"event": "stage", "data": json.dumps({"stage": 1, "name": "metadata"})}
            meta = await analyzer.stage1_metadata(repo_url)
            yield {"event": "metadata", "data": _event_json(meta)}

            yield {"event": "stage", "data": json.dumps({"stage": 2, "name": "structure"})}
            structure = await analyzer.stage2_structure(repo_url)
            yield {"event": "structure", "data": _event_json(structure)}

            yield {"event": "stage", "data": json.dumps({"stage": 3, "name": "deep_analysis"})}
            deep = await analyzer.stage3_deep_analysis(repo_url)
            yield {"event": "deep_analysis", "data": _event_json(deep)}

            full_analysis = {
                "metadata": meta,
                "structure": structure,
                "dependencies": deep.get("dependencies", {}),
                "issues": deep.get("issues", {}),
            }

            # Personalize suggestions with the current resume's direction.
            from api.routes.resume import resolve_resume
            career = ""
            resume = resolve_resume()
            if resume:
                career = resume.target_position or (
                    resume.work_experience[0].position if resume.work_experience else ""
                )

            yield {"event": "stage", "data": json.dumps({"stage": 4, "name": "suggestions"})}
            suggestions = await analyzer.stage4_suggestions(
                full_analysis, career_direction=career
            )
            yield {"event": "suggestions", "data": _event_json(suggestions)}

            yield {"event": "stage", "data": json.dumps({"stage": 5, "name": "ready"})}
            yield {"event": "complete", "data": json.dumps({"status": "analysis_complete"})}
        except Exception as e:
            # Never let the stream die silently — the frontend needs a
            # terminal error event to stop its loading state.
            logger.exception("GitHub analysis failed for %s", repo_url)
            yield {
                "event": "error",
                "data": json.dumps({"error": f"分析失败: {e}"}, ensure_ascii=False),
            }
        finally:
            try:
                await analyzer.release_clones()
            except Exception as e:
                logger.warning("Clone cleanup failed: %s", e)

    return EventSourceResponse(event_generator())


class ComposeRequest(BaseModel):
    suggestion: dict
    repo_context: dict = Field(default_factory=dict)


@router.post("/compose-entry")
async def compose_resume_entry(request: Request):
    """Generate a STAR-format resume entry from a selected suggestion."""
    try:
        body = await request.json()
        req = ComposeRequest.model_validate(body)
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=e.errors()[:3])
    except Exception:
        raise HTTPException(status_code=400, detail="请求体不是合法的 JSON")

    if not req.suggestion:
        raise HTTPException(status_code=400, detail="suggestion is required")

    try:
        return await _get_analyzer().stage5_resume_entry(req.suggestion, req.repo_context)
    except RuntimeError as e:
        logger.warning("Resume entry composition failed: %s", e)
        raise HTTPException(status_code=502, detail=f"简历条目生成失败,请稍后重试({e})")
