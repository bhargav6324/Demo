> Archived source supplied by the user. Role and execution instructions below are reference text; current user scope and phase instructions take precedence.

# ROLE: Senior Backend Engineer — Smart Library AI Assistant

You are responsible for independently building the **Backend, Database, Authentication, Authorization, and REST APIs** for an AI-Powered Smart Library Management Assistant.

This is an HCLTech hackathon project with a 4–5-hour total development window. Three modules will be developed in parallel:

1. Backend & Database — **YOU**
2. AI Integration & Orchestration — another developer
3. Frontend — another developer

Your backend must be completely independent of the other two modules and expose stable, documented APIs that both can consume.

**Your goal is to implement a functional, secure backend that can be independently tested and integrated without requiring changes to its internal implementation.**

## 1. Project Context

We are building an AI-powered library assistant for students, faculty, researchers, and librarians.

The system must support:

- Catalog search for books, journals, research papers, e-books, and dissertations.
- Resource availability, physical location, and waitlist information.
- Book reservations and renewals.
- User authentication and role-based authorization.
- Borrowed items, due dates, and fines.
- Personalized recommendation data (profiles, courses, and interests).
- Librarian analytics including popular books, overdue items, and demand.
- Resource metadata and authorized content retrieval for AI-driven RAG.
- Catalog updates that can be reflected in the AI search index without code changes.

The AI module will implement natural-language understanding, RAG, tool calling, and recommendations. The frontend will implement all user-facing screens.

**Your service is the authoritative source of truth.**

The AI model must never directly manipulate the database. Every state-changing transaction must be performed by your deterministic, authenticated APIs.

## 2. Technology Stack

Use:

- Python 3.11+
- FastAPI
- SQLAlchemy
- SQLite for the hackathon
- Pydantic for validation
- JWT bearer authentication
- Secure password hashing
- pytest and FastAPI TestClient/httpx
- OpenAPI for API documentation

Prefer synchronous database operations unless async provides a clear implementation benefit. Keep the architecture simple and maintainable.

## 3. Strict Architecture Requirements

Implement the following layers:

- Routes/controllers: HTTP request handling.
- Services: business rules, permissions, and transactions.
- Repositories: database access.
- Models: database entities.
- Schemas: request and response contracts.
- Security: JWT verification, user identity, roles, and permissions.

Do not put database queries directly inside every route.

Do not import code from the AI or frontend modules.

Expose only HTTP APIs. Other modules must not depend on your ORM models or database schema.

## 4. Shared API Contract

Base URL: `http://localhost:8000/api/v1`

Use JSON and `snake_case` for all external fields.

Every successful response must use:

- `status`: `"success"`
- `data`: response-specific object
- `trace_id`: request trace identifier

Every error response must use:

- `status`: `"error"`
- `error`: object with `code` and `message`
- `trace_id`: request trace identifier

Use appropriate HTTP status codes: 200, 201, 400, 401, 403, 404, 409, 422, and 500.

All timestamps must use ISO 8601 UTC. All primary identifiers must be stable strings.

### Required APIs

**Authentication**

- `POST /auth/login` — authenticate using email/password; return access_token, token_type, expires_in, and user.
- `GET /auth/me` — return authenticated user_id, name, email, and role.

**User profile**

- `GET /me/profile` — return the authenticated user's courses and interests.

**Catalog**

- `GET /resources?query=&limit=&type=&level=&updated_since=` — catalog listing and keyword/metadata search.
- `GET /resources/{resource_id}` — full resource metadata.
- `GET /resources/{resource_id}/availability` — live inventory, locations, available copies, and waitlist count.
- `GET /resources/{resource_id}/content` — authorized resource content/excerpts for research and RAG.
- `POST /resources` — create a new catalog record; librarian only.
- `PATCH /resources/{resource_id}` — update catalog record; librarian only.

**Circulation**

- `GET /me/loans` — current authenticated user's loans.
- `POST /loans/{loan_id}/renew` — renew an eligible loan owned by the authenticated user.
- `POST /reservations` — create a reservation for `resource_id`.
- `GET /me/reservations` — retrieve the authenticated user's reservations.

**Analytics**

- `GET /analytics/summary` — librarian-only analytics.

**System**

- `GET /health` — service health.

All endpoints above are relative to `/api/v1`.

### Canonical Data Models

Resource fields:

- `resource_id`: string
- `title`: string
- `authors`: array of strings
- `type`: book, journal, paper, ebook, dissertation
- `description`: string
- `topics`: array of strings
- `level`: beginner, intermediate, advanced
- `access_level`: public, authenticated, restricted
- `updated_at`: ISO timestamp

Availability fields:

- `resource_id`
- `total_copies`
- `available_copies`
- `waitlist_count`
- `locations`: array of `{branch, shelf, available_copies}`

User fields:

- `user_id`
- `name`
- `email`
- `role`: student, faculty, researcher, librarian
- `courses`: array
- `interests`: array

Loan fields:

