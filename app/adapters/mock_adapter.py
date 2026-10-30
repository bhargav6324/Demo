"""Deterministic in-memory backend built from local fixtures.

Behaves like the real backend: same canonical models, same error codes,
authorization enforced on protected operations, and mutable state for
reservations/renewals. Failures can be injected per method for testing."""
import copy
import json
import re
from datetime import datetime, timedelta, timezone
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

RENEWAL_DAYS = 14
_STOPWORDS = {
    "a", "an", "the", "on", "of", "for", "to", "in", "and", "or", "about", "with",
    "book", "books", "find", "me", "some", "any", "is", "are", "i", "my", "show",
}


def _tokens(text: str) -> list[str]:
    words = re.findall(r"[a-z0-9]+", text.lower())
    # Light stemming so "papers" matches "paper"
    return [w[:-1] if len(w) > 3 and w.endswith("s") else w for w in words if w not in _STOPWORDS]


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
                fine_amount=raw["fine_amount"],
                status="overdue" if due_at < self.now else "active",
            )
            self.loans[loan.loan_id] = {"user_id": raw["user_id"], "loan": loan}

        self.reservations: dict[str, dict] = {
            r["reservation_id"]: {"user_id": r.pop("user_id"), "reservation": Reservation(**r)}
            for r in copy.deepcopy(circulation["reservations"])
        }
        self.analytics_base = self._read("analytics.json")
        self._idempotency: dict[str, object] = {}
        self._reservation_seq = 8000

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

    def _replay(self, key: str):
        return self._idempotency.get(key)

    # ---------- catalog ----------

    async def search_resources(self, ctx, query="", limit=10, type=None, level=None, updated_since=None):
        self._maybe_fail("search_resources")
        q_tokens = set(_tokens(query))
        scored: list[tuple[float, Resource]] = []
        for res in self.resources.values():
            if type and res.type != type:
                continue
            if level and res.level != level:
                continue
            if updated_since and res.updated_at <= updated_since:
                continue
            if not q_tokens:
                scored.append((0.0, res))
                continue
            title = set(_tokens(res.title))
            topics = set(_tokens(" ".join(res.topics)))
            authors = set(_tokens(" ".join(res.authors)))
            desc = set(_tokens(res.description))
            score = (
                3 * len(q_tokens & title)
                + 2 * len(q_tokens & topics)
                + 2 * len(q_tokens & authors)
                + 1 * len(q_tokens & desc)
            )
            # Require most query terms to appear somewhere, so unrelated titles don't match on one word
            matched = q_tokens & (title | topics | authors | desc)
            if score > 0 and len(matched) >= max(1, round(len(q_tokens) * 0.6)):
                scored.append((score, res))
        scored.sort(key=lambda s: (-s[0], s[1].resource_id))
        return SearchResult(items=[r for _, r in scored[:limit]], total=len(scored))

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
        if not can_access(ctx.role if ctx else None, res.access_level):
            raise ToolError(ToolError.PERMISSION_DENIED, "You are not authorized to read this content.")
        path = self.fixtures_dir / "content" / f"{resource_id}.md"
        if not path.exists():
            raise ToolError(ToolError.NOT_FOUND, f"No authorized content is available for {resource_id}.")
        return ResourceContent(
            resource_id=res.resource_id,
            title=res.title,
            source_type=res.type,
            access_level=res.access_level,
            text=path.read_text(encoding="utf-8"),
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

    async def create_reservation(self, ctx, resource_id, idempotency_key):
        self._maybe_fail("create_reservation")
        ctx = self._require_auth(ctx)
        if (prior := self._replay(idempotency_key)) is not None:
            return prior
        self._resource_or_404(resource_id)

        for e in self.reservations.values():
            r = e["reservation"]
            if e["user_id"] == ctx.user_id and r.resource_id == resource_id and r.status in ("waitlisted", "ready_for_pickup"):
                raise ToolError(ToolError.CONFLICT, "You already have an active reservation for this resource.")
        for e in self.loans.values():
            if e["user_id"] == ctx.user_id and e["loan"].resource_id == resource_id and e["loan"].status != "returned":
                raise ToolError(ToolError.CONFLICT, "You already have this resource on loan.")

        avail = self.availability[resource_id]
        if avail.available_copies > 0:
            # Hold one copy at the first branch that has stock
            loc = next(l for l in avail.locations if l.available_copies > 0)
            loc.available_copies -= 1
            avail.available_copies -= 1
            status, position = "ready_for_pickup", 0
        else:
            avail.waitlist_count += 1
            status, position = "waitlisted", avail.waitlist_count

        self._reservation_seq += 1
        reservation = Reservation(
            reservation_id=f"rsv-{self._reservation_seq}",
            resource_id=resource_id,
            status=status,
            queue_position=position,
        )
        self.reservations[reservation.reservation_id] = {"user_id": ctx.user_id, "reservation": reservation}
        self._idempotency[idempotency_key] = reservation
        return reservation

    async def renew_loan(self, ctx, loan_id, idempotency_key):
        self._maybe_fail("renew_loan")
        ctx = self._require_auth(ctx)
        if (prior := self._replay(idempotency_key)) is not None:
            return prior
        entry = self.loans.get(loan_id)
        # Someone else's loan is reported as not found so loan IDs can't be probed
        if entry is None or entry["user_id"] != ctx.user_id:
            raise ToolError(ToolError.NOT_FOUND, f"Loan {loan_id} not found.")
        loan: Loan = entry["loan"]
        if not loan.renewable or loan.status != "active":
            raise ToolError(ToolError.NOT_RENEWABLE, "This loan is not eligible for renewal.")
        if self.availability[loan.resource_id].waitlist_count > 0:
            raise ToolError(ToolError.NOT_RENEWABLE, "This item has a waitlist and cannot be renewed.")

        renewed = loan.model_copy(update={"due_at": loan.due_at + timedelta(days=RENEWAL_DAYS), "renewable": False})
        entry["loan"] = renewed
        self._idempotency[idempotency_key] = renewed
        return renewed

    # ---------- analytics ----------

    async def get_analytics_summary(self, ctx):
        self._maybe_fail("get_analytics_summary")
        ctx = self._require_auth(ctx)
        if not ctx.is_librarian:
            raise ToolError(ToolError.PERMISSION_DENIED, "Library analytics are available to librarians only.")

        waitlisted = sorted(
            (a for a in self.availability.values() if a.waitlist_count > 0),
            key=lambda a: -a.waitlist_count,
        )
        overdue = [e["loan"] for e in self.loans.values() if e["loan"].status == "overdue"]
        return AnalyticsSummary(
            generated_at=self.now,
            top_waitlisted=[
                {
                    "resource_id": a.resource_id,
                    "title": self.resources[a.resource_id].title,
                    "waitlist_count": a.waitlist_count,
                    "total_copies": a.total_copies,
                }
                for a in waitlisted[:5]
            ],
            circulation_trend=self.analytics_base["circulation_trend"],
            overdue_summary={
                "overdue_loans": len(overdue),
                "total_outstanding_fines": round(sum(l.fine_amount for l in overdue), 2),
            },
            utilization_by_type=self.analytics_base["utilization_by_type"],
            catalog_gaps=self.analytics_base["catalog_gaps"],
        )
