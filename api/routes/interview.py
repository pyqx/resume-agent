"""Interview preparation API routes."""

import logging

from fastapi import APIRouter, HTTPException, Request

from core.interview.question_generator import InterviewQuestionGenerator
from core.interview.intro_generator import SelfIntroGenerator
from core.interview.weakness_strategist import WeaknessStrategist
from api.routes.resume import _resume_store

logger = logging.getLogger(__name__)

router = APIRouter()


def _get_resume(resume_id: str = ""):
    if resume_id:
        return _resume_store.get(resume_id)
    if _resume_store:
        return next(iter(_resume_store.values()))
    return None


@router.post("/questions")
async def generate_questions(request: Request):
    """Generate interview questions from resume (and optionally JD)."""
    body = await request.json()
    resume_id = body.get("resume_id", "")
    jd_text = body.get("jd_text", "")

    resume = _get_resume(resume_id)
    if not resume:
        raise HTTPException(status_code=404, detail="No resume found")

    generator = InterviewQuestionGenerator()
    questions = await generator.generate(resume)
    return questions


@router.post("/intro")
async def generate_intro(request: Request):
    """Generate self-introduction scripts."""
    body = await request.json()
    resume_id = body.get("resume_id", "")

    resume = _get_resume(resume_id)
    if not resume:
        raise HTTPException(status_code=404, detail="No resume found")

    generator = SelfIntroGenerator()
    intro = await generator.generate(resume)
    return intro


@router.post("/weaknesses")
async def analyze_weaknesses(request: Request):
    """Analyze resume for potential interview concerns."""
    body = await request.json()
    resume_id = body.get("resume_id", "")

    resume = _get_resume(resume_id)
    if not resume:
        raise HTTPException(status_code=404, detail="No resume found")

    strategist = WeaknessStrategist()
    weaknesses = await strategist.analyze(resume)
    return {"weaknesses": weaknesses}
