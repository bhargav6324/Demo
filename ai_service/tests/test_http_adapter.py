"""HTTP adapter contract tests against an in-process fake backend.

Core behaviour tests are parametrized over BOTH adapters: mock and http
must be interchangeable. The last section boots the full app with
TOOL_ADAPTER=http (config only) and runs chat flows end to end."""
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.adapters.errors import ToolError
from app.adapters.http_adapter import HttpLibraryToolAdapter
from app.adapters.mock_adapter import MockLibraryToolAdapter
from app.auth.identity import HttpIdentityAdapter, MockIdentityAdapter
from app.config import Settings
from app.llm.fake_llm import ScriptedLLM, call, final
from app.main import create_app
from app.services import build_adapter, build_services
from tests.conftest import AUTH, FIXTURES
from tests.fake_backend import INDEXER_TOKEN, FakeBackend

API = "http://backend.test/api/v1"


@pytest.fixture
def backend():
    return FakeBackend()


@pytest.fixture
def http(backend):
    return HttpLibraryToolAdapter(API, transport=backend.transport)


@pytest.fixture(params=["mock", "http"])
def pair(request, backend):
    """(adapter, identity) for each implementation."""
    if request.param == "mock":
        return MockLibraryToolAdapter(FIXTURES), MockIdentityAdapter(FIXTURES)
    adapter = HttpLibraryToolAdapter(API, transport=backend.transport)
    return adapter, HttpIdentityAdapter(adapter)


# ======================================================================= shared contract

async def test_contract_search(pair):
    adapter, _ = pair
    res = await adapter.search_resources(None, "python", limit=3)
    assert res.total >= 3 and len(res.items) == 3          # total counts all matches before paging
    page2 = await adapter.search_resources(None, "python", limit=3, offset=3)
    assert not {r.resource_id for r in res.items} & {r.resource_id for r in page2.items}
    assert (await adapter.search_resources(None, "zzz-no-such-thing")).items == []  # 200 + empty, not 404


async def test_contract_updated_since(pair):
    adapter, _ = pair
    res = await adapter.search_resources(None, "", limit=50, updated_since=datetime(2026, 10, 5, tzinfo=timezone.utc))
    assert {r.resource_id for r in res.items} == {"res-020", "res-025"}


async def test_contract_availability_and_not_found(pair):
    adapter, _ = pair
    assert (await adapter.get_availability(None, "res-004")).waitlist_count == 6
    with pytest.raises(ToolError) as e:
        await adapter.get_resource(None, "res-999")
    assert e.value.code == "not_found"


async def test_contract_identity(pair):
    _, identity = pair
    ctx = await identity.authenticate("mock-token-student")
    assert (ctx.user_id, ctx.role) == ("u-1001", "student")
    with pytest.raises(ToolError) as e:
        await identity.authenticate("forged")
    assert e.value.code == "unauthorized"


async def test_contract_account_scoped(pair):
    adapter, identity = pair
    student = await identity.authenticate("mock-token-student")
    assert {l.loan_id for l in await adapter.get_my_loans(student)} == {"loan-5001", "loan-5002", "loan-5003"}
    assert (await adapter.get_profile(student)).courses[0].startswith("CS201")
    assert await adapter.get_my_reservations(student) == []


async def test_contract_reservation_idempotent(pair):
    adapter, identity = pair
    student = await identity.authenticate("mock-token-student")
    a = await adapter.create_reservation(student, "res-006", "idem-key-1")
    b = await adapter.create_reservation(student, "res-006", "idem-key-1")
    assert a.status == "active" and a.queue_position is None and a.reservation_id == b.reservation_id
    with pytest.raises(ToolError) as e:   # 409 duplicate_reservation (new key, same hold)
        await adapter.create_reservation(student, "res-006", "idem-key-2")
    assert e.value.code == "conflict"


async def test_contract_renewal_and_rules(pair):
    adapter, identity = pair
    student = await identity.authenticate("mock-token-student")
    student2 = await identity.authenticate("mock-token-student2")
    loan = await adapter.renew_loan(student, "loan-5001", "r1")
    assert loan.renewable is True and str(loan.fine_amount) == "0.00"
    with pytest.raises(ToolError) as e:   # 409 renewal_not_allowed
        await adapter.renew_loan(student, "loan-5002", "r2")
    assert e.value.code == "not_renewable"
    with pytest.raises(ToolError) as e:   # 403 non-owner
        await adapter.renew_loan(student2, "loan-5003", "r3")
    assert e.value.code == "permission_denied"


