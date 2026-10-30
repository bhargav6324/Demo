// Mock implementations of the five client interfaces, backed by MockDb.
import { config } from "../../config";
import type {
  AiHealth,
  AnalyticsSummary,
  ChatRequest,
  ChatResource,
  ChatResponse,
  Citation,
  ConfirmActionResult,
  LoginData,
  PagedData,
  ProposedAction,
  Resource,
  ResourceContent,
  ResourceQuery,
  User,
} from "../../types/models";
import { ApiError } from "../errors";
import type {
  AnalyticsClient,
  ApiClients,
  AuthClient,
  CatalogClient,
  ChatClient,
  CirculationClient,
  ClientContext,
} from "../interfaces";
import { getMockDb, mockControls, randomId, type MockDb } from "./db";
import { DIGITAL_URLS, SEED_CONTENT } from "./fixtures";

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

/** Shared wrapper: latency, offline simulation, 401 propagation, and deep copies. */
function makeRunner(ctx: ClientContext) {
  return async function run<T>(fn: (db: MockDb) => T, opts: { notifyUnauthorized?: boolean } = {}): Promise<T> {
    if (config.mockLatencyMs > 0) await sleep(config.mockLatencyMs);
    if (mockControls.offline) throw new ApiError("network_error", "Cannot reach the library service. Check your connection and retry.");
    try {
      return structuredClone(fn(getMockDb()));
    } catch (err) {
      if (err instanceof ApiError && err.isUnauthorized && opts.notifyUnauthorized !== false) ctx.onUnauthorized();
      throw err;
    }
  };
}

const STOPWORDS = new Set(
  "a an and any are about book books can could find for from get give have help i in is it me my need of on or please recommend reserve resource resources show some something the to want what with you looking available".split(
    " ",
  ),
);

function terms(text: string) {
  return text
    .toLowerCase()
    .split(/[^a-z0-9-]+/)
    .filter((w) => w.length > 1 && !STOPWORDS.has(w));
}

/** Simple keyword relevance used by both mock search and mock chat. */
function score(resource: Resource, words: string[]) {
  const title = resource.title.toLowerCase();
  const topics = resource.topics.join(" ").toLowerCase();
  const rest = `${resource.description} ${resource.authors.join(" ")}`.toLowerCase();
  return words.reduce((n, w) => n + (title.includes(w) ? 3 : 0) + (topics.includes(w) ? 2 : 0) + (rest.includes(w) ? 1 : 0), 0);
}

function matchedTopics(resource: Resource, words: string[]) {
  return resource.topics.filter((t) => words.some((w) => t.includes(w)));
}

// ---------- Auth ----------

class MockAuthClient implements AuthClient {
  private run;
  constructor(private ctx: ClientContext) {
    this.run = makeRunner(ctx);
  }
  login(email: string, password: string): Promise<LoginData> {
    return this.run(
      (db) => {
        const { token, user } = db.login(email, password);
        return { access_token: token, token_type: "bearer" as const, user };
      },
      { notifyUnauthorized: false },
    );
  }
  me(): Promise<User> {
    return this.run((db) => db.userForToken(this.ctx.getToken()));
  }
  profile(): Promise<User> {
    return this.me();
  }
}

// ---------- Catalog ----------

class MockCatalogClient implements CatalogClient {
  private run;
  constructor(private ctx: ClientContext) {
    this.run = makeRunner(ctx);
  }
  searchResources(q: ResourceQuery): Promise<PagedData<Resource>> {
    return this.run((db) => {
      const user = db.userForToken(this.ctx.getToken());
      const words = terms(q.query ?? "");
      let items = db.resources.filter((r) => db.canSee(user, r));
      if (q.type) items = items.filter((r) => r.type === q.type);
      if (q.level) items = items.filter((r) => r.level === q.level);
      if (q.updated_since) items = items.filter((r) => r.updated_at >= q.updated_since!);
      if (words.length) {
        items = items
          .map((r) => ({ r, s: score(r, words) }))
          .filter(({ s }) => s > 0)
          .sort((a, b) => b.s - a.s || a.r.resource_id.localeCompare(b.r.resource_id))
          .map(({ r }) => r);
      } else {
        items = [...items].sort((a, b) => a.title.localeCompare(b.title));
      }
      const limit = Math.min(Math.max(q.limit ?? 20, 1), 50);
      return { items: items.slice(0, limit), total: items.length };
    });
  }
  getResource(resourceId: string): Promise<Resource> {
    return this.run((db) => db.visibleResource(db.userForToken(this.ctx.getToken()), resourceId));
  }
  getAvailability(resourceId: string) {
    return this.run((db) => {
      db.visibleResource(db.userForToken(this.ctx.getToken()), resourceId);
      return db.availability(resourceId);
    });
  }
  getContent(resourceId: string): Promise<ResourceContent> {
    return this.run((db) => {
      const resource = db.visibleResource(db.userForToken(this.ctx.getToken()), resourceId);
      const url = DIGITAL_URLS[resourceId] ?? null;
      const body = SEED_CONTENT[resourceId] ?? null;
      if (!url && !body) throw new ApiError("not_found", "No readable content is available for this resource.", 404);
      return { resource_id: resource.resource_id, format: url ? ("link" as const) : ("text" as const), body, url };
    });
  }
}

