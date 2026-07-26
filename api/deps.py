"""Dependency injection container — wires the full object graph."""

import asyncio
import logging

import aiosqlite
from chromadb.api import ClientAPI
from diskcache import Cache

from core.config import settings
from core.database import init_database
from core.llm import LLMClient, get_llm_client_from_settings
from core.vector_store import init_vector_store
from core.cache import init_cache

from agent.checkpoint import CheckpointManager
from agent.context import ContextAssembler
from agent.loop import AgentLoop
from agent.memory.consolidator import MemoryConsolidator
from agent.memory.extractor import MemoryExtractor
from agent.memory.retriever import MemoryRetriever
from agent.memory.store import MemoryStore
from agent.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)

# ── Singleton instances (initialized lazily, guarded by one lock) ──

_init_lock = asyncio.Lock()

_db_conn: aiosqlite.Connection | None = None
_chroma_client: ClientAPI | None = None
_cache_instance: Cache | None = None
_tool_registry: ToolRegistry | None = None
_memory_store: MemoryStore | None = None
_memory_retriever: MemoryRetriever | None = None
_memory_extractor: MemoryExtractor | None = None
_memory_consolidator: MemoryConsolidator | None = None
_agent_loop: AgentLoop | None = None
_llm_client: LLMClient | None = None
_gh_analyzer = None
_version_manager = None
_consolidation_task: asyncio.Task | None = None

# Consolidation cadence (seconds)
_CONSOLIDATE_INTERVAL = 30 * 60


async def get_db() -> aiosqlite.Connection:
    global _db_conn
    if _db_conn is None:
        async with _init_lock:
            if _db_conn is None:
                _db_conn = await init_database()
    return _db_conn


def get_chroma_client() -> ClientAPI:
    global _chroma_client
    if _chroma_client is None:
        _chroma_client = init_vector_store()
    return _chroma_client


def get_disk_cache() -> Cache:
    global _cache_instance
    if _cache_instance is None:
        _cache_instance = init_cache()
    return _cache_instance


def get_llm_client() -> LLMClient:
    global _llm_client
    if _llm_client is None:
        _llm_client = get_llm_client_from_settings()
    return _llm_client


def get_tool_registry() -> ToolRegistry:
    global _tool_registry
    if _tool_registry is None:
        _tool_registry = ToolRegistry()
    return _tool_registry


async def get_memory_store() -> MemoryStore:
    global _memory_store
    if _memory_store is None:
        async with _init_lock:
            if _memory_store is None:
                db = await get_db()
                chroma = get_chroma_client()
                _memory_store = MemoryStore(chroma_client=chroma, db=db)
    return _memory_store


async def get_memory_retriever() -> MemoryRetriever:
    global _memory_retriever
    if _memory_retriever is None:
        store = await get_memory_store()
        async with _init_lock:
            if _memory_retriever is None:
                _memory_retriever = MemoryRetriever(store=store)
    return _memory_retriever


async def get_memory_extractor() -> MemoryExtractor:
    global _memory_extractor
    if _memory_extractor is None:
        async with _init_lock:
            if _memory_extractor is None:
                _memory_extractor = MemoryExtractor(llm_client=get_llm_client())
    return _memory_extractor


async def get_memory_consolidator() -> MemoryConsolidator:
    global _memory_consolidator
    if _memory_consolidator is None:
        store = await get_memory_store()
        async with _init_lock:
            if _memory_consolidator is None:
                _memory_consolidator = MemoryConsolidator(store=store)
    return _memory_consolidator


async def get_session_manager():
    from api.session_manager import SessionManager
    return SessionManager(await get_db())


async def get_agent_loop() -> AgentLoop:
    global _agent_loop
    if _agent_loop is not None:
        return _agent_loop
    async with _init_lock:
        if _agent_loop is not None:
            return _agent_loop
        _agent_loop = await _build_agent_loop()
        return _agent_loop


