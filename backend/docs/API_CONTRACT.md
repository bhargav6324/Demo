# Backend API contract

Status: Phases 1-4 complete. Ten implemented operations cover health, login, identity/profile, and the six catalog operations. See [openapi.draft.json](openapi.draft.json) for all 15 operations; the five remaining circulation/analytics operations are documentation-only and never mounted in the runtime app. The draft reuses implemented routes.

## Shared conventions

- Base URL: `http://localhost:8000/api/v1`; JSON with `snake_case` fields.
- Success: `status: "success"`, typed `data`, and `trace_id`.
- Error: `status: "error"`, `error: {code, message}`, and `trace_id`.
- Errors include appropriate 400/401/403/404/405/409/422/500 status codes. Validation errors never echo raw values or secrets. Unexpected errors return a generic 500 message.
- Each request receives a server-generated UUID trace and `X-Trace-ID`. A retried operation gets a new request trace; persistent idempotency semantics will be specified in Phase 5.
- Primary IDs are nonempty, immutable strings, at most 128 characters, using letters, digits, underscores, and hyphens. IDs are server-generated for new catalog records; seed IDs remain stable.
- Datetimes require timezone information and normalize to UTC (`Z` or `+00:00`) on serialization. Timezone-free inputs are rejected.
- List responses use `data.items`; resource search also includes `data.total`, counting matches before offset/limit.
- Authentication uses bearer JWTs, implemented in Phase 3. Runtime identity/profile routes verify the token and load the current database user. Catalog writes and content access enforce their policies now; circulation/analytics enforcement will be added with those routes.
- Catalog writes and analytics are librarian-only. Personal data always derives identity from the verified token. There is no client-authorized `user_id` input.
- Reservation and renewal require a nonempty `Idempotency-Key` header, max 128 characters. Identity-scoped persistence and conflicting-payload behavior will be finalized before Phase 5.

## Implemented interface behavior and remaining proposals

Catalog and authentication contracts below are implemented. Reservation/renewal/fine workflow details remain proposals for Phase 5.

- Catalog metadata, search, and availability allow public reads. Public content permits anonymous reads; authenticated content requires any valid user; restricted content requires a librarian. Invalid supplied credentials return 401 even on public content. There is no per-resource entitlement table in this prototype.
- Search `limit` defaults to 20 (1-100); optional `offset` defaults to 0 (0-2147483647), a backward-compatible extension for paging. `query` matches a trimmed, literal case-insensitive substring across ID, title, description, individual author names, and topics. Whitespace-only queries list all matching records. SQL wildcard characters are escaped. Type/level filters combine with search; results sort by updated_at, then resource_id.
- `updated_since` requires an aware timestamp and uses a strictly newer-than boundary after UTC normalization. API metadata writes choose a timestamp strictly later than the current catalog maximum and at least the current clock, giving serialized mutations a monotonic sync order even with future fixtures or a clock rollback. Clients should page, overlap synchronization windows, and deduplicate by stable resource ID; offset pagination is not a snapshot under concurrent edits.
- Catalog create accepts title, authors, type, description, topics, level, and access level. Resource IDs and update timestamps are server-owned. These APIs do not provision holdings or content; newly created metadata has zero inventory and content retrieval returns 404 until separately provisioned.
- PATCH omits unchanged fields, rejects empty bodies/explicit nulls, and forbids unknown/server-owned fields. Nonempty text fields trim whitespace and reject blank values. Access-level changes apply to subsequent content requests.
- Login returns the canonical user including courses/interests. `/auth/me` returns identity fields; `/me/profile` returns courses/interests.
- Content returns resource_id, plain-text content, provenance source, and updated_at from resource_contents. Metadata responses do not include content. Missing resources/content return 404; access checks happen before reading protected excerpts. Content and availability responses disable caching.
- Renewal proposes returning the updated loan. Reservation creation returns the canonical reservation with HTTP 201. Queue positions start at 1; no queue position is represented by null.
- `fine_amount` is a nonnegative decimal serialized as a JSON string to preserve precision. Currency, calculation, and renewal restrictions remain unresolved.

## Audit and transaction behavior

- Catalog create/update recheck the librarian role within BEGIN IMMEDIATE. Metadata changes and successful audit entries commit atomically; an audit failure rolls back the change. Authenticated permission denials and missing write targets are audited before returning the error.
- Content success, access denial, and missing-resource/content outcomes are audited with actor (when known), action/result, trace ID, and UTC time. Raw credentials, query text, and excerpt bodies are not logged. Authentication failures rejected before the catalog service and request-validation failures are not separately audited yet; full audit coverage remains Phase 6 work.
- Auth dependencies close their read transaction before the route starts catalog writes or content audit writes, avoiding self-blocking SQLite read/write locks. Metadata listing/detail/availability are read-only and are not individually audited in this phase.

## Phase boundaries and unresolved policies

Phases 2-4 added storage, seeds, authentication, and catalog/content. Phase 5 adds circulation; Phase 6 adds analytics. The backend does not implement semantic ranking, RAG, recommendations, frontend screens, or AI tool adapters.

## Implemented authentication behavior

- Login accepts JSON `email`/`password` only, normalizes email, verifies the seeded PBKDF2 hashes, and returns the standard success envelope with `LoginData`. Unknown accounts still perform dummy password verification; invalid credentials share one generic 401 error.
- Access tokens expire after 60 minutes by default. Verification fixes the algorithm to HS256 and requires/validates `sub`, `exp`, `iat`, `nbf`, `iss`, `aud`, `type: access`, and `jti`. Tokens with no valid current database user fail authentication. No role is trusted from token claims.
- `/auth/me` returns `user_id`, name, email, and current role. `/me/profile` returns only the caller's courses and interests; a `user_id` query cannot select a different account. An absent optional profile yields empty arrays.
- Missing/invalid/expired credentials return the shared 401 envelope and `WWW-Authenticate: Bearer`. Authorization helpers return 403 when an authenticated caller lacks librarian role or ownership. Those helpers do not expose later-phase business routes.
- Auth success responses and API errors disable caching. Request validation and error logs do not echo passwords or tokens.
- Signing secrets are environment-managed. Development can use a random per-instance key; production requires an explicit key of at least 32 bytes. Issuer, audience, and token lifetime are configurable. See the README for persistent local configuration and reload behavior.

See [decisions and progress](../memory/DECISIONS_AND_PROGRESS.md) for renewal limits, hold allocation, waitlist advancement, any future expansion beyond librarian-only restricted content, fine policy, idempotency retention, concurrency, and analytics counting decisions. These must be documented before the affected business logic is built.

## Framework references

Infrastructure follows the official [FastAPI error-handler documentation](https://fastapi.tiangolo.com/tutorial/handling-errors/), [CORS documentation](https://fastapi.tiangolo.com/tutorial/cors/), and [environment settings documentation](https://fastapi.tiangolo.com/advanced/settings/). Authentication uses the [FastAPI JWT guidance](https://fastapi.tiangolo.com/tutorial/security/oauth2-jwt/) and [PyJWT verification API](https://pyjwt.readthedocs.io/en/stable/api.html).

Catalog query implementation follows SQLAlchemy's [literal substring escaping](https://docs.sqlalchemy.org/en/21/core/sqlelement.html) and SQLite [JSON value iteration](https://www.sqlite.org/json1.html) for author/topic arrays.
