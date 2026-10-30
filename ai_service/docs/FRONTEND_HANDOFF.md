# Smart Library AI service: frontend integration handoff

Updated: 2026-10-30. This is for the frontend developer, or their coding assistant. It covers the AI chat API only. Login, catalog, loans, reservations pages and analytics talk to the backend as described in the backend team's `BACKEND_API_HANDOFF.md`.

**Good news:** the existing frontend (`frontend/src/api/http/clients.ts` and `frontend/src/types/models.ts`) already matches this contract. The two shapes it marked "ASSUMED" (confirm result and AI health) are now implemented exactly as the frontend expects. **No code changes are needed, only configuration.**

---

## 1. Connection details

| Service | Origin (no `/api/v1`) | Runs on |
|---|---|---|
| AI service (chat) | `http://100.114.163.7:8002` | Santosh's PC, via Tailscale |
| Backend | `http://100.83.115.82:8001` | Bhargav's Mac, via Tailscale |

Put these in `frontend/.env.real.local` and restart `npm run dev:real`:

```env
VITE_API_MODE=real
VITE_BACKEND_URL=http://100.83.115.82:8001
VITE_AI_URL=http://100.114.163.7:8002
```

The frontend appends `/api/v1` itself (`config.apiPrefix`), so leave it out of these URLs.

