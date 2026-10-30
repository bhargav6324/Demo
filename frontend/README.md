# Smart Library — Frontend

React + Vite + TypeScript web app for the AI-powered Smart Library assistant. It runs **fully standalone in mock mode** and switches to the real Backend and AI services by configuration only.

- **Stack:** React 18, Vite 5, TypeScript, Tailwind CSS 3, React Router 6, Axios, Recharts, Vitest + React Testing Library
- **Node:** 18+ (developed on Node 24)

## Quick start

```bash
cd frontend
npm install
npm run dev          # mock mode → http://127.0.0.1:5173
```

Sign in with a demo account (one-click buttons on the login page):

| Role | Email | Password |
|---|---|---|
| Student | `student@demo.edu` | `demo123` |
| Researcher | `researcher@demo.edu` | `demo123` |
| Faculty | `faculty@demo.edu` | `demo123` |
| Librarian | `librarian@demo.edu` | `demo123` |
| Second student (privacy checks) | `student2@demo.edu` | `demo123` |

These are synthetic demo credentials. Only the librarian sees **Analytics**.

## Commands

| Command | What it does |
|---|---|
| `npm run dev` | Dev server in **mock** mode (no backend/AI needed) |
| `npm run dev:real` | Dev server in **real** mode (uses `.env.real`) |
| `npm test` | Run all tests once (always against mock clients) |
| `npm run test:watch` | Tests in watch mode |
| `npm run typecheck` | TypeScript check |
| `npm run build` | Typecheck + production build to `dist/` |
| `npm run preview` | Serve the production build on :4173 |

## Configuration

All settings are `VITE_*` variables (see `.env.example`). Put local overrides in `.env.local` or `.env.real.local`; never put secrets here, since everything is shipped to the browser.

| Variable | Default | Purpose |
|---|---|---|
| `VITE_API_MODE` | `mock` | `mock` = in-browser fake services; `real` = HTTP clients |
| `VITE_BACKEND_URL` | `http://localhost:8000` | Backend & DB service (`/api/v1` is appended) |
| `VITE_AI_URL` | `http://localhost:8001` | AI orchestration service (`/api/v1` is appended) |
| `VITE_MOCK_LATENCY_MS` | `350` | Simulated delay in mock mode so loading states show |
| `VITE_SHOW_DEMO_LOGINS` | on in mock, off in real | Show one-click demo logins |

### Mock mode

- No backend or AI process is required. All data is seeded in the browser with stable IDs (`user-001`…`user-005`, `res-001`…`res-016`).
- The mock behaves like the agreed contract:
  - It enforces auth (401) and roles (403 for analytics).
  - Restricted resources return 404 to students.
  - Reservations update holdings, and duplicates return 409.
  - Renewals are allowed once; overdue loans or titles another member is waiting for return 409.
  - Fines are derived from overdue days.
- Chat returns structured responses for every outcome (`answered`, `not_found`, `refused`, `needs_confirmation`). Proposed actions run only on `confirmAction`, and a second confirm returns 409.
- Mock state resets on page reload. A **Mock data** badge is always visible in this mode.

Chat prompts that show each outcome in mock mode:

| Prompt | Outcome |
|---|---|
| "Recommend a beginner Python book" | `answered` with recommendation cards and citations |
| "Reserve a statistics book for me" | `needs_confirmation` → reservation |
| "Can I renew my loans?" | `needs_confirmation` → renewal |
| "Show me another user's loans" | `refused` |
| "Do you have books on quantum basket weaving?" | `not_found` |

### Real mode

```bash
npm run dev:real     # or: VITE_API_MODE=real npm run dev
```

The browser calls the services directly from `http://127.0.0.1:5173` (or `http://localhost:5173`):

- **Backend:** `VITE_BACKEND_URL/api/v1/...` for auth, catalog, circulation and analytics.
- **AI service:** `VITE_AI_URL/api/v1/chat/...` and `/health`.

**Both services must allow CORS from that origin**, including the `Authorization` and `Content-Type` headers. No page changes are needed to switch modes.

## Screens

| Route | Screen | Clients used |
|---|---|---|
| `/login` | Email/password sign-in, demo logins, redirect back to the requested page | `AuthClient` |
| `/dashboard` | Welcome + search, borrowing overview, picks for your interests, assistant entry, quick actions | `CatalogClient`, `CirculationClient` |
| `/discover` | Search, type & level filters (in the URL), resource cards with live availability badges | `CatalogClient` |
| `/discover/:id` | Metadata, branch/shelf availability, excerpt / online link, reserve with confirmation | `CatalogClient`, `CirculationClient` |
| `/assistant` | Chat with conversation memory, recommendation cards, citations, confirm-before-action, not-found/refusal states, retry | `ChatClient` |
| `/my-library` | Loans (due dates, fines, renewability, renew), reservations (status, queue position) | `CirculationClient`, `CatalogClient` |
| `/analytics` | Librarian only: stat cards, loan-health meter, most-borrowed chart, demand table | `AnalyticsClient` |

