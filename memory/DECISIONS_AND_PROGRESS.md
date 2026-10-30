# Decisions and progress

Last updated: 2026-10-30

## Confirmed decisions

- Work only on the backend. AI and frontend are separately developed modules.
- Use the detailed pasted brief as the backend requirements source and the workspace PDF as product reference.
- Preserve context in `memory/` as Markdown.
- The user authorized Phases 1 and 2. Both are complete; Phases 3-7 remain pending.
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
| Catalog access | Which metadata/availability routes allow anonymous access? | Phase 1/4 |
| Restricted content | Which roles or explicit entitlements permit access, and where are entitlements stored? | Phase 4 |
| Content persistence | Resolved in Phase 2: resource_contents stores text, provenance, and UTC update time; services will authorize access. | Phase 4 access enforcement |
| JWT settings | Expiry, signing configuration, and demo secret provisioning. | Phase 3 |
| Reservations | Phase 2: active holds allocate one named copy; one open hold per user/resource. Expiry, eligibility, and limits remain open. | Phase 5 |
| Waitlists | FIFO ordering, queue positions, and advancement behavior within the supported operations. | Phase 5 |
| Renewals | Extension duration, maximum count, overdue/fine restrictions, and effect of another user's hold. | Phase 5 |
| Fines | Seeded or computed amounts, currency, rate, and grace period; no payment endpoint is requested. | Phase 5 |
| Idempotency | Persistence, retention, user/operation scope, conflicting payloads, and replay behavior. | Phase 2/5 |
| Inventory concurrency | Phase 2: BEGIN IMMEDIATE, conditional allocation, and competing last-copy test complete. Full API workflow/retry handling remains open. | Phase 5 |
| Synchronization | Inclusive/exclusive `updated_since` boundary and consistent timestamp precision. | Phase 4 |
| Analytics | Overdue/active overlap, included reservation statuses, and popular-title ordering. | Phase 6 |

## Progress

| Item | Status |
| --- | --- |
| Read pasted backend brief | Complete |
| Read seven-page reference PDF | Complete |
| Create persistent Markdown memory and backend phase plan | Complete |
| Phase 1 - Foundation and shared API contract | Complete |
| Phase 2 - Database and seed data | Complete |
| Phase 3 - Authentication and profile | Pending |
| Phase 4 - Catalog, inventory, content, synchronization | Pending |
| Phase 5 - Circulation and transaction safety | Pending |
| Phase 6 - Analytics and audit coverage | Pending |
| Phase 7 - Verification and handoff | Pending |

## Next action

Next is Phase 3: JWT login, authenticated identity/profile routes, and reusable permission checks. The workspace library.db is initialized and seeded; do not reset it automatically. Runtime business endpoints are still unimplemented. Preserve the foundation, schema, fixtures, and draft API contract when continuing.

## Repository

- User-specified GitHub repository: https://github.com/bhargav6324/Demo
- Local remote: `origin`; branch: `main`.
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
