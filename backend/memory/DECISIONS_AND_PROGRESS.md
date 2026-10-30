# Decisions and progress

Last updated: 2026-10-30

## Confirmed decisions

- Work only on the backend. AI and frontend are separately developed modules.
- Use the detailed pasted brief as the backend requirements source and the workspace PDF as product reference.
- Preserve context in `memory/` as Markdown.
- The user authorized Phases 1-4. All four are complete; Phases 5-7 remain pending.
- Phase 4 access policy: metadata/search/availability public; public content anonymous; authenticated content any valid user; restricted content librarians only. No per-resource entitlement grants.
- Optional offset pagination is added as a compatible catalog extension. Search is literal, with SQL wildcards escaped; result order is updated_at/resource_id.
- Catalog writes are audited atomically and use monotonically increasing update timestamps; updated_since is a strict UTC greater-than filter.
- Authentication identity reads close before catalog write/audit transactions, preventing self-blocking SQLite locks.
- Phase 3 JWT policy: fixed HS256; default lifetime 60 minutes; required issuer, audience, subject, time claims, access type, and token ID. Current identity/role come from the database, not client claims.
- JWT keys are environment-managed (at least 32 bytes); development may generate a private per-instance key, while production requires an explicit key. Reloads invalidate tokens when a generated development key is used.
- Phase 2 uses SQLite and locally generated synthetic fixtures; no external catalog API is required.
- Active holds allocate a named holding copy; waitlists allocate none. This is now reflected in the schema and fixtures.
- Content is stored in a separate resource_contents table with provenance; API access checks remain Phase 4 work.
- Completed idempotency results have persistent, user/operation/key-scoped storage; replay and retention behavior remain Phase 5 work.
- Write units of work take BEGIN IMMEDIATE before reading, with conditional copy decrements and database inventory checks.
- Fine storage uses integer hundredths; currency and calculation remain undecided.
- Seed anchor defaults to 2026-10-30 UTC; --as-of permits a different explicit date for a fresh seed. IDs/scenarios are reproducible; password salts are intentionally random.
- Do not adopt the source brief's senior backend engineer role instruction.
- Follow the requested FastAPI/SQLAlchemy/SQLite stack and layered architecture.
- External modules consume HTTP APIs and forward the authenticated user's token; no shared ORM/database access.

## Policies to resolve during implementation planning

These are unspecified details, not reasons to block the current phase breakdown. Record an agreed rule or clearly labeled proposed default before implementing affected behavior.

| Topic | Decision needed | Resolve by |
| --- | --- | --- |
| Catalog access | Resolved in Phase 4: metadata, search, and availability are public. | Complete |
| Restricted content | Resolved in Phase 4: librarians only; authenticated content allows all logged-in roles; public content allows anonymous reads. No per-resource grants. | Complete |
| Content persistence | Resolved in Phases 2/4: resource_contents stores text/provenance/time, and CatalogService enforces access before retrieval. | Complete |
| JWT settings | Resolved in Phase 3: 60-minute configurable expiry, fixed HS256, issuer/audience checks, and explicit production/per-instance development keys. | Complete |
| Reservations | Phase 2: active holds allocate one named copy; one open hold per user/resource. Expiry, eligibility, and limits remain open. | Phase 5 |
| Waitlists | FIFO ordering, queue positions, and advancement behavior within the supported operations. | Phase 5 |
| Renewals | Extension duration, maximum count, overdue/fine restrictions, and effect of another user's hold. | Phase 5 |
| Fines | Seeded or computed amounts, currency, rate, and grace period; no payment endpoint is requested. | Phase 5 |
| Idempotency | Persistence, retention, user/operation scope, conflicting payloads, and replay behavior. | Phase 2/5 |
| Inventory concurrency | Phase 2: BEGIN IMMEDIATE, conditional allocation, and competing last-copy test complete. Full API workflow/retry handling remains open. | Phase 5 |
| Synchronization | Resolved in Phase 4: strict greater-than, UTC microsecond precision, monotonically increasing API mutation timestamps, and offset paging; overlap/deduplicate during live sync. | Complete |
| Analytics | Overdue/active overlap, included reservation statuses, and popular-title ordering. | Phase 6 |

