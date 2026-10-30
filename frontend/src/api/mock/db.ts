// In-memory simulated backend for mock mode. It plays the role of the backend's
// authorization, holdings and circulation rules so the UI can be exercised end to
// end; the real backend remains authoritative in real mode.
import type {
  Availability,
  Loan,
  LoanStatus,
  Reservation,
  ReservationStatus,
  Resource,
  User,
} from "../../types/models";
import { ApiError } from "../errors";
import {
  DEMO_PASSWORD,
  SEED_BORROW_HISTORY,
  SEED_HOLDINGS,
  SEED_RESOURCES,
  SEED_USERS,
  seedLoans,
  seedReservations,
} from "./fixtures";

const DAY = 86_400_000;
const FINE_PER_DAY = 10; // synthetic mock policy, INR
const FINE_CAP = 500;
const LOAN_DAYS = 14;
const MAX_RENEWALS = 1;
const DIGITAL_TYPES = new Set(["ebook", "digital_resource"]);
const PRIVILEGED_ROLES = new Set(["faculty", "librarian"]);

interface MockLoan {
  loan_id: string;
  user_id: string;
  resource_id: string;
  borrowed_at: string;
  due_at: string;
  returned_at: string | null;
  renew_count: number;
}

interface MockReservation {
  reservation_id: string;
  user_id: string;
  resource_id: string;
  status: ReservationStatus;
  created_at: string;
}

export interface MockAction {
  action_id: string;
  user_id: string;
  action_type: "reservation" | "renewal";
  resource_id?: string;
  loan_id?: string;
  used: boolean;
}

const clone = <T>(value: T): T => structuredClone(value);
const isoNow = () => new Date().toISOString().replace(/\.\d{3}Z$/, "Z");

export function randomId(prefix: string) {
  const raw = globalThis.crypto?.randomUUID?.() ?? Math.random().toString(16).slice(2) + Date.now().toString(16);
  return `${prefix}-${raw.replace(/-/g, "").slice(0, 10)}`;
}

export class MockDb {
  users = clone(SEED_USERS);
  resources = clone(SEED_RESOURCES);
  holdings = clone(SEED_HOLDINGS);
  borrowHistory = clone(SEED_BORROW_HISTORY);
  loans: MockLoan[] = seedLoans(Date.now());
  reservations: MockReservation[] = seedReservations(Date.now());
  /** token -> user_id. Tokens are random per login and never persisted. */
  sessions = new Map<string, string>();
  conversations = new Map<string, string>();
  actions = new Map<string, MockAction>();
  private seq = 100;

  nextId(prefix: string) {
    this.seq += 1;
    return `${prefix}-${String(this.seq).padStart(3, "0")}`;
  }

  // ---------- Auth ----------

  login(email: string, password: string): { token: string; user: User } {
    const user = this.users.find((u) => u.email.toLowerCase() === email.trim().toLowerCase());
    if (!user || password !== DEMO_PASSWORD) {
      throw new ApiError("unauthorized", "Invalid email or password.", 401);
    }
    const token = randomId("mock-token");
    this.sessions.set(token, user.user_id);
    return { token, user: clone(user) };
  }

  userForToken(token: string | null): User {
    const userId = token ? this.sessions.get(token) : undefined;
    const user = userId && this.users.find((u) => u.user_id === userId);
    if (!user) throw new ApiError("unauthorized", "Your session has expired. Please sign in again.", 401);
    return clone(user);
  }

  // ---------- Catalog ----------

  canSee(user: User, resource: Resource) {
    return resource.access_level !== "restricted" || PRIVILEGED_ROLES.has(user.role);
  }

  /** Inaccessible resources are indistinguishable from missing ones. */
  visibleResource(user: User, resourceId: string): Resource {
    const resource = this.resources.find((r) => r.resource_id === resourceId);
    if (!resource || !this.canSee(user, resource)) {
      throw new ApiError("not_found", "Resource not found.", 404);
    }
    return resource;
  }

  isDigital(resource: Resource) {
    return DIGITAL_TYPES.has(resource.type);
  }

  queued(resourceId: string) {
    return this.reservations
      .filter((r) => r.resource_id === resourceId && r.status === "queued")
      .sort((a, b) => a.created_at.localeCompare(b.created_at) || a.reservation_id.localeCompare(b.reservation_id));
  }

  availability(resourceId: string): Availability {
    const locations = this.holdings[resourceId] ?? [];
    return {
      resource_id: resourceId,
      total_copies: locations.reduce((n, l) => n + l.total, 0),
      available_copies: locations.reduce((n, l) => n + l.available, 0),
      waitlist_count: this.queued(resourceId).length,
      locations: locations.map((l) => ({ branch: l.branch, shelf: l.shelf, available_copies: l.available })),
    };
  }

