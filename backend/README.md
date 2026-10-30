# Smart Library backend

All backend source, tests, documentation, memory, dependencies, and reference files live in this directory. Run the commands below from `backend/` unless explicitly starting from the repository root.

Phases 1-4 are complete: the FastAPI foundation, SQLite data layer, synthetic demo data, JWT authentication, identity/profile APIs, and catalog/search/availability/content APIs. The backend owns authoritative library data and deterministic transactions. AI and frontend modules consume HTTP APIs separately.

## Setup and run

Requires Python 3.11 or newer. From the repository root, enter `backend/` before setup:

```bash
cd backend
python3 --version
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
cp .env.example .env
python -m scripts.database init
python -m scripts.database seed
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

If `python3` is older than 3.11, use the path to a newer interpreter when creating the environment. On the current workstation `/opt/homebrew/bin/python3` is suitable. All later `python` commands above use the activated environment.

- Base URL: `http://localhost:8000/api/v1`
- Runtime Swagger UI: `http://localhost:8000/docs`
- Runtime OpenAPI: `http://localhost:8000/openapi.json`
- Draft of all planned APIs: [docs/openapi.draft.json](docs/openapi.draft.json)
- Contract details and proposed defaults: [docs/API_CONTRACT.md](docs/API_CONTRACT.md)

## Implemented behavior

Implemented APIs:

| Method | Path | Behavior |
| --- | --- | --- |
| GET | `/api/v1/health` | Process liveness, not database connectivity |
| POST | `/api/v1/auth/login` | JSON email/password login; returns access token, expiry, and user |
| GET | `/api/v1/auth/me` | Authenticated identity from the verified JWT and current database user |
| GET | `/api/v1/me/profile` | Authenticated user's courses and interests |
| GET | `/api/v1/resources` | Public metadata search, filters, pagination, and incremental synchronization |
| GET | `/api/v1/resources/{resource_id}` | Public resource metadata |
| GET | `/api/v1/resources/{resource_id}/availability` | Live copies, branch/shelf locations, and waitlist count |
| GET | `/api/v1/resources/{resource_id}/content` | Content according to public/authenticated/restricted access policy |
| POST | `/api/v1/resources` | Librarian-only metadata creation |
| PATCH | `/api/v1/resources/{resource_id}` | Librarian-only metadata update |

Ten of the fifteen planned operations now run. Circulation and analytics APIs remain draft contracts for later phases. The server does not automatically create tables, seed data, or reset anything on startup.

```bash
curl -i http://localhost:8000/api/v1/health
```

```json
{
  "status": "success",
  "data": {"service": "Smart Library Backend", "version": "0.1.0", "status": "ok"},
  "trace_id": "server-generated-uuid"
}
```

Unknown routes and resources use the shared error envelope:

```bash
curl -i http://localhost:8000/api/v1/missing
```

```json
{"status":"error","error":{"code":"not_found","message":"Not Found"},"trace_id":"server-generated-uuid"}
```

HTTP API responses include `X-Trace-ID`, matching the JSON trace. Client-supplied trace IDs are ignored and a fresh UUID is generated per request. Framework documentation uses its native HTML/JSON format. CORS preflight responses use protocol status/headers rather than API envelopes.

## Authentication and permissions

After initializing/seeding the database and starting the server:

```bash
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"student1@library.example","password":"DemoLibrary123!"}'
```

The success envelope's `data` contains `access_token`, `token_type: "bearer"`, `expires_in` (seconds), and the user including courses/interests. Copy the returned token into the authorization header:

```bash
curl http://localhost:8000/api/v1/auth/me \
  -H 'Authorization: Bearer <access_token>'
curl http://localhost:8000/api/v1/me/profile \
  -H 'Authorization: Bearer <access_token>'
```

The JSON login uses email/password, not an OAuth form. Email matching is case-insensitive and trims surrounding whitespace. Incorrect credentials return a generic 401; missing, malformed, expired, wrong-signature, or wrong-scope bearer tokens return 401 with `WWW-Authenticate: Bearer`. Login and personal responses, plus API errors, use `Cache-Control: no-store`.