// ---------- Circulation ----------

class MockCirculationClient implements CirculationClient {
  private run;
  constructor(private ctx: ClientContext) {
    this.run = makeRunner(ctx);
  }
  listLoans() {
    return this.run((db) => db.loansFor(db.userForToken(this.ctx.getToken())));
  }
  renewLoan(loanId: string) {
    return this.run((db) => db.renew(db.userForToken(this.ctx.getToken()), loanId));
  }
  createReservation(resourceId: string) {
    return this.run((db) => db.reserve(db.userForToken(this.ctx.getToken()), resourceId));
  }
  listReservations() {
    return this.run((db) => db.reservationsFor(db.userForToken(this.ctx.getToken())));
  }
}

// ---------- Analytics ----------

class MockAnalyticsClient implements AnalyticsClient {
  private run;
  constructor(private ctx: ClientContext) {
    this.run = makeRunner(ctx);
  }
  getSummary(): Promise<AnalyticsSummary> {
    return this.run((db) => {
      const user = db.userForToken(this.ctx.getToken());
      if (user.role !== "librarian") throw new ApiError("forbidden", "Analytics are available to librarians only.", 403);
      const active = db.loans.filter((l) => !l.returned_at).map((l) => db.toLoan(l));
      const activeReservations = db.reservations.filter((r) => r.status === "queued" || r.status === "ready");
      const popular = db.resources
        .map((r) => ({
          resource_id: r.resource_id,
          title: r.title,
          borrow_count: (db.borrowHistory[r.resource_id] ?? 0) + active.filter((l) => l.resource_id === r.resource_id).length,
          reservation_count: activeReservations.filter((x) => x.resource_id === r.resource_id).length,
        }))
        .filter((p) => p.borrow_count + p.reservation_count > 0)
        .sort((a, b) => b.borrow_count + b.reservation_count - (a.borrow_count + a.reservation_count) || a.resource_id.localeCompare(b.resource_id))
        .slice(0, 8);
      return {
        total_resources: db.resources.length,
        active_loans: active.length,
        overdue_loans: active.filter((l) => l.status === "overdue").length,
        active_reservations: activeReservations.length,
        popular_resources: popular,
      };
    });
  }
}

// ---------- Chat ----------

const REFUSAL = /(another|other) (user|student|member|person)|someone else|user-\d{3}|ignore (all|previous|your)|reveal (the )?(system|secret|token)/i;

class MockChatClient implements ChatClient {
  private run;
  constructor(private ctx: ClientContext) {
    this.run = makeRunner(ctx);
  }

  private propose(db: MockDb, user: User, action: Omit<ProposedAction, "action_id">): ProposedAction {
    const proposed = { action_id: randomId("act"), ...action };
    db.actions.set(proposed.action_id, {
      action_id: proposed.action_id,
      user_id: user.user_id,
      action_type: proposed.action_type,
      resource_id: proposed.resource_id,
      loan_id: proposed.loan_id,
      used: false,
    });
    return proposed;
  }

