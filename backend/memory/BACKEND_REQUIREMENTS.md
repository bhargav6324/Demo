# Backend requirements and contract checklist

This is a working reference derived from the supplied brief. The full source is preserved in [sources/BACKEND_BRIEF.md](sources/BACKEND_BRIEF.md). Phases 1-5 foundation, health, SQLite data, synthetic fixtures, JWT login, identity/profile, catalog, and four circulation operations are implemented. Phase 6 now implements analytics and broader audit fallback; all 15 runtime operations exist, but Phase 6 has not been tested by the implementing agent and awaits the assigned tester.

## HTTP conventions

- Base URL: `http://localhost:8000/api/v1`.
- JSON field names use `snake_case`; primary IDs are stable strings; timestamps are ISO 8601 UTC.
- Success: `{"status":"success","data":{},"trace_id":"..."}`.
- Error: `{"status":"error","error":{"code":"...","message":"..."},"trace_id":"..."}`.
- Appropriate statuses: 200, 201, 400, 401, 403, 404, 409, 422, 500.
- Document request, success, and error contracts in OpenAPI for every endpoint.
- Reservation and renewal writes require `Idempotency-Key`.

## Endpoint inventory

All paths below are relative to `/api/v1`.

| Method | Path | Requirement |
| --- | --- | --- |
| POST | `/auth/login` | Email/password; return `access_token`, `token_type`, `expires_in`, and `user`. |
| GET | `/auth/me` | Verified user's `user_id`, `name`, `email`, and `role`. |
| GET | `/me/profile` | Verified user's courses and interests. |
| GET | `/resources` | `query`, `limit`, `offset`, `type`, `level`, `updated_since`; return `data.items`, `data.total`. |
| GET | `/resources/{resource_id}` | Full metadata. |
| GET | `/resources/{resource_id}/availability` | Current copies, locations, and waitlist. |
| GET | `/resources/{resource_id}/content` | Authorized content/excerpts for research/RAG. |
| POST | `/resources` | Librarian-only creation. |
| PATCH | `/resources/{resource_id}` | Librarian-only update. |
| GET | `/me/loans` | Current user's loans in `data.items`. |
| POST | `/loans/{loan_id}/renew` | Eligible current-user loan; idempotent transaction. |
| POST | `/reservations` | Body `{"resource_id":"res-001"}`; idempotent transaction. |
| GET | `/me/reservations` | Current user's reservations in `data.items`. |
| GET | `/analytics/summary` | Librarian-only summary. |
| GET | `/health` | Service health. |

There are 15 required method/path operations in this inventory.

## Canonical response models

| Model | Required fields |
| --- | --- |
| Resource | `resource_id`, `title`, `authors[]`, `type`, `description`, `topics[]`, `level`, `access_level`, `updated_at` |
| Availability | `resource_id`, `total_copies`, `available_copies`, `waitlist_count`, `locations[]` containing `branch`, `shelf`, `available_copies` |
| User | `user_id`, `name`, `email`, `role`, `courses[]`, `interests[]` |
| Loan | `loan_id`, `resource_id`, `resource_title`, `borrowed_at`, `due_at`, `renewable`, `fine_amount`, `status` |
| Reservation | `reservation_id`, `resource_id`, `status`, `queue_position` (integer or null) |
| Analytics | `total_resources`, `active_loans`, `overdue_loans`, `active_reservations`, `popular_resources[]` containing `resource_id`, `title`, `loan_count` |

Enums:
- Resource type: `book`, `journal`, `paper`, `ebook`, `dissertation`.
- Level: `beginner`, `intermediate`, `advanced`.
- Access: `public`, `authenticated`, `restricted`.
- User role: `student`, `faculty`, `researcher`, `librarian`.
- Loan status: `active`, `returned`, `overdue`.
- Reservation status: `active`, `waitlisted`, `cancelled`, `fulfilled`.

## Persistence and transactions

- Required tables: `users`, `user_profiles`, `resources`, `holdings`, `loans`, `reservations`, `audit_logs`.
- Add storage needed for reliable idempotency; the brief does not prescribe its schema.
- Use foreign keys, uniqueness constraints, indexes, and transaction boundaries for circulation writes.
- Available inventory must never become negative. Reservation allocation and queue behavior must be specified before implementation.
- Audit action, user, result, trace ID, and timestamp.
- Maintain stable IDs and resource update timestamps so AI clients can synchronize without code changes.

