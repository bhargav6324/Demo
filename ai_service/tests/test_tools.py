import pytest

from app.adapters.mock_adapter import MockLibraryToolAdapter
from app.observability.trace import Trace
from app.tools.definitions import build_registry
from app.tools.executor import ToolExecutor
from app.tools.registry import ExecContext, ToolDeps
from tests.conftest import FIXTURES

EXPECTED_TOOLS = {
    "search_catalog", "get_resource", "get_availability", "get_my_loans", "get_my_reservations",
    "create_reservation", "renew_loan", "get_user_profile", "get_resource_content",
    "get_library_analytics", "semantic_search", "generate_recommendations",
}


@pytest.fixture
def executor():
    return ToolExecutor(build_registry())


def ctx(adapter, user=None, key=None):
    return ExecContext(user=user, deps=ToolDeps(adapter=adapter), idempotency_key=key)


# ---------- registry ----------

def test_all_tools_registered_with_strict_schemas():
    reg = build_registry()
    assert set(reg.names()) == EXPECTED_TOOLS
    for decl in reg.declarations():
        assert decl["description"]
        assert decl["parameters"]["additionalProperties"] is False
        # No tool may accept an identity or URL from the model
        assert not {"user_id", "url", "token"} & set(decl["parameters"]["properties"])


def test_confirmation_and_role_flags():
    reg = build_registry()
    assert reg.get("create_reservation").requires_confirmation
    assert reg.get("renew_loan").requires_confirmation
    assert reg.get("get_library_analytics").allowed_roles == {"librarian"}
    assert not reg.get("search_catalog").requires_confirmation


# ---------- allowlist & validation ----------

async def test_unknown_tool_rejected(executor, adapter):
    trace = Trace()
    res = await executor.execute("delete_all_books", {}, ctx(adapter), trace)
    assert res.status == "rejected" and res.error_code == "unknown_tool"
    assert trace.tool_calls[0].status == "rejected"


@pytest.mark.parametrize("args", [
    {},                                              # missing required
    {"resource_id": 42},                             # wrong type
    {"resource_id": "res-001", "user_id": "u-1002"}, # extra field (identity smuggling)
    {"resource_id": "http://evil.example/x"},        # URL injection blocked by pattern
    {"resource_id": "../../etc/passwd"},             # path traversal blocked by pattern
])
async def test_invalid_arguments_rejected(executor, adapter, args):
    res = await executor.execute("get_availability", args, ctx(adapter), Trace())
    assert res.status == "rejected" and res.error_code == "invalid_argument"


async def test_non_dict_arguments_rejected(executor, adapter):
    res = await executor.execute("search_catalog", "python", ctx(adapter), Trace())
    assert res.error_code == "invalid_argument"


async def test_limit_bounds_enforced(executor, adapter):
    res = await executor.execute("search_catalog", {"query": "python", "limit": 500}, ctx(adapter), Trace())
    assert res.error_code == "invalid_argument"


# ---------- auth & roles ----------

async def test_account_tool_requires_login(executor, adapter):
    res = await executor.execute("get_my_loans", {}, ctx(adapter), Trace())
    assert res.status == "rejected" and res.error_code == "unauthorized"


async def test_student_denied_analytics(executor, adapter, student):
    res = await executor.execute("get_library_analytics", {}, ctx(adapter, student), Trace())
    assert res.status == "rejected" and res.error_code == "permission_denied"


async def test_librarian_gets_analytics(executor, adapter, librarian):
    res = await executor.execute("get_library_analytics", {}, ctx(adapter, librarian), Trace())
    assert res.ok and res.data["total_resources"] == 26 and res.data["popular_resources"]


# ---------- execution ----------

async def test_search_returns_json_data(executor, adapter):
    res = await executor.execute("search_catalog", {"query": "python"}, ctx(adapter), Trace())
    assert res.ok
    assert res.data["total"] >= 1
    assert isinstance(res.data["items"][0]["updated_at"], str)  # JSON-serialized


async def test_loans_wrapped_in_items(executor, adapter, student):
    res = await executor.execute("get_my_loans", {}, ctx(adapter, student), Trace())
    assert {l["loan_id"] for l in res.data["items"]} == {"loan-5001", "loan-5002", "loan-5003"}


