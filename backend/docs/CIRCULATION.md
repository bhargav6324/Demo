# Circulation policy and API behavior

Phase 5 prototype defaults, selected to make the supplied backend contract deterministic. These are demo policies, not an imported university lending policy. All operations use the authenticated database user; clients cannot authorize operations by supplying a user ID.

## Endpoints

| Method | Path under /api/v1 | Result |
| --- | --- | --- |
| GET | /me/loans | All caller-owned loans, including returned history, due dates, effective status, fines, and renewability |
| GET | /me/reservations | All caller-owned reservations, including closed history |
| POST | /reservations | Allocate a copy or join the waitlist; HTTP 201 |
| POST | /loans/{loan_id}/renew | Renew an eligible caller-owned loan; HTTP 200 |

All responses use the shared envelope, a fresh per-request trace ID, and no-store caching. Successful mutations return `Idempotency-Replayed: false` on the initial effect and `true` on replay. Browser clients can read this header through CORS.

## Reservations and waitlists

- Request body is exactly `{"resource_id":"res-011"}`. All authenticated roles can reserve catalog resources. Resource access_level governs content retrieval; reservation does not grant access to protected digital content.
- Only one active/waitlisted reservation per user/resource is allowed. A different-key duplicate returns 409 `duplicate_reservation`; the original same-key retry replays instead.
- Active holds allocate one named holding copy immediately. Copy selection is deterministic by holding ID. A resource with no free copies (including no holdings) gets a waitlisted reservation.
- Existing waiters have priority over a new arrival. During a new successful reservation attempt, available copies first promote existing queue heads to active holds in queue order, then any remaining free copy may serve the new arrival.
- Queue order is FIFO through positions assigned under the write lock, with creation time/ID as tie-breakers. After promotions, remaining positions are normalized to 1..N. Waitlisted reservations allocate no inventory.
- This prototype has no automatic hold expiry, checkout/return, cancellation, or inventory-management endpoint. Those were not in the supplied API contract. If inventory is externally replenished, the next new reservation attempt reconciles that resource's queue; ordinary reads and idempotent replays do not promote or mutate it.
- There is no additional per-role/global hold cap or prohibition on reserving a title already borrowed. Adding those rules requires an explicit policy change. A reservation does not create a loan.

## Renewals and fines

- Renewal adds 14 days to the existing due date, at most twice per loan.
- Returned loans, stored-overdue loans, loans due at or before the current UTC time, and loans with a positive stored fine cannot renew.
- Another user's active/waitlisted reservation for the resource blocks renewal. The caller's own reservation and other users' cancelled/fulfilled reservations do not block it.
- Only the owner may renew; an authenticated non-owner receives 403, including librarians. Missing loans receive 404. Ineligible owner requests return 409 `renewal_not_allowed` without changing the due date or renewal count.
- GET /me/loans uses the same eligibility rules as the write. An open loan whose date has elapsed is reported as overdue without needing a background job; returned status takes priority. Reads do not rewrite persisted statuses.
- Demo fine amounts are denominated in INR and stored as integer hundredths, serialized as decimal strings through fine_amount. Existing stored values are authoritative. No daily accrual, grace-period calculation, fine payment, or automatic fine clearing is implemented. A fine on another loan does not block renewal of an otherwise eligible loan.
- Renew accepts no parameters. The body may be absent, null, or `{}`; extra fields such as user_id/days are rejected. New due dates cannot be chosen by the client.

## Idempotency

- Reservation and renewal require an Idempotency-Key of 1-128 printable non-whitespace ASCII characters.
- Keys are scoped to the verified user plus operation/target path: `POST /reservations` or `POST /loans/{loan_id}/renew`.
- A SHA-256 fingerprint of canonical validated request data distinguishes conflicting requests. JSON field order does not affect the fingerprint. Renewal's canonical payload is empty.
- A successful effect, its serialized result/status, and audit entry commit in the same SQLite transaction. Retrying after a timeout, even through a new app instance, returns the original data/status without another allocation or extension.
- Replay returns the original result snapshot, not refreshed queue/renewability state. Use GET endpoints for current state. Every replay gets a new response trace ID and a replay audit entry.
- Reusing a committed key with a different reservation resource returns 409 `idempotency_conflict`. Different users or different loan target paths can independently use the same key.
- Only successful results are stored. Authorization, validation, eligibility, duplicate, and missing-target failures do not consume a key; after correcting the condition a retry can succeed. Authentication and loan ownership are checked before any replay.
- Results are retained indefinitely in this prototype, until an explicit demo reset. Clients must generate a new key for each intended new effect. There is no silent expiry or automated pruning that could turn an old retry into a new transaction.

## Transactions and audits

BEGIN IMMEDIATE serializes writers before business reads. Copy allocation is additionally conditional on available_copies > 0; database constraints prevent negative inventory. SQLite waits up to five seconds for locks. A remaining SQLITE_BUSY/LOCKED condition returns 409 `database_busy`; retry using the same key. Other database failures remain sanitized 500s.

A savepoint groups allocations, FIFO promotions, loan updates, promotion audits, and idempotency insertion. Expected business failures roll back this group while allowing the outer transaction to record the failure. An unexpected persistence/audit failure rolls back the entire transaction. Successful effects, replays, known denials/conflicts, and FIFO promotions are audited with trace IDs, without tokens/passwords/request bodies. Authentication/validation failures rejected before the service and lock failures that prevent audit storage remain part of Phase 6's audit-coverage review.

The transaction strategy follows SQLite's official [transaction documentation](https://www.sqlite.org/lang_transaction.html) and [result-code documentation](https://www.sqlite.org/rescode.html). Tests exercise competing reservations and renewals against temporary file-backed databases, not a shared single in-memory connection.
