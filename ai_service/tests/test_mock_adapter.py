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

async def test_search_is_literal_substring_ordered_by_updated_at(adapter):
    """Backend contract: case-insensitive literal substring, ordered by updated_at then resource_id."""
    result = await adapter.search_resources(None, "PYTHON")
    assert result.total > 0
    haystacks = [" ".join([r.resource_id, r.title, r.description, *r.authors, *r.topics]).lower()
                 for r in result.items]
    assert all("python" in h for h in haystacks)
    keys = [(r.updated_at, r.resource_id) for r in result.items]
    assert keys == sorted(keys)
    # a multi-word phrase only matches where it appears literally
    assert (await adapter.search_resources(None, "beginner books on machine learning")).total == 0


async def test_search_paging_limit_and_offset(adapter):
    everything = await adapter.search_resources(None, "", limit=100)
    page1 = await adapter.search_resources(None, "", limit=10, offset=0)
    page3 = await adapter.search_resources(None, "", limit=10, offset=20)
    assert page1.total == everything.total == 26          # total counts all matches before paging
    assert [r.resource_id for r in page1.items] == [r.resource_id for r in everything.items[:10]]
    assert [r.resource_id for r in page3.items] == [r.resource_id for r in everything.items[20:30]]
    with pytest.raises(ToolError) as exc:
        await adapter.search_resources(None, "", limit=500)
    assert exc.value.code == ToolError.INVALID_ARGUMENT


async def test_search_filters_by_type_and_level(adapter):
    result = await adapter.search_resources(None, "machine learning", type="book", level="beginner")
    assert "res-006" in [r.resource_id for r in result.items]
    assert all(r.type == "book" and r.level == "beginner" for r in result.items)


async def test_search_unknown_title_returns_empty(adapter):
    result = await adapter.search_resources(None, "Quantum Basket Weaving for Dragons")
    assert result.total == 0 and result.items == []


async def test_search_updated_since(adapter):
    since = datetime(2026, 10, 5, tzinfo=timezone.utc)
    result = await adapter.search_resources(None, "", limit=50, updated_since=since)
    assert {r.resource_id for r in result.items} == {"res-020", "res-025"}
    # strictly newer-than: the exact timestamp of res-025 excludes it
    newest = max(r.updated_at for r in result.items)
    assert (await adapter.search_resources(None, "", updated_since=newest)).total == 0


async def test_availability_known_and_unknown(adapter):
    avail = await adapter.get_availability(None, "res-004")
    assert avail.available_copies == 0 and avail.waitlist_count == 6
    with pytest.raises(ToolError) as exc:
        await adapter.get_availability(None, "res-999")
    assert exc.value.code == ToolError.NOT_FOUND


async def test_restricted_content_is_librarian_only(adapter, student, faculty, librarian):
    for caller in (student, faculty):
        with pytest.raises(ToolError) as exc:
            await adapter.get_resource_content(caller, "res-019")
        assert exc.value.code == ToolError.PERMISSION_DENIED
    content = await adapter.get_resource_content(librarian, "res-019")
    assert content.resource_id == "res-019" and "Hybrid" in content.content and content.source


async def test_authenticated_content_requires_login(adapter, student):
    with pytest.raises(ToolError) as exc:
        await adapter.get_resource_content(None, "res-016")
    assert exc.value.code == ToolError.UNAUTHORIZED  # 401, not 403, when not logged in
    assert (await adapter.get_resource_content(student, "res-016")).content


async def test_public_content_anonymous(adapter):
    assert (await adapter.get_resource_content(None, "res-013")).content


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
    assert rsv.status == "active" and rsv.queue_position is None
    assert (await adapter.get_availability(None, "res-006")).available_copies == before - 1


async def test_earlier_student_beats_new_student(adapter, student):
    # res-010: 1 free copy, 1 student already waiting. Ranked first, then promoted:
    # the earlier student gets the copy; the new student is next in line.
    rsv = await adapter.create_reservation(student, "res-010", "key-w")
    assert rsv.status == "waitlisted" and rsv.queue_position == 1
    assert (await adapter.get_availability(None, "res-010")).available_copies == 0


async def test_faculty_ranks_before_waiting_students(adapter, faculty):
    # Same situation, but a faculty member outranks the waiting student and gets the copy
    rsv = await adapter.create_reservation(faculty, "res-010", "key-f")
    assert rsv.status == "active" and rsv.queue_position is None


