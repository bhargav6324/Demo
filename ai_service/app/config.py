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
    # Full API base from the backend handoff (already includes /api/v1); takes precedence
    library_api_base_url: str | None = None
    # Backend origin; "/api/v1" is appended when LIBRARY_API_BASE_URL is not set
    backend_base_url: str = "http://100.83.115.82:8001"
    backend_timeout_seconds: float = 10.0
    # Mock-only outage simulation, e.g. "get_availability:timeout,search_resources:error" or "*:error"
    mock_failures: str = ""

    # LLM
    llm_provider: Literal["gemini", "fake"] = "gemini"
    llm_model: str = "gemini-2.5-flash"
    # Comma-separated models tried in order when the primary model's quota is used up
    llm_fallback_models: str = ""
    gemini_api_key: SecretStr | None = None

    # Embeddings / RAG
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"  # or "hashing" (offline, no model)
    rag_top_k: int = 5
    rag_min_score: float = 0.3          # cosine threshold below which hits are ignored
    rag_refresh_seconds: int = 300      # background updated_since refresh; 0 disables
    # Optional bearer token the indexer uses to read non-public content (http mode).
    # The backend has no service identity, so by default only public content is indexed
    # (metadata is always indexed); other content is fetched live with the caller's token.
    indexer_token: SecretStr | None = None

    # Orchestrator
    max_tool_calls: int = Field(default=6, ge=1, le=20)
    action_ttl_seconds: int = 300

    # Service
    # Where this AI service listens. 8002 avoids confusion with the backend's 8001.
    # Use this PC's Tailscale IP (or 0.0.0.0) so teammates on the tailnet can reach it.
    service_host: str = "127.0.0.1"
    service_port: int = 8002
    log_level: str = "INFO"
    fixtures_dir: Path = BASE_DIR / "fixtures"

    @property
    def mock_failure_map(self) -> dict[str, str]:
        pairs = (item.split(":", 1) for item in self.mock_failures.split(",") if ":" in item)
        return {k.strip(): v.strip() for k, v in pairs}

    @property
    def backend_api_url(self) -> str:
        if self.library_api_base_url:
            return self.library_api_base_url.rstrip("/")
        return self.backend_base_url.rstrip("/") + "/api/v1"


@lru_cache
def get_settings() -> Settings:
    return Settings()