## Progress

| Item | Status |
| --- | --- |
| Read pasted backend brief | Complete |
| Read seven-page reference PDF | Complete |
| Create persistent Markdown memory and backend phase plan | Complete |
| Phase 1 - Foundation and shared API contract | Complete |
| Phase 2 - Database and seed data | Complete |
| Phase 3 - Authentication and profile | Complete |
| Phase 4 - Catalog, inventory, content, synchronization | Complete |
| Phase 5 - Circulation and transaction safety | Pending |
| Phase 6 - Analytics and audit coverage | Pending |
| Phase 7 - Verification and handoff | Pending |

## Next action

Next is Phase 5: loans, reservations, renewals, and persistent idempotent transaction workflows. Resolve renewal limits/duration, fines/currency, waitlist promotion/expiry, and idempotency replay/retention rules before implementing them. The workspace library.db remains initialized and seeded; do not reset it automatically. Ten runtime operations now cover health, auth/profile, and catalog. Preserve their contracts and tests.

## Repository

- User-specified GitHub repository: https://github.com/bhargav6324/Demo
- Local remote: `origin`; branch: `main`.
- Backend module root: `backend/`. All backend application files, dependencies, tests, docs, memory, synthetic fixture generators, and the reference PDF belong inside it. Repository-root README links to backend setup; other modules may use sibling directories.
- Run setup, server, database, tests, and API export commands from backend/.
- Git history is based on the repository's existing initial commit. The project README replaces the initial `# Demo` placeholder.
- Publish application code, tests, documentation, memory, synthetic fixture generators, and the supplied reference PDF. Keep `.venv`, local SQLite files, caches, build output, and private `.env` files excluded through `.gitignore`.
- The GitHub connector is authenticated as a different account with read-only access to this repository; local Git is used for the requested push.

## Future phase log format

For each completed phase, record date, changed files, decisions made, checks and outcomes, unresolved issues, and the next action. Do not mark planned work as complete.

## Phase 1 completion log - 2026-10-30

Implemented:
- FastAPI factory and `GET /api/v1/health`; `/docs` and `/openapi.json` describe the actual runtime.
- Layer directories: API routes, services, repositories, models, schemas, security, and core.
- Environment settings, `.env.example`, explicit local CORS, packaging, virtual environment, and exact dependency snapshot.
- Typed success/error envelopes, server-generated per-request trace UUIDs and `X-Trace-ID`, sanitized validation and unexpected errors, HTTP exception handling.
- Stable ID and UTC timestamp schema conventions.
- Typed request/response schemas and separate `docs/openapi.draft.json` covering all 15 planned operations; future route stubs are never mounted on the running application.
- README, `docs/API_CONTRACT.md`, reproducible export command, and foundation tests.

Proposed contract defaults (documented for review, not implemented business policy): public metadata/availability, authenticated content, search limit 20 (1-100), strictly-newer `updated_since`, server-owned IDs/timestamps, nonempty/non-null PATCH, updated-loan renewal response, decimal fine strings, and content provenance fields. Restricted entitlements, currency, circulation rules, concurrency, and idempotency persistence remain open.

Verification:
- `.venv/bin/python -m pytest`: 17 passed. One upstream Starlette deprecation warning about its httpx TestClient adapter; no test failures.
- `.venv/bin/python -m pip check`: no broken requirements.
- `.venv/bin/python -m scripts.export_openapi`: draft exported; tests check export/schema consistency and exactly 15 operations.
- Actual Uvicorn startup and HTTP GET on `127.0.0.1:18000`: health returned 200, correct JSON, and matching trace header. Temporary server stopped afterward.
- Verified with Python 3.14.7 on macOS arm64. Project declares Python >=3.11; Python 3.11 itself was not available for a separate test run.

