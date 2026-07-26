"""resume_to_text — render ResumeData as human-readable plain text.

This rendered text is the single evaluation source shared by the rule
engine, the ATS simulator and the LLM judge. Never evaluate
``str(resume.model_dump())`` — that is a Python dict repr which leaks
UUIDs, field names and quoting into every text-based metric (page-length
estimates, "special character" checks, keyword matching, ...).
"""

from datetime import date

from core.resume.schema import ResumeData


def _fmt_date(d: date | None) -> str:
    return d.strftime("%Y-%m") if d else ""


def _date_range(start: date | None, end: date | None, is_current: bool = False) -> str:
    if start is None and end is None and not is_current:
        return ""
    left = _fmt_date(start)
    right = "至今" if (is_current or end is None) else _fmt_date(end)
    return f"{left} ~ {right}".strip()


def resume_to_text(resume: ResumeData) -> str:
    """Render a resume the way a human (or an ATS) would read it.

    Layout: name/contact lines, summary, education (school degree major
    dates), work (company position dates + one line per bullet), projects
    (name role tech stack + bullets), skills grouped by category.
    """
    lines: list[str] = []
    info = resume.personal_info

    if info.full_name:
        lines.append(info.full_name)
    contact = [
        v.strip()
        for v in (info.email, info.phone, info.location, info.linkedin, info.github, info.website)
        if v and v.strip()
    ]
    if contact:
        lines.append(" | ".join(contact))

    if info.summary:
        lines.append("")
        lines.append("个人概述:")
        lines.append(info.summary)

    if resume.education:
        lines.append("")
        lines.append("教育经历:")
        for edu in resume.education:
            head = " ".join(x for x in (edu.school, edu.degree, edu.major) if x)
            dates = _date_range(edu.start_date, edu.end_date)
            lines.append(" ".join(x for x in (head, dates) if x))
            if edu.gpa:
                lines.append(f"  GPA: {edu.gpa}")
            if edu.description:
                lines.append(f"  {edu.description}")

    if resume.work_experience:
        lines.append("")
        lines.append("工作经历:")
        for work in resume.work_experience:
            head = " ".join(x for x in (work.company, work.position) if x)
            dates = _date_range(work.start_date, work.end_date, work.is_current)
            lines.append(" ".join(x for x in (head, dates) if x))
            for bullet in work.bullets:
                lines.append(f"  - {bullet}")
            if work.description:
                lines.append(f"  {work.description}")

    if resume.project_experience:
        lines.append("")
        lines.append("项目经历:")
        for proj in resume.project_experience:
            head = " ".join(x for x in (proj.name, proj.role) if x)
            dates = _date_range(proj.start_date, proj.end_date)
            lines.append(" ".join(x for x in (head, dates) if x))
            if proj.technologies:
                lines.append(f"  技术栈: {', '.join(t for t in proj.technologies if t)}")
            for bullet in proj.bullets:
                lines.append(f"  - {bullet}")
            if proj.description:
                lines.append(f"  {proj.description}")

    if resume.skills:
        groups: dict[str, list[str]] = {}
        for skill in resume.skills:
            if skill.name:
                groups.setdefault(skill.category or "其他", []).append(skill.name)
        if groups:
            lines.append("")
            lines.append("技能:")
            for category, names in groups.items():
                lines.append(f"  {category}: {', '.join(names)}")

    # Drop a leading blank line if the resume had no name/contact block.
    while lines and not lines[0]:
        lines.pop(0)
    return "\n".join(lines)