async def test_contract_authorization(pair):
    adapter, identity = pair
    student = await identity.authenticate("mock-token-student")
    librarian = await identity.authenticate("mock-token-librarian")
    with pytest.raises(ToolError) as e:
        await adapter.get_analytics_summary(student)
    assert e.value.code == "permission_denied"
    summary = await adapter.get_analytics_summary(librarian)
    assert summary.total_resources == 26 and summary.popular_resources[0].loan_count == 1
    with pytest.raises(ToolError) as e:
        await adapter.get_resource_content(student, "res-019")
    assert e.value.code == "permission_denied"
    with pytest.raises(ToolError) as e:
        await adapter.get_resource_content(None, "res-016")   # authenticated content, no token
    assert e.value.code == "unauthorized"


async def test_contract_content_shape(pair):
    adapter, _ = pair
    c = await adapter.get_resource_content(None, "res-013")
    assert c.resource_id == "res-013" and c.content and c.source and c.updated_at


# ======================================================================= http specifics

async def test_bearer_forwarded_and_idempotency_header(http, backend):
    student = await HttpIdentityAdapter(http).authenticate("mock-token-student")
    await http.create_reservation(student, "res-006", "key-abc")
    req = backend.requests[-1]
    assert req.headers["Authorization"] == "Bearer mock-token-student"
    assert req.headers["Idempotency-Key"] == "key-abc"
    assert req.url.path == "/api/v1/reservations"


async def test_anonymous_calls_send_no_auth_header(http, backend):
    await http.search_resources(None, "python")
    assert "Authorization" not in backend.requests[-1].headers


async def test_ids_are_encoded_as_single_path_segment(http, backend):
    with pytest.raises(ToolError):
        await http.get_resource(None, "../admin")
    assert backend.requests[-1].url.raw_path.startswith(b"/api/v1/resources/..%2Fadmin")


@pytest.mark.parametrize("mode,code", [
    ("timeout", "backend_timeout"), ("down", "backend_error"), ("500", "backend_error"),
    ("html", "backend_error"), ("malformed", "backend_error"),
])
async def test_failures_map_to_tool_errors(http, backend, mode, code):
    backend.fail[r"/resources/res-001/availability"] = mode
    with pytest.raises(ToolError) as e:
        await http.get_availability(None, "res-001")
    assert e.value.code == code
    assert "db-7.internal" not in e.value.message  # internal details never leak


async def test_database_busy_retried_with_same_key(http, backend):
    student = await HttpIdentityAdapter(http).authenticate("mock-token-student")
    backend.fail[r"/reservations"] = "busy"
    backend.busy_responses = 2          # two 409 database_busy, then success
    rsv = await http.create_reservation(student, "res-006", "busy-key")
    assert rsv.status == "active"
    posts = [r for r in backend.requests if r.method == "POST"]
    assert len(posts) == 3 and {r.headers["Idempotency-Key"] for r in posts} == {"busy-key"}


async def test_database_busy_exhausted_is_retryable_error(http, backend):
    student = await HttpIdentityAdapter(http).authenticate("mock-token-student")
    backend.fail[r"/reservations"] = "busy"
    backend.busy_responses = 10
    with pytest.raises(ToolError) as e:
        await http.create_reservation(student, "res-006", "busy-key")
    assert e.value.code == "backend_error" and e.value.retryable and "Nothing was changed" in e.value.message


async def test_profile_merges_caller_identity(http, backend):
    student = await HttpIdentityAdapter(http).authenticate("mock-token-student")
    profile = await http.get_profile(student)   # backend sends only courses/interests
    assert (profile.user_id, profile.role) == ("u-1001", "student")
    assert profile.interests == ["data science", "machine learning"]


async def test_search_sends_limit_and_offset(http, backend):
    await http.search_resources(None, "python", limit=100, offset=200)
    params = backend.requests[-1].url.params
    assert (params["limit"], params["offset"], params["query"]) == ("100", "200", "python")


async def test_renew_sends_empty_json_body(http, backend):
    student = await HttpIdentityAdapter(http).authenticate("mock-token-student")
    await http.renew_loan(student, "loan-5001", "k")
    assert backend.requests[-1].content == b"{}"


async def test_health(http, backend):
    assert await http.health() is True
    backend.fail[r"/health"] = "down"
    assert await http.health() is False


