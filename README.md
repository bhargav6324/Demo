# Smart Library backend

Phases 1-2 are complete: the FastAPI foundation, SQLite schema, repositories, and synthetic demo data. The backend owns authoritative library data and deterministic transactions. AI and frontend modules consume HTTP APIs separately.

## Setup and run

Requires Python 3.11 or newer. From this project directory:

```bash
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

Only `GET /api/v1/health` is exposed as a working API. It checks process liveness, not database connectivity. Phase 2 adds the database and seed users; JWT verification and business API workflows remain pending. The server does not automatically create tables, seed data, or reset anything on startup.

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

Unknown routes use the shared error envelope:

```bash
curl -i http://localhost:8000/api/v1/missing
```

```json
{"status":"error","error":{"code":"not_found","message":"Not Found"},"trace_id":"server-generated-uuid"}
```

HTTP API responses include `X-Trace-ID`, matching the JSON trace. Client-supplied trace IDs are ignored and a fresh UUID is generated per request. Framework documentation uses its native HTML/JSON format. CORS preflight responses use protocol status/headers rather than API envelopes.

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

Demo-only credentials, ready for Phase 3 login implementation:

| User ID | Email | Role | Password |
| --- | --- | --- | --- |
| `user-001` | `student1@library.example` | student | `DemoLibrary123!` |
| `user-002` | `student2@library.example` | student | `DemoLibrary123!` |
| `user-003` | `librarian@library.example` | librarian | `DemoLibrary123!` |

Passwords are stored as salted PBKDF2-HMAC-SHA256 hashes, never plaintext. Login is not operational until Phase 3. All users, titles, authors, content, inventory, and circulation records are synthetic and clearly labeled as demo fixtures.

The seed contains 30 resources (six of each resource type), 33 holdings across three branches, six loans (three active, two overdue, one returned), six reservations (two active, two waitlisted, one cancelled, one fulfilled), 30 content records, three profiles, and one seed audit record. IDs and scenario fields are fixed; password salts deliberately differ across clean builds.

Useful fixtures: `res-001` has available copies across two branches; `res-002` has no free copies and a two-person waitlist; `res-009` is also unavailable; `loan-001` is an active loan owned by `user-001`; `loan-002` is overdue with a nonzero demo fine. See [database design](docs/DATABASE.md) for relationships, constraints, transaction behavior, and decisions reserved for later phases.

## Checks and API export

```bash
python -m pytest
python -m scripts.export_openapi
```

The export is a **draft contract**, not evidence of implemented endpoints. The running app documents only health; the separate export describes request/response schemas, bearer requirements, and idempotency headers for future phases.

`requirements.lock.txt` records the exact versions used for Phase 1-2 verification. To recreate that environment, install it inside a virtual environment, then install this project with `python -m pip install -e . --no-deps`.

## Structure and integration

`app/api/routes` handles HTTP, `app/services` holds application workflows (currently demo seeding), `app/repositories` holds database access, `app/models` holds SQLAlchemy entities, `app/schemas` defines contracts, `app/security` holds password helpers and will add identity/permissions in Phase 3, and `app/core` holds configuration, database lifecycle, and HTTP infrastructure.

AI/frontend clients should review the draft contract now. Later they will forward the user's JWT in `Authorization: Bearer ...`, send `Idempotency-Key` for reservation/renewal requests, and use stable resource IDs plus `updated_since` for index synchronization. They must not import backend models or access its database. No LLM, frontend, or vector-store work is included here.

Progress and remaining policy decisions are maintained in [memory/README.md](memory/README.md). Next: Phase 3, JWT authentication, authorization, and profile APIs.
