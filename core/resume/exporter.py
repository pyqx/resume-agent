"""ResumeExporter — export ResumeData to Markdown and PDF."""

import logging
from pathlib import Path

from core.resume.schema import ResumeData

logger = logging.getLogger(__name__)

# Simple HTML template for PDF export
PDF_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<style>
  body {{ font-family: 'Segoe UI', Arial, sans-serif; max-width: 800px; margin: 40px auto; color: #333; line-height: 1.6; }}
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
                level_bar = "████" if skill.level else "----"
                parts.append(f"- **{skill.name}** [{skill.category}] — {skill.years}年")
            parts.append("")

        return "\n".join(parts)

    def export_html(self, resume: ResumeData) -> str:
        """Render resume as HTML."""
        md = self.export_markdown(resume)
        # Simple markdown-to-HTML conversion
        return self._md_to_html(md)

    def export_pdf_html(self, resume: ResumeData) -> str:
        """Render resume as full HTML page for PDF generation."""
        md = self.export_markdown(resume)
        html_body = self._md_to_html(md)
        return PDF_TEMPLATE.format(content=html_body)

    @staticmethod
    def _format_date_range(start_date, end_date, is_current: bool = False) -> str:
        """Format a date range for display."""
        start = str(start_date) if start_date else "?"
        if is_current:
            return f"{start} — 至今"
        end = str(end_date) if end_date else "?"
        return f"{start} — {end}"

    def _md_to_html(self, md: str) -> str:
        """Basic markdown to HTML conversion (lightweight)."""
        import re

        lines = md.split("\n")
        html_lines = []
        in_list = False

        for line in lines:
            # Headers
            if line.startswith("# "):
                if in_list:
                    html_lines.append("</ul>")
                    in_list = False
                html_lines.append(f'<h1>{line[2:]}</h1>')
            elif line.startswith("## "):
                if in_list:
                    html_lines.append("</ul>")
                    in_list = False
                html_lines.append(f'<h2>{line[3:]}</h2>')
            elif line.startswith("### "):
                if in_list:
                    html_lines.append("</ul>")
                    in_list = False
                html_lines.append(f'<h3>{line[4:]}</h3>')
            # Bold
            elif "**" in line:
                line = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', line)
                if line.startswith("- "):
                    if not in_list:
                        html_lines.append("<ul>")
                        in_list = True
                    html_lines.append(f'<li>{line[2:]}</li>')
                else:
                    if in_list:
                        html_lines.append("</ul>")
                        in_list = False
                    html_lines.append(f'<p>{line}</p>')
            # Italic
            elif "*" in line:
                line = re.sub(r'\*(.+?)\*', r'<em>\1</em>', line)
                html_lines.append(f'<p>{line}</p>')
            # List items
            elif line.startswith("- "):
                if not in_list:
                    html_lines.append("<ul>")
                    in_list = True
                html_lines.append(f'<li>{line[2:]}</li>')
            # Blockquote
            elif line.startswith("> "):
                if in_list:
                    html_lines.append("</ul>")
                    in_list = False
                html_lines.append(f'<blockquote>{line[2:]}</blockquote>')
            # Empty lines
            elif not line.strip():
                if in_list:
                    html_lines.append("</ul>")
                    in_list = False
            # Regular text
            else:
                if in_list and not line.startswith("- "):
                    html_lines.append("</ul>")
                    in_list = False
                html_lines.append(f'<p>{line}</p>')

        if in_list:
            html_lines.append("</ul>")

        return "\n".join(html_lines)