async def _build_agent_loop() -> AgentLoop:
    global _gh_analyzer, _version_manager

    llm = get_llm_client()
    registry = get_tool_registry()
    db = await get_db()
    # NOTE: called while holding _init_lock; use the internal builders to
    # avoid re-entering the lock.
    global _memory_store, _memory_retriever
    if _memory_store is None:
        _memory_store = MemoryStore(chroma_client=get_chroma_client(), db=db)
    store = _memory_store
    if _memory_retriever is None:
        _memory_retriever = MemoryRetriever(store=store)
    retriever = _memory_retriever

    from api.routes.resume import resolve_resume, _save_resume

    # ── Quality evaluators ─────────────────────────────────
    from core.evaluation.rules import RuleEvaluator
    from core.evaluation.llm_judge import LLMJudge
    from core.evaluation.ats_simulator import ATSSimulator
    from core.evaluation.scorer import Scorer
    from agent.tools.quality_tools import (
        EvaluateStarCompletenessTool,
        EvaluateEntryQualityTool,
        CheckVerbStrengthTool,
        CheckSensitiveInfoTool,
        RunFullQualityAuditTool,
    )
    rule_evaluator = RuleEvaluator()
    llm_judge = LLMJudge(llm_client=llm)
    ats_simulator = ATSSimulator()
    scorer = Scorer()

    # ── Web + memory tools ─────────────────────────────────
    from agent.tools.web_tools import WebSearchTool, WebFetchTool
    from agent.tools.memory_tools import (
        SearchMemoryTool,
        SaveMemoryTool,
        GetUserProfileTool,
        GetUserPreferencesTool,
        ForgetMemoryTool,
    )

    registry.register_many([
        WebSearchTool(),
        WebFetchTool(),
        SearchMemoryTool(store),
        SaveMemoryTool(store),
        GetUserProfileTool(store),
        GetUserPreferencesTool(store),
        ForgetMemoryTool(store),
        EvaluateStarCompletenessTool(resolve_resume),
        EvaluateEntryQualityTool(llm_judge, resolve_resume),
        CheckVerbStrengthTool(rule_evaluator, resolve_resume),
        CheckSensitiveInfoTool(rule_evaluator, resolve_resume),
        RunFullQualityAuditTool(rule_evaluator, llm_judge, ats_simulator, scorer, resolve_resume),
    ])

    # ── Resume CRUD + version tools ────────────────────────
    from core.resume.version_manager import VersionManager
    from agent.tools.resume_tools import (
        ReadResumeSectionTool,
        UpdateResumeEntryTool,
        AddResumeEntryTool,
        DeleteResumeEntryTool,
        CreateResumeVersionTool,
        ListResumeVersionsTool,
        ForkResumeVersionTool,
        DiffResumeVersionsTool,
    )
    _version_manager = VersionManager()
    registry.register_many([
        ReadResumeSectionTool(resolve_resume),
        UpdateResumeEntryTool(resolve_resume, _save_resume),
        AddResumeEntryTool(resolve_resume, _save_resume),
        DeleteResumeEntryTool(resolve_resume, _save_resume),
        CreateResumeVersionTool(_version_manager, resolve_resume),
        ListResumeVersionsTool(_version_manager),
        ForkResumeVersionTool(_version_manager),
        DiffResumeVersionsTool(_version_manager),
    ])

    # ── JD tools ───────────────────────────────────────────
    from core.jd.parser import JDParser
    from core.jd.matcher import JDMatcher
    from core.jd.signal_detector import SignalDetector
    from agent.tools.jd_tools import (
        ParseJDTool,
        MatchJDToResumeTool,
        AnalyzeKeywordCoverageTool,
        DetectJDSignalsTool,
    )
    jd_parser = JDParser(llm_client=llm)
    jd_matcher = JDMatcher(llm_client=llm, cache=get_disk_cache())
    signal_detector = SignalDetector()
    registry.register_many([
        ParseJDTool(jd_parser),
        MatchJDToResumeTool(jd_matcher, jd_parser, resolve_resume),
        AnalyzeKeywordCoverageTool(jd_parser, resolve_resume),
        DetectJDSignalsTool(signal_detector),
    ])

    # ── GitHub analysis tools ──────────────────────────────
    from core.github.analyzer import GitHubAnalyzer
    from agent.tools.github_tools import (
        FetchRepoMetadataTool,
        AnalyzeRepoStructureTool,
        AnalyzeRepoDependenciesTool,
        ScanIssuesForOpportunitiesTool,
        GenerateDevSuggestionsTool,
        ComposeResumeEntryFromGitHubTool,
    )
    _gh_analyzer = GitHubAnalyzer(llm_client=llm, cache=get_disk_cache())
    registry.register_many([
        FetchRepoMetadataTool(_gh_analyzer),
        AnalyzeRepoStructureTool(_gh_analyzer),
        AnalyzeRepoDependenciesTool(_gh_analyzer),
        ScanIssuesForOpportunitiesTool(_gh_analyzer),
        GenerateDevSuggestionsTool(_gh_analyzer, resolve_resume),
        ComposeResumeEntryFromGitHubTool(_gh_analyzer),
    ])

    # ── Interview tools ────────────────────────────────────
    from core.interview.question_generator import InterviewQuestionGenerator
    from core.interview.intro_generator import SelfIntroGenerator
    from core.interview.weakness_strategist import WeaknessStrategist
    from agent.tools.interview_tools import (
        GenerateInterviewQuestionsTool,
        GenerateSelfIntroTool,
        AnalyzeResumeWeaknessesTool,
    )
    qg = InterviewQuestionGenerator(llm_client=llm)
    ig = SelfIntroGenerator(llm_client=llm)
    ws = WeaknessStrategist(llm_client=llm)
    registry.register_many([
        GenerateInterviewQuestionsTool(qg, resolve_resume, jd_parser),
        GenerateSelfIntroTool(ig, resolve_resume),
        AnalyzeResumeWeaknessesTool(ws, resolve_resume),
    ])

    context_assembler = ContextAssembler(retriever=retriever, tool_registry=registry)
    checkpoint_manager = CheckpointManager(db=db)

    logger.info("Agent loop wired: %d tools registered", len(registry.list_all()))
    return AgentLoop(
        llm_client=llm,
        context_assembler=context_assembler,
        tool_registry=registry,
        checkpoint_manager=checkpoint_manager,
    )


