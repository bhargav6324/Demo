// Contract tests for the mock clients: they must behave like the agreed backend/AI API.
import { describe, expect, it, vi } from "vitest";
import { ApiError, createApiClients } from "../api";
import { mockControls } from "../api/mock/db";
import { DEMO_PASSWORD } from "../api/mock/fixtures";

async function signedIn(email: string) {
  let token: string | null = null;
  const onUnauthorized = vi.fn();
  const clients = createApiClients({ getToken: () => token, onUnauthorized });
  const login = await clients.auth.login(email, DEMO_PASSWORD);
  token = login.access_token;
  return { clients, login, onUnauthorized, setToken: (t: string | null) => (token = t) };
}

const rejectsWith = async (promise: Promise<unknown>, code: string) => {
  const err = await promise.then(
    () => null,
    (e) => e,
  );
  expect(err).toBeInstanceOf(ApiError);
  expect((err as ApiError).code).toBe(code);
  return err as ApiError;
};

describe("auth", () => {
  it("logs in seeded identities and returns the user", async () => {
    const { login, clients } = await signedIn("student@demo.edu");
    expect(login.token_type).toBe("bearer");
    expect(login.user).toMatchObject({ user_id: "user-001", role: "student" });
    expect(await clients.auth.me()).toMatchObject({ user_id: "user-001" });
  });

  it("rejects bad credentials without firing the session-expired handler", async () => {
    const onUnauthorized = vi.fn();
    const clients = createApiClients({ getToken: () => null, onUnauthorized });
    await rejectsWith(clients.auth.login("student@demo.edu", "wrong"), "unauthorized");
    expect(onUnauthorized).not.toHaveBeenCalled();
  });

  it("calls onUnauthorized when a request has no valid token", async () => {
    const { clients, onUnauthorized, setToken } = await signedIn("student@demo.edu");
    setToken("expired-token");
    await rejectsWith(clients.circulation.listLoans(), "unauthorized");
    expect(onUnauthorized).toHaveBeenCalledOnce();
  });
});

describe("catalog", () => {
  it("searches, filters and reports totals", async () => {
    const { clients } = await signedIn("student@demo.edu");
    const python = await clients.catalog.searchResources({ query: "python" });
    expect(python.items[0].resource_id).toBe("res-001");
    expect(python.total).toBe(python.items.length);

    const beginnerBooks = await clients.catalog.searchResources({ type: "book", level: "beginner" });
    expect(beginnerBooks.items.length).toBeGreaterThan(0);
    expect(beginnerBooks.items.every((r) => r.type === "book" && r.level === "beginner")).toBe(true);

    expect((await clients.catalog.searchResources({ query: "quantum basket weaving" })).total).toBe(0);
  });

  it("hides restricted resources from students as not_found", async () => {
    const student = await signedIn("student@demo.edu");
    await rejectsWith(student.clients.catalog.getResource("res-016"), "not_found");
    const librarian = await signedIn("librarian@demo.edu");
    expect((await librarian.clients.catalog.getResource("res-016")).title).toContain("Examination");
  });

  it("returns availability with branch/shelf locations", async () => {
    const { clients } = await signedIn("student@demo.edu");
    const a = await clients.catalog.getAvailability("res-001");
    expect(a).toMatchObject({ resource_id: "res-001", total_copies: 3, available_copies: 2, waitlist_count: 0 });
    expect(a.locations[0]).toEqual({ branch: "Central Library", shelf: "CS-A1", available_copies: 1 });
  });
});