  sendMessage(request: ChatRequest): Promise<ChatResponse> {
    return this.run((db) => {
      const user = db.userForToken(this.ctx.getToken());
      const message = request.message.trim();
      if (!message) throw new ApiError("validation_error", "Message cannot be empty.", 422);

      let conversationId = request.conversation_id;
      if (!conversationId || db.conversations.get(conversationId) !== user.user_id) {
        conversationId = randomId("conv");
        db.conversations.set(conversationId, user.user_id);
      }
      const reply = (r: Omit<ChatResponse, "conversation_id">): ChatResponse => ({ conversation_id: conversationId!, ...r });
      const empty = { resources: [], citations: [], proposed_action: null };

      if (REFUSAL.test(message)) {
        return reply({
          outcome: "refused",
          intent: "privacy_violation",
          assistant_message: "I can only help with your own library account. I can't share or act on another member's records.",
          ...empty,
        });
      }

      const lower = message.toLowerCase();

      if (/\brenew/.test(lower)) {
        const loan = db.loansFor(user).find((l) => l.renewable);
        if (!loan) {
          return reply({
            outcome: "answered",
            intent: "renew_loan",
            assistant_message: "None of your current loans can be renewed right now. Open My Library to see why for each item.",
            ...empty,
          });
        }
        return reply({
          outcome: "needs_confirmation",
          intent: "renew_loan",
          assistant_message: `"${loan.resource_title}" is eligible for renewal. Please confirm and I'll submit it.`,
          resources: [],
          citations: [],
          proposed_action: this.propose(db, user, {
            action_type: "renewal",
            loan_id: loan.loan_id,
            resource_id: loan.resource_id,
            description: `Renew "${loan.resource_title}" for 14 more days`,
          }),
        });
      }

      if (/\b(my loans|borrowed|due date|what do i have)\b/.test(lower)) {
        const loans = db.loansFor(user);
        return reply({
          outcome: "answered",
          intent: "list_loans",
          assistant_message: loans.length
            ? `You have ${loans.length} item(s) on loan: ${loans.map((l) => `"${l.resource_title}"`).join(", ")}. See My Library for due dates and fines.`
            : "You have no items on loan right now.",
          ...empty,
        });
      }

      const words = terms(message);
      const ranked = db.resources
        .filter((r) => db.canSee(user, r))
        .map((r) => ({ r, s: score(r, words) }))
        .filter(({ s }) => s >= 2)
        .sort((a, b) => b.s - a.s || a.r.resource_id.localeCompare(b.r.resource_id))
        .slice(0, 3)
        .map(({ r }) => r);

      if (!ranked.length) {
        return reply({
          outcome: "not_found",
          intent: "search",
          assistant_message: "I couldn't find any resource in the library catalog that matches that request. Try different keywords or browse Discover.",
          ...empty,
        });
      }

      const interests = [...user.interests, ...user.courses].map((x) => x.toLowerCase());
      const resources: ChatResource[] = ranked.map((r) => {
        const matched = matchedTopics(r, words);
        const personal = r.topics.filter((t) => interests.some((i) => i.includes(t) || t.includes(i)));
        const reason = [
          matched.length ? `Covers ${matched.join(", ")}` : `Relevant to your query`,
          `${r.level} level`,
          personal.length ? `matches your interest in ${personal[0]}` : null,
        ]
          .filter(Boolean)
          .join(" · ");
        const item: ChatResource = { resource_id: r.resource_id, title: r.title, reason };
        if (!db.isDigital(r)) item.available_copies = db.availability(r.resource_id).available_copies;
        return item;
      });
      const citations: Citation[] = ranked.map((r) => ({
        resource_id: r.resource_id,
        source_type: "catalog",
        source_id: r.resource_id,
        title: r.title,
      }));

      if (/\b(reserve|hold|place a hold)\b/.test(lower)) {
        const target = ranked.find((r) => !db.isDigital(r));
        if (target) {
          return reply({
            outcome: "needs_confirmation",
            intent: "reserve_resource",
            assistant_message: `"${target.title}" is the best match. Confirm below and I'll place the reservation — availability is re-checked when you confirm.`,
            resources,
            citations,
            proposed_action: this.propose(db, user, {
              action_type: "reservation",
              resource_id: target.resource_id,
              description: `Reserve "${target.title}"`,
            }),
          });
        }
      }

      return reply({
        outcome: "answered",
        intent: "search",
        assistant_message: `I found ${ranked.length} resource(s) in the catalog that fit your request. Each one is cited below.`,
        resources,
        citations,
        proposed_action: null,
      });
    });
  }

  confirmAction(actionId: string): Promise<ConfirmActionResult> {
    return this.run((db) => {
      const user = db.userForToken(this.ctx.getToken());
      const action = db.actions.get(actionId);
      if (!action || action.user_id !== user.user_id) throw new ApiError("not_found", "This action no longer exists.", 404);
      if (action.used) throw new ApiError("conflict", "This action has already been confirmed.", 409);
      action.used = true;
      try {
        if (action.action_type === "reservation") {
          const r = db.reserve(user, action.resource_id!);
          return {
            action_id: actionId,
            action_type: "reservation" as const,
            transaction_status: "completed" as const,
            transaction_id: r.reservation_id,
            message: r.status === "ready" ? "Reserved — a copy is being held for pickup." : `Added to the waitlist at position ${r.queue_position}.`,
          };
        }
        const loan = db.renew(user, action.loan_id!);
        return {
          action_id: actionId,
          action_type: "renewal" as const,
          transaction_status: "completed" as const,
          transaction_id: loan.loan_id,
          message: `Renewed. New due date: ${loan.due_at.slice(0, 10)}.`,
        };
      } catch (err) {
        if (err instanceof ApiError && (err.isConflict || err.isNotFound)) {
          return {
            action_id: actionId,
            action_type: action.action_type,
            transaction_status: "rejected" as const,
            transaction_id: null,
            message: err.message,
          };
        }
        throw err;
      }
    });
  }

  health(): Promise<AiHealth> {
    return this.run(() => ({ status: "ok" as const }), { notifyUnauthorized: false });
  }
}

export function createMockClients(ctx: ClientContext): ApiClients {
  return {
    auth: new MockAuthClient(ctx),
    catalog: new MockCatalogClient(ctx),
    circulation: new MockCirculationClient(ctx),
    analytics: new MockAnalyticsClient(ctx),
    chat: new MockChatClient(ctx),
  };
}