Tokens use fixed HS256 signatures, default to 60 minutes, and require subject, expiry, issue/not-before times, issuer, audience, access-token type, and unique token ID. The user and current role are loaded from SQLite on each protected request; client-supplied user/role fields cannot grant access. A librarian role check and a strict ownership check are available for later route services. Librarians do not bypass personal-data ownership.

Without `LIBRARY_JWT_SECRET`, development creates a random signing key per app instance. Existing tokens become invalid after a restart/reload. To keep local sessions stable or run multiple workers, generate a random key and put it in your private `.env`:

```bash
python -c 'import secrets; print(secrets.token_urlsafe(48))'
```

Set `LIBRARY_JWT_SECRET` to that value. Production requires an explicitly configured key of at least 32 bytes and fails configuration if it is missing or too short. Never commit it. Configure `LIBRARY_JWT_ACCESS_TOKEN_MINUTES` (1-1440), `LIBRARY_JWT_ISSUER`, and `LIBRARY_JWT_AUDIENCE` as needed. Key rotation invalidates existing tokens; refresh/logout/revocation endpoints are outside the supplied scope. Token claims are signed, not encrypted, and contain no password or profile data.


## Catalog and content

```bash
curl 'http://localhost:8000/api/v1/resources?query=Python&type=book&level=beginner&limit=10&offset=0'
curl http://localhost:8000/api/v1/resources/res-002/availability
curl http://localhost:8000/api/v1/resources/res-001/content
```

Search matches a literal case-insensitive substring in resource ID, title, description, author names, or topics. SQL wildcard characters are treated literally. Empty/whitespace-only queries list the catalog. `type`, `level`, and `updated_since` filters combine with search. `limit` defaults to 20 (1-100); `offset` defaults to 0. `data.total` counts all matches before pagination. Results sort by `updated_at`, then `resource_id`.

Metadata and availability are public, including metadata about restricted resources. Content has a separate policy:

| Resource access level | Who can read content |
| --- | --- |
| `public` | Anonymous callers and authenticated users |
| `authenticated` | Any valid logged-in user |
| `restricted` | Librarians only in this prototype |

Supply `Authorization: Bearer <access_token>` for protected content. Invalid supplied credentials return 401 even on public content. Restricted access by an authenticated non-librarian returns 403. Missing records/content return 404. Content responses contain provenance and disable caching. This phase adds no per-resource entitlement grants or content ingestion API.

Librarian creation example:

```bash
curl -X POST http://localhost:8000/api/v1/resources \
  -H 'Authorization: Bearer <librarian_access_token>' \
  -H 'Content-Type: application/json' \
  -d '{"title":"Synthetic Python Guide","authors":["Demo Author"],"type":"book","description":"Demo catalog record","topics":["Python"],"level":"beginner","access_level":"public"}'
```

Creation returns HTTP 201 with a generated stable ID and timestamp. It creates metadata only: a new record has zero inventory and no content until those are provisioned separately. PATCH accepts a nonempty subset of metadata fields; explicit nulls, blank titles/authors/topics, unknown fields, and client-owned IDs/timestamps are rejected. Library writes recheck the current role inside the write transaction. Successful changes and their audit records commit together; permission denials and missing-target outcomes are recorded too.

For AI index refreshes, request `updated_since=<last_timestamp>` using an ISO 8601 timezone-aware timestamp. The filter is strictly newer-than; API create/update timestamps increase across the catalog even when fixture dates or a clock adjustment would otherwise move backward. Page with `offset`, overlap time windows, and deduplicate by resource ID when updating a live index; offset pagination is not a frozen snapshot. Recheck content authorization when retrieving or serving indexed excerpts, since access levels can change. Keyword search and synchronization are backend features; semantic ranking and RAG remain in the separate AI module.


## Configuration

