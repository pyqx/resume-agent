"""Centralized logging configuration for the Resume Agent."""

import logging
import sys
from pathlib import Path
from logging.handlers import RotatingFileHandler

from core.config import settings
from core.resume.sanitizer import PIILogFilter

_configured = False

LOG_FORMAT = "%(asctime)s [%(levelname)-5s] %(name)s: %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def setup_logging(
    log_level: str = "INFO",
    log_dir: str | Path | None = None,
    log_file: str = "app.log",
    max_bytes: int = 10 * 1024 * 1024,  # 10 MB
    backup_count: int = 5,
):
    """Configure root logger with console + rotating file handlers.

    Call once at application startup. Subsequent calls are no-ops.
    All handlers carry a PII filter that masks phones/emails/ids in
    formatted messages before they reach disk or the console.
    """
    global _configured
    if _configured:
        return
    _configured = True

    root = logging.getLogger()
    root.setLevel(getattr(logging, log_level.upper(), logging.INFO))
    pii_filter = PIILogFilter()

    console = logging.StreamHandler(sys.stderr)
    console.setLevel(root.level)
    console.setFormatter(logging.Formatter(LOG_FORMAT, DATE_FORMAT))
    console.addFilter(pii_filter)
    root.addHandler(console)

    log_path = Path(log_dir) if log_dir else settings.data_dir / "logs"
    log_path.mkdir(parents=True, exist_ok=True)
    file_handler = RotatingFileHandler(
        log_path / log_file,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    file_handler.setLevel(root.level)
    file_handler.setFormatter(logging.Formatter(LOG_FORMAT, DATE_FORMAT))
    file_handler.addFilter(pii_filter)
    root.addHandler(file_handler)

    # Quiet noisy third-party loggers
    for noisy in (
        "chromadb", "chromadb.telemetry", "urllib3", "httpx", "httpcore",
        "openai", "anthropic", "sentence_transformers", "watchfiles",
    ):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    logger = logging.getLogger(__name__)
    logger.info("Logging configured (level=%s, file=%s)", log_level, log_path / log_file)
