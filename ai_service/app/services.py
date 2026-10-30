"""Builds the service graph from configuration. Switching TOOL_ADAPTER or
LLM_PROVIDER changes only which implementations are constructed here."""
import logging
from dataclasses import dataclass

from app.adapters.base import LibraryToolAdapter
from app.adapters.http_adapter import HttpLibraryToolAdapter
from app.adapters.mock_adapter import MockLibraryToolAdapter
from app.auth.context import UserContext
from app.auth.identity import HttpIdentityAdapter, IdentityAdapter, MockIdentityAdapter
from app.config import Settings
from app.llm.base import LLMClient
from app.rag.embedder import build_embedder
from app.rag.retriever import Retriever
from app.recommend.recommender import Recommender
from app.orchestrator.actions import ActionStore
from app.orchestrator.conversations import ConversationStore
from app.orchestrator.orchestrator import Orchestrator
from app.tools.definitions import build_registry
from app.tools.executor import ToolExecutor
from app.tools.registry import ToolDeps

logger = logging.getLogger("smartlibrary.services")


@dataclass
class Services:
    settings: Settings
    adapter: LibraryToolAdapter
    identity: IdentityAdapter
    executor: ToolExecutor
    deps: ToolDeps
    actions: ActionStore
    orchestrator: Orchestrator | None  # None when the LLM is not configured
    retriever: Retriever
    llm_error: str | None = None


def build_adapter(settings: Settings, transport=None) -> tuple[LibraryToolAdapter, IdentityAdapter]:
    """The single switch point between mock and real backend (TOOL_ADAPTER)."""
    if settings.tool_adapter == "mock":
        return (MockLibraryToolAdapter(settings.fixtures_dir, failures=settings.mock_failure_map),
                MockIdentityAdapter(settings.fixtures_dir))
    adapter = HttpLibraryToolAdapter(settings.backend_api_url, settings.backend_timeout_seconds, transport=transport)
    return adapter, HttpIdentityAdapter(adapter)


def build_llm(settings: Settings) -> LLMClient:
    if settings.llm_provider == "fake":
        from app.llm.fake_llm import RuleBasedLLM
        return RuleBasedLLM()
    from app.llm.gemini_client import GeminiClient
    key = settings.gemini_api_key.get_secret_value() if settings.gemini_api_key else ""
    fallbacks = [m.strip() for m in settings.llm_fallback_models.split(",") if m.strip()]
    return GeminiClient(api_key=key, model=settings.llm_model, fallback_models=fallbacks)


def build_retriever(settings: Settings, adapter: LibraryToolAdapter) -> Retriever:
    token = settings.indexer_token.get_secret_value() if settings.indexer_token else ""
    # Ingestion-only identity; librarian role so restricted content is indexed and
    # then filtered per caller at query time.
    indexer = UserContext(user_id="svc-ai-indexer", name="AI Indexer", role="librarian", token=token)
    return Retriever(build_embedder(settings.embedding_model), adapter, indexer, min_score=settings.rag_min_score)


def build_services(settings: Settings, *, llm: LLMClient | None = None,
                   adapter: LibraryToolAdapter | None = None,
                   identity: IdentityAdapter | None = None, transport=None) -> Services:
    if adapter is None or identity is None:
        built_adapter, built_identity = build_adapter(settings, transport=transport)
        adapter, identity = adapter or built_adapter, identity or built_identity

    executor = ToolExecutor(build_registry())
    retriever = build_retriever(settings, adapter)
    deps = ToolDeps(adapter=adapter, retriever=retriever, recommender=Recommender(adapter, retriever))
    actions = ActionStore(settings.action_ttl_seconds)

    llm_error = None
    if llm is None:
        try:
            llm = build_llm(settings)
        except ValueError as e:
            llm_error = str(e)
            logger.warning("LLM not configured: %s", e)

    orchestrator = None
    if llm is not None:
        orchestrator = Orchestrator(llm, executor, deps, ConversationStore(), actions, settings.max_tool_calls)
    return Services(settings, adapter, identity, executor, deps, actions, orchestrator, retriever, llm_error)
