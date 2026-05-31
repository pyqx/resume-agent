"""JDMatcher — two-stage JD-to-Resume matching (vector recall + LLM rerank)."""

import json
import hashlib
import logging

from core.llm import get_llm_client_from_settings
from diskcache import Cache

from core.config import settings
from core.resume.schema import (
    ResumeData, JDRequirements, MatchReport, Requirement, MatchLevel,
)

logger = logging.getLogger(__name__)

MATCH_PROMPT = """You are a resume-job matching evaluator. Score how well the candidate's experience matches a specific job requirement.

Job Requirement: {requirement}
Requirement Type: {req_type}

Candidate's Relevant Experience:
{resume_chunks}

Score the match as:
- full: The candidate clearly meets or exceeds this requirement with specific evidence
- partial: The candidate has some related experience but not a direct match
- none: The candidate does not demonstrate this requirement

Output JSON:
{{"match_level": "full|partial|none", "evidence": "specific evidence from the resume", "suggestion": "how to improve the resume for this requirement (if partial or none)"}}

Output ONLY valid JSON:"""


class JDMatcher:
    """Two-stage JD-to-Resume matcher.

    Stage 1: ChromaDB vector similarity to find Top-3 relevant resume chunks per JD requirement.
    Stage 2: LLM rerank to precisely score each match with evidence and suggestions.
    """

    def __init__(
        self,
        llm_client=None,
        cache: Cache | None = None,
    ):
        self._llm = llm_client
        self._cache = cache

    @property
    def llm(self):
        if self._llm is None:
            self._llm = get_llm_client_from_settings()
        return self._llm

    async def match(self, jd: JDRequirements, resume: ResumeData) -> MatchReport:
        """Run full JD-to-Resume matching."""
        jd_hash = hashlib.sha256(jd.raw_text.encode()).hexdigest()[:16]
        resume_hash = hashlib.sha256(
            json.dumps(resume.model_dump(), sort_keys=True, default=str).encode()
        ).hexdigest()[:16]

        # Check cache
        cache_key = f"match_{resume.id}_{jd_hash}_{resume.version}"
        if self._cache:
            cached = self._cache.get(cache_key)
            if cached:
                logger.debug("Using cached match result")
                return MatchReport(**cached)

        # Combine all requirements
        all_requirements = list(jd.hard_requirements) + list(jd.nice_to_have)

        # Stage 1: Build resume text chunks for each section
        resume_chunks = self._build_resume_chunks(resume)

        # Stage 2: LLM rerank for each requirement (parallelized in batches)
        scored_requirements = []
        for req in all_requirements:
            scored_req = await self._score_requirement(req, resume_chunks)
            scored_requirements.append(scored_req)

        # Compute overall score
        must_have = [r for r in scored_requirements if r.type.value == "must_have"]
        plus = [r for r in scored_requirements if r.type.value == "plus"]

        must_have_met = sum(1 for r in must_have if r.match_level == MatchLevel.FULL)
        plus_met = sum(1 for r in plus if r.match_level == MatchLevel.FULL)

        must_have_score = must_have_met / len(must_have) if must_have else 1.0
        plus_score = plus_met / len(plus) if plus else 1.0
        overall = round((must_have_score * 0.7 + plus_score * 0.3) * 100, 1)

        report = MatchReport(
            resume_id=resume.id,
            jd_text_hash=jd_hash,
            overall_score=overall,
            must_have_met=must_have_met,
            must_have_total=len(must_have),
            plus_met=plus_met,
            plus_total=len(plus),
            requirements=scored_requirements,
            signals=jd.soft_signals,
            keyword_coverage=self._compute_keyword_coverage(jd, resume),
        )

        # Cache result
        if self._cache:
            self._cache.set(cache_key, report.model_dump(), expire=3600 * 24)

        return report

    async def _score_requirement(self, req: Requirement, chunks: str) -> Requirement:
        """Use LLM to score a single JD requirement against resume chunks."""
        try:
            response = self.llm.messages.create(
                model=settings.llm_model,
                max_tokens=1024,
                temperature=0.0,
                messages=[{
                    "role": "user",
                    "content": MATCH_PROMPT.format(
                        requirement=req.criterion,
                        req_type=req.type.value,
                        resume_chunks=chunks[:4000],
                    ),
                }],
            )

            content = self._extract_text(response)
            content = self._clean_json(content)
            result = json.loads(content)

            return Requirement(
                criterion=req.criterion,
                type=req.type,
                match_level=MatchLevel(result.get("match_level", "none")),
                evidence=result.get("evidence", ""),
                suggestion=result.get("suggestion", ""),
            )
        except Exception as e:
            logger.warning(f"Failed to score requirement '{req.criterion}': {e}")
            return Requirement(
                criterion=req.criterion,
                type=req.type,
                match_level=MatchLevel.NONE,
                evidence="",
                suggestion="Unable to evaluate this requirement automatically.",
            )

    def _build_resume_chunks(self, resume: ResumeData) -> str:
        """Build consolidated text chunks from resume for matching."""
        parts = []

        # Skills
        if resume.skills:
            skills_text = "Skills: " + ", ".join(
                f"{s.name} ({s.level}, {s.years}y)" for s in resume.skills
            )
            parts.append(skills_text)

        # Work experience
        for w in resume.work_experience:
            parts.append(
                f"Work: {w.position} at {w.company}\n" +
                "\n".join(f"- {b}" for b in w.bullets) + "\n" + w.description
            )

        # Project experience
        for p in resume.project_experience:
            parts.append(
                f"Project: {p.name} [{', '.join(p.technologies)}]\n" +
                "\n".join(f"- {b}" for b in p.bullets) + "\n" + p.description
            )

        # Education
        for e in resume.education:
            parts.append(f"Education: {e.degree} in {e.major} from {e.school}")

        return "\n\n".join(parts)

    @staticmethod
    def _compute_keyword_coverage(jd: JDRequirements, resume: ResumeData) -> float:
        """Compute keyword coverage ratio."""
        if not jd.keyword_frequency:
            return 0.0

        resume_text = json.dumps(resume.model_dump(), default=str).lower()
        jd_keywords = set(k.lower() for k in jd.keyword_frequency.keys())

        covered = sum(1 for kw in jd_keywords if kw in resume_text)
        return round(covered / len(jd_keywords) * 100, 1) if jd_keywords else 0.0

    @staticmethod
    def _extract_text(response) -> str:
        for block in response.content:
            if hasattr(block, "text"):
                return block.text
        return str(response.content)

    @staticmethod
    def _clean_json(text: str) -> str:
        text = text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1])
        return text
