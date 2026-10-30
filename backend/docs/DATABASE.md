# Phase 2 database design

SQLite is the local hackathon store, accessed through SQLAlchemy synchronous sessions. These tables and repositories are internal implementation details, not shared integration contracts. Phases 3-5 use this data for authentication/profiles, catalog/search/availability/content, and deterministic circulation workflows. AI/frontend modules consume HTTP APIs; analytics remains pending.

## Tables and relationships

| Table | Primary key | Purpose and references |
| --- | --- | --- |
| `users` | `user_id` | Normalized unique email, name, password hash, role, created time |
| `user_profiles` | `user_id` | One profile per user; JSON courses/interests |
| `resources` | `resource_id` | Canonical metadata, JSON authors/topics, access level, updated time |
| `resource_contents` | `resource_id` | One plain-text excerpt/content record with provenance and timestamp per resource |
| `holdings` | `holding_id` | Resource, branch/shelf, total/available copies |
| `loans` | `loan_id` | User, resource, matching holding, borrowed/due/return dates, status, renewals, fine |
| `reservations` | `reservation_id` | User/resource, status, queue position, allocated holding for active holds |
| `audit_logs` | `audit_id` | Optional known user, action/result, trace ID, timestamp; no raw credentials or request bodies |
| `idempotency_records` | `idempotency_id` | User/operation/key, request fingerprint, success status, JSON result, created time |

Explicit ORM relationships connect users to profiles/loans/reservations and resources to holdings/content. Foreign keys connect all other associations. Primary IDs are stable strings, with UUID defaults for future records and fixed readable IDs for fixtures.

## Database-enforced invariants

- Foreign-key enforcement is enabled on every connection. Referenced users, resources, and holdings cannot simply be deleted while dependent records remain.
- Emails are unique and lowercase. Roles, resource types/levels/access levels, and circulation statuses have CHECK constraints.
- Holdings are unique per resource/branch/shelf. Copy counts are nonnegative, and available cannot exceed total.
- A loan's holding must belong to its resource, enforced through a composite foreign key.
- Due dates cannot precede borrowing. Returned status requires a valid return time; open loans cannot carry one. Renewal counts and fines cannot be negative.
- A user can have at most one open reservation per resource. Multiple historical cancelled/fulfilled records are allowed.
- Waitlisted reservations have a positive unique queue position per resource and no allocated holding. Active reservations have a matching allocated holding and no queue position. Closed reservations have neither.
- Idempotency records are unique per user, operation (including target path), and key. Completed statuses must be successful HTTP statuses; fingerprint storage has SHA-256-length constraints.
- Indexes support user/status loan lookups, overdue dates, resource/status reservation lookups, catalog type/level and update time, holdings, and audit traces/times.

Cross-row inventory balance cannot be enforced by a simple CHECK: every decrement and corresponding loan/hold must be committed together by the circulation service. The seed satisfies `total = available + open loans + active allocated holds` for each holding. Schema constraints alone are not a complete circulation implementation.

## Sessions and transaction behavior

`Database.session()` provides a session without automatically committing; closing an uncommitted session rolls back changes. Repositories query or flush but never commit.

`Database.write_session()` starts `BEGIN IMMEDIATE` before the first read, commits on success, and rolls back on failure. This serializes SQLite writers, avoiding stale read-then-write allocation decisions. `HoldingRepository.try_allocate()` additionally decrements only if an available copy exists. Two competing last-copy allocations are tested against a file-backed database.

All connections enable foreign keys and a five-second busy timeout. Ordinary transactions use explicit `BEGIN DEFERRED`, avoiding differences in legacy sqlite3 transaction behavior across Python versions. In-memory tests use a single pooled connection; concurrent allocation tests deliberately use a temporary file-backed database.

The service factory owns the engine and disposes it at shutdown, but does not create schemas or seed automatically. Explicit commands own those operations. Health remains a liveness check, not a database readiness check. Phase 5 maps busy/locked circulation writes to retryable 409s and implements persistent replay; clients retry using the same key. Complete authentication/validation audit coverage remains Phase 6 work.

## Storage decisions made in Phase 2

