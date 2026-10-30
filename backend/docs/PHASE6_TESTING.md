# Phase 6 tester handoff

Implementation is delivered; no Phase 6 automated tests, manual API requests, live-server checks, or runtime verification were performed by the implementing agent, as requested. Phase 5's previous 167 passing tests do not validate Phase 6. The existing expected-runtime-path list was updated but not executed. No new analytics test suite was added; validation belongs to the assigned tester.

## 1. Isolated setup

From the repository root, use Python >=3.11:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
export LIBRARY_ENVIRONMENT=test
export LIBRARY_DATABASE_URL="sqlite:///./phase6-tester-$(date -u +%Y%m%dT%H%M%SZ).db"
export LIBRARY_JWT_SECRET="$(python -c 'import secrets; print(secrets.token_urlsafe(48))')"
python -m scripts.database init
python -m scripts.database seed --as-of "$(date -u +%Y-%m-%d)"
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Use a fresh filename for each baseline. Keep these environment settings in the setup shell for later DB inspection. Explicit init installs missing metadata-defined indexes without dropping existing data; no column migration/reset is needed. Run fixture edits only against this disposable file, not development library.db. Current-UTC seeding makes the baseline predictable.

## 2. Authentication and baseline

In a second terminal, activate the same environment:

```bash
BASE=http://127.0.0.1:8000/api/v1
LIB_TOKEN=$(curl -fsS "$BASE/auth/login" -H 'Content-Type: application/json' \
  -d '{"email":"librarian@library.example","password":"DemoLibrary123!"}' \
  | python -c 'import json,sys; print(json.load(sys.stdin)["data"]["access_token"])')
STUDENT_TOKEN=$(curl -fsS "$BASE/auth/login" -H 'Content-Type: application/json' \
  -d '{"email":"student1@library.example","password":"DemoLibrary123!"}' \
  | python -c 'import json,sys; print(json.load(sys.stdin)["data"]["access_token"])')
curl -i "$BASE/analytics/summary" -H "Authorization: Bearer $LIB_TOKEN"
```

Expected: HTTP 200, success envelope, Cache-Control: no-store, and X-Trace-ID matching the body. No borrower identities are included.

| Field | Expected on fresh today-anchored seed |
| --- | --- |
| total_resources | 30 |
| active_loans | 5, including the two overdue loans |
| overdue_loans | 2 |
| active_reservations | 4: two active plus two waitlisted |
| popular_resources | res-001, res-002, res-003, res-004, res-005, in that order, each loan_count=1 and its current catalog title |

Popularity includes returned history, excludes never-borrowed titles, limits to five, and breaks count ties by ascending resource ID. The returned res-004 loan therefore contributes to popularity. Successful analytics access should audit as analytics.summary/success/user-003.

## 3. Permission checks

```bash
curl -i "$BASE/analytics/summary"
curl -i "$BASE/analytics/summary" -H 'Authorization: Bearer invalid-token'
curl -i "$BASE/analytics/summary" -H "Authorization: Bearer $STUDENT_TOKEN"
```

Expect 401 with Bearer challenge for missing/invalid credentials, and 403 for the student. Responses must use error envelopes and contain no summary data. Audit actor is null for unverified callers and user-001 for verified student denial. Repeat with faculty/researcher fixture roles; they must also be forbidden. Downgrade a librarian in the disposable DB and confirm the original token no longer grants access on the next request.

## 4. Current-time and returned-loan counting

In the original setup shell (after stopping the server if needed), edit only the isolated fixture:

```bash
python - <<'PY'
from datetime import timedelta
from app.core.config import Settings
from app.core.database import Database
from app.models import Loan
from app.models.base import utc_now
db = Database(Settings().database_url)
try:
    with db.write_session() as session:
        session.get(Loan, 'loan-001').due_at = utc_now() - timedelta(seconds=1)
finally:
    db.dispose()
PY
```

Restart against the same file. Expect active_loans=5 and overdue_loans=3 even while loan-001's stored status remains active. GET /me/loans should agree it is overdue. Then set this fixture loan to returned, set returned_at to current UTC, and restore its holding's available_copies by one. Expect active_loans=4, overdue_loans=2, and unchanged popularity. Also verify an explicitly stored overdue loan counts overdue even if its due date is moved into the future, matching circulation policy.

## 5. Reservation demand, popularity, and empty data

- On a fresh baseline, reserve res-011 as student1 with a new key: active_reservations becomes 5. Replay the key: no further increase.
- With a new key reserve unavailable res-002: the waitlisted hold makes active_reservations=6. Both allocated and waiting demand count.
- Cancel/fulfill a fixture reservation, clearing queue_position/allocated_holding_id and restoring any allocated copy: open demand decreases.
- Add another valid historical loan for a title in the disposable fixture: loan_count becomes 2 and that title ranks first. Renewing a loan must not increase borrowing count.
- On a separate fixture, retain users/profiles but remove idempotency, circulation, content, holdings, and resource rows in FK-safe order. Expect zero counts and popular_resources=[], not an error.

## 6. Audit coverage and privacy

Exercise valid/invalid login, missing/invalid token, analytics success/denial, catalog reads, content denial, personal circulation reads, reservations/replays/conflicts, and renewal success/denial. Trigger validation and unknown-route outcomes:

```bash
curl -i "$BASE/resources?limit=0"
curl -i "$BASE/not-a-real-route"
```

Inspect records from the original setup shell, using its isolated database environment:

```bash
python - <<'PY'
from sqlalchemy import select
from app.core.config import Settings
from app.core.database import Database
from app.models import AuditLog
db = Database(Settings().database_url)
try:
    with db.session() as session:
        for row in session.scalars(select(AuditLog).order_by(AuditLog.created_at.desc()).limit(40)):
            print(row.created_at.isoformat(), row.user_id, row.action, row.result, row.trace_id)
finally:
    db.dispose()
PY
```

Expect UTC time, trusted actor where verified, action, result, and matching response trace IDs. Unknown/invalid identities must not be inferred from submitted emails or unverified JWT claims. Validation failures use validation_error; unmatched routes use request.unknown/not_found. Passwords, bearer tokens, raw emails, raw paths/queries, request bodies, and excerpts must not appear in audit fields or sanitized operational errors.

Existing business audits take priority: the request fallback skips traces already recorded. FIFO promotions may legitimately produce several business records under one trace. Allow request-completion persistence to finish before inspection, polling briefly if needed. Health, docs/OpenAPI, and CORS preflight are excluded.

On the disposable DB only, simulate unavailable audit storage (for example temporarily rename audit_logs, then restore it). Analytics/read/auth responses should retain their original status and emit a sanitized audit_persistence_failed signal with only trace and exception type. Catalog/circulation business audit failures must still roll back their mutation. Completion audits are best effort; they are not a durable external queue and can be lost on abrupt process termination.

## 7. Indexes, contract, regression, and report

- After init, inspect PRAGMA index_list('reservations') for ix_reservations_status. Existing loan status/due and resource lookup indexes must remain. Repeated init must preserve data.
- Run the existing regression suite yourself: `python -m pytest`. Record the new result; the old 167-pass result applies only to Phase 5. Add analytics/audit tests as needed.
- Run `python -m scripts.export_openapi`; inspect all 15 implemented operations, analytics response fields, and bearer requirements in /docs and /openapi.json.
- Verify search/analytics reads do not alter circulation or inventory; only audit rows may increase.
- Report pass/fail, UTC seed date, versions, trace IDs, expected/actual values, and reproduction steps. Exclude tokens/secrets from reports.

Phase 6 remains pending tester verification. Phase 7 is still pending for final verification and handoff.
