"""JD matching API routes."""

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from core.jd.parser import JDParser
from core.jd.matcher import JDMatcher
from core.jd.signal_detector import SignalDetector
from api.routes.resume import _resume_store

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/parse")
async def parse_jd(request: Request):
    """Parse a job description text into structured requirements."""
    body = await request.json()
    jd_text = body.get("jd_text", "")

    if not jd_text:
        raise HTTPException(status_code=400, detail="jd_text is required")

    parser = JDParser()
    jd_reqs = await parser.parse(jd_text)

    # Also detect signals
    detector = SignalDetector()
    signals = detector.detect(jd_text)
    jd_reqs.soft_signals = signals

    return jd_reqs.model_dump(mode="json")


@router.post("/match")
async def match_jd(request: Request):
    """Match a JD against a resume and generate a match report."""
    body = await request.json()
    jd_text = body.get("jd_text", "")
    resume_id = body.get("resume_id", "")

    if not jd_text:
        raise HTTPException(status_code=400, detail="jd_text is required")

    # Get resume
    resume = None
    if resume_id:
        resume = _resume_store.get(resume_id)
    elif _resume_store:
        resume = next(iter(_resume_store.values()))

    if not resume:
        raise HTTPException(status_code=404, detail="No resume found. Upload a resume first.")

    # Parse JD
    parser = JDParser()
    jd_reqs = await parser.parse(jd_text)

    # Match
    matcher = JDMatcher()
    report = await matcher.match(jd_reqs, resume)

    return report.model_dump(mode="json")


@router.post("/signals")
async def detect_signals(request: Request):
    """Detect hidden signals in a JD text."""
    body = await request.json()
    jd_text = body.get("jd_text", "")

    if not jd_text:
        raise HTTPException(status_code=400, detail="jd_text is required")

    detector = SignalDetector()
    signals = detector.detect(jd_text)

    return {"signals": [s.model_dump(mode="json") for s in signals]}


@router.post("/keywords")
async def analyze_keywords(request: Request):
    """Analyze keyword overlap between a JD and resume."""
    body = await request.json()
    jd_text = body.get("jd_text", "")
    resume_id = body.get("resume_id", "")

    if not jd_text:
        raise HTTPException(status_code=400, detail="jd_text is required")

    resume = None
    if resume_id:
        resume = _resume_store.get(resume_id)
    elif _resume_store:
        resume = next(iter(_resume_store.values()))

    import json
    resume_text = json.dumps(resume.model_dump(mode="json"), default=str) if resume else ""

    jd_lower = jd_text.lower()
    resume_lower = resume_text.lower()

    import re
    tech_words = set(re.findall(r'\b[a-zA-Z+#.-]{2,}\b', jd_lower))
    common_words = {'the', 'a', 'an', 'is', 'are', 'and', 'or', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'you', 'will', 'be', 'we', 'our'}
    jd_keywords = {w for w in tech_words if w not in common_words}

    matched = [kw for kw in jd_keywords if kw in resume_lower]
    missing = list(jd_keywords - set(matched))

    return {
        "coverage_rate": round(len(matched) / len(jd_keywords) * 100, 1) if jd_keywords else 0,
        "matched_keywords": matched[:50],
        "missing_keywords": missing[:50],
    }
