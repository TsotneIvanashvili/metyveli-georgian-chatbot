from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    app_name: str = "მეტყველი API"
    app_version: str = "1.0.0"
    environment: str = "development"
    database_url: str | None = None
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_api_key: str | None = None
    ollama_model: str = "qwen3:8b"
    ollama_timeout_seconds: float = 120
    ollama_context_size: int = 4096
    frontend_origins: str = Field(
        default="http://localhost:5173,http://127.0.0.1:5173",
        validation_alias=AliasChoices("ALLOWED_ORIGINS", "FRONTEND_ORIGINS"),
    )
    rag_top_k: int = 4
    rag_min_score: float = 0.025
    knowledge_base_path: Path = (
        PROJECT_ROOT / "data" / "processed" / "knowledge_base.jsonl"
    )
    grammar_model_path: Path = (
        PROJECT_ROOT / "models" / "grammar_classifier.joblib"
    )
    auth_database_path: Path = PROJECT_ROOT / "data" / "auth.db"
    auth_session_days: int = 7

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / "backend" / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def allowed_origins(self) -> list[str]:
        return [
            origin.strip()
            for origin in self.frontend_origins.split(",")
            if origin.strip()
        ]

    @property
    def is_production(self) -> bool:
        return self.environment.casefold() in {"prod", "production", "render"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