Environment notes:
- Default `/usr/bin/python3` is 3.9.6; use `/opt/homebrew/bin/python3` to create the environment, then `.venv/bin/python`. The apparent `~/.local/bin/python3.11` entry was unusable.
- Dependency download and localhost bind required sandbox escalation; both completed successfully.
- No demo credentials, database, or real authentication exist yet. No AI or frontend code was added.

## Phase 2 completion log - 2026-10-30

Implemented:
- Nine SQLAlchemy tables: users, user_profiles, resources, holdings, loans, reservations, audit_logs, resource_contents, idempotency_records.
- Foreign keys, matching resource/holding constraints, enum/count/date/status checks, unique normalized emails, unique open holds and queue slots, and lookup indexes.
- Engine/session lifecycle, UTC-aware timestamp round trips, tracked metadata updates, explicit write transactions, and repository primitives without implicit commits.
- Salted PBKDF2-HMAC-SHA256 password helpers with 600,000 iterations; no JWT/login yet.
- Explicit `python -m scripts.database init`, `seed`, and guarded `reset --confirm-reset`; demo seed/reset disabled in production configuration.
- Local library.db: 3 users/profiles, 30 resources/content records, 33 holdings across 3 branches, 6 loans (3 active, 2 overdue, 1 returned), 6 reservations (2 active, 2 waitlisted, 1 cancelled, 1 fulfilled), 1 seed audit record, 0 idempotency records.
- Stable seed IDs, fixed scenario anchor, no-op seed reruns, protection for unmarked nonempty databases, and synthetic provenance labels.
- README demo credentials, database documentation, and database tests. No schema migration tool or business API implementation was added.

Verification:
- Full suite: 44 tests passed, including the original 17 foundation tests. One existing upstream Starlette/httpx adapter deprecation warning remains.
- File-backed competing allocation: exactly one writer claims the last free copy; no negative inventory.
- All seeded holdings balance against open loans and allocated active holds.
- Fresh-database fixture snapshots match apart from intentionally random password hashes.
- Workspace init/seed and a second no-op seed completed; selected fixtures, password verification, row counts, and PRAGMA foreign_key_check passed.
- Reset and production command guards tested only against temporary databases; workspace data was preserved.

Demo users use the reserved library.example domain; credentials are documented in the project README. library.db is ignored by Git and can be recreated from source. Phase 5 still needs complete reservation/renewal services, idempotency fingerprint comparison/replay, policy decisions, and API-level concurrency checks. Phase 3 is next.

## Phase 3 completion log - 2026-10-30

Implemented:
- `POST /api/v1/auth/login`, `GET /api/v1/auth/me`, and `GET /api/v1/me/profile`, using the standard typed success/error envelopes and trace IDs.
- Case/whitespace-normalized email login, PBKDF2 password verification, generic invalid-credential failures, and dummy verification for unknown users.
- PyJWT dependency and fixed-HS256 token issuance/verification; required sub/exp/iat/nbf/iss/aud/type/jti claims; invalid, expired, unsigned, wrong-signature, malformed, wrong-algorithm, and wrong-scope tokens rejected with 401 and Bearer challenge.
- Current-user dependency reloads the database user and role; no role/profile data is trusted from token claims.
- Reusable librarian and strict owner checks return 403. No implicit librarian bypass for another patron's private data. Test-only routes exercise the helpers without prematurely exposing later-phase endpoints.
- All four roles supported; profile queries derive user identity solely from the verified token. Missing optional profiles yield empty arrays.
- Configurable expiry/issuer/audience and SecretStr signing keys; per-instance random development keys, explicit production keys >=32 bytes, and sanitized configuration errors.
- No-store headers on auth/personal responses and API errors; credentials/tokens excluded from error bodies and application logs.
- Updated README examples, environment example, dependency snapshot, memory, and draft OpenAPI export. Implemented auth routes are reused in the full draft instead of duplicated stubs.

