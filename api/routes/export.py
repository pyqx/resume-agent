"""Export API routes — Markdown and PDF export."""

import logging

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, PlainTextResponse

from core.resume.exporter import ResumeExporter
from api.routes.resume import _resume_store

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/markdown")
async def export_markdown(request: Request):
    """Export a resume as Markdown text."""
    body = await request.json()
    resume_id = body.get("resume_id", "")

    resume = _get_resume(resume_id)
    if not resume:
        raise HTTPException(status_code=404, detail="Resume not found")

    exporter = ResumeExporter()
    markdown = exporter.export_markdown(resume)

    return PlainTextResponse(content=markdown, media_type="text/markdown; charset=utf-8")


@router.post("/html")
async def export_html(request: Request):
    """Export a resume as HTML (for PDF generation)."""
    body = await request.json()
    resume_id = body.get("resume_id", "")

    resume = _get_resume(resume_id)
    if not resume:
        raise HTTPException(status_code=404, detail="Resume not found")

    exporter = ResumeExporter()
    html = exporter.export_pdf_html(resume)

    return HTMLResponse(content=html)


@router.get("/templates")
async def list_templates():
    """List available resume templates."""
    return {
        "templates": [
            {"id": "classic", "name": "经典模板", "description": "适合金融/法律/国企等传统行业"},
            {"id": "modern", "name": "现代模板", "description": "适合互联网/技术行业"},
            {"id": "minimal", "name": "极简模板", "description": "适合设计/创意行业"},
        ]
    }


def _get_resume(resume_id: str = ""):
    """Helper to get resume from store."""
    if resume_id:
        return _resume_store.get(resume_id)
    if _resume_store:
        return next(iter(_resume_store.values()))
    return None
