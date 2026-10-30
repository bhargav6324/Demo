# Initial backend API contract

Status: Phase 1 draft, ready for AI/frontend review. See [openapi.draft.json](openapi.draft.json) for all 15 method/path operations. Only `GET /api/v1/health` runs in the current service. Business routes in `app/api/contract.py` are documentation-only and never mounted in `app.main`; they cannot perform transactions or authenticate users.

## Shared conventions

- Base URL: `http://localhost:8000/api/v1`; JSON with `snake_case` fields.
- Success: `status: "success"`, typed `data`, and `trace_id`.
- Error: `status: "error"`, `error: {code, message}`, and `trace_id`.
- Errors include appropriate 400/401/403/404/405/409/422/500 status codes. Validation errors never echo raw values or secrets. Unexpected errors return a generic 500 message.
- Each request receives a server-generated UUID trace and `X-Trace-ID`. A retried operation gets a new request trace; persistent idempotency semantics will be specified in Phase 5.
- Primary IDs are nonempty, immutable strings, at most 128 characters, using letters, digits, underscores, and hyphens. IDs are server-generated for new catalog records; seed IDs remain stable.
- Datetimes require timezone information and normalize to UTC (`Z` or `+00:00`) on serialization. Timezone-free inputs are rejected.
- List responses use `data.items`; resource search also includes `data.total`, counting matches before the limit.
- Authentication uses bearer JWTs in later phases. JWT verification and role enforcement are not implemented by this draft.
- Catalog writes and analytics are librarian-only. Personal data always derives identity from the verified token. There is no client-authorized `user_id` input.
- Reservation and renewal require a nonempty `Idempotency-Key` header, max 128 characters. Identity-scoped persistence and conflicting-payload behavior will be finalized before Phase 5.

## Proposed interface defaults

These choices make the draft concrete for review; they are not claims of already implemented policy.

- Catalog metadata, keyword search, and availability allow public reads. Authorized content retrieval requires authentication in this initial draft; restricted-content entitlements remain undecided. Revisit public content retrieval in Phase 4 if required.
- Search `limit` defaults to 20, allowed range 1-100. `query` is optional; `type` and `level` use the brief's enums. There is no offset/cursor parameter in the supplied contract.
- `updated_since` accepts an aware timestamp; the draft proposes a strictly newer-than boundary. Clients should overlap synchronization windows and deduplicate by stable resource ID to avoid timestamp-boundary omissions; final consistency rules belong to Phase 4.
- Catalog create accepts title, authors, type, description, topics, level, and access level. Resource IDs and update timestamps are server-owned. Holdings mutation is not added to this metadata API in Phase 1.
- PATCH omits unchanged fields, rejects an empty body or explicit nulls, and forbids unknown fields and server-owned fields.
- Login returns the canonical user including courses/interests. `/auth/me` returns identity fields; `/me/profile` returns courses/interests.
- Content response proposes `resource_id`, plain-text `content`, provenance `source`, and `updated_at`. Content storage and entitlement models will be chosen later.
- Renewal proposes returning the updated loan. Reservation creation returns the canonical reservation with HTTP 201. Queue positions start at 1; no queue position is represented by null.
- `fine_amount` is a nonnegative decimal serialized as a JSON string to preserve precision. Currency, calculation, and renewal restrictions remain unresolved.

## Phase boundaries and unresolved policies

Phase 2 adds storage and seeds; Phase 3 adds authentication; Phase 4 adds catalog/content; Phase 5 adds circulation; Phase 6 adds analytics. The backend does not implement semantic ranking, RAG, recommendations, frontend screens, or AI tool adapters.

See [decisions and progress](../memory/DECISIONS_AND_PROGRESS.md) for renewal limits, hold allocation, waitlist advancement, content entitlements, fine policy, idempotency retention, concurrency, and analytics counting decisions. These must be documented before the affected business logic is built.

## Framework references

Infrastructure follows the official [FastAPI error-handler documentation](https://fastapi.tiangolo.com/tutorial/handling-errors/), [CORS documentation](https://fastapi.tiangolo.com/tutorial/cors/), and [environment settings documentation](https://fastapi.tiangolo.com/advanced/settings/).
