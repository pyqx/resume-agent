"""Application configuration via pydantic-settings."""

from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


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

    def model_post_init(self, _context):
        self.sqlite_path = self.data_dir / "sqlite.db"
        self.chroma_path = self.data_dir / "chroma"
        self.cache_path = self.data_dir / "cache"
        self.uploads_path = self.data_dir / "uploads"

    # Server
    host: str = "127.0.0.1"
    port: int = 8000
    log_level: str = "INFO"

    # Agent
    max_loop_iterations: int = 15
    max_consecutive_failures: int = 3
    tool_retry_max: int = 3
    tool_retry_base_delay: float = 1.0

    # CORS
    cors_origins: list[str] = [
        "http://localhost:3000", "http://localhost:3001", "http://localhost:3002",
        "http://127.0.0.1:3000", "http://127.0.0.1:3001", "http://127.0.0.1:3002",
    ]


settings = Settings()
