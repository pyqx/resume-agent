"""Interview preparation API routes."""

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, ValidationError
from starlette.requests import Request

from api.deps import get_llm_client

logger = logging.getLogger(__name__)

router = APIRouter()

_question_generator = None
_intro_generator = None
_strategist = None
_jd_parser = None


def _components():
    global _question_generator, _intro_generator, _strategist, _jd_parser
    if _question_generator is None:
        from core.interview.question_generator import InterviewQuestionGenerator
        from core.interview.intro_generator import SelfIntroGenerator
        from core.interview.weakness_strategist import WeaknessStrategist
        from core.jd.parser import JDParser
        llm = get_llm_client()
        _question_generator = InterviewQuestionGenerator(llm_client=llm)
        _intro_generator = SelfIntroGenerator(llm_client=llm)
        _strategist = WeaknessStrategist(llm_client=llm)
        _jd_parser = JDParser(llm_client=llm)
    return _question_generator, _intro_generator, _strategist, _jd_parser


class InterviewRequest(BaseModel):
    resume_id: str = ""
    jd_text: str = Field(default="", max_length=20000)


async def _resolve(request: Request) -> tuple[InterviewRequest, object]:
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="请求体不是合法的 JSON")
    try:
        req = InterviewRequest.model_validate(body)
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=e.errors()[:3])

    from api.routes.resume import resolve_resume
    resume = resolve_resume(req.resume_id)
    if not resume:
        raise HTTPException(status_code=404, detail="未找到简历,请先上传或选择简历")
    return req, resume


@router.post("/questions")
async def generate_questions(request: Request):
    """Generate interview questions from resume (JD-targeted when jd_text given)."""
    req, resume = await _resolve(request)
    qg, _, _, jd_parser = _components()

    jd = None
    if req.jd_text and len(req.jd_text) >= 10:
        try:
            jd = await jd_parser.parse(req.jd_text)
        except RuntimeError as e:
            logger.warning("JD parse failed for questions; proceeding without JD: %s", e)

    try:
        return await qg.generate(resume, jd)
    except RuntimeError as e:
        logger.warning("Question generation failed: %s", e)
        raise HTTPException(status_code=502, detail=f"面试问题生成失败,请稍后重试({e})")


@router.post("/intro")
async def generate_intro(request: Request):
    """Generate self-introduction scripts."""
    _, resume = await _resolve(request)
    _, ig, _, _ = _components()
    try:
        return await ig.generate(resume)
    except RuntimeError as e:
        logger.warning("Intro generation failed: %s", e)
        raise HTTPException(status_code=502, detail=f"自我介绍生成失败,请稍后重试({e})")


@router.post("/weaknesses")
async def analyze_weaknesses(request: Request):
    """Analyze resume for potential interview concerns."""
    _, resume = await _resolve(request)
    _, _, ws, _ = _components()
    try:
        weaknesses = await ws.analyze(resume)
    except RuntimeError as e:
        logger.warning("Weakness analysis failed: %s", e)
        raise HTTPException(status_code=502, detail=f"弱点分析失败,请稍后重试({e})")
    return {"weaknesses": weaknesses}
