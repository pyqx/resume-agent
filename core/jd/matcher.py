"""JDMatcher — 将简历渲染为文本,逐条需求由 LLM 评分(有界并发)。"""

import asyncio
import hashlib
import json
import logging

from diskcache import Cache

from core.jd.keywords import compute_keyword_coverage
from core.llm import (
    UNTRUSTED_NOTE,
    get_llm_client_from_settings,
    parse_json_response,
    render_prompt,
    wrap_untrusted,
)
from core.resume.schema import (
    ResumeData, JDRequirements, MatchReport, Requirement, RequirementType, MatchLevel,
)

logger = logging.getLogger(__name__)

# Bump this to invalidate cached match reports when the prompt or the
# scoring logic changes (it is part of the cache key).
PROMPT_VERSION = "match-v2"

# Resume text sent to the LLM is truncated to this many characters.
MAX_RESUME_CHARS = 4000

# Upper bound on concurrent per-requirement LLM scoring calls.
MAX_CONCURRENT_SCORES = 4

_LEVEL_SCORES = {
    MatchLevel.FULL: 1.0,
    MatchLevel.PARTIAL: 0.5,
    MatchLevel.NONE: 0.0,
}

MATCH_SYSTEM_PROMPT = (
    "You are a resume-job matching evaluator. Score how well the candidate's "
    "experience matches a specific job requirement. " + UNTRUSTED_NOTE
)

MATCH_PROMPT = """Score how well the candidate's experience matches this job requirement.

Job Requirement:
{requirement}

Requirement Type: {req_type}

Candidate's Relevant Experience:
{resume_chunks}

Score the match as:
- full: The candidate clearly meets or exceeds this requirement with specific evidence
- partial: The candidate has some related experience but not a direct match
- none: The candidate does not demonstrate this requirement

Output JSON:
{"match_level": "full|partial|none", "evidence": "specific evidence from the resume", "suggestion": "how to improve the resume for this requirement (if partial or none)"}

Output ONLY valid JSON:"""


