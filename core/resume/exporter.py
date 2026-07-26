"""ResumeExporter — export ResumeData to Markdown and PDF."""

import html
import logging
import re

from core.resume.schema import ResumeData

logger = logging.getLogger(__name__)

# Simple HTML template for PDF export
PDF_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<style>
  body {{ font-family: "Segoe UI", "Microsoft YaHei", "PingFang SC", "Noto Sans CJK SC", sans-serif; max-width: 800px; margin: 40px auto; color: #333; line-height: 1.6; }}
  h1 {{ font-size: 24px; border-bottom: 2px solid #2563eb; padding-bottom: 8px; }}
  h2 {{ font-size: 18px; color: #2563eb; margin-top: 24px; border-bottom: 1px solid #ddd; padding-bottom: 4px; }}
  .contact {{ color: #666; font-size: 14px; margin-bottom: 16px; }}
  .contact span {{ margin-right: 16px; }}
  .summary {{ margin-bottom: 20px; font-size: 14px; }}
  .entry {{ margin-bottom: 16px; }}
  .entry-header {{ font-weight: bold; }}
  .entry-sub {{ color: #666; font-size: 14px; }}
  .entry-date {{ color: #888; font-size: 13px; float: right; }}
  ul {{ margin: 4px 0; padding-left: 20px; }}
  li {{ margin-bottom: 2px; font-size: 14px; }}
  .skills {{ display: flex; flex-wrap: wrap; gap: 8px; }}
  .skill-tag {{ background: #eff6ff; color: #2563eb; padding: 4px 12px; border-radius: 4px; font-size: 13px; }}
</style>
</head>
<body>
{content}
</body>
</html>"""

# Headings are exactly 1-3 leading '#' followed by whitespace; anything else
# (e.g. "#tag" or "####") is treated as regular text.
_HEADING_RE = re.compile(r"^(#{1,3})\s+")
_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
_ITALIC_RE = re.compile(r"\*([^*]+?)\*")


class ResumeExporter:
    """Export ResumeData to various formats."""

    def export_markdown(self, resume: ResumeData) -> str:
        """Render resume as clean Markdown."""
        parts = []
        pi = resume.personal_info

        # Header
        parts.append(f"# {pi.full_name or 'Untitled'}")
        contacts = []
        if pi.email:
            contacts.append(pi.email)
        if pi.phone:
            contacts.append(pi.phone)
        if pi.location:
            contacts.append(pi.location)
        if contacts:
            parts.append(" | ".join(contacts))
        if pi.github:
            parts.append(f"GitHub: {pi.github}")
        if pi.linkedin:
            parts.append(f"LinkedIn: {pi.linkedin}")
        parts.append("")

        # Summary
        if pi.summary:
            parts.append("## 个人概述")
            parts.append(pi.summary)
            parts.append("")

        # Education
        if resume.education:
            parts.append("## 教育背景")
            for edu in resume.education:
                parts.append(f"### {edu.school}")
                parts.append(f"- **{edu.degree}** · {edu.major}")
                if edu.gpa:
                    parts.append(f"- GPA: {edu.gpa}")
                if edu.description:
                    parts.append(f"- {edu.description}")
                parts.append("")

        # Work Experience
        if resume.work_experience:
            parts.append("## 工作经历")
            for work in resume.work_experience:
                date_range = self._format_date_range(work.start_date, work.end_date, work.is_current)
                parts.append(f"### {work.company} — {work.position}")
                if date_range:
                    parts.append(f"*{date_range}*")
                if work.location:
                    parts.append(f"地点: {work.location}")
                for bullet in work.bullets:
                    parts.append(f"- {bullet}")
                if work.description:
                    parts.append(work.description)
                parts.append("")

        # Project Experience
        if resume.project_experience:
            parts.append("## 项目经历")
            for proj in resume.project_experience:
                date_range = self._format_date_range(proj.start_date, proj.end_date)
                parts.append(f"### {proj.name}")
                parts.append(f"**角色**: {proj.role}")
                if date_range:
                    parts.append(f"*{date_range}*")
                if proj.technologies:
                    parts.append(f"**技术栈**: {', '.join(proj.technologies)}")
                for bullet in proj.bullets:
                    parts.append(f"- {bullet}")
                if proj.description:
                    parts.append(proj.description)
                if proj.is_planned:
                    parts.append("> ⚠️ 计划中的项目")
                parts.append("")

        # Skills
        if resume.skills:
            parts.append("## 技能")
            for skill in resume.skills:
                line = f"- **{skill.name}**"
                if skill.category:
                    line += f" [{skill.category}]"
                if skill.years:
                    line += f" — {skill.years}年"
                parts.append(line)
            parts.append("")

        return "\n".join(parts)

    def export_pdf_html(self, resume: ResumeData) -> str:
        """Render resume as full HTML page for PDF generation."""
        md = self.export_markdown(resume)
        html_body = self._md_to_html(md)
        return PDF_TEMPLATE.format(content=html_body)

    @staticmethod
    def _format_date_range(start_date, end_date, is_current: bool = False) -> str:
        """Format a date range for display; returns "" when no dates are known."""
        start = str(start_date) if start_date else ""
        if is_current:
            return f"{start} — 至今" if start else "至今"
        end = str(end_date) if end_date else ""
        if start and end:
            return f"{start} — {end}"
        # Single-ended range: show the known side only; "" when both missing.
        return start or end

    @staticmethod
    def _inline_md(text: str) -> str:
        """HTML-escape user text, then apply inline markdown (bold/italic).

        Escaping runs first (html.escape replaces '&' before '<'/'>'/quotes),
        so no raw user content can reach the HTML output; the '*' markers are
        untouched by escaping and transformed afterwards.
        """
        text = html.escape(text)
        text = _BOLD_RE.sub(r"<strong>\1</strong>", text)
        text = _ITALIC_RE.sub(r"<em>\1</em>", text)
        return text

    def _md_to_html(self, md: str) -> str:
        """Lightweight markdown to HTML conversion.

        Lines are classified by structure first (heading / list item /
        blockquote / blank / paragraph) so the <ul> state machine always
        closes correctly — inline bold/italic never affects classification.
        """
        html_lines: list[str] = []
        in_list = False

        def close_list():
            nonlocal in_list
            if in_list:
                html_lines.append("</ul>")
                in_list = False

        for line in md.split("\n"):
            heading = _HEADING_RE.match(line)
            if heading:
                close_list()
                level = len(heading.group(1))
                content = line[heading.end():].strip()
                html_lines.append(f"<h{level}>{self._inline_md(content)}</h{level}>")
            elif line.startswith("- "):
                if not in_list:
                    html_lines.append("<ul>")
                    in_list = True
                html_lines.append(f"<li>{self._inline_md(line[2:])}</li>")
            elif line.startswith("> "):
                close_list()
                html_lines.append(f"<blockquote>{self._inline_md(line[2:])}</blockquote>")
            elif not line.strip():
                close_list()
            else:
                close_list()
                html_lines.append(f"<p>{self._inline_md(line)}</p>")

        close_list()
        return "\n".join(html_lines)
