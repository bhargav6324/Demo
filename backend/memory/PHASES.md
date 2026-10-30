# Backend implementation phases

Current status: Phases 1-5 complete and verified on 2026-10-30; Phases 6-7 pending.

Scope: backend only. Each phase produces a reviewable result and updates the memory progress log. Tests are added alongside the relevant behavior; the final phase consolidates verification and handoff.

## Phase 1 - Foundation and shared API contract

**Goal:** Establish a runnable project and agree on interfaces before feature implementation.

Work:
- Inspect the workspace again and preserve any existing code or project conventions.
- Create the FastAPI project with routes, services, repositories, models, schemas, security, and tests directories.
- Set up dependencies, environment configuration, local CORS, and `.env.example`.
- Establish `/api/v1`, stable string IDs, UTC timestamps, response envelopes, trace IDs, and centralized error handling, including validation errors.
- Implement `GET /health` and outline request/response schemas for all required endpoints.
- Record unresolved circulation and access policies before implementing those behaviors.

Deliverables: runnable skeleton, initial README, configuration example, health route, and initial API contract.

Complete when: the service starts locally; health works; representative success/error responses follow the shared envelope; AI/frontend developers can review the contract.

## Phase 2 - Database, models, and reproducible seed data

**Goal:** Provide a reliable persistence layer and useful standalone demo fixtures.

Work:
- Model users, user profiles, resources, holdings, loans, reservations, and audit logs.
- Enable SQLite foreign keys and define uniqueness constraints, relationships, and indexes.
- Design persistent idempotency storage and inventory invariants for later circulation transactions.
- Add database initialization and an explicitly documented seed/reset workflow.
- Seed at least 30 resources spanning topics and types, multiple branches/shelves, available and unavailable resources, active and overdue loans, and reservation/waitlist examples.
- Seed two students and one librarian with courses/interests, hashed passwords, and stable IDs such as `res-001` and `user-001`.

Deliverables: models, repositories, initialization/seed commands, and deterministic fixture data.

Complete when: a clean database can be recreated reproducibly; relationships and constraints work; seed counts and scenarios meet the brief.

## Phase 3 - Authentication, authorization, and profile

**Goal:** Establish trusted user identity and reusable permissions.

Endpoints:
- `POST /auth/login`
- `GET /auth/me`
- `GET /me/profile`

Work:
- Implement secure password verification, JWT issuance/verification/expiry, and authenticated-user dependencies.
- Support student, faculty, researcher, and librarian roles.
- Implement reusable librarian and ownership checks; derive identity from the JWT.
- Ensure credentials and tokens are excluded from logs.

Deliverables: login, identity/profile APIs, permission utilities, and authentication tests.

Complete when: valid login succeeds; invalid login and expired/invalid tokens fail appropriately; users receive only their own profile; permission failures return consistent 401/403 responses.

## Phase 4 - Catalog, inventory, authorized content, and synchronization

**Goal:** Expose authoritative resource data for direct clients and AI tools.

Endpoints:
- `GET /resources?query=&limit=&offset=&type=&level=&updated_since=`
- `GET /resources/{resource_id}`
- `GET /resources/{resource_id}/availability`
- `GET /resources/{resource_id}/content`
- `POST /resources` (librarian)
- `PATCH /resources/{resource_id}` (librarian)

Work:
- Implement keyword/metadata search and required filters with `data.items` and `data.total`.
- Return accurate branch/shelf availability and waitlist counts.
- Apply the agreed public/authenticated/restricted content policy before returning excerpts/content.
- Validate catalog writes and maintain stable resource IDs and `updated_at` for incremental AI index refreshes.
- Log relevant actions and return clear empty-search/not-found outcomes.

Deliverables: catalog APIs, inventory/content access, synchronization support, and associated tests.

Complete when: search and filters work; missing resources are handled correctly; inventory matches fixtures; unauthorized content and student catalog writes are denied; create/update changes are discoverable using `updated_since`.

## Phase 5 - Loans, reservations, renewals, and transaction safety

**Goal:** Complete deterministic circulation workflows.

Endpoints:
- `GET /me/loans`
- `POST /loans/{loan_id}/renew`
- `POST /reservations`
- `GET /me/reservations`

Work:
- Expose current-user loans, due dates, renewability, fine amounts, and reservations.
- Enforce agreed renewal, duplicate-hold, queue, and inventory policies in services.
- Require `Idempotency-Key` on reservation and renewal writes; scope stored results to the user and operation and define payload-mismatch behavior.
- Use transactions so competing requests cannot overbook or produce negative available inventory.
- Audit successful and denied operations with trace IDs; maintain ownership checks.

Deliverables: complete reservation and renewal flows, persistent retry protection, and circulation tests.

Complete when: an eligible reservation and renewal succeed; ineligible renewals fail correctly; retries create no duplicate effects; competing requests preserve inventory; another user cannot read or modify someone else's circulation data; queue results are deterministic.

## Phase 6 - Librarian analytics and audit coverage

**Goal:** Provide the required operational summary and traceable backend activity.

Endpoint: `GET /analytics/summary` (librarian only).

Work:
- Return total resources, active loans, overdue loans, active reservations, and popular resources with loan counts.
- Define how overdue loans contribute to active-loan totals and how reservation statuses contribute to summary counts.
- Verify audit records capture action, actor where known, result, trace ID, and UTC time without credentials.
- Check that catalog, circulation, and analytics queries use appropriate indexes.

Deliverables: librarian summary, complete required backend audit coverage, and analytics/permission tests.

Complete when: librarian results match fixtures, student access is denied, and relevant operations have traceable audit records. Forecasting and AI analytics models remain outside this scope.

## Phase 7 - Independent verification, API export, and handoff

**Goal:** Deliver a backend that the other developers can consume without importing its code.

Work:
- Run the complete independent backend suite, including authentication expiry, filters, content permissions, catalog synchronization, idempotency, competing reservations, renewal failures, ownership isolation, analytics, and envelope/schema checks.
- Verify all 15 required endpoints and export the complete OpenAPI contract.
- Finalize README setup/run/test commands, seed procedure, demo credentials, sample requests, response/error structures, and integration instructions.
- Document user-token forwarding, `Idempotency-Key`, trace IDs, and `updated_since` behavior for AI/frontend clients.
- Rehearse a backend demo: login, search, availability, reserve or renew, privacy denial, librarian analytics, and a catalog update visible through synchronization.
- Record remaining limitations honestly; do not require running AI or frontend services to validate the backend.

Deliverables: tested backend, `openapi.yaml` or equivalent JSON export, README, `.env.example`, and handoff examples.

Complete when: all required routes and automated checks pass independently, setup is reproducible, and external clients can use the documented HTTP contract.

## Priority and dependencies

Order: Phase 1 -> Phase 2 -> Phase 3 -> Phase 4 -> Phase 5 -> Phase 6 -> Phase 7.

The first useful integrated backend milestone is completion of Phases 1-5: authentication, catalog, live availability, and complete circulation workflows. Analytics, final contract verification, and handoff remain required for completion. A time limit does not silently remove requirements.
