"""FastAPI application entry point."""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from core.config import settings
from core.logging_setup import setup_logging

# Configure logging before anything else
setup_logging(log_level=settings.log_level)

from api.deps import startup, shutdown
from api.middleware.logging import LoggingMiddleware
from api.middleware.sanitizer import PrivacyLoggingMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI):
    await startup()
    yield
    await shutdown()


app = FastAPI(
    title="Resume Agent",
    description="AI-powered resume assistant with deep reasoning",
    version="0.1.0",
    lifespan=lifespan,
)

# Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(LoggingMiddleware)
app.add_middleware(PrivacyLoggingMiddleware)


@app.get("/health")
async def health_check():
    return {"status": "ok", "version": "0.1.0"}


# Register route modules
from api.routes import chat, resume, jd, export, github, interview, sessions

app.include_router(chat.router, prefix="/chat", tags=["chat"])
app.include_router(resume.router, prefix="/resume", tags=["resume"])
app.include_router(jd.router, prefix="/jd", tags=["jd"])
app.include_router(export.router, prefix="/export", tags=["export"])
app.include_router(github.router, prefix="/github", tags=["github"])
app.include_router(interview.router, prefix="/interview", tags=["interview"])
app.include_router(sessions.router, prefix="/sessions", tags=["sessions"])
