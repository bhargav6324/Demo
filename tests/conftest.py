from pathlib import Path

import pytest

from app.adapters.mock_adapter import MockLibraryToolAdapter
from app.auth.identity import MockIdentityAdapter

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


@pytest.fixture
def adapter() -> MockLibraryToolAdapter:
    # Fresh instance per test so reservation/renewal state never leaks between tests
    return MockLibraryToolAdapter(FIXTURES)


AUTH = {
    "student": {"Authorization": "Bearer mock-token-student"},
    "student2": {"Authorization": "Bearer mock-token-student2"},
    "faculty": {"Authorization": "Bearer mock-token-faculty"},
    "librarian": {"Authorization": "Bearer mock-token-librarian"},
}


@pytest.fixture
def make_app():
    """make_app(llm, failures=None) -> (TestClient, services). Fresh state per call."""
    from fastapi.testclient import TestClient

    from app.config import Settings
    from app.main import create_app
    from app.services import build_services

    def _make(llm, failures=None, max_tool_calls=6):
        settings = Settings(_env_file=None, tool_adapter="mock", llm_provider="fake", max_tool_calls=max_tool_calls,
                            embedding_model="hashing", rag_min_score=0.1, rag_refresh_seconds=0)
        services = build_services(
            settings, llm=llm,
            adapter=MockLibraryToolAdapter(FIXTURES, failures=failures),
            identity=MockIdentityAdapter(FIXTURES),
        )
        return TestClient(create_app(services)), services

    return _make


@pytest.fixture
def identity() -> MockIdentityAdapter:
    return MockIdentityAdapter(FIXTURES)


@pytest.fixture
async def student(identity):
    return await identity.authenticate("mock-token-student")


@pytest.fixture
async def student2(identity):
    return await identity.authenticate("mock-token-student2")


@pytest.fixture
async def faculty(identity):
    return await identity.authenticate("mock-token-faculty")


@pytest.fixture
async def librarian(identity):
    return await identity.authenticate("mock-token-librarian")
