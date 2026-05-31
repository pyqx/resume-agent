"""Centralized logging configuration for the Resume Agent."""

import logging
import sys
from pathlib import Path
from logging.handlers import RotatingFileHandler

_configured = False

LOG_FORMAT = "%(asctime)s [%(levelname)-5s] %(name)s: %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def setup_logging(
    log_level: str = "INFO",
    log_dir: str | Path = "data/logs",
    log_file: str = "app.log",
    max_bytes: int = 10 * 1024 * 1024,  # 10 MB
    backup_count: int = 5,
):
    """Configure root logger with console + rotating file handlers.

    Call once at application startup. Subsequent calls are no-ops.
    """
    global _configured
    if _configured:
        return
    _configured = True

    root = logging.getLogger()
    root.setLevel(getattr(logging, log_level.upper(), logging.INFO))

    # Console handler (stderr)
    console = logging.StreamHandler(sys.stderr)
    console.setLevel(root.level)
    console.setFormatter(logging.Formatter(LOG_FORMAT, DATE_FORMAT))
    root.addHandler(console)

    # File handler (rotating)
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)
    file_handler = RotatingFileHandler(
        log_path / log_file,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    file_handler.setLevel(root.level)
    file_handler.setFormatter(logging.Formatter(LOG_FORMAT, DATE_FORMAT))
    root.addHandler(file_handler)

    # Quiet noisy third-party loggers
    for noisy in ("chromadb", "urllib3", "httpx", "openai", "httpcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    logger = logging.getLogger(__name__)
    logger.info("Logging configured (level=%s, file=%s)", log_level, log_path / log_file)
