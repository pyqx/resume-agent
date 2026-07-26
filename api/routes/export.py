"""Export API routes — Markdown and PDF export."""

import io
import logging
import re
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, StreamingResponse
from starlette.concurrency import run_in_threadpool

from core.config import settings
from core.resume.exporter import ResumeExporter
from api.routes.resume import resolve_resume

logger = logging.getLogger(__name__)

router = APIRouter()

# PyMuPDF built-in CJK font (covers Chinese + Latin glyphs).
_PDF_FONT = "china-s"
_PDF_MARGIN = 50
_BODY_FONTSIZE = 10
# Exact-prefix markdown headings (#/##/###) with tiered font sizes.
_HEADING_SIZES = {1: 14, 2: 12, 3: 11}
_HEADING_RE = re.compile(r"^(#{1,3})\s+")


def _sanitize_filename(filename) -> str:
    """Derive a safe *.pdf download filename from untrusted client input."""
    if not isinstance(filename, str):
        filename = ""
    # Basename only (strips any path components), then drop control chars.
    name = Path(filename).name
    name = "".join(ch for ch in name if ch.isprintable()).strip()
    stem = Path(name).stem.strip().strip(".") if name else ""
    if not stem:
        return "export.pdf"
    return f"{stem}.pdf"


def _build_pdf(text: str) -> bytes:
    """Render text (with #/##/### headings) to a PDF.

    Blocking / CPU-bound (per-character font metrics) — must run in a
    worker thread, never on the event loop.
    """
    import fitz  # PyMuPDF

    def wrap_line(line: str, fontsize: int, max_width: float) -> list[str]:
        """Greedy per-character wrap using real font metrics.

        Correct for both CJK (no spaces, ~2x glyph width) and Latin text;
        `current` never exceeds one visual line, so each measurement is cheap.
        """
        if not line:
            return [""]
        segments: list[str] = []
        current = ""
        for ch in line:
            candidate = current + ch
            if current and fitz.get_text_length(
                candidate, fontname=_PDF_FONT, fontsize=fontsize
            ) > max_width:
                segments.append(current)
                current = ch
            else:
                current = candidate
        if current:
            segments.append(current)
        return segments

    doc = fitz.open()
    page = doc.new_page()
    max_width = page.rect.width - 2 * _PDF_MARGIN
    y = _PDF_MARGIN

    for raw_line in text.split("\n"):
        heading = _HEADING_RE.match(raw_line)
        if heading:
            fontsize = _HEADING_SIZES[len(heading.group(1))]
            content = raw_line[heading.end():].strip()
        else:
            fontsize = _BODY_FONTSIZE
            content = raw_line
        line_height = fontsize * 1.5

        for segment in wrap_line(content, fontsize, max_width):
            if y > page.rect.height - _PDF_MARGIN:
                page = doc.new_page()
                y = _PDF_MARGIN
            if segment:
                page.insert_text(
                    (_PDF_MARGIN, y), segment,
                    fontsize=fontsize, fontname=_PDF_FONT, color=(0, 0, 0),
                )
            y += line_height
        if heading:
            y += 4  # extra spacing below headings

    buf = io.BytesIO()
    doc.save(buf, garbage=4, deflate=True)
    doc.close()
    return buf.getvalue()


async def _resolve_from_body(request: Request):
    """Read resume_id from the JSON body and resolve the target resume."""
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="JSON body must be an object")

    resume_id = str(body.get("resume_id") or "")
    resume = resolve_resume(resume_id)
    if not resume:
        raise HTTPException(status_code=404, detail="未找到简历,请先上传或选择")
    return resume


@router.post("/pdf-text")
async def export_pdf_text(request: Request):
    """Generate a real PDF from plain text content and return as file."""
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="JSON body must be an object")

    text = body.get("text", "")
    if not isinstance(text, str):
        raise HTTPException(status_code=400, detail="text must be a string")
    if len(text) > settings.export_text_max_chars:
        raise HTTPException(
            status_code=413,
            detail=f"text too large (max {settings.export_text_max_chars} characters)",
        )
    if not text.strip():
        raise HTTPException(status_code=400, detail="text is required")

    filename = _sanitize_filename(body.get("filename"))

    try:
        pdf_bytes = await run_in_threadpool(_build_pdf, text)
    except Exception:
        logger.exception("PDF generation failed")
        raise HTTPException(status_code=500, detail="PDF generation failed")

    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename*=utf-8''{quote(filename)}"},
    )


@router.post("/markdown")
async def export_markdown(request: Request):
    """Export a resume as Markdown text."""
    resume = await _resolve_from_body(request)

    try:
        markdown = ResumeExporter().export_markdown(resume)
    except Exception:
        logger.exception("Markdown export failed")
        raise HTTPException(status_code=500, detail="Markdown export failed")

    return PlainTextResponse(content=markdown, media_type="text/markdown; charset=utf-8")


@router.post("/html")
async def export_html(request: Request):
    """Export a resume as HTML (for PDF generation)."""
    resume = await _resolve_from_body(request)

    try:
        html = ResumeExporter().export_pdf_html(resume)
    except Exception:
        logger.exception("HTML export failed")
        raise HTTPException(status_code=500, detail="HTML export failed")

    return HTMLResponse(
        content=html,
        headers={
            # Text is escaped server-side; CSP is defense-in-depth so nothing
            # can execute even if this HTML is opened directly in a browser.
            "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'",
            "X-Content-Type-Options": "nosniff",
        },
    )