Verification:
- Full independent suite: 81 passed (37 added authentication cases plus 44 existing cases). One existing upstream Starlette/httpx TestClient deprecation warning remains.
- Tests cover role reload after changes, ignored client role claims, cross-user profile selection attempts, ownership denial including librarians, faculty/researcher login, unknown-user verification, required JWT claims, wrong issuer/audience/type, invalid/expired tokens, secrets in errors/logs, and production key configuration.
- Real Uvicorn HTTP smoke against the existing workspace seed: login, identity, profile, trace consistency, no-store header, and unauthenticated 401/Bearer challenge passed; temporary server stopped afterward.
- `python -m pip check`: no broken requirements. Draft export consistency is checked by the suite.
- Existing SQLite data was preserved; no reset or migration was required. No catalog/circulation/analytics, refresh/logout/revocation endpoint, AI, or frontend implementation was added.

Phase 4 is next.

## Phase 4 completion log - 2026-10-30

Implemented:
- Six runtime catalog operations: GET /resources, GET /resources/{id}, GET /resources/{id}/availability, GET /resources/{id}/content, POST /resources, PATCH /resources/{id}.
- Literal case-insensitive metadata search across ID/title/description/authors/topics, combined type/level/update-time filters, total-before-pagination, optional offset, and stable update-time/ID ordering. User wildcards are escaped and query values are parameter-bound.
- Live holdings/location counts and waitlisted-only queue totals, including empty inventory for new metadata records.
- Public/authenticated/librarian-restricted content policy, explicit 401/403/404 outcomes, invalid-credential rejection even on public content, provenance, no-store headers, and access-outcome audits.
- Librarian-only metadata create/PATCH, server-owned stable IDs/timestamps, nonempty/nonnull patch validation, current-role recheck in the write transaction, atomic successful audit/change commits, and denied/missing-target audit records.
- Strict updated_since boundary, timezone validation/normalization, and globally advancing API catalog mutation timestamps even when fixtures are in the future or the clock moves backward.
- Optional-current-user dependency with closed identity read sessions before catalog writes/audits; no lingering reader self-lock. Existing authentication tests continue to pass.
- Draft contract now reuses all ten implemented routes; five circulation/analytics operations remain documentation-only. Updated README, API/database documentation, and memory. No schema migration, reset, new dependency, content-ingestion API, or frontend/AI implementation.

Verification:
- Full independent suite: 123 passed (42 added catalog cases plus 81 existing cases). One pre-existing upstream Starlette/httpx TestClient deprecation warning remains.
- Covered pagination, metadata fields and combined filters, literal wildcard/injection-like input, invalid parameters, missing records, live availability updates, content access matrix, role denial/audit, create/update/sync, timestamp boundaries, access-level changes, current-role recheck, audit-failure rollback, optional-auth OpenAPI, and future-fixture monotonic timestamps.
- Real Uvicorn smoke against a temporary seeded SQLite file passed search, availability, content permissions, librarian create/PATCH, student denial, and incremental sync. Temporary server stopped and temporary database removed.
- Existing workspace data was read for search/availability checks only; no workspace catalog changes, schema changes, or reset.
- Dependency check passed; OpenAPI export consistency is covered by tests.

Phase 5 is next.

## Repository reorganization - 2026-10-30

User requested that all backend work live under backend/ to avoid conflicts with other contributors. Moved the module source/configuration/tests/docs/memory/reference PDF together, preserving relative links. Added a short root README linking to backend setup and kept module-specific ignore rules inside backend/. Local SQLite data moved with the module and remains ignored. The existing root virtual environment is local-only and ignored; fresh clones create their environment from backend/ using the documented commands.

The reorganization also includes completed Phase 3-4 work that had not yet been pushed after the Phase 1-2 commit. Application API contracts and phase status are unchanged.

Reorganization verification: all 123 tests passed when run from backend/; the draft OpenAPI export regenerated successfully; documentation links and source credential-pattern checks passed. Local database and environment/cache files remain excluded from version control.
