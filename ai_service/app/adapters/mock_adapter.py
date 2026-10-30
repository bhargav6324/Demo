"""Deterministic in-memory backend built from local fixtures.

Mirrors the backend handoff contract: same models, same search semantics
(literal case-insensitive substring, ordered by updated_at then resource_id,
limit/offset paging), same authorization and transaction rules, and mutable
state for reservations/renewals. Failures can be injected per method."""
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from app.adapters.base import LibraryToolAdapter
from app.adapters.errors import ToolError
from app.auth.access import can_access
from app.auth.context import UserContext
from app.schemas.library import (
    AnalyticsSummary,
    Availability,
    Loan,
    Reservation,
    Resource,
    ResourceContent,
    SearchResult,
    User,
)
from app.tools.policy import PATRON_ROLES, QUEUE_RANK, renewal_days

MAX_RENEWALS = 2
MAX_LIMIT = 100


class MockLibraryToolAdapter(LibraryToolAdapter):
    def __init__(self, fixtures_dir: Path, failures: dict[str, str] | None = None, now: datetime | None = None):
        """`failures` maps a method name to "timeout" or "error" to simulate outages."""
        self.fixtures_dir = Path(fixtures_dir)
        self.failures = dict(failures or {})
        self.now = now or datetime.now(timezone.utc)
        self._load()

    # ---------- fixture loading ----------

    def _read(self, name: str):
        return json.loads((self.fixtures_dir / name).read_text(encoding="utf-8"))

    def _load(self) -> None:
        self.resources: dict[str, Resource] = {
            r["resource_id"]: Resource(**r) for r in self._read("resources.json")
        }
        self.availability: dict[str, Availability] = {
            a["resource_id"]: Availability(**a) for a in self._read("availability.json")
        }
        self.users: dict[str, User] = {u["user"]["user_id"]: User(**u["user"]) for u in self._read("users.json")}

        circulation = self._read("loans.json")
        self.loans: dict[str, dict] = {}
        for raw in circulation["loans"]:
            due_at = self.now + timedelta(days=raw["due_in_days"])
            loan = Loan(
                loan_id=raw["loan_id"],
                resource_id=raw["resource_id"],
                resource_title=self.resources[raw["resource_id"]].title,
                borrowed_at=self.now - timedelta(days=raw["borrowed_days_ago"]),
                due_at=due_at,
                renewable=raw["renewable"],
                fine_amount=Decimal(raw["fine_amount"]),
                status="overdue" if due_at < self.now else "active",
            )
            self.loans[loan.loan_id] = {"user_id": raw["user_id"], "loan": loan, "renewals": 0}

        self.reservations: dict[str, dict] = {}
        for raw in circulation["reservations"]:
            raw = dict(raw)
            self.reservations[raw["reservation_id"]] = {"user_id": raw.pop("user_id"), "reservation": Reservation(**raw)}
        self._idempotency: dict[tuple, object] = {}
        self._reservation_seq = 8000
        self._queue_seq = 0
        self._build_queues()

    def _build_queues(self) -> None:
        """Per-resource priority waitlist. Fixture waitlist counts include patrons we
        have no records for; they are modelled as earlier-arriving students."""
        self.queues: dict[str, list[dict]] = {}
        for rid, avail in self.availability.items():
            known = [(rsv_id, e["user_id"]) for rsv_id, e in self.reservations.items()
                     if e["reservation"].resource_id == rid and e["reservation"].status == "waitlisted"]
            queue = [self._queue_entry(None, None) for _ in range(max(0, avail.waitlist_count - len(known)))]
            queue += [self._queue_entry(uid, rsv_id) for rsv_id, uid in known]
            self.queues[rid] = queue
            self._settle_queue(rid, promote=False)  # keep fixture inventory exactly as loaded

    def _queue_entry(self, user_id: str | None, reservation_id: str | None) -> dict:
        self._queue_seq += 1
        role = self.users[user_id].role if user_id in self.users else "student"
        return {"user_id": user_id, "rank": QUEUE_RANK.get(role, 2), "seq": self._queue_seq,
                "reservation_id": reservation_id}

    def _settle_queue(self, resource_id: str, promote: bool = True) -> None:
        """Order by role priority then arrival, hand free copies to the front of the
        queue, then renumber positions (backend rule: faculty > researcher > student)."""
        queue = self.queues[resource_id]
        queue.sort(key=lambda e: (e["rank"], e["seq"]))
        avail = self.availability[resource_id]
        while promote and avail.available_copies > 0 and queue:
            promoted = queue.pop(0)
            loc = next(l for l in avail.locations if l.available_copies > 0)
            loc.available_copies -= 1
            avail.available_copies -= 1
            if promoted["reservation_id"] in self.reservations:
                entry = self.reservations[promoted["reservation_id"]]
                entry["reservation"] = entry["reservation"].model_copy(update={"status": "active",
                                                                               "queue_position": None})
        avail.waitlist_count = len(queue)
        for position, e in enumerate(queue, start=1):
            if e["reservation_id"] in self.reservations:
                entry = self.reservations[e["reservation_id"]]
                entry["reservation"] = entry["reservation"].model_copy(update={"status": "waitlisted",
                                                                               "queue_position": position})

    # ---------- helpers ----------

    def _maybe_fail(self, method: str) -> None:
        mode = self.failures.get(method) or self.failures.get("*")
        if mode == "timeout":
            raise ToolError(ToolError.BACKEND_TIMEOUT, "Library backend did not respond in time.")
        if mode == "error":
            raise ToolError(ToolError.BACKEND_ERROR, "Library backend returned an internal error.")

    @staticmethod
    def _require_auth(ctx: UserContext | None) -> UserContext:
        if ctx is None:
            raise ToolError(ToolError.UNAUTHORIZED, "Authentication required.")
        return ctx

    def _resource_or_404(self, resource_id: str) -> Resource:
        res = self.resources.get(resource_id)
        if res is None:
            raise ToolError(ToolError.NOT_FOUND, f"Resource {resource_id} not found.")
        return res

    # ---------- catalog ----------

    async def search_resources(self, ctx, query="", limit=20, type=None, level=None, updated_since=None, offset=0):
        self._maybe_fail("search_resources")
        if not 1 <= limit <= MAX_LIMIT or offset < 0:
            raise ToolError(ToolError.INVALID_ARGUMENT, "limit must be 1-100 and offset >= 0.")
        needle = query.strip().lower()
        matches = []
        for res in self.resources.values():
            if type and res.type != type:
                continue
            if level and res.level != level:
                continue
            if updated_since and res.updated_at <= updated_since:  # strictly newer-than
                continue
            haystack = " ".join([res.resource_id, res.title, res.description, *res.authors, *res.topics]).lower()
            if needle and needle not in haystack:  # literal substring, like the backend
                continue
            matches.append(res)
        matches.sort(key=lambda r: (r.updated_at, r.resource_id))
        return SearchResult(items=matches[offset:offset + limit], total=len(matches))

    async def get_resource(self, ctx, resource_id):
        self._maybe_fail("get_resource")
        return self._resource_or_404(resource_id)

    async def get_availability(self, ctx, resource_id):
        self._maybe_fail("get_availability")
        self._resource_or_404(resource_id)
        # Copy so callers can't mutate live inventory state
        return self.availability[resource_id].model_copy(deep=True)

    async def get_resource_content(self, ctx, resource_id):
        self._maybe_fail("get_resource_content")
        res = self._resource_or_404(resource_id)
        if res.access_level != "public" and ctx is None:
            raise ToolError(ToolError.UNAUTHORIZED, "Authentication required for this content.")
        if not can_access(ctx.role if ctx else None, res.access_level):
            raise ToolError(ToolError.PERMISSION_DENIED, "You are not authorized to read this content.")
        path = self.fixtures_dir / "content" / f"{resource_id}.md"
        if not path.exists():
            raise ToolError(ToolError.NOT_FOUND, f"No content is available for {resource_id}.")
        return ResourceContent(
            resource_id=res.resource_id,
            content=path.read_text(encoding="utf-8"),
            source=f"Synthetic demo repository excerpt: {res.title}",
            updated_at=res.updated_at,
        )

    # ---------- account ----------

    async def get_profile(self, ctx):
        self._maybe_fail("get_profile")
        ctx = self._require_auth(ctx)
        return self.users[ctx.user_id]

    async def get_my_loans(self, ctx):
        self._maybe_fail("get_my_loans")
        ctx = self._require_auth(ctx)
        return [e["loan"] for e in self.loans.values() if e["user_id"] == ctx.user_id]

    async def get_my_reservations(self, ctx):
        self._maybe_fail("get_my_reservations")
        ctx = self._require_auth(ctx)
        return [e["reservation"] for e in self.reservations.values() if e["user_id"] == ctx.user_id]

    # ---------- transactions ----------

    def _require_patron(self, ctx: UserContext | None) -> UserContext:
        ctx = self._require_auth(ctx)
        if ctx.role not in PATRON_ROLES:
            raise ToolError(ToolError.PERMISSION_DENIED, "Librarians cannot reserve or renew items.")
        return ctx

    async def create_reservation(self, ctx, resource_id, idempotency_key):
        self._maybe_fail("create_reservation")
        ctx = self._require_patron(ctx)
        replay_key = (ctx.user_id, "reserve", idempotency_key)
        if (prior := self._idempotency.get(replay_key)) is not None:
            if prior.resource_id != resource_id:
                raise ToolError(ToolError.CONFLICT, "Idempotency key was already used for another resource.")
            return prior
        self._resource_or_404(resource_id)

        for e in self.reservations.values():
            r = e["reservation"]
            if e["user_id"] == ctx.user_id and r.resource_id == resource_id and r.status in ("active", "waitlisted"):
                raise ToolError(ToolError.CONFLICT, "You already have an active or waitlisted hold for this resource.")

        # The caller is ranked against existing waiters *before* any free copy is promoted
        self._reservation_seq += 1
        rsv_id = f"rsv-{self._reservation_seq}"
        self.reservations[rsv_id] = {"user_id": ctx.user_id, "reservation": Reservation(
            reservation_id=rsv_id, resource_id=resource_id, status="waitlisted", queue_position=None)}
        self.queues.setdefault(resource_id, []).append(self._queue_entry(ctx.user_id, rsv_id))
        self._settle_queue(resource_id)

        reservation = self.reservations[rsv_id]["reservation"]
        self._idempotency[replay_key] = reservation
        return reservation

    def _renewal_blocked(self, entry: dict) -> bool:
        loan: Loan = entry["loan"]
        return (
            loan.status != "active"
            or loan.fine_amount > 0
            or entry["renewals"] >= MAX_RENEWALS
            or self.availability[loan.resource_id].waitlist_count > 0  # another patron is waiting
        )

    async def renew_loan(self, ctx, loan_id, idempotency_key):
        self._maybe_fail("renew_loan")
        ctx = self._require_patron(ctx)
        replay_key = (ctx.user_id, "renew", loan_id, idempotency_key)
        if (prior := self._idempotency.get(replay_key)) is not None:
            return prior
        entry = self.loans.get(loan_id)
        if entry is None:
            raise ToolError(ToolError.NOT_FOUND, f"Loan {loan_id} not found.")
        if entry["user_id"] != ctx.user_id:  # non-owner, including librarians
            raise ToolError(ToolError.PERMISSION_DENIED, "You can only renew your own loans.")
        if not entry["loan"].renewable or self._renewal_blocked(entry):
            raise ToolError(ToolError.NOT_RENEWABLE, "This loan is not eligible for renewal.")

        entry["renewals"] += 1
        loan: Loan = entry["loan"]
        entry["loan"] = loan.model_copy(update={"due_at": loan.due_at + timedelta(days=renewal_days(ctx.role))})
        # Recompute eligibility for the next renewal (e.g. false after the second one)
        entry["loan"] = entry["loan"].model_copy(update={"renewable": not self._renewal_blocked(entry)})
        self._idempotency[replay_key] = entry["loan"]
        return entry["loan"]

    # ---------- analytics ----------

    async def get_analytics_summary(self, ctx):
        self._maybe_fail("get_analytics_summary")
        ctx = self._require_auth(ctx)
        if not ctx.is_librarian:
            raise ToolError(ToolError.PERMISSION_DENIED, "Librarian permission is required.")

        loans = [e["loan"] for e in self.loans.values()]
        counts: dict[str, int] = {}
        for l in loans:  # popularity includes returned history
            counts[l.resource_id] = counts.get(l.resource_id, 0) + 1
        popular = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:5]
        return AnalyticsSummary(
            total_resources=len(self.resources),
            active_loans=sum(l.status in ("active", "overdue") for l in loans),
            overdue_loans=sum(l.status == "overdue" for l in loans),
            active_reservations=sum(e["reservation"].status in ("active", "waitlisted")
                                    for e in self.reservations.values()),
            popular_resources=[{"resource_id": rid, "title": self.resources[rid].title, "loan_count": n}
                               for rid, n in popular],
        )
