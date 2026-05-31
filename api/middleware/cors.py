"""CORS configuration for FastAPI."""

from core.config import settings


def get_cors_config():
    return {
        "allow_origins": settings.cors_origins,
        "allow_credentials": True,
        "allow_methods": ["*"],
        "allow_headers": ["*"],
    }
