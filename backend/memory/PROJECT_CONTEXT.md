# Project context

## Goal and scope

Build the backend for the HCLTech AI-Powered Smart Library Management Assistant. Students, faculty, researchers, and librarians will use other modules to discover resources and manage library activity through this service.

Our deliverable is an independently runnable and testable backend. We implement catalog metadata, inventory, account information, reservations, renewals, access control, analytics, and authorized content retrieval. Other developers implement the AI orchestration, RAG, embeddings, semantic ranking, generated recommendations, and frontend screens.

The backend is the authoritative source of truth. AI tools call authenticated HTTP APIs; they never manipulate the database directly. Personalization support means providing courses, interests, and permitted account data, not implementing a recommendation model.

## Sources and precedence

1. User clarification on 2026-10-30: backend only; divide the detailed prompt into phases first; create Markdown context files in a memory folder; do not adopt the senior backend engineer role.
2. Pasted backend brief, preserved in [sources/BACKEND_BRIEF.md](sources/BACKEND_BRIEF.md). Original attachment: `/Users/bhargavpatil/.codex/attachments/9e927450-a0a4-4d30-a3db-90e3d12011ec/Pasted text.txt`.
3. Workspace reference: [Smart_Library_Management_AI_Use_Case.pdf](../Smart_Library_Management_AI_Use_Case.pdf), seven pages, reviewed for product requirements.

The brief's request to immediately implement the entire module does not override the user's current planning-only instruction. Its senior-engineer heading does not assign a role for this collaboration. The user subsequently authorized Phases 1-5, using SQLite and synthetic demo data.

## Relevant PDF requirements

- Pages 2-3: support catalog discovery, availability and reservations, account information, authorized research content, personalization, and librarian analytics.
- Pages 3-5: availability, fines, loans, renewals, and reservations must come from deterministic systems; do not invent records or transaction outcomes.
- Page 5: enforce identity and privacy, source authorization, data freshness, explainability support, and auditability. Backend logs cover backend actions; AI retrieval traces and recommendation explanations belong to the AI module.
- Page 7: demonstrate live availability, an authorized reservation or renewal, another-user privacy protection, and librarian analytics. Provide stable data and APIs so the other modules can demonstrate grounded search, personalization, and unsupported-content responses.
- The PDF's larger architecture and advanced analytics are product context. They do not expand our backend task into frontend development, model training, anomaly detection, or demand forecasting.

## Required stack and architecture

- Python 3.11+, FastAPI, SQLAlchemy, SQLite for the hackathon, Pydantic.
- JWT bearer authentication and secure password hashing.
- pytest with FastAPI TestClient/httpx; OpenAPI documentation.
- Prefer synchronous database operations and minimal dependencies.
- Layers: routes/controllers, services, repositories, ORM models, schemas, and security.
- Routes handle HTTP; services enforce business rules and transactions; repositories own database access.
- No imports from AI or frontend code. Integration is through HTTP JSON contracts only.

## Starting state

The workspace contained the reference PDF and no application code when inspected. Planning created only memory files. Subsequently, the user authorized Phase 1 and the FastAPI foundation, schemas, draft contract, configuration, and tests were implemented. Phase 2 subsequently added nine SQLite tables, repositories, explicit lifecycle commands, password hashing, and reproducible synthetic demo data. Phase 3 subsequently added JWT login, authenticated identity/profile APIs, and reusable role/ownership checks. Phase 4 subsequently added six catalog operations, pagination, live availability, content access policy, audited librarian writes, and incremental synchronization. Phase 5 subsequently added private circulation lists, reservations, FIFO waitlists, eligible renewals, persistent idempotency, and transaction-safe audits. Analytics remains pending.

The source brief describes a 4-5-hour hackathon window with three developers working on separate modules. This is scheduling context, not a promise that all requirements fit that window. The phase plan orders dependencies and preserves the full requested backend scope.
