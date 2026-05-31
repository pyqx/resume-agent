"""Persistent disk cache via diskcache."""

from contextlib import contextmanager
from pathlib import Path

from diskcache import Cache

from core.config import settings


_cache: Cache | None = None


def init_cache() -> Cache:
    """Initialize diskcache at configured path."""
    global _cache
    Path(settings.cache_path).mkdir(parents=True, exist_ok=True)
    _cache = Cache(str(settings.cache_path))
    return _cache


def get_cache() -> Cache:
    """Get the initialized cache instance."""
    if _cache is None:
        return init_cache()
    return _cache


@contextmanager
def cache_context():
    """Context manager for cache access with automatic close."""
    cache = get_cache()
    try:
        yield cache
    finally:
        pass