- Authorized content has a separate `resource_contents` table and provenance field. Data access is internal; the Phase 4 content API authorizes public content anonymously, authenticated content for logged-in users, and restricted content for librarians. There are no per-resource entitlement grants.
- An active reservation allocates one copy at a named holding. Waitlisted reservations allocate none. This assumption is recorded now because the schema and fixtures need it; FIFO promotion on new reservation attempts, eligibility, and limits are documented in docs/CIRCULATION.md. No automatic expiry is implemented.
- Fine amounts use integer hundredths internally (`fine_amount_minor`), avoiding floating-point storage. The read property returns a Decimal for the existing API contract. Seeded fine values are stored demo INR amounts; they do not accrue automatically or implement a payment policy.
- Persistent idempotency storage holds completed success data, not JWTs or credentials. Phase 5 stores it in the same transaction as the effect, compares canonical SHA-256 request fingerprints, and creates a fresh trace for each replay. Keys are user/operation-target scoped and retained until explicit demo reset; failures do not consume keys.
- Resource metadata ORM updates refresh `updated_at`; mutable JSON lists track in-place changes. Future content-update services must also refresh the parent resource timestamp when content needs reindexing. Bulk SQL writes do not bypass this requirement.
- Fixtures use a fixed default UTC anchor of 2026-10-30, optionally changed by `seed --as-of YYYY-MM-DD`. Password hashes use random salts, so those bytes differ between clean seeds while IDs and scenario fields remain reproducible.
- All catalog data and content are synthetic. Digital-library copy counts represent simulated licensed seats for the demo. No external catalog API or content download is required.

## Initialization and reset

Run commands from the backend directory using its virtual environment:

```bash
python -m scripts.database init
python -m scripts.database seed
```

Creation is idempotent, not a schema migration. The seed marker `audit_logs.audit_id = seed-v1` makes subsequent seed runs a no-op; it does not repair manually edited/deleted fixtures. An unmarked nonempty database is rejected to protect existing records.

For an isolated database or a different scenario date:

```bash
python -m scripts.database --database-url sqlite:///./isolated-demo.db seed --as-of 2026-11-01
```

For an intentionally disposable local database:

```bash
python -m scripts.database reset --confirm-reset
python -m scripts.database seed
```

Reset drops/recreates the application's nine known tables and does not seed automatically. It requires the explicit flag and is disabled, along with demo seeding, in production configuration. No actual reset of the workspace demo database was needed for Phase 2 verification; reset tests use temporary files. Versioned migrations will be needed before preserving real data through schema evolution.

## Verification references

Connection and transaction handling follow the official [SQLAlchemy SQLite documentation](https://docs.sqlalchemy.org/en/21/dialects/sqlite.html) and [session transaction documentation](https://docs.sqlalchemy.org/en/21/orm/session_transaction.html). The password helper uses PBKDF2-HMAC-SHA256 with 600,000 iterations and random salts, following the work factor listed in the [OWASP password storage guidance](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html).

## Phase 4 catalog usage

- Search uses parameter-bound literal substring predicates, including JSON-array element matching for authors/topics. It counts before offset/limit and sorts by updated_at/resource_id.
- Catalog create/update and successful audit writes share a single immediate transaction. Denied librarian operations are audited without modifying metadata.
- API mutation timestamps are later than the current catalog maximum or system clock, whichever is greater. This preserves incremental synchronization across fixture dates and clock changes. Raw database writes/content imports must preserve parent-resource timestamp freshness themselves.
- Availability reads holdings and waitlisted reservation counts in one read transaction. Creating a resource does not invent holdings or content; empty inventory is represented by zero totals and an empty locations array.
- Content reads authorize before fetching text, then audit the outcome after the read transaction closes. Current-user dependencies also close their identity read transactions before routes begin write transactions. This prevents a request's own open reader from blocking its audit/catalog commit in SQLite.
- No schema change, migration, or workspace reset was needed in Phase 4.

## Phase 5 circulation usage

- Circulation services acquire the writer lock before identity/ownership/eligibility checks and idempotency lookup. Their nested savepoint covers all effect changes, queue promotions, promotion audits, and the result snapshot; expected business failures roll it back while the outer transaction can persist a failure audit. Unexpected persistence failures roll back everything.
- Same-key retries replay without new allocation or extension. Distinct concurrent requests preserve copy counts, queue-position uniqueness, and the two-renewal cap.
- Existing waiters are promoted before new arrivals if inventory has been externally replenished; normal reads and replays never reconcile/mutate queues. Active holds account for allocated copies; waitlists do not.
- Loan status/renewability use current UTC time on reads without rewriting stored statuses. Fine amounts remain stored integers. Phase 6 analytics must account for elapsed due dates, not rely exclusively on stored status strings.
- There was no schema migration or workspace database reset in Phase 5. See [circulation policy](CIRCULATION.md) for exact defaults, replay behavior, and supported lifecycle boundaries.