async def test_faculty_joins_queue_ahead_of_students(adapter, student2, faculty):
    # res-004: no copies, 6 waiting (students, incl. student2 at the back)
    rsv = await adapter.create_reservation(faculty, "res-004", "key-f2")
    assert rsv.status == "waitlisted" and rsv.queue_position == 1
    mine = {r.resource_id: r for r in await adapter.get_my_reservations(student2)}
    assert mine["res-004"].queue_position == 7  # pushed back by the faculty request


async def test_librarians_cannot_reserve_or_renew(adapter, librarian):
    for call in (adapter.create_reservation(librarian, "res-006", "k"),
                 adapter.renew_loan(librarian, "loan-5001", "k")):
        with pytest.raises(ToolError) as exc:
            await call
        assert exc.value.code == ToolError.PERMISSION_DENIED


async def test_faculty_renewal_is_28_days(adapter, faculty):
    adapter.availability["res-010"].waitlist_count = 0  # nobody waiting, so renewal is allowed
    adapter.queues["res-010"] = []
    before = {l.loan_id: l for l in await adapter.get_my_loans(faculty)}["loan-5005"]
    renewed = await adapter.renew_loan(faculty, "loan-5005", "f-1")
    assert (renewed.due_at - before.due_at).days == 28


async def test_reservation_unavailable_item_joins_waitlist(adapter, student):
    rsv = await adapter.create_reservation(student, "res-004", "key-2")
    assert rsv.status == "waitlisted" and rsv.queue_position == 7


async def test_reservation_is_idempotent(adapter, student):
    first = await adapter.create_reservation(student, "res-006", "same-key")
    second = await adapter.create_reservation(student, "res-006", "same-key")
    assert first.reservation_id == second.reservation_id
    with pytest.raises(ToolError) as exc:  # same key, different resource -> idempotency conflict
        await adapter.create_reservation(student, "res-008", "same-key")
    assert exc.value.code == ToolError.CONFLICT


async def test_duplicate_hold_conflicts(adapter, student2):
    with pytest.raises(ToolError) as exc:
        await adapter.create_reservation(student2, "res-004", "k2")  # already waitlisted
    assert exc.value.code == ToolError.CONFLICT


async def test_renewal_adds_14_days_at_most_twice(adapter, student):
    before = {l.loan_id: l for l in await adapter.get_my_loans(student)}["loan-5001"]
    first = await adapter.renew_loan(student, "loan-5001", "r-1")
    assert (first.due_at - before.due_at).days == 14 and first.renewable is True
    second = await adapter.renew_loan(student, "loan-5001", "r-2")
    assert (second.due_at - before.due_at).days == 28 and second.renewable is False
    with pytest.raises(ToolError) as exc:
        await adapter.renew_loan(student, "loan-5001", "r-3")
    assert exc.value.code == ToolError.NOT_RENEWABLE


async def test_renewal_replay_does_not_extend_twice(adapter, student):
    a = await adapter.renew_loan(student, "loan-5001", "same")
    b = await adapter.renew_loan(student, "loan-5001", "same")
    assert a.due_at == b.due_at


async def test_renewal_rules(adapter, student, student2, librarian):
    with pytest.raises(ToolError) as exc:
        await adapter.renew_loan(student, "loan-5002", "x")  # overdue and fined
    assert exc.value.code == ToolError.NOT_RENEWABLE
    with pytest.raises(ToolError) as exc:
        await adapter.renew_loan(student2, "loan-5004", "y")  # another patron is waiting
    assert exc.value.code == ToolError.NOT_RENEWABLE
    for caller in (student2, librarian):  # non-owner, including librarians -> 403
        with pytest.raises(ToolError) as exc:
            await adapter.renew_loan(caller, "loan-5001", "z")
        assert exc.value.code == ToolError.PERMISSION_DENIED
    with pytest.raises(ToolError) as exc:
        await adapter.renew_loan(student, "loan-9999", "w")
    assert exc.value.code == ToolError.NOT_FOUND


async def test_fine_amount_is_decimal_string_on_the_wire(adapter, student):
    loans = {l.loan_id: l for l in await adapter.get_my_loans(student)}
    assert loans["loan-5002"].model_dump(mode="json")["fine_amount"] == "1.00"


# ---------- analytics ----------

async def test_analytics_librarian_only(adapter, student, librarian):
    with pytest.raises(ToolError) as exc:
        await adapter.get_analytics_summary(student)
    assert exc.value.code == ToolError.PERMISSION_DENIED
    s = await adapter.get_analytics_summary(librarian)
    assert (s.total_resources, s.active_loans, s.overdue_loans, s.active_reservations) == (26, 5, 1, 2)
    assert len(s.popular_resources) == 5
    assert [p.resource_id for p in s.popular_resources] == sorted(p.resource_id for p in s.popular_resources)


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
