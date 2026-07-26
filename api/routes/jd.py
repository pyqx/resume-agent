"""JD matching API routes."""

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, ValidationError
from starlette.requests import Request

from api.deps import get_llm_client, get_disk_cache

logger = logging.getLogger(__name__)

router = APIRouter()

_MAX_JD_CHARS = 20000

_parser = None
_matcher = None
_detector = None


def _get_parser():
    global _parser
    if _parser is None:
        from core.jd.parser import JDParser
        _parser = JDParser(llm_client=get_llm_client())
    return _parser


def _get_matcher():
    global _matcher
    if _matcher is None:
        from core.jd.matcher import JDMatcher
        _matcher = JDMatcher(llm_client=get_llm_client(), cache=get_disk_cache())
    return _matcher


def _get_detector():
    global _detector
    if _detector is None:
        from core.jd.signal_detector import SignalDetector
        _detector = SignalDetector()
    return _detector


class JDTextRequest(BaseModel):
    jd_text: str = Field(min_length=10, max_length=_MAX_JD_CHARS)
    resume_id: str = ""


async def _parse_body(request: Request, model):
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="请求体不是合法的 JSON")
    try:
        return model.model_validate(body)
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=e.errors()[:3])


def _merged_signals(jd_reqs, jd_text: str):
    """Rule-detected signals + LLM-extracted signals, deduped by phrase.

    Previously /parse overwrote the LLM's signals with rules while /match
    kept only the LLM's — two endpoints disagreed on the same JD.
    """
    rule_signals = _get_detector().detect(jd_text)
    seen = {s.phrase for s in rule_signals}
    merged = list(rule_signals)
    for s in jd_reqs.soft_signals:
        if s.phrase and s.phrase not in seen:
            merged.append(s)
            seen.add(s.phrase)
    return merged


@router.post("/parse")
async def parse_jd(request: Request):
    """Parse a job description text into structured requirements."""
    req = await _parse_body(request, JDTextRequest)

    logger.info("JD parse: input length=%d", len(req.jd_text))
    try:
        jd_reqs = await _get_parser().parse(req.jd_text)
    except RuntimeError as e:
        logger.warning("JD parse failed: %s", e)
        raise HTTPException(status_code=502, detail=f"JD 解析失败,请稍后重试({e})")

    jd_reqs.soft_signals = _merged_signals(jd_reqs, req.jd_text)
    logger.info(
        "JD parse result: hard=%d nice=%d keywords=%d signals=%d",
        len(jd_reqs.hard_requirements), len(jd_reqs.nice_to_have),
        len(jd_reqs.keyword_frequency), len(jd_reqs.soft_signals),
    )
    return jd_reqs.model_dump(mode="json")


@router.post("/match")
async def match_jd(request: Request):
    """Match a JD against a resume and generate a match report.

    Response is the MatchReport (top-level, backward compatible) plus a
    "jd_requirements" key so the frontend needs only this one call.
    """
    req = await _parse_body(request, JDTextRequest)

    from api.routes.resume import resolve_resume
    resume = resolve_resume(req.resume_id)
    if not resume:
        raise HTTPException(status_code=404, detail="未找到简历,请先上传或选择简历")

    logger.info("JD match: input length=%d resume=%s", len(req.jd_text), resume.id)
    try:
        jd_reqs = await _get_parser().parse(req.jd_text)
        jd_reqs.soft_signals = _merged_signals(jd_reqs, req.jd_text)
        report = await _get_matcher().match(jd_reqs, resume)
    except RuntimeError as e:
        logger.warning("JD match failed: %s", e)
        raise HTTPException(status_code=502, detail=f"匹配失败,请稍后重试({e})")

    logger.info(
        "JD match result: score=%.1f%% must=%d/%d plus=%d/%d errors=%d",
        report.overall_score, report.must_have_met, report.must_have_total,
        report.plus_met, report.plus_total, report.scoring_errors,
    )
    payload = report.model_dump(mode="json")
    payload["jd_requirements"] = jd_reqs.model_dump(mode="json")
    return payload


@router.post("/signals")
async def detect_signals(request: Request):
    """Detect hidden signals in a JD text (rule-based, instant)."""
    req = await _parse_body(request, JDTextRequest)
    signals = _get_detector().detect(req.jd_text)
    return {"signals": [s.model_dump(mode="json") for s in signals]}


class KeywordRequest(BaseModel):
    jd_text: str = Field(default="", max_length=_MAX_JD_CHARS)
    keywords: list[str] = Field(default_factory=list, max_length=200)
    resume_id: str = ""


@router.post("/keywords")
async def analyze_keywords(request: Request):
    """Keyword coverage between a JD and the resume.

    Pass `keywords` (e.g. keys of a previous /parse result's
    keyword_frequency) to skip the LLM parse; otherwise `jd_text` is parsed.
    """
    req = await _parse_body(request, KeywordRequest)

    from api.routes.resume import resolve_resume
    resume = resolve_resume(req.resume_id)
    if not resume:
        raise HTTPException(status_code=404, detail="未找到简历,请先上传或选择简历")

    keywords = [k for k in (req.keywords or []) if isinstance(k, str) and k.strip()]
    if not keywords:
        if not req.jd_text or len(req.jd_text) < 10:
            raise HTTPException(status_code=400, detail="需要提供 keywords 或 jd_text")
        try:
            jd_reqs = await _get_parser().parse(req.jd_text)
        except RuntimeError as e:
            raise HTTPException(status_code=502, detail=f"JD 解析失败({e})")
        keywords = list(jd_reqs.keyword_frequency.keys())

    if not keywords:
        return {"coverage_rate": None, "matched_keywords": [], "missing_keywords": [],
                "note": "该 JD 未提取到关键词"}

    from core.jd.keywords import compute_keyword_coverage
    result = compute_keyword_coverage(keywords, resume)
    return {
        "coverage_rate": result.get("coverage_rate"),
        "matched_keywords": result.get("matched", [])[:50],
        "missing_keywords": result.get("missing", [])[:50],
    }