## Security

- Hash passwords securely; verify JWTs and expiry on protected requests.
- Personal operations derive identity from the token, never a client-supplied `user_id`.
- Enforce ownership independently on every account operation.
- Restrict analytics and catalog writes to librarians.
- Deny unauthorized resource content; AI callers receive no bypass.
- Never log passwords, credentials, or bearer tokens; keep production secrets out of source control.
- Configure basic local-development CORS.

## Seed and verification requirements

- At least 30 realistic resources; multiple topics/types and branches/shelves; available/unavailable inventory.
- Multiple active and overdue loans; reservations and waitlist examples.
- Two student users and one librarian; profiles with courses/interests; stable seed IDs.
- Reproducible, isolated tests that do not need AI or frontend services.
- Cover valid/invalid login; JWT expiry; search and metadata filters; resource-not-found; availability; authorized content; reservation success, duplicate handling, retry safety, and overbooking prevention; renewal success/failure; another-user denial; student/librarian analytics access; catalog create/update and incremental synchronization; response/error schemas.

## Final deliverables

FastAPI app; models; initialization/seeding; routes, repositories, and services; JWT and permissions; automated tests; OpenAPI export; `.env.example`; README with setup, run/test commands, demo credentials, requests, responses, and integration instructions.

Not part of this contract: frontend screens, LLM features, vector database management, AI tool adapters, or additional user registration, checkout/return, cancellation, fine payment, and policy administration endpoints. Additions require an explicit scope decision rather than being assumed.

## Phase 4 policy decisions

- Public metadata/search/availability. Public content can be read anonymously; authenticated content requires any valid user; restricted content requires a librarian. Invalid supplied content credentials fail 401. No individual entitlement grants are implemented.
- Added optional offset pagination without changing existing callers; total counts before pagination; ordering is updated_at/resource_id. Search is literal keyword/metadata matching, not semantic ranking.
- updated_since is strictly newer-than after UTC normalization. API catalog mutation timestamps increase across the catalog, including with fixed/future fixtures or clock rollback. Clients page, overlap sync windows, and deduplicate IDs under concurrent edits.
- Create/PATCH accept metadata only, with server-owned IDs/timestamps. New resources have zero holdings and no content until provisioned separately.
- Catalog writes and success audits share one transaction. Content access outcomes and authenticated catalog-write denials are audited. Full authentication/validation audit coverage remains Phase 6 work.

## Phase 5 policy decisions

- Personal lists include only caller-owned records and closed history; effective overdue status/renewability are computed from current UTC time, stored fines/counts, and other-user holds.
- Reserve allocates a deterministic free holding or joins FIFO. Existing waiters get priority; successful new attempts reconcile available inventory and normalize queue positions. One open reservation per user/resource. No automatic expiry or extra hold cap.
- Renewal adds 14 days, at most twice, only for the owner. Returned/overdue/target-fined loans and other-user open holds block renewal. Demo fine amounts are stored INR values without automatic accrual or payment.
- Idempotency keys are 1-128 printable non-whitespace ASCII characters, scoped per user plus operation/loan target. Completed result snapshots/statuses persist until explicit demo reset. Same-key retries get the original effect result and a fresh trace; conflicting reservation payloads return 409. Failed requests do not consume keys.
- Effects, results, and audits commit atomically under BEGIN IMMEDIATE with savepoints. Busy/locked circulation writes return retryable 409. No checkout, return, cancellation, automatic expiry, or inventory-management API was added.
- Full details: [circulation policy](../docs/CIRCULATION.md).

## Phase 6 decisions and validation status

- active_loans includes all outstanding active/overdue loans; overdue_loans is its subset stored overdue or due by current UTC. Returned history contributes only to popularity.
- active_reservations includes active and waitlisted records. Popularity returns up to five borrowed titles by all-time loan count descending and ID ascending.
- Librarian permission and aggregates share a read snapshot. No borrower details are exposed.
- Request fallback audits otherwise-unrecorded authentication/validation/read/analytics outcomes using trusted identity and allowlisted actions; no raw secrets or request text. Existing atomic business audits take priority. Fallback persistence is best effort with sanitized operational failure signals.
- New status index is additive and installed by explicit init; no workspace init/reset was run.
- User explicitly assigned testing elsewhere: implementation is delivered but Phase 6 is not verified. Testing steps: [PHASE6_TESTING.md](../docs/PHASE6_TESTING.md).