**Before testing:**
- **Tailscale:** the computer running the browser must be signed in to the team's Tailscale network. The browser calls both IPs directly.
- **AI service:** check `http://100.114.163.7:8002/api/v1/health`. It should return `"status": "ok"`.
- **Backend CORS:** the backend must allow your exact page origin, e.g. `http://localhost:5173` (Bhargav's `LIBRARY_CORS_ORIGINS`). The AI service already allows any origin, so it needs no CORS setup.

---

## 2. How the pieces talk

```
 Browser ── POST /auth/login, catalog, loans, analytics ──────────► Backend :8001
    │
    └──── POST /chat/messages, /chat/actions/confirm ──► AI :8002 ──► Backend :8001
          Authorization: Bearer <same backend token>       (tool calls made with that same token)
```

1. Log in against the **backend** (`POST /auth/login`) and keep `data.access_token`.
2. Send that **same token** to the AI service as `Authorization: Bearer <token>`. Your HTTP client already does this for both services.
3. The AI service checks the token with the backend (`/auth/me`) and calls backend tools **as that user**. The backend enforces all permissions.

Never send a `user_id` or role to the AI service. Identity comes only from the token.

---

## 3. Endpoints

All responses use the shared envelope:

- **Success:** `{ "status": "success", "data": …, "trace_id": "…" }`
- **Error:** `{ "status": "error", "error": { "code", "message" }, "trace_id": "…" }`

### 3.1 `POST /api/v1/chat/messages`

The token is **optional**. Anonymous users can search the catalog and check availability. Anything account-related comes back as `outcome: "refused"` with a "please sign in" message.

Request:

```json
{ "conversation_id": null, "message": "Recommend beginner resources for machine learning" }
```

- Send `conversation_id: null` for a new chat, then reuse the `conversation_id` from each response so follow-ups such as "reserve the first one" have context.
- A conversation belongs to the user who started it. Another user's ID returns `404 conversation_not_found`; start a new chat in that case.
- `message` must be 1–2000 characters.

Response `data`. This is `ChatResponse` in `types/models.ts`:

```json
{
  "conversation_id": "conv-…",
  "outcome": "answered",
  "assistant_message": "Here are some beginner picks…",
  "intent": "recommendation",
  "resources": [
    { "resource_id": "res-003", "title": "Getting Started with Generative AI",
      "reason": "Semantically relevant to …; beginner level as requested. Catalog facts: beginner book by …; 2 available at Central Library.",
      "available_copies": 2 }
  ],
  "citations": [
    { "resource_id": "res-003", "source_type": "catalog", "source_id": "res-003", "title": "Getting Started with Generative AI" }
  ],
  "proposed_action": null
}
```

#### `outcome` values

| `outcome` | Meaning | What the UI should do |
|---|---|---|
| `answered` | Normal answer | Show `assistant_message`, resource cards and citations. |
| `not_found` | Nothing matching exists in the library | Show the message; there are no resources. |
| `refused` | Privacy, role or sign-in refusal (e.g. another user's loans, a student asking for analytics, a librarian trying to reserve) | Show the message as a polite refusal. |
| `needs_confirmation` | A reservation or renewal is **proposed, not done** | Show `proposed_action.description` with **Confirm** and **Cancel** buttons. |

#### Other fields

- **`intent`** is one of `search`, `availability`, `recommendation`, `account`, `reservation`, `renewal`, `research`, `analytics`, `general` or `out_of_scope`. Use it for icons or labels if you like.
- **`resources[].available_copies`:**
  - a **number** only when it was checked live with the backend;
  - **`null`** when it wasn't checked. Show nothing in that case, not "0". `RecommendationCard` already handles this with `typeof … === "number"`.
- **`resources[].reason`:** the explanation shown to the user. For recommendations it ends with `Catalog facts: …`, which are the verified facts.
- **`citations[].source_type`:**
  - `catalog`: a catalog record;
  - `document`: a document passage, where `source_id` looks like `res-013#c1`.
- **`proposed_action`:**
  ```json
  { "action_id": "act-…", "action_type": "reservation", "resource_id": "res-011", "loan_id": null,
    "description": "Reserve 'Applied Statistics for Engineers'. 2 of 3 copies are available now; one will be held for pickup at Central Library." }
  ```
  For a renewal, `action_type` is `"renewal"` and `loan_id` is set. Treat `action_id` as opaque: never build or change it.
- **`assistant_message`** can contain line breaks and `- ` bullet lines. Render it with `white-space: pre-line`, or as simple markdown.

### 3.2 `POST /api/v1/chat/actions/confirm`

A token is **required**, and it must belong to the same user who received the proposal.

Request:

```json
{ "action_id": "act-…" }
```

Response `data`. This is `ConfirmActionResult` in `types/models.ts`:

```json
{
  "action_id": "act-…",
  "action_type": "reservation",
  "transaction_status": "completed",
  "transaction_id": "8f1c…",
  "reservation_id": "8f1c…",
  "loan_id": null,
  "message": "Reservation confirmed: 'Applied Statistics for Engineers' is being held for you to pick up.",
  "details": { "…": "backend record" }
}
```

| `transaction_status` | Meaning | UI |
|---|---|---|
| `completed` | The backend applied it. `transaction_id` is the reservation or loan ID. | Success toast with `message`. Refresh "My library". |
| `rejected` | A library rule refused it: already reserved, not renewable, librarian account. `details.error_code` gives the reason. | Show `message`. Don't offer a retry. |
| `failed` | Temporary outage; **nothing changed** | Show `message` and let the user press **Confirm again**. It is safe: the same idempotency key is reused, so it never applies twice. |

**Notes:**
- **Double-clicks are safe.** Confirming a completed action again returns the same result without reserving twice.
- **Expiry.** Proposals expire after **5 minutes**. Confirming later gives `404 action_not_found`; tell the user to ask again.
- **Wording.** For waitlisted reservations, `message` includes the queue position and notes that faculty and researchers are prioritised.

### 3.3 `GET /api/v1/health`

No token is needed. `data.status` is:
- `"ok"`: chat fully works;
- `"degraded"`: the AI service is up, but the backend or the LLM isn't reachable.

The response also includes `backend_reachable`, `llm_ready` and `tool_adapter`, which are useful for debugging.

---

## 4. Errors to handle

| HTTP | `error.code` | When | UI |
|---|---|---|---|
| 401 | `http_401` / `unauthorized` | Token invalid or expired; there is no refresh endpoint | Send the user to log in again |
| 404 | `conversation_not_found` | Reused someone else's or an expired `conversation_id` | Start a new chat (`conversation_id: null`) |
| 404 | `action_not_found` | The proposal expired (5 min) or isn't this user's | "This request expired, please ask again" |
| 422 | `invalid_request` | Empty or too-long message, malformed body | Validate input |
| 429 | `llm_rate_limited` | The AI model's quota was hit | "Too many requests, wait a moment" |
| 503 | `llm_unavailable` / `llm_not_configured` | AI model down or not set up | "Assistant temporarily unavailable" |

When the **backend** is down, chat still returns `200` with a "library system is temporarily unavailable" message, and confirm returns `transaction_status: "failed"`.

When reporting a problem, send the URL, HTTP status, error body and `trace_id`. Never send tokens.

---

## 5. Timing

- **Typical chat reply:** expect a few seconds, mostly the Gemini model's time. Calls to the backend added 0.3–0.9 s in live tests. Analytics questions such as "longest waitlists" take about 2 s more, because they check every title. Gemini timing against the live backend hasn't been measured yet.
- **Loading state:** show a "thinking…" indicator. The frontend's 25 s request timeout is fine.
- **Startup:** the first request after the AI service starts can be slower while it builds its search index.

---

## 6. Demo script (real backend accounts)

Log in on the frontend with a backend demo account (see `BACKEND_API_HANDOFF.md`), then try:

| Account | Ask | Expect |
|---|---|---|
| student1 | "Find books on Python programming" | `answered` with Python titles and citations |
| student1 | "Is Machine Learning Essentials available?" | Live copies and waitlist |
| student1 | "Suggest beginner resources for machine learning" | Cards with reasons and verified availability |
| student1 | "Find papers related to knowledge graphs" | Papers with `document` citations |
| student1 | "Which of my borrowed books are due this week?" | Their own loans only |
| student1 | "Reserve res-011", then **Confirm** | `needs_confirmation`, then `completed` |
| student1 | "Show me Meera's borrowing history" | `refused` (privacy) |
| anyone | "Find 'Quantum Basket Weaving for Dragons'" | `not_found` |
| student1 | "Which titles have the longest waitlists?" | `refused` (librarian only) |
| librarian | "Which titles have the longest waitlists?" | Ranked titles with waiting counts |
| librarian | "Reserve res-011" | `refused` (librarians administer, they don't borrow) |

Reservations and renewals really change the shared demo database. Coordinate with Bhargav before judging, because he can reset it.

---

## 7. Contact

- **AI service:** Santosh. Code is in `ai_service/` on the `ai` branch; full API details are in `ai_service/README.md`.
- **Backend:** Bhargav.