async def _consolidation_loop():
    """Periodically merge/dedupe memories in the background."""
    while True:
        await asyncio.sleep(_CONSOLIDATE_INTERVAL)
        try:
            consolidator = await get_memory_consolidator()
            stats = await consolidator.consolidate(user_id="default")
            logger.info("Memory consolidation: %s", stats)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.warning("Memory consolidation failed: %s", e)


async def startup():
    """Initialize all services on app startup."""
    global _consolidation_task
    if not settings.llm_api_key:
        logger.critical(
            "LLM_API_KEY is not set — chat/analysis features will fail. "
            "Configure it in .env (see .env.example)."
        )
    await get_db()
    get_chroma_client()
    get_disk_cache()
    await get_agent_loop()  # Pre-wire all dependencies
    _consolidation_task = asyncio.create_task(_consolidation_loop())


async def shutdown():
    """Gracefully close all connections on app shutdown."""
    global _db_conn, _chroma_client, _cache_instance, _agent_loop
    global _memory_store, _memory_retriever, _memory_extractor, _memory_consolidator
    global _tool_registry, _llm_client, _gh_analyzer, _version_manager, _consolidation_task

    if _consolidation_task:
        _consolidation_task.cancel()
        try:
            await _consolidation_task
        except asyncio.CancelledError:
            pass
        _consolidation_task = None

    if _gh_analyzer is not None:
        try:
            await _gh_analyzer.release_clones()
        except Exception as e:
            logger.warning("GitHub clone cleanup failed: %s", e)
        _gh_analyzer = None

    if _db_conn:
        await _db_conn.close()
        _db_conn = None
    if _cache_instance:
        _cache_instance.close()
        _cache_instance = None
    _chroma_client = None
    _agent_loop = None
    _memory_store = None
    _memory_retriever = None
    _memory_extractor = None
    _memory_consolidator = None
    _tool_registry = None
    _llm_client = None
    _version_manager = None