class JDMatcher:
    """JD-to-Resume matcher.

    将简历渲染为纯文本,逐条 JD 需求交给 LLM 评分(asyncio.Semaphore 有界
    并发),汇总为 MatchReport。结果按 (简历内容 hash + JD 文本 hash +
    prompt 版本) 在 diskcache 中缓存。
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
        jd_hash = hashlib.sha256(jd.raw_text.encode("utf-8")).hexdigest()[:16]
        resume_hash = hashlib.sha256(
            json.dumps(resume.model_dump(), sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()[:16]

        # Cache key: resume content hash + JD fingerprint + prompt version.
        # The fingerprint covers the raw JD text AND the requirement list, so
        # two JDRequirements that share raw_text (or both lack it) but carry
        # different requirements never serve each other's cached reports.
        jd_fingerprint = hashlib.sha256(
            "\n".join(
                [jd.raw_text]
                + [
                    f"{r.type.value}:{r.criterion}"
                    for r in list(jd.hard_requirements) + list(jd.nice_to_have)
                ]
            ).encode("utf-8")
        ).hexdigest()[:16]
        cache_key = f"match_{resume_hash}_{jd_fingerprint}_{PROMPT_VERSION}"
        if self._cache is not None:
            cached = await asyncio.to_thread(self._cache.get, cache_key)
            if cached:
                logger.debug("Match report cache hit (key=%s)", cache_key)
                return MatchReport(**cached)

        all_requirements = list(jd.hard_requirements) + list(jd.nice_to_have)
        logger.info(
            "Matcher: total requirements=%d (hard=%d, plus=%d)",
            len(all_requirements), len(jd.hard_requirements), len(jd.nice_to_have),
        )

        resume_text = self._build_resume_chunks(resume)
        if len(resume_text) > MAX_RESUME_CHARS:
            logger.warning(
                "Resume text truncated from %d to %d chars for match scoring",
                len(resume_text), MAX_RESUME_CHARS,
            )
            resume_text = resume_text[:MAX_RESUME_CHARS]

        # Score every requirement concurrently, bounded by a semaphore.
        semaphore = asyncio.Semaphore(MAX_CONCURRENT_SCORES)

        async def score_bounded(req: Requirement) -> Requirement:
            async with semaphore:
                return await self._score_requirement(req, resume_text)

        scored: list[Requirement] = list(
            await asyncio.gather(*(score_bounded(r) for r in all_requirements))
        )

        must_have = [r for r in scored if r.type == RequirementType.MUST_HAVE]
        plus = [r for r in scored if r.type == RequirementType.PLUS]
        scoring_errors = sum(1 for r in scored if r.match_level == MatchLevel.ERROR)

        # ERROR entries count neither toward the numerator nor the denominator.
        must_rate = self._score_rate(
            [r for r in must_have if r.match_level != MatchLevel.ERROR]
        )
        plus_rate = self._score_rate(
            [r for r in plus if r.match_level != MatchLevel.ERROR]
        )

        # FULL=1, PARTIAL=0.5, NONE=0. When one group is empty (or fully
        # errored) the other carries the whole score instead of being capped
        # by its 0.7/0.3 weight; with nothing scorable at all the score is 0.
        if must_rate is None and plus_rate is None:
            overall = 0.0
        elif must_rate is None:
            overall = round(plus_rate * 100, 1)
        elif plus_rate is None:
            overall = round(must_rate * 100, 1)
        else:
            overall = round((must_rate * 0.7 + plus_rate * 0.3) * 100, 1)

        report = MatchReport(
            resume_id=resume.id,
            jd_text_hash=jd_hash,
            overall_score=overall,
            must_have_met=sum(1 for r in must_have if r.match_level == MatchLevel.FULL),
            must_have_total=len(must_have),
            plus_met=sum(1 for r in plus if r.match_level == MatchLevel.FULL),
            plus_total=len(plus),
            requirements=scored,
            signals=jd.soft_signals,
            keyword_coverage=compute_keyword_coverage(
                list(jd.keyword_frequency.keys()), resume
            )["coverage_rate"],
            scoring_errors=scoring_errors,
        )

        # Cache only clean reports — a report with failed scorings would
        # otherwise pin the failure for the whole TTL.
        if self._cache is not None and scoring_errors == 0:
            await asyncio.to_thread(
                self._cache.set, cache_key, report.model_dump(mode="json"),
                expire=3600 * 24,
            )

        return report

    @staticmethod
    def _score_rate(reqs: list[Requirement]) -> float | None:
        """FULL=1 / PARTIAL=0.5 / NONE=0 的得分率;无可评分条目返回 None。"""
        if not reqs:
            return None
        return sum(_LEVEL_SCORES.get(r.match_level, 0.0) for r in reqs) / len(reqs)

    async def _score_requirement(self, req: Requirement, resume_text: str) -> Requirement:
        """Use the LLM to score a single JD requirement against the resume."""
        logger.debug("Scoring requirement: %s (%s)", req.criterion, req.type.value)
        prompt = render_prompt(
            MATCH_PROMPT,
            requirement=wrap_untrusted(req.criterion, "jd_requirement"),
            req_type=req.type.value,
            resume_chunks=wrap_untrusted(resume_text, "resume"),
        )
        try:
            response = await self.llm.messages.create(
                max_tokens=1024,
                temperature=0.0,
                expect_json=True,
                system=MATCH_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )
            result = parse_json_response(response)
            if not isinstance(result, dict):
                raise ValueError(f"expected a JSON object, got {type(result).__name__}")

            raw_level = str(result.get("match_level", "")).strip().lower()
            if raw_level not in ("full", "partial", "none"):
                raise ValueError(f"invalid match_level: {raw_level!r}")

            return Requirement(
                criterion=req.criterion,
                type=req.type,
                match_level=MatchLevel(raw_level),
                evidence=str(result.get("evidence") or ""),
                suggestion=str(result.get("suggestion") or ""),
            )
        except Exception as e:
            logger.warning("Failed to score requirement '%s': %s", req.criterion, e)
            return Requirement(
                criterion=req.criterion,
                type=req.type,
                match_level=MatchLevel.ERROR,
                evidence="",
                suggestion="评分失败,未能自动评估该条需求。",
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
