"""Dependency injection container — wires the full object graph."""

from core.llm import LLMClient, LLMConfig, LLMProvider
from chromadb.api import ClientAPI
from diskcache import Cache

from core.config import settings
from core.database import init_database
from core.vector_store import init_vector_store
from core.cache import init_cache

from agent.tools.registry import ToolRegistry
from agent.tools.echo_tool import EchoTool
from agent.tools.memory_tools import (
    SearchMemoryTool,
    GetUserProfileTool,
    GetUserPreferencesTool,
    ForgetMemoryTool,
)

from agent.memory.store import MemoryStore
from agent.memory.retriever import MemoryRetriever
from agent.memory.extractor import MemoryExtractor
from agent.memory.consolidator import MemoryConsolidator

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

from agent.context import ContextAssembler
from agent.planner import Planner
from agent.checkpoint import CheckpointManager
from agent.loop import AgentLoop


# ── Singleton instances (initialized lazily) ───────────────

import aiosqlite

_db_conn: aiosqlite.Connection | None = None
_chroma_client: ClientAPI | None = None
_cache_instance: Cache | None = None
_tool_registry: ToolRegistry | None = None
_memory_store: MemoryStore | None = None
_memory_retriever: MemoryRetriever | None = None
_agent_loop: AgentLoop | None = None
_llm_client: LLMClient | None = None


async def get_db() -> aiosqlite.Connection:
    global _db_conn
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
        config = LLMConfig(
            provider=LLMProvider(settings.llm_provider),
            api_key=settings.llm_api_key,
            model=settings.llm_model,
            base_url=settings.llm_base_url,
            temperature=settings.llm_temperature,
            max_tokens=settings.llm_max_tokens,
        )
        _llm_client = LLMClient(api_key=settings.llm_api_key, config=config)
    return _llm_client


def get_tool_registry() -> ToolRegistry:
    global _tool_registry
    if _tool_registry is None:
        _tool_registry = ToolRegistry()
    return _tool_registry


async def get_memory_store() -> MemoryStore:
    global _memory_store
    if _memory_store is None:
        db = await get_db()
        chroma = get_chroma_client()
        _memory_store = MemoryStore(chroma_client=chroma, db=db)
    return _memory_store


async def get_memory_retriever() -> MemoryRetriever:
    global _memory_retriever
    if _memory_retriever is None:
        store = await get_memory_store()
        _memory_retriever = MemoryRetriever(store=store)
    return _memory_retriever


async def get_agent_loop() -> AgentLoop:
    global _agent_loop
    if _agent_loop is None:
        llm = get_llm_client()
        retriever = await get_memory_retriever()
        registry = get_tool_registry()
        db = await get_db()

        # Register core tools
        store = await get_memory_store()
        from api.routes.resume import _get_resume

        def get_current_resume():
            return _get_resume()

        # Quality evaluators
        rule_evaluator = RuleEvaluator()
        llm_judge = LLMJudge(llm_client=llm)
        ats_simulator = ATSSimulator()
        scorer = Scorer()

        registry.register_many([
            EchoTool(),
            SearchMemoryTool(store),
            GetUserProfileTool(store),
            GetUserPreferencesTool(store),
            ForgetMemoryTool(store),
            # Quality tools
            EvaluateStarCompletenessTool(rule_evaluator, llm_judge, get_current_resume),
            EvaluateEntryQualityTool(llm_judge, get_current_resume),
            CheckVerbStrengthTool(rule_evaluator, get_current_resume),
            CheckSensitiveInfoTool(rule_evaluator, get_current_resume),
            RunFullQualityAuditTool(rule_evaluator, llm_judge, ats_simulator, scorer, get_current_resume),
        ])

        # Resume version tools
        from api.routes.resume import _version_manager, _save_resume
        from agent.tools.resume_tools import (
            ReadResumeSectionTool,
            UpdateResumeEntryTool,
            AddResumeEntryTool,
            DeleteResumeEntryTool,
            ListResumeVersionsTool,
            ForkResumeVersionTool,
            DiffResumeVersionsTool,
        )
        registry.register_many([
            ReadResumeSectionTool(get_current_resume),
            UpdateResumeEntryTool(get_current_resume, _save_resume),
            AddResumeEntryTool(get_current_resume, _save_resume),
            DeleteResumeEntryTool(get_current_resume, _save_resume),
            ListResumeVersionsTool(_version_manager),
            ForkResumeVersionTool(_version_manager),
            DiffResumeVersionsTool(_version_manager),
        ])

        # GitHub analysis tools
        from core.github.analyzer import GitHubAnalyzer
        from core.cache import get_cache
        from agent.tools.github_tools import (
            FetchRepoMetadataTool,
            AnalyzeRepoStructureTool,
            AnalyzeRepoDependenciesTool,
            ScanIssuesForOpportunitiesTool,
            GenerateDevSuggestionsTool,
            ComposeResumeEntryFromGitHubTool,
        )
        gh_analyzer = GitHubAnalyzer(llm_client=llm, cache=get_cache())
        registry.register_many([
            FetchRepoMetadataTool(gh_analyzer),
            AnalyzeRepoStructureTool(gh_analyzer),
            AnalyzeRepoDependenciesTool(gh_analyzer),
            ScanIssuesForOpportunitiesTool(gh_analyzer),
            GenerateDevSuggestionsTool(gh_analyzer, get_current_resume),
            ComposeResumeEntryFromGitHubTool(gh_analyzer),
        ])

        # Interview tools
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
            GenerateInterviewQuestionsTool(qg, get_current_resume),
            GenerateSelfIntroTool(ig, get_current_resume),
            AnalyzeResumeWeaknessesTool(ws, get_current_resume),
        ])

        # Build Agent dependencies
        context_assembler = ContextAssembler(
            retriever=retriever,
            tool_registry=registry,
        )
        checkpoint_manager = CheckpointManager(db=db)
        planner = Planner()

        _agent_loop = AgentLoop(
            llm_client=llm,
            context_assembler=context_assembler,
            tool_registry=registry,
            checkpoint_manager=checkpoint_manager,
            planner=planner,
        )
    return _agent_loop


async def startup():
    """Initialize all services on app startup."""
    await get_db()
    get_chroma_client()
    get_disk_cache()
    await get_agent_loop()  # Pre-wire all dependencies


async def shutdown():
    """Gracefully close all connections on app shutdown."""
    global _db_conn, _chroma_client, _cache_instance, _agent_loop, _memory_store, _memory_retriever, _tool_registry
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
    _tool_registry = None
