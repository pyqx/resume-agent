"""Application configuration via pydantic-settings."""

from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

# Project root (parent of core/), used to anchor relative data paths so the
# app behaves the same regardless of the CWD uvicorn is launched from.
PROJECT_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # LLM Provider: "anthropic" or "openai_compatible" (DeepSeek, OpenAI, etc.)
    llm_provider: str = "anthropic"
    llm_api_key: str = ""
    llm_model: str = "claude-sonnet-4-6"
    llm_base_url: str = ""  # For OpenAI-compatible: https://api.deepseek.com
    llm_temperature: float = 0.7
    llm_max_tokens: int = 4096
    llm_timeout: float = 120.0  # seconds, per LLM request
    llm_retry_max: int = 2  # retries on 429/5xx/network errors
    llm_retry_base_delay: float = 1.0

    # Privacy: mask PII (phone/email/id/wechat/salary) before sending to LLM,
    # restore placeholders in responses. See core/resume/sanitizer.py.
    sanitize_pii: bool = True

    # GitHub API token (optional; unauthenticated = 60 req/h)
    github_token: str = ""

    # Backward compat
    @property
    def anthropic_api_key(self) -> str:
        return self.llm_api_key if self.llm_provider == "anthropic" else ""

    # Data paths
    data_dir: Path = Path("data")
    sqlite_path: Path | None = None
    chroma_path: Path | None = None
    cache_path: Path | None = None
    uploads_path: Path | None = None
    versions_path: Path | None = None

    def model_post_init(self, _context):
        if not self.data_dir.is_absolute():
            self.data_dir = PROJECT_ROOT / self.data_dir
        # Derive sub-paths only when not explicitly configured, so
        # SQLITE_PATH etc. in .env are honored instead of silently ignored.
        if self.sqlite_path is None:
            self.sqlite_path = self.data_dir / "sqlite.db"
        if self.chroma_path is None:
            self.chroma_path = self.data_dir / "chroma"
        if self.cache_path is None:
            self.cache_path = self.data_dir / "cache"
        if self.uploads_path is None:
            self.uploads_path = self.data_dir / "uploads"
        if self.versions_path is None:
            self.versions_path = self.data_dir / "versions"

    # Server
    host: str = "127.0.0.1"
    port: int = 8000
    log_level: str = "INFO"
    # Debug endpoints (/resume/debug-parse) are disabled unless explicitly on.
    debug_endpoints: bool = False

    # Upload limits
    max_upload_size_mb: int = 10

    # Agent
    max_loop_iterations: int = 15
    max_consecutive_failures: int = 3
    tool_retry_max: int = 3
    tool_retry_base_delay: float = 1.0

    # Web tools
    web_fetch_max_bytes: int = 2 * 1024 * 1024  # 2 MB response body cap

    # Export
    export_text_max_chars: int = 200_000

    # CORS
    cors_origins: list[str] = [
        "http://localhost:3000", "http://localhost:3001", "http://localhost:3002",
        "http://127.0.0.1:3000", "http://127.0.0.1:3001", "http://127.0.0.1:3002",
    ]


settings = Settings()
