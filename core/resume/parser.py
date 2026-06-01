"""Multi-strategy resume parsing pipeline — PDF, DOCX, Markdown → ResumeData."""

import json
import logging
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any

from core.llm import get_llm_client_from_settings

from core.config import settings
from core.resume.schema import (
    ResumeData, PersonalInfo, Education, WorkExperience,
    ProjectExperience, Skill, EducationLevel, EDUCATION_LEVEL_CN_MAP,
)

logger = logging.getLogger(__name__)

EXTRACTION_PROMPT = """You are a resume data extraction system. Extract structured fields from the resume text below.

Output a JSON object matching this schema:
{
  "personal_info": {"full_name": "", "email": "", "phone": "", "location": "", "linkedin": "", "github": "", "website": "", "summary": ""},
  "education": [{"school": "", "degree": "", "major": "", "level": "bachelor", "start_date": "", "end_date": "", "gpa": "", "description": "", "confidence": 1.0}],
  "work_experience": [{"company": "", "position": "", "start_date": "", "end_date": "", "is_current": false, "location": "", "bullets": [], "description": "", "confidence": 1.0}],
  "project_experience": [{"name": "", "role": "", "url": "", "start_date": "", "end_date": "", "technologies": [], "bullets": [], "description": "", "confidence": 1.0}],
  "skills": [{"name": "", "category": "", "level": "", "years": 0.0}],
  "target_position": "",
  "target_industry": ""
}

Rules:
- Extract EVERYTHING you can find. Leave empty strings for missing fields.
- For dates, use ISO format YYYY-MM-DD. If only year/month is available, use YYYY-MM or YYYY.
- Set confidence between 0.0 and 1.0 based on how certain you are.
- DO NOT invent or guess information not present in the text.
- For work experience: extract each bullet point into the bullets array.
- For skills: try to categorize them.
- For education level: use English enum values (high_school/associate/bachelor/master/phd/other).
  Map Chinese: 高中/中专→high_school, 大专/专科→associate, 本科/学士→bachelor, 硕士/研究生→master, 博士→phd, 其他→other.
- IMPORTANT: The resume text may contain garbled/unreadable characters (shown as spaces).
  Skip garbled sections and extract only the readable information.
- IMPORTANT: Output ONLY pure ASCII-safe JSON. Do not include garbled Unicode in strings.
  If a field value contains garbled characters, either skip it or write the readable portion.

Resume Text:
{text}

Output ONLY valid JSON, no other text:"""