async def test_identity_cache_avoids_repeat_auth_calls(http, backend):
    identity = HttpIdentityAdapter(http)
    await identity.authenticate("mock-token-student")
    await identity.authenticate("mock-token-student")
    assert sum(r.url.path.endswith("/auth/me") for r in backend.requests) == 1


def test_build_adapter_switch_is_config_only():
    adapter, identity = build_adapter(Settings(_env_file=None, tool_adapter="http",
                                               backend_base_url="http://localhost:8000"))
    assert isinstance(adapter, HttpLibraryToolAdapter) and isinstance(identity, HttpIdentityAdapter)
    assert str(adapter._client.base_url).rstrip("/") == "http://localhost:8000/api/v1"


# ======================================================================= full app in http mode

@pytest.fixture
def http_app(backend):
    def _make(steps):
        settings = Settings(_env_file=None, tool_adapter="http", backend_base_url="http://backend.test",
                            indexer_token=INDEXER_TOKEN, llm_provider="fake", embedding_model="hashing",
                            rag_min_score=0.1, rag_refresh_seconds=0)
        services = build_services(settings, llm=ScriptedLLM(steps), transport=backend.transport)
        return TestClient(create_app(services)), services
    return _make


def test_http_mode_search_and_availability(http_app):
    client, _ = http_app([
        call("search_catalog", query="Artificial Intelligence Modern Approach", limit=1),
        call("get_availability", resource_id="res-004"),
        final("Not available right now.", "availability", [{"resource_id": "res-004"}]),
    ])
    d = client.post("/api/v1/chat/messages", json={"message": "Is AIMA available?"},
                    headers=AUTH["student"]).json()["data"]
    assert d["outcome"] == "answered" and d["resources"][0]["available_copies"] == 0


def test_http_mode_reserve_and_confirm(http_app, backend):
    client, _ = http_app([call("create_reservation", resource_id="res-006"), final("Confirm?", "reservation")])
    d = client.post("/api/v1/chat/messages", json={"message": "reserve res-006"},
                    headers=AUTH["student"]).json()["data"]
    assert d["outcome"] == "needs_confirmation"
    assert not any(r.method == "POST" for r in backend.requests)  # nothing written before confirm

    c = client.post("/api/v1/chat/actions/confirm", json={"action_id": d["proposed_action"]["action_id"]},
                    headers=AUTH["student"]).json()["data"]
    assert c["transaction_status"] == "succeeded"
    posts = [r for r in backend.requests if r.method == "POST"]
    assert len(posts) == 1 and posts[0].headers["Idempotency-Key"]
    assert posts[0].headers["Authorization"] == "Bearer mock-token-student"  # acting as the user


def test_http_mode_rag_index_built_through_backend(http_app, backend):
    client, services = http_app([
        call("semantic_search", query="retrieval-augmented generation"),
        final("RAG papers", "research", [{"resource_id": "res-013"}]),
    ])
    d = client.post("/api/v1/chat/messages", json={"message": "papers on RAG"},
                    headers=AUTH["student"]).json()["data"]
    assert ("document", "res-013") in {(c["source_type"], c["resource_id"]) for c in d["citations"]}
    indexer_calls = [r for r in backend.requests if r.headers.get("Authorization") == f"Bearer {INDEXER_TOKEN}"]
    assert indexer_calls, "indexer should read content with its own service token"


def test_http_mode_privacy_and_authorization(http_app):
    client, _ = http_app([call("get_library_analytics"), final("stats", "analytics")])
    d = client.post("/api/v1/chat/messages", json={"message": "show waitlists"},
                    headers=AUTH["student"]).json()["data"]
    assert d["outcome"] == "refused"


def test_http_mode_invalid_token_and_health(http_app, backend):
    client, _ = http_app([])
    assert client.post("/api/v1/chat/messages", json={"message": "hi"},
                       headers={"Authorization": "Bearer forged"}).status_code == 401
    h = client.get("/api/v1/health").json()["data"]
    assert h["tool_adapter"] == "http" and h["backend_reachable"] is True


def test_http_mode_backend_outage(http_app, backend):
    backend.fail[r"/resources.*"] = "timeout"
    client, _ = http_app([call("get_availability", resource_id="res-001"), final("2 available", "availability")])
    d = client.post("/api/v1/chat/messages", json={"message": "is res-001 available"},
                    headers=AUTH["student"]).json()["data"]
    assert "temporarily unavailable" in d["assistant_message"] and d["resources"] == []