## Architecture

```
src/
  types/models.ts        Shared contract types (snake_case, mirrors the API)
  api/
    interfaces.ts        AuthClient, CatalogClient, CirculationClient, AnalyticsClient, ChatClient
    index.ts             createApiClients(): picks mock or HTTP from VITE_API_MODE
    http/clients.ts      Axios implementations: envelope unwrap, error mapping, bearer token
    mock/                Seed fixtures, in-memory MockDb, mock implementations
  app/                   ApiProvider (useApi), AuthProvider (useAuth), route guards, toasts, nav
  components/            Reusable UI (ResourceCard, AvailabilityBadge, ChatMessage, LoanCard, …)
  hooks/                 useAsync, useReservation, useRenewal, useMediaQuery
  pages/                 One file per screen
  test/                  Vitest + RTL suites (mock clients only)
```

Rules the code follows:
- **API access:** pages and components never call URLs or import fixtures. Everything goes through `useApi()` and the five client interfaces.
- **The token** is held in memory only (never in localStorage or URLs), so a refresh means signing in again.
- **Session handling:**
  - Any 401 clears the session and returns to `/login`.
  - Signing in as someone else remounts the whole app shell and clears notifications.
- **Authorization:** role-based navigation is for convenience only; the backend remains the authority.
- **Displayed data:** availability, fines and renewability are shown exactly as the API returns them, never calculated in the browser.
- **Chat:** behaviour depends only on the `outcome` and `proposed_action` fields, never on the assistant's text. A success message is shown only from the `confirmAction` result.
- **State-changing actions** need a confirmation dialog, are guarded against double submission (one request per action), and reload the affected data afterwards.

## Contract assumptions to confirm with Backend/AI

The brief leaves these shapes open. Each is marked `ASSUMED` in `src/types/models.ts`, and parsing lives only in `src/api/http/clients.ts`, so a change touches those files only.

| Item | Assumed shape |
|---|---|
| `POST /auth/login` → `data` | `{ access_token, token_type: "bearer", user: User }` |
| `GET /resources/{id}/content` → `data` | `{ resource_id, format: "text" \| "link", body, url }` |
| `popular_resources[]` | `{ resource_id, title, borrow_count, reservation_count }` |
| `POST /chat/actions/confirm` → `data` | `{ action_id, action_type, transaction_status: "completed" \| "rejected" \| "failed", transaction_id, message }` |
| `GET /health` (AI) → `data` | `{ status: "ok" \| "degraded" \| "down" }` |
| Enums | `type`: book, ebook, journal, paper, dissertation, digital_resource · `level`: beginner/intermediate/advanced · `access_level`: open/members/restricted · loan `status`: active/overdue/returned · reservation `status`: queued/ready/fulfilled/cancelled |
| `fine_amount` | number, in rupees (INR) |
| Roles | `student`, `researcher`, `faculty`, `librarian` |
| `POST /reservations` body | `{ resource_id }`; `POST /loans/{id}/renew` body `{}` |

## Testing

```bash
npm test
```

All suites use the mock clients, plus a fake Axios adapter for the HTTP clients, so no network is used. Coverage includes:
- **Login:** student, librarian and invalid credentials.
- **Routing and roles:** protected-route redirects and blocked analytics access.
- **Discovery:** catalog search, filters, empty results, availability and branch/shelf details.
- **Circulation:** reservation confirmation and conflicts, loan renewal and refusal.
- **Assistant:** chat submission, recommendation cards with citations, the `needs_confirmation` / `not_found` / `refused` flows, and send failure with retry.
- **Failures and duplicates:** network failure with retry, and duplicate-action prevention.
- **HTTP clients:** envelope unwrapping, error mapping, 401 handling, timeouts, and no leaked raw error bodies.

## Known limitations

- **Never run against live services.** Real mode is covered only by fake-adapter tests; it needs the services running plus CORS.
- **Renewal reasons:** the contract has no denial reason on `Loan`, so the UI shows "Not eligible for renewal" without a reason. Server messages appear when a renewal is refused.
- **Reservation titles** are resolved through `GET /resources/{id}`, one call per title, because `Reservation` has no title field.
- **Sessions end on page refresh,** which the brief allows. There's no token refresh.
- **Catalog editing** for librarians is not implemented (optional in the brief).
- **No pagination:** search shows the first 24 results along with the total count.
