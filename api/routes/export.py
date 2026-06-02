"""Export API routes — Markdown and PDF export."""

import logging
import io
import textwrap
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, StreamingResponse

from core.resume.exporter import ResumeExporter
from api.routes.resume import _resume_store

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/pdf-text")
async def export_pdf_text(request: Request):
    """Generate a real PDF from plain text content and return as file."""
    body = await request.json()
    text = body.get("text", "")
    filename = body.get("filename", "export.pdf")

    if not text.strip():
        raise HTTPException(status_code=400, detail="text is required")

    try:
        import fitz
        doc = fitz.open()
        page = doc.new_page()
        margin = 50
        line_height = 16
        max_width = page.rect.width - 2 * margin
        y = margin
        font = "china-s"  # Built-in CJK font supporting Chinese characters

        for line in text.split("\n"):
            if y > page.rect.height - margin:
                page = doc.new_page()
                y = margin
            # Handle headings: bold = larger font
            if line.startswith("# ") or line.startswith("## "):
                fontsize = 14 if line.startswith("# ") else 12
                line = line.lstrip("#").strip()
                page.insert_text((margin, y), line, fontsize=fontsize, fontname=font, color=(0, 0, 0))
                y += line_height + 4
            else:
                # Word-wrap long lines
                wrapped = textwrap.fill(line, width=int(max_width / 6)) if line.strip() else ""
                for w_line in (wrapped.split("\n") if wrapped else [""]):
                    if y > page.rect.height - margin:
                        page = doc.new_page()
                        y = margin
                    page.insert_text((margin, y), w_line, fontsize=10, fontname=font, color=(0, 0, 0))
                    y += line_height

        buf = io.BytesIO()
        doc.save(buf, garbage=4, deflate=True)
        doc.close()
        buf.seek(0)

        return StreamingResponse(
            buf,
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename*=utf-8''{quote(filename)}"},
        )
    except Exception as e:
        logger.exception("PDF generation failed")
        raise HTTPException(status_code=500, detail=f"PDF generation failed: {e}")


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