class ResumeParser:
    """Multi-strategy resume parsing pipeline.

    Strategy chain:
    1. pymupdf (PDF with text) or python-docx (DOCX) or raw text (MD)
    2. OCR fallback for scanned PDFs (future)
    3. LLM-based structured extraction
    """

    def __init__(self, llm_client=None):
        self._llm = llm_client
        self.last_raw_response: str = ""
        self.last_cleaned_json: str = ""
        self.last_parse_error: str = ""

    @property
    def llm(self):
        if self._llm is None:
            self._llm = get_llm_client_from_settings()
        return self._llm

    async def parse(self, file_path: str | Path) -> tuple[ResumeData, dict[str, Any]]:
        """Parse a resume file into structured ResumeData.

        Returns:
            (ResumeData, metadata) where metadata includes parse strategy used,
            confidence info, and any warnings.
        """
        file_path = Path(file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        suffix = file_path.suffix.lower()
        raw_text = ""
        strategy = ""
        warnings: list[str] = []

        # Stage 1: Text extraction
        if suffix == ".pdf":
            raw_text, warnings = self._parse_pdf(file_path)
            strategy = "pymupdf"
        elif suffix in (".docx", ".doc"):
            raw_text, warnings = self._parse_docx(file_path)
            strategy = "python-docx"
        elif suffix in (".md", ".txt", ".markdown"):
            raw_text = file_path.read_text(encoding="utf-8")
            strategy = "text"
        else:
            raise ValueError(f"Unsupported file format: {suffix}")

        if not raw_text.strip():
            raise ValueError("No text could be extracted from the file.")

        # Clean garbled text: keep only valid printable characters + common CJK
        raw_text = self._sanitize_text(raw_text)

        # Stage 2: LLM-based structured extraction
        resume_data = await self._extract_structured(raw_text)

        # Stage 3: OCR fallback if LLM extraction returned empty results
        if strategy == "pymupdf" and self._is_text_garbled(raw_text):
            has_content = bool(resume_data.education or resume_data.work_experience or resume_data.project_experience)
            if has_content:
                logger.info("Parse route = pymupdf text, garbled=%s, has_content=True (skipping OCR)", raw_text[:80].strip() != "")
            else:
                logger.info("Parse route = pymupdf text, garbled=%s, has_content=False → trying OCR", raw_text[:80].strip() != "")
                ocr_text = self._ocr_pdf(file_path)
                if ocr_text.strip():
                    ocr_text = self._sanitize_text(ocr_text)
                    resume_data = await self._extract_structured(ocr_text)
                    strategy = "pymupdf+ocr"
                    logger.info("Parse route = OCR fallback succeeded")
                else:
                    logger.info("Parse route = OCR unavailable, keeping original extraction")
        else:
            logger.info("Parse route = %s, garbled=%s", strategy, self._is_text_garbled(raw_text) if strategy == "pymupdf" else "N/A")

        metadata = {
            "strategy": strategy,
            "warnings": warnings,
            "raw_text_length": len(raw_text),
            "raw_text_preview": raw_text[:500],
        }

        return resume_data, metadata

    def _parse_pdf(self, file_path: Path) -> tuple[str, list[str]]:
        """Extract text from PDF using pymupdf, with OCR fallback for garbled text."""
        import fitz  # pymupdf

        doc = fitz.open(str(file_path))
        try:
            warnings: list[str] = []
            all_text: list[str] = []

            for page_num, page in enumerate(doc):
                blocks = page.get_text("dict")["blocks"]
                text_blocks = [b for b in blocks if b["type"] == 0]
                if not text_blocks:
                    continue

                x_centers = [(b["bbox"][0] + b["bbox"][2]) / 2 for b in text_blocks]
                if self._is_dual_column(x_centers):
                    warnings.append(f"Page {page_num+1}: dual-column detected, linearized")
                    linearized = self._linearize_dual_column(text_blocks)
                    page_text = "\n".join(self._block_to_text(b) for b in linearized)
                else:
                    page_text = page.get_text()

                all_text.append(page_text)

            raw_text = "\n\n".join(all_text)
        finally:
            doc.close()

        if not raw_text.strip():
            warnings.append("No text extracted from PDF")
        elif self._is_text_garbled(raw_text):
            warnings.append("PDF text partially garbled")

        logger.info("PDF extraction: text_len=%d garbled=%s", len(raw_text), self._is_text_garbled(raw_text))
        return raw_text, warnings

    @staticmethod
    def _is_text_garbled(text: str) -> bool:
        if len(text) < 50:
            return False
        valid = sum(1 for ch in text if (
            '一' <= ch <= '鿿' or '㐀' <= ch <= '䶿' or
            ' ' <= ch <= '~' or ch in '\n\r\t'
        ))
        return valid / len(text) < 0.4

    def _ocr_pdf(self, file_path: Path) -> str:
        try:
            import fitz
        except ImportError:
            return ""

        try:
            from PIL import Image
            import pytesseract
        except ImportError:
            return ""
        import io

        doc = fitz.open(str(file_path))
        try:
            all_text: list[str] = []
            for page in doc:
                pix = page.get_pixmap(dpi=300)
                img = Image.open(io.BytesIO(pix.tobytes("png")))
                text = pytesseract.image_to_string(img, lang="chi_sim+eng")
                if text.strip():
                    all_text.append(text)
            return "\n\n".join(all_text)
        except Exception:
            return ""
        finally:
            doc.close()

    def _parse_docx(self, file_path: Path) -> tuple[str, list[str]]:
        """Extract text from DOCX preserving paragraph styles and tables."""
        from docx import Document
        from docx.opc.exceptions import PackageNotFoundError
        import zipfile

        warnings: list[str] = []
        all_paragraphs: list[str] = []

        # .doc (old binary format) is NOT supported by python-docx
        suffix = file_path.suffix.lower()
        if suffix == ".doc":
            try:
                with zipfile.ZipFile(str(file_path), "r") as zf:
                    pass  # Valid ZIP, might be misnamed DOCX
            except zipfile.BadZipFile:
                raise ValueError(
                    "Old .doc format is not supported. Please convert to .docx using Microsoft Word or an online converter."
                )

        try:
            doc = Document(str(file_path))
        except PackageNotFoundError:
            raise ValueError(
                "Cannot read this DOCX file. It may be corrupted or in an older format. "
                "Please re-save it as a modern DOCX file."
            )
        except Exception:
            raise ValueError(
                "Unable to parse this document. Please convert it to PDF or plain text (.txt) and try again."
            )

        for para in doc.paragraphs:
            text = para.text.strip()
            if not text:
                continue

            style_name = para.style.name if para.style else ""
            # Use heading styles as section markers
            if "Heading" in style_name or "heading" in style_name:
                all_paragraphs.append(f"## {text}")
            else:
                all_paragraphs.append(text)

        # Extract tables
        for table in doc.tables:
            for row in table.rows:
                cells = [cell.text.strip() for cell in row.cells if cell.text.strip()]
                if cells:
                    all_paragraphs.append(" | ".join(cells))

        if not all_paragraphs:
            warnings.append("No text content found in DOCX")

        return "\n\n".join(all_paragraphs), warnings

    async def _extract_structured(self, text: str) -> ResumeData:
        """Use LLM to extract structured ResumeData from plain text."""
        self.last_raw_response = ""
        self.last_cleaned_json = ""
        self.last_parse_error = ""

        try:
            # Escape the text to prevent KeyError from curly braces in PDF content
            safe_text = text[:8000].replace("{", "{{").replace("}", "}}")
            # Then format with the already-escaped prompt
            prompt = EXTRACTION_PROMPT.replace("{text}", safe_text)

            response = self.llm.messages.create(
                model=settings.llm_model,
                max_tokens=8192,
                temperature=0.0,
                system="You are a precise data extraction system. Output ONLY valid JSON, no other text.",
                messages=[{
                    "role": "user",
                    "content": prompt,
                }],
            )

            content = self._extract_text_from_response(response)
            self.last_raw_response = content
            logger.info(f"LLM extraction raw (first 500): {content[:500]}")

            cleaned = self._clean_json(content)
            self.last_cleaned_json = cleaned
            logger.info(f"LLM extraction cleaned (first 500): {cleaned[:500]}")

            try:
                data = json.loads(cleaned)
            except json.JSONDecodeError:
                # Try repairing the JSON
                repaired = self._repair_json(cleaned)
                logger.info(f"Attempting JSON repair. Repaired preview: {repaired[:500]}")
                try:
                    data = json.loads(repaired)
                except json.JSONDecodeError:
                    # Last resort: strip all garbled chars from cleaned JSON and retry
                    sanitized = self._sanitize_text(repaired)
                    data = json.loads(sanitized)

            return self._dict_to_resume_data(data)

        except json.JSONDecodeError as e:
            self.last_parse_error = f"JSONDecodeError at pos {e.pos}: {e.msg}"
            logger.warning(f"{self.last_parse_error}. Cleaned: {self.last_cleaned_json[:500]}")
            return self._rule_based_extraction(text)
        except Exception as e:
            self.last_parse_error = f"{type(e).__name__}: {e}"
            logger.warning(f"LLM extraction failed: {self.last_parse_error}")
            return self._rule_based_extraction(text)

    def _rule_based_extraction(self, text: str) -> ResumeData:
        """Fallback: basic regex-based extraction without LLM."""
        resume = ResumeData()

        # Email
        email_match = re.search(r'[\w.+-]+@[\w-]+\.[\w.-]+', text)
        if email_match:
            resume.personal_info.email = email_match.group()

        # Phone
        phone_match = re.search(r'(?:\+86|86)?1[3-9]\d{9}', text)
        if phone_match:
            resume.personal_info.phone = phone_match.group()

        # GitHub URL
        github_match = re.search(r'github\.com/[\w-]+', text)
        if github_match:
            resume.personal_info.github = github_match.group()

        # LinkedIn URL
        linkedin_match = re.search(r'linkedin\.com/in/[\w-]+', text)
        if linkedin_match:
            resume.personal_info.linkedin = linkedin_match.group()

        return resume

    @staticmethod
    def _is_dual_column(x_centers: list[float], threshold: float = 100.0) -> bool:
        """Detect dual-column layout by X-coordinate clustering."""
        if len(x_centers) < 4:
            return False
        x_centers.sort()
        gap = max(
            x_centers[i+1] - x_centers[i]
            for i in range(len(x_centers) - 1)
        )
        return gap > threshold

    @staticmethod
    def _linearize_dual_column(blocks: list[dict]) -> list[dict]:
        """Linearize dual-column blocks to single-column reading order."""
        # Sort by Y first, then X (top-to-bottom, left-to-right)
        return sorted(blocks, key=lambda b: (b["bbox"][1], b["bbox"][0]))

    @staticmethod
    def _block_to_text(block: dict) -> str:
        """Extract text from a pymupdf block dict."""
        lines = []
        for line in block.get("lines", []):
            spans = line.get("spans", [])
            line_text = " ".join(s.get("text", "") for s in spans)
            if line_text.strip():
                lines.append(line_text)
        return "\n".join(lines)

    @staticmethod
    def _clean_json(text: str) -> str:
        """Extract JSON from LLM response, handling markdown blocks and extra text."""
        text = text.strip()
        # Remove markdown code blocks
        if text.startswith("```"):
            lines = text.split("\n")
            # Remove opening ```json or ```
            if lines[0].startswith("```"):
                lines = lines[1:]
            # Remove closing ```
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines)
        # If JSON is embedded in text, find the outermost { }
        if not text.startswith("{"):
            start = text.find("{")
            end = text.rfind("}")
            if start >= 0 and end > start:
                text = text[start:end + 1]
        return text.strip()

    @staticmethod
    def _extract_text_from_response(response) -> str:
        """Extract text content from  API response, skipping thinking blocks."""
        texts = []
        for block in response.content:
            if hasattr(block, "text"):
                texts.append(block.text)
        if texts:
            return "\n".join(texts)
        # Fallback: return string representation
        return str(response.content)

    def _dict_to_resume_data(self, data: dict) -> ResumeData:
        """Convert extracted dict to ResumeData with validation."""
        resume = ResumeData()

        # Personal info
        pi = data.get("personal_info", {})
        if pi:
            resume.personal_info = PersonalInfo(
                full_name=pi.get("full_name", ""),
                email=pi.get("email", ""),
                phone=pi.get("phone", ""),
                location=pi.get("location", ""),
                linkedin=pi.get("linkedin", ""),
                github=pi.get("github", ""),
                website=pi.get("website", ""),
                summary=pi.get("summary", ""),
            )

        # Education
        for edu in data.get("education", []):
            try:
                resume.education.append(Education(
                    school=edu.get("school", ""),
                    degree=edu.get("degree", ""),
                    major=edu.get("major", ""),
                    level=self._safe_enum(EducationLevel, edu.get("level"), "other", EDUCATION_LEVEL_CN_MAP),
                    start_date=self._parse_date(edu.get("start_date")),
                    end_date=self._parse_date(edu.get("end_date")),
                    gpa=edu.get("gpa", ""),
                    description=edu.get("description", ""),
                    confidence=self._safe_float(edu.get("confidence"), 0.8),
                ))
            except Exception:
                pass

        # Work experience
        for work in data.get("work_experience", []):
            try:
                resume.work_experience.append(WorkExperience(
                    company=work.get("company", ""),
                    position=work.get("position", ""),
                    start_date=self._parse_date(work.get("start_date")),
                    end_date=self._parse_date(work.get("end_date")),
                    is_current=bool(work.get("is_current", False)),
                    location=work.get("location", ""),
                    bullets=work.get("bullets", []),
                    description=work.get("description", ""),
                    confidence=self._safe_float(work.get("confidence"), 0.8),
                ))
            except Exception:
                pass

        # Project experience
        for proj in data.get("project_experience", []):
            try:
                resume.project_experience.append(ProjectExperience(
                    name=proj.get("name", ""),
                    role=proj.get("role", ""),
                    url=proj.get("url", ""),
                    start_date=self._parse_date(proj.get("start_date")),
                    end_date=self._parse_date(proj.get("end_date")),
                    technologies=proj.get("technologies", []),
                    bullets=proj.get("bullets", []),
                    description=proj.get("description", ""),
                    confidence=self._safe_float(proj.get("confidence"), 0.8),
                ))
            except Exception:
                pass

        # Skills
        for skill in data.get("skills", []):
            try:
                resume.skills.append(Skill(
                    name=skill.get("name", ""),
                    category=skill.get("category", ""),
                    level=skill.get("level", ""),
                    years=self._safe_float(skill.get("years"), 0),
                ))
            except Exception:
                pass

        resume.target_position = str(data.get("target_position", ""))
        resume.target_industry = str(data.get("target_industry", ""))
        return resume

    @staticmethod
    def _safe_enum(enum_cls, value, default, cn_map=None):
        """Safely convert a value to an enum member, with Chinese→English mapping."""
        if not value:
            return enum_cls(default)
        # Try Chinese→English mapping first
        if cn_map:
            mapped = cn_map.get(str(value).strip(), value)
        else:
            mapped = value
        try:
            return enum_cls(mapped)
        except ValueError:
            return enum_cls(default)

    @staticmethod
    def _safe_float(value, default=0.8):
        """Safely convert a value to float, falling back to default."""
        if not value:
            return default
        try:
            return float(value)
        except (ValueError, TypeError):
            return default

    @staticmethod
    def _sanitize_text(text: str) -> str:
        """Clean garbled characters from extracted text.

        Keeps: ASCII printable, common CJK ranges, newlines, common punctuation.
        Replaces everything else with spaces to preserve structure.
        """
        result = []
        for ch in text:
            cp = ord(ch)
            if (
                (0x20 <= cp <= 0x7E)        # ASCII printable
                or (0x4E00 <= cp <= 0x9FFF)  # CJK Unified
                or (0x3400 <= cp <= 0x4DBF)  # CJK Extension A
                or (0x2000 <= cp <= 0x206F)  # General Punctuation
                or (0x3000 <= cp <= 0x303F)  # CJK Punctuation
                or (0xFF00 <= cp <= 0xFFEF)  # Half/Full-width forms
                or (0x00A0 <= cp <= 0x00FF)  # Latin-1 Supplement
                or cp in (0x0A, 0x0D)        # newline, carriage return
            ):
                result.append(ch)
            else:
                result.append(" ")
        return "".join(result)

    @staticmethod
    def _repair_json(text: str) -> str:
        """Attempt to repair common JSON issues from LLM output."""
        import re
        # Remove trailing commas before } or ]
        text = re.sub(r",\s*}", "}", text)
        text = re.sub(r",\s*]", "]", text)
        # Fix unterminated strings: find last valid field boundary
        if text.count('"') % 2 != 0:
            # Find the last complete key-value pair before the broken string
            # Pattern: "key": "value", ... or "key": "value"
            # Find last properly closed string (even number of quotes before it)
            last_good = 0
            quote_count = 0
            for i, ch in enumerate(text):
                if ch == '"' and (i == 0 or text[i-1] != '\\'):
                    quote_count += 1
                if quote_count % 2 == 0:
                    if ch == ',' or ch == '}' or ch == ']':
                        last_good = i
            if last_good > 0:
                text = text[:last_good + 1]  # Keep the comma/bracket
        # If the JSON is truncated (missing closing braces), try to close it
        open_braces = text.count("{") - text.count("}")
        open_brackets = text.count("[") - text.count("]")
        if open_braces > 0 or open_brackets > 0:
            # Remove trailing comma if present
            text = re.sub(r",\s*$", "", text)
            text += "]" * open_brackets + "}" * open_braces
        return text

    @staticmethod
    def _parse_date(val) -> date | None:
        """Parse a date string from LLM output into a date object."""
        if not val:
            return None
        if isinstance(val, date):
            return val
        s = str(val).strip()
        if not s:
            return None
        # Try YYYY-MM-DD, YYYY-MM, YYYY
        for fmt in ("%Y-%m-%d", "%Y-%m", "%Y"):
            try:
                return datetime.strptime(s, fmt).date()
            except ValueError:
                continue
        # Try ISO format
        try:
            return date.fromisoformat(s)
        except (ValueError, TypeError):
            pass
        logger.debug(f"Could not parse date: {s}")
        return None