  // ---------- Circulation ----------

  private loanStatus(loan: MockLoan, now = Date.now()): LoanStatus {
    if (loan.returned_at) return "returned";
    return Date.parse(loan.due_at) < now ? "overdue" : "active";
  }

  private renewalBlock(loan: MockLoan): string | null {
    const status = this.loanStatus(loan);
    if (status === "returned") return "This loan has already been returned.";
    if (status === "overdue") return "Overdue loans cannot be renewed. Please return the item.";
    if (loan.renew_count >= MAX_RENEWALS) return "This loan has already been renewed the maximum number of times.";
    const waiting = this.reservations.some(
      (r) => r.resource_id === loan.resource_id && r.user_id !== loan.user_id && (r.status === "queued" || r.status === "ready"),
    );
    if (waiting) return "Another member is waiting for this title, so it cannot be renewed.";
    return null;
  }

  toLoan(loan: MockLoan): Loan {
    const now = Date.now();
    const status = this.loanStatus(loan, now);
    const overdueDays = status === "overdue" ? Math.floor((now - Date.parse(loan.due_at)) / DAY) : 0;
    const title = this.resources.find((r) => r.resource_id === loan.resource_id)?.title ?? "Unknown title";
    return {
      loan_id: loan.loan_id,
      resource_id: loan.resource_id,
      resource_title: title,
      borrowed_at: loan.borrowed_at,
      due_at: loan.due_at,
      renewable: this.renewalBlock(loan) === null,
      fine_amount: Math.min(FINE_CAP, overdueDays * FINE_PER_DAY),
      status,
    };
  }

  toReservation(r: MockReservation): Reservation {
    const position = r.status === "queued" ? this.queued(r.resource_id).findIndex((q) => q.reservation_id === r.reservation_id) + 1 : 0;
    return {
      reservation_id: r.reservation_id,
      resource_id: r.resource_id,
      status: r.status,
      queue_position: r.status === "queued" ? position : null,
    };
  }

  loansFor(user: User): Loan[] {
    return this.loans
      .filter((l) => l.user_id === user.user_id && !l.returned_at)
      .sort((a, b) => a.due_at.localeCompare(b.due_at) || a.loan_id.localeCompare(b.loan_id))
      .map((l) => this.toLoan(l));
  }

  reservationsFor(user: User): Reservation[] {
    return this.reservations
      .filter((r) => r.user_id === user.user_id)
      .sort((a, b) => b.created_at.localeCompare(a.created_at) || a.reservation_id.localeCompare(b.reservation_id))
      .map((r) => this.toReservation(r));
  }

  renew(user: User, loanId: string): Loan {
    // Another member's loan is reported exactly like a missing one.
    const loan = this.loans.find((l) => l.loan_id === loanId && l.user_id === user.user_id);
    if (!loan) throw new ApiError("not_found", "Loan not found.", 404);
    const block = this.renewalBlock(loan);
    if (block) throw new ApiError("conflict", block, 409);
    loan.due_at = new Date(Date.parse(loan.due_at) + LOAN_DAYS * DAY).toISOString().replace(/\.\d{3}Z$/, "Z");
    loan.renew_count += 1;
    return this.toLoan(loan);
  }

  reserve(user: User, resourceId: string): Reservation {
    const resource = this.visibleResource(user, resourceId);
    if (this.isDigital(resource)) {
      throw new ApiError("conflict", "Digital resources are available online and cannot be reserved.", 409);
    }
    const duplicate = this.reservations.some(
      (r) => r.user_id === user.user_id && r.resource_id === resourceId && (r.status === "queued" || r.status === "ready"),
    );
    if (duplicate) throw new ApiError("conflict", "You already have an active reservation for this title.", 409);

    const free = (this.holdings[resourceId] ?? []).find((l) => l.available > 0);
    const reservation: MockReservation = {
      reservation_id: this.nextId("rsv"),
      user_id: user.user_id,
      resource_id: resourceId,
      status: "queued",
      created_at: isoNow(),
    };
    if (free && this.queued(resourceId).length === 0) {
      free.available -= 1; // copy is now held for pickup
      reservation.status = "ready";
    }
    this.reservations.push(reservation);
    return this.toReservation(reservation);
  }
}

let db: MockDb | null = null;

export function getMockDb(): MockDb {
  db ??= new MockDb();
  return db;
}

/** Tests: start every case from the seed state. */
export function resetMockDb() {
  db = new MockDb();
  mockControls.offline = false;
}

/** Test/demo switches for simulating failures. */
export const mockControls = { offline: false };
