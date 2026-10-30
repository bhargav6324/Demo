from datetime import datetime, timezone

import pytest

from app.adapters.errors import ToolError
from app.adapters.mock_adapter import MockLibraryToolAdapter
from tests.conftest import FIXTURES


async def test_identity_rejects_unknown_token(identity):
    with pytest.raises(ToolError) as exc:
        await identity.authenticate("not-a-token")
    assert exc.value.code == ToolError.UNAUTHORIZED


async def test_identity_context_hides_token(student):
    assert student.role == "student"
    assert "mock-token-student" not in repr(student)


# ---------- catalog ----------

async def test_search_python_returns_ranked_python_titles(adapter):
    result = await adapter.search_resources(None, "python programming")
    assert result.total > 0
    top = result.items[:5]
    assert all("python" in (r.title + " ".join(r.topics)).lower() for r in top)
    # titles with "Python" in the name rank above topic-only matches
    assert "python" in top[0].title.lower()


async def test_search_filters_by_type_and_level(adapter):
    result = await adapter.search_resources(None, "machine learning", type="book", level="beginner")
    ids = [r.resource_id for r in result.items]
    assert ids[0] == "res-006"  # "Machine Learning" in title ranks first
    assert all(r.type == "book" and r.level == "beginner" for r in result.items)


async def test_search_unknown_title_returns_empty(adapter):
    result = await adapter.search_resources(None, "Quantum Basket Weaving for Dragons")
    assert result.total == 0 and result.items == []


async def test_search_updated_since(adapter):
    since = datetime(2026, 10, 5, tzinfo=timezone.utc)
    result = await adapter.search_resources(None, "", limit=50, updated_since=since)
    assert {r.resource_id for r in result.items} == {"res-020", "res-025"}


async def test_availability_known_and_unknown(adapter):
    avail = await adapter.get_availability(None, "res-004")
    assert avail.available_copies == 0 and avail.waitlist_count == 6
    with pytest.raises(ToolError) as exc:
        await adapter.get_availability(None, "res-999")
    assert exc.value.code == ToolError.NOT_FOUND


async def test_restricted_content_requires_role(adapter, student, faculty):
    with pytest.raises(ToolError) as exc:
        await adapter.get_resource_content(student, "res-019")
    assert exc.value.code == ToolError.PERMISSION_DENIED
    content = await adapter.get_resource_content(faculty, "res-019")
    assert "Hybrid" in content.title


async def test_university_content_requires_login(adapter, student):
    with pytest.raises(ToolError):
        await adapter.get_resource_content(None, "res-016")
    assert (await adapter.get_resource_content(student, "res-016")).text


# ---------- account ----------

async def test_loans_are_scoped_to_caller(adapter, student, student2):
    mine = {l.loan_id for l in await adapter.get_my_loans(student)}
    theirs = {l.loan_id for l in await adapter.get_my_loans(student2)}
    assert mine == {"loan-5001", "loan-5002", "loan-5003"}
    assert mine.isdisjoint(theirs)


async def test_overdue_status_is_computed(adapter, student):
    loans = {l.loan_id: l for l in await adapter.get_my_loans(student)}
    assert loans["loan-5002"].status == "overdue"
    assert loans["loan-5001"].status == "active"


async def test_account_tools_require_auth(adapter):
    with pytest.raises(ToolError) as exc:
        await adapter.get_my_loans(None)
    assert exc.value.code == ToolError.UNAUTHORIZED


# ---------- transactions ----------

async def test_reservation_available_item_holds_copy(adapter, student):
    before = (await adapter.get_availability(None, "res-006")).available_copies
    rsv = await adapter.create_reservation(student, "res-006", "key-1")
    assert rsv.status == "ready_for_pickup"
    assert (await adapter.get_availability(None, "res-006")).available_copies == before - 1


async def test_reservation_unavailable_item_joins_waitlist(adapter, student):
    rsv = await adapter.create_reservation(student, "res-004", "key-2")
    assert rsv.status == "waitlisted" and rsv.queue_position == 7


async def test_reservation_is_idempotent(adapter, student):
    first = await adapter.create_reservation(student, "res-006", "same-key")
    second = await adapter.create_reservation(student, "res-006", "same-key")
    assert first.reservation_id == second.reservation_id


async def test_reservation_conflicts(adapter, student, student2):
    with pytest.raises(ToolError) as exc:
        await adapter.create_reservation(student, "res-007", "k")  # already on loan
    assert exc.value.code == ToolError.CONFLICT
    with pytest.raises(ToolError) as exc:
        await adapter.create_reservation(student2, "res-004", "k2")  # already waitlisted
    assert exc.value.code == ToolError.CONFLICT


async def test_renewal_extends_due_date_once(adapter, student):
    before = {l.loan_id: l for l in await adapter.get_my_loans(student)}["loan-5001"]
    renewed = await adapter.renew_loan(student, "loan-5001", "r-1")
    assert (renewed.due_at - before.due_at).days == 14
    assert renewed.renewable is False
    with pytest.raises(ToolError) as exc:
        await adapter.renew_loan(student, "loan-5001", "r-2")
    assert exc.value.code == ToolError.NOT_RENEWABLE


async def test_renewal_rules(adapter, student, student2):
    with pytest.raises(ToolError) as exc:
        await adapter.renew_loan(student, "loan-5002", "x")  # overdue
    assert exc.value.code == ToolError.NOT_RENEWABLE
    with pytest.raises(ToolError) as exc:
        await adapter.renew_loan(student2, "loan-5004", "y")  # item has a waitlist
    assert exc.value.code == ToolError.NOT_RENEWABLE
    with pytest.raises(ToolError) as exc:
        await adapter.renew_loan(student2, "loan-5001", "z")  # someone else's loan
    assert exc.value.code == ToolError.NOT_FOUND


# ---------- analytics ----------

async def test_analytics_librarian_only(adapter, student, librarian):
    with pytest.raises(ToolError) as exc:
        await adapter.get_analytics_summary(student)
    assert exc.value.code == ToolError.PERMISSION_DENIED
    summary = await adapter.get_analytics_summary(librarian)
    assert summary.top_waitlisted[0]["resource_id"] == "res-004"
    assert summary.overdue_summary["overdue_loans"] == 1


# ---------- failure simulation ----------

@pytest.mark.parametrize("mode,code", [("timeout", ToolError.BACKEND_TIMEOUT), ("error", ToolError.BACKEND_ERROR)])
async def test_simulated_backend_failures(mode, code):
    adapter = MockLibraryToolAdapter(FIXTURES, failures={"get_availability": mode})
    with pytest.raises(ToolError) as exc:
        await adapter.get_availability(None, "res-001")
    assert exc.value.code == code and exc.value.retryable
    # other methods unaffected
    assert (await adapter.get_resource(None, "res-001")).title == "Python Crash Course"


def test_failure_map_parsing():
    from app.config import Settings

    s = Settings(mock_failures="get_availability:timeout, *:error")
    assert s.mock_failure_map == {"get_availability": "timeout", "*": "error"}