async def test_adapter_error_becomes_error_result(executor, adapter):
    res = await executor.execute("get_availability", {"resource_id": "res-999"}, ctx(adapter), Trace())
    assert res.status == "error" and res.error_code == "not_found"
    assert res.for_llm() == {"status": "error", "error": res.error}


async def test_backend_timeout_is_graceful(executor):
    failing = MockLibraryToolAdapter(FIXTURES, failures={"*": "timeout"})
    res = await executor.execute("search_catalog", {"query": "python"}, ctx(failing), Trace())
    assert res.status == "error" and res.error_code == "backend_timeout"


async def test_malformed_backend_data_caught(executor, adapter, monkeypatch):
    async def bad(*_a, **_k):
        return {"items": "not-a-list", "total": "x"}
    monkeypatch.setattr(adapter, "search_resources", bad)
    res = await executor.execute("search_catalog", {"query": "python"}, ctx(adapter), Trace())
    assert res.status == "error" and res.error_code == "backend_error"


async def test_unexpected_exception_contained(executor, adapter, monkeypatch):
    async def boom(*_a, **_k):
        raise RuntimeError("db exploded")
    monkeypatch.setattr(adapter, "get_resource", boom)
    res = await executor.execute("get_resource", {"resource_id": "res-001"}, ctx(adapter), Trace())
    assert res.error_code == "backend_error" and "exploded" not in res.error["message"]


async def test_ai_tools_unavailable_until_wired(executor, adapter, student):
    res = await executor.execute("semantic_search", {"query": "rag"}, ctx(adapter, student), Trace())
    assert res.status == "error" and res.error_code == "backend_error"


# ---------- confirmation gate ----------

async def test_reservation_not_executed_without_confirmation(executor, adapter, student):
    before = (await adapter.get_availability(None, "res-006")).available_copies
    res = await executor.execute("create_reservation", {"resource_id": "res-006"}, ctx(adapter, student), Trace())
    assert res.status == "confirmation_required"
    assert res.data["resource"]["title"] == "Machine Learning for Absolute Beginners"
    assert (await adapter.get_availability(None, "res-006")).available_copies == before  # no state change
    assert "NOT been executed" in res.for_llm()["message"]


async def test_reservation_precheck_unknown_resource(executor, adapter, student):
    res = await executor.execute("create_reservation", {"resource_id": "res-999"}, ctx(adapter, student), Trace())
    assert res.status == "error" and res.error_code == "not_found"


async def test_confirmed_reservation_executes(executor, adapter, student):
    res = await executor.execute("create_reservation", {"resource_id": "res-006"},
                                 ctx(adapter, student, key="idem-1"), Trace(), confirmed=True)
    assert res.ok and res.data["status"] == "active"


async def test_confirmed_action_requires_idempotency_key(executor, adapter, student):
    res = await executor.execute("create_reservation", {"resource_id": "res-006"},
                                 ctx(adapter, student), Trace(), confirmed=True)
    assert res.status == "rejected"


async def test_renewal_precheck(executor, adapter, student, student2):
    ok = await executor.execute("renew_loan", {"loan_id": "loan-5001"}, ctx(adapter, student), Trace())
    assert ok.status == "confirmation_required" and ok.data["loan"]["loan_id"] == "loan-5001"
    overdue = await executor.execute("renew_loan", {"loan_id": "loan-5002"}, ctx(adapter, student), Trace())
    assert overdue.error_code == "not_renewable"
    other = await executor.execute("renew_loan", {"loan_id": "loan-5001"}, ctx(adapter, student2), Trace())
    assert other.error_code == "not_found"


# ---------- tracing ----------

async def test_trace_records_order_and_redacts(executor, adapter, student):
    trace = Trace(user_id=student.user_id)
    await executor.execute("search_catalog", {"query": "python"}, ctx(adapter, student), trace)
    await executor.execute("get_availability", {"resource_id": "res-001"}, ctx(adapter, student), trace)
    await executor.execute("nope", {"token": "secret-value"}, ctx(adapter, student), trace)
    assert trace.tool_names == ["search_catalog", "get_availability", "nope"]
    assert trace.tool_calls[2].args == {"token": "***"}
    assert all(r.latency_ms >= 0 for r in trace.tool_calls)
