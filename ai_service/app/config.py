from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BASE_DIR / ".env", extra="ignore")

    # Backend tool adapter
    tool_adapter: Literal["mock", "http"] = "mock"
    backend_base_url: str = "http://localhost:8000"
    backend_timeout_seconds: float = 5.0
    # Mock-only outage simulation, e.g. "get_availability:timeout,search_resources:error" or "*:error"
    mock_failures: str = ""

    # LLM
    llm_provider: Literal["gemini", "fake"] = "gemini"
    llm_model: str = "gemini-2.5-flash"
    gemini_api_key: SecretStr | None = None

    # Embeddings / RAG
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"  # or "hashing" (offline, no model)
    rag_top_k: int = 5
    rag_min_score: float = 0.3          # cosine threshold below which hits are ignored
    rag_refresh_seconds: int = 300      # background updated_since refresh; 0 disables
    # Service token the indexer uses to read content from the backend (http mode)
    indexer_token: SecretStr | None = None

    # Orchestrator
    max_tool_calls: int = Field(default=6, ge=1, le=20)
    action_ttl_seconds: int = 300

    # Service
    service_port: int = 8001
    log_level: str = "INFO"
    fixtures_dir: Path = BASE_DIR / "fixtures"

    @property
    def mock_failure_map(self) -> dict[str, str]:
        pairs = (item.split(":", 1) for item in self.mock_failures.split(",") if ":" in item)
        return {k.strip(): v.strip() for k, v in pairs}

    @property
    def backend_api_url(self) -> str:
        return self.backend_base_url.rstrip("/") + "/api/v1"


@lru_cache
def get_settings() -> Settings:
    return Settings()