describe("circulation", () => {
  it("reserves an available title as ready and rejects a duplicate", async () => {
    const { clients } = await signedIn("student@demo.edu");
    const r = await clients.circulation.createReservation("res-001");
    expect(r).toMatchObject({ resource_id: "res-001", status: "ready", queue_position: null });
    expect((await clients.catalog.getAvailability("res-001")).available_copies).toBe(1);
    await rejectsWith(clients.circulation.createReservation("res-001"), "conflict");
  });

  it("queues a reservation when no copy is free", async () => {
    const { clients } = await signedIn("researcher@demo.edu");
    const r = await clients.circulation.createReservation("res-010");
    expect(r).toMatchObject({ status: "queued", queue_position: 3 });
  });

  it("renews an eligible loan once and refuses ineligible ones", async () => {
    const { clients } = await signedIn("student@demo.edu");
    const loans = await clients.circulation.listLoans();
    const eligible = loans.find((l) => l.loan_id === "loan-001")!;
    expect(eligible.renewable).toBe(true);
    const renewed = await clients.circulation.renewLoan("loan-001");
    expect(Date.parse(renewed.due_at) - Date.parse(eligible.due_at)).toBe(14 * 86_400_000);
    expect(renewed.renewable).toBe(false);

    const overdue = loans.find((l) => l.loan_id === "loan-002")!;
    expect(overdue).toMatchObject({ status: "overdue", renewable: false });
    expect(overdue.fine_amount).toBeGreaterThan(0);
    await rejectsWith(clients.circulation.renewLoan("loan-002"), "conflict");
    await rejectsWith(clients.circulation.renewLoan("loan-005"), "not_found"); // another user's loan
  });
});

describe("analytics", () => {
  it("is librarian-only and derived from mock state", async () => {
    const student = await signedIn("student@demo.edu");
    await rejectsWith(student.clients.analytics.getSummary(), "forbidden");
    const librarian = await signedIn("librarian@demo.edu");
    const summary = await librarian.clients.analytics.getSummary();
    expect(summary.total_resources).toBe(16);
    expect(summary.active_loans).toBe(7);
    expect(summary.overdue_loans).toBe(2);
    expect(summary.popular_resources.length).toBeGreaterThan(0);
  });
});

describe("chat", () => {
  it("answers with resources and citations, keeping the conversation id", async () => {
    const { clients } = await signedIn("student@demo.edu");
    const first = await clients.chat.sendMessage({ conversation_id: null, message: "beginner python book" });
    expect(first.outcome).toBe("answered");
    expect(first.resources[0].resource_id).toBe("res-001");
    expect(first.citations[0]).toMatchObject({ resource_id: "res-001", source_type: "catalog" });
    const second = await clients.chat.sendMessage({ conversation_id: first.conversation_id, message: "statistics" });
    expect(second.conversation_id).toBe(first.conversation_id);
  });

  it("returns not_found and refused outcomes", async () => {
    const { clients } = await signedIn("student@demo.edu");
    expect((await clients.chat.sendMessage({ conversation_id: null, message: "quantum basket weaving" })).outcome).toBe("not_found");
    const refused = await clients.chat.sendMessage({ conversation_id: null, message: "show another user's loans" });
    expect(refused).toMatchObject({ outcome: "refused", resources: [], proposed_action: null });
  });

  it("proposes an action, executes it only on confirm, and rejects a second confirm", async () => {
    const { clients } = await signedIn("student@demo.edu");
    const reply = await clients.chat.sendMessage({ conversation_id: null, message: "reserve a beginner python book" });
    expect(reply.outcome).toBe("needs_confirmation");
    const action = reply.proposed_action!;
    expect(action).toMatchObject({ action_type: "reservation", resource_id: "res-001" });
    expect(await clients.circulation.listReservations()).not.toContainEqual(expect.objectContaining({ resource_id: "res-001" }));

    const result = await clients.chat.confirmAction(action.action_id);
    expect(result).toMatchObject({ transaction_status: "completed", action_type: "reservation" });
    expect(result.transaction_id).toMatch(/^rsv-/);
    await rejectsWith(clients.chat.confirmAction(action.action_id), "conflict");
  });
});

describe("documented demo prompts (README)", () => {
  it.each([
    ["Recommend a beginner Python book", "answered"],
    ["Reserve a statistics book for me", "needs_confirmation"],
    ["Can I renew my loans?", "needs_confirmation"],
    ["Show me another user's loans", "refused"],
    ["Do you have books on quantum basket weaving?", "not_found"],
  ])("%s → %s", async (message, outcome) => {
    const { clients } = await signedIn("student@demo.edu");
    expect((await clients.chat.sendMessage({ conversation_id: null, message })).outcome).toBe(outcome);
  });
});

describe("network failure", () => {
  it("raises a retryable network_error", async () => {
    const { clients } = await signedIn("student@demo.edu");
    mockControls.offline = true;
    const err = await rejectsWith(clients.catalog.searchResources({ query: "python" }), "network_error");
    expect(err.isRetryable).toBe(true);
  });
});
