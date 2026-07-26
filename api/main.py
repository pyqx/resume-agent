"""FastAPI application entry point."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from core.config import settings
from core.logging_setup import setup_logging

# Configure logging before anything else
setup_logging(log_level=settings.log_level)

from api.deps import startup, shutdown, get_db, get_chroma_client, get_disk_cache
from api.middleware.logging import LoggingMiddleware

logger = logging.getLogger(__name__)

APP_VERSION = "0.2.0"


@asynccontextmanager
async def lifespan(app: FastAPI):
    await startup()
    yield
    await shutdown()


app = FastAPI(
    title="Resume Agent",
    description="AI-powered resume assistant with deep reasoning",
    version=APP_VERSION,
    lifespan=lifespan,
)

# Middleware. Starlette wraps in reverse add order — CORS is added LAST so it
# is the OUTERMOST layer and error responses still carry CORS headers.
app.add_middleware(LoggingMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID"],
)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Uniform 500 without leaking internals; details go to the log."""
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "服务器内部错误,请稍后重试"},
    )


@app.get("/health")
async def health_check():
    """Real dependency probes (SQLite / ChromaDB / disk cache)."""
    components: dict[str, str] = {}

    try:
        db = await get_db()
        async with db.execute("SELECT 1") as cur:
            await cur.fetchone()
        components["sqlite"] = "ok"
    except Exception as e:
        components["sqlite"] = f"error: {type(e).__name__}"

    try:
        get_chroma_client().heartbeat()
        components["chromadb"] = "ok"
    except Exception as e:
        components["chromadb"] = f"error: {type(e).__name__}"

    try:
        cache = get_disk_cache()
        cache.set("_health", 1, expire=10)
        components["cache"] = "ok"
    except Exception as e:
        components["cache"] = f"error: {type(e).__name__}"

    components["llm_configured"] = "ok" if settings.llm_api_key else "missing_api_key"

    healthy = all(v == "ok" for k, v in components.items() if k != "llm_configured")
    return JSONResponse(
        status_code=200 if healthy else 503,
        content={
            "status": "ok" if healthy else "degraded",
            "version": APP_VERSION,
            "components": components,
        },
    )


# Register route modules. versions must precede resume so that
# /resume/versions/* is matched before /resume/{resume_id}.
from api.routes import chat, resume, versions, jd, export, github, interview, sessions

app.include_router(chat.router, prefix="/chat", tags=["chat"])
app.include_router(versions.router, prefix="/resume/versions", tags=["versions"])
app.include_router(resume.router, prefix="/resume", tags=["resume"])
app.include_router(jd.router, prefix="/jd", tags=["jd"])
app.include_router(export.router, prefix="/export", tags=["export"])
app.include_router(github.router, prefix="/github", tags=["github"])
app.include_router(interview.router, prefix="/interview", tags=["interview"])
app.include_router(sessions.router, prefix="/sessions", tags=["sessions"])