Settings are loaded from `.env` and environment variables with the `LIBRARY_` prefix; environment variables take priority. See [.env.example](.env.example). `LIBRARY_DATABASE_URL` defaults to `sqlite:///./library.db`, relative to the working directory; only SQLite is supported in this prototype. CORS defaults allow local frontend ports 3000 and 5173; configure a JSON array of exact origins for other ports. Authorization and idempotency headers are allowed, and `X-Trace-ID` is exposed to browser clients.

## Database and demo data

```bash
python -m scripts.database init
python -m scripts.database seed
# Optional: choose a different fixed UTC reference date for a fresh seed.
python -m scripts.database --database-url sqlite:///./demo.db seed --as-of 2026-10-30
```

`init` creates missing tables and preserves existing data; it is not a migration command. `seed` writes one atomic synthetic dataset into an empty database. Repeating it after a successful seed changes nothing, including user edits. A nonempty database without the seed marker is rejected.

The default fixture date is **2026-10-30 UTC**. Due dates are relative to that fixed anchor, so demo scenarios are reproducible. To refresh scenarios later, use a new database and `--as-of YYYY-MM-DD`, or explicitly reset your local demo database first. Resetting removes all application data:

```bash
python -m scripts.database reset --confirm-reset
python -m scripts.database seed
```

Reset leaves empty tables and does not seed automatically. Demo seed/reset commands are disabled when `LIBRARY_ENVIRONMENT=production`. Local SQLite files are gitignored. Back up a database you want to keep before explicitly resetting it; no schema migration tooling is included yet.

Demo-only credentials:

| User ID | Email | Role | Password |
| --- | --- | --- | --- |
| `user-001` | `student1@library.example` | student | `DemoLibrary123!` |
| `user-002` | `student2@library.example` | student | `DemoLibrary123!` |
| `user-003` | `librarian@library.example` | librarian | `DemoLibrary123!` |

Passwords are stored as salted PBKDF2-HMAC-SHA256 hashes, never plaintext. All users, titles, authors, content, inventory, and circulation records are synthetic and clearly labeled as demo fixtures.

The seed contains 30 resources (six of each resource type), 33 holdings across three branches, six loans (three active, two overdue, one returned), six reservations (two active, two waitlisted, one cancelled, one fulfilled), 30 content records, three profiles, and one seed audit record. IDs and scenario fields are fixed; password salts deliberately differ across clean builds.

Useful fixtures: `res-001` has available copies across two branches; `res-002` has no free copies and a two-person waitlist; `res-009` is also unavailable; `loan-001` is an active loan owned by `user-001`; `loan-002` is overdue with a nonzero demo fine. See [database design](docs/DATABASE.md) for relationships, constraints, transaction behavior, and decisions reserved for later phases.

## Checks and API export

```bash
python -m pytest
python -m scripts.export_openapi
```

The export is a **draft contract** for all 15 operations. The running app documents the ten implemented health/authentication/profile/catalog operations; the separate export also describes future circulation and analytics routes. Exporting an operation does not implement it.

`requirements.lock.txt` records the exact versions used for Phase 1-4 verification. To recreate that environment, install it inside a virtual environment, then install this project with `python -m pip install -e . --no-deps`.

## Structure and integration

`app/api/routes` handles HTTP, `app/services` holds application workflows (authentication, catalog, and demo seeding), `app/repositories` holds database access, `app/models` holds SQLAlchemy entities, `app/schemas` defines contracts, `app/security` holds password/token/identity/permission helpers, and `app/core` holds configuration, database lifecycle, and HTTP infrastructure.

AI/frontend clients can authenticate, search/read metadata, fetch live availability, retrieve authorized content, and synchronize using stable IDs and `updated_since`. Forward the user's JWT in `Authorization: Bearer ...`. Later they will send `Idempotency-Key` for reservation/renewal requests. They must not import backend models or access its database. No LLM, frontend, or vector-store work is included here.

Progress and remaining policy decisions are maintained in [memory/README.md](memory/README.md). Next: Phase 5, loans, reservations, renewals, and idempotent transaction workflows.