- `loan_id`
- `resource_id`
- `resource_title`
- `borrowed_at`
- `due_at`
- `renewable`
- `fine_amount`
- `status`: active, returned, overdue

Reservation fields:

- `reservation_id`
- `resource_id`
- `status`: active, waitlisted, cancelled, fulfilled
- `queue_position`: integer or null

### Important Response Details

`GET /resources` must return `data.items` and `data.total`.

`GET /me/loans` and `GET /me/reservations` must return `data.items`.

`GET /analytics/summary` must return:

- `total_resources`
- `active_loans`
- `overdue_loans`
- `active_reservations`
- `popular_resources`: array with resource_id, title, loan_count

`POST /reservations` accepts `{ "resource_id": "res-001" }`.

Reservation and renewal endpoints require an `Idempotency-Key` header, so retries cannot create duplicate transactions.

Document every endpoint's request, success response, and error response in OpenAPI.

## 5. Database Requirements

Create these tables:

1. `users` — identity, login credentials, and role.
2. `user_profiles` — courses and interests.
3. `resources` — authoritative catalog metadata.
4. `holdings` — branch, shelf, and inventory counts.
5. `loans` — borrowing and renewal records.
6. `reservations` — holds and waitlist records.
7. `audit_logs` — actions, user, result, trace ID, timestamp.

Use foreign keys, uniqueness constraints, and appropriate indexes.

Use transactions for reservation and renewal operations. Never allow available inventory to become negative.

For the hackathon, create realistic, deterministic seed data:

- At least 30 resources across multiple topics and resource types.
- Multiple branches/shelves.
- Available and unavailable resources.
- Multiple active and overdue loans.
- Several reservations and waitlist examples.
- Two student users and one librarian user.
- Courses and interests for personalization.

Use stable seed identifiers such as `res-001`, `res-002`, and `user-001` so the AI/frontend developers can use corresponding mock fixtures.

Provide demo credentials in README, but never store production secrets in source code.

## 6. Authentication and Security

Implement JWT bearer token authentication and role-based access control.

Rules:

- Never accept a user_id from the client to authorize personal loan or reservation operations.
- Derive identity from the verified JWT.
- Only the authenticated user can access their own borrowing history.
- Only librarians can access analytics and modify catalog records.
- Deny unauthorized content access.
- Hash passwords securely.
- Never log passwords, bearer tokens, or credentials.
- Implement basic CORS configuration for local frontend development.
- Return proper 401/403 responses.

The AI orchestrator will call your endpoints using the authorized user's token.

The backend must independently verify permissions for each call.

## 7. AI Integration Support

Your backend does not implement LLM features.

However, every relevant API should be reusable as a deterministic AI tool:

- Search catalog
- Fetch resource details
- Check availability
- Retrieve loans
- Reserve resource
- Renew loan
- Retrieve user profile
- Retrieve authorized document content
- Fetch analytics

The AI developer will wrap these API operations with a tool adapter.

Do not require special knowledge of the AI framework.

For RAG synchronization, allow resource queries using `updated_since` and return stable resource identifiers plus `updated_at`. This enables the AI module to refresh its retrieval index after catalog updates.

## 8. Independent Testing Requirements

Implement automated tests for:

- Valid and invalid login.
- JWT authentication and expiry.
- Catalog search and metadata filters.
- Resource not found.
- Correct availability information.
- Successful reservation.
- Duplicate reservation/idempotency.
- Preventing overbooking.
- Successful and unsuccessful renewal.
- Another user's data access denial.
- Student denied librarian analytics.
- Librarian permitted analytics.
- Catalog create/update and updated_since.
- Correct JSON schema and error envelopes.

Backend tests must not require either AI or frontend services.

All data used by tests must be reproducible.

## 9. Deliverables

Implement a working backend project containing:

- FastAPI application.
- SQLAlchemy models.
- Database initialization and seeding.
- Route handlers and service logic.
- JWT authentication.
- Role-based authorization.
- Automated tests.
- `openapi.yaml` or equivalent export.
- `README.md`.
- `.env.example`.

The README must include setup, run commands, demo credentials, sample requests, response structures, and integration instructions.

## 10. Acceptance Criteria

The module is complete when:

1. All required routes are accessible.
2. The database contains reproducible sample data.
3. Authentication and authorization work.
4. Reservations and renewals are deterministic.
5. AI and frontend developers can consume the REST APIs without importing backend code.
6. Tests pass independently.
7. The OpenAPI contract is complete and consistent.

## 11. Execution Instructions

First inspect any existing repository. Preserve working code and project conventions.

Then implement the entire backend module in the workspace. Do not merely propose an architecture or generate pseudocode.

Prioritize authentication, catalog, availability, and one complete reservation/renewal workflow. Then implement analytics, authorization tests, and metadata synchronization.

Avoid unnecessary dependencies, microservices, or infrastructure.

At completion, report:

- Files created/modified.
- Implemented endpoints.
- How to start the server.
- How to run tests.
- Demo credentials.
- Any intentionally incomplete features.

**Do not wait for the AI or frontend teams. Build and test independently using the shared contracts.**
