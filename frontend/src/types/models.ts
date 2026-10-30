// Shared models — mirror the agreed backend/AI contract exactly (snake_case).
// Fields marked "ASSUMED" are not fully specified in the contract; adjust here only.

// ---------- Envelope ----------

export interface ApiSuccess<T> {
  status: "success";
  data: T;
  trace_id: string;
}

export interface ApiFailure {
  status: "error";
  error: { code: string; message: string };
  trace_id: string;
}

export type ApiEnvelope<T> = ApiSuccess<T> | ApiFailure;

export interface ListData<T> {
  items: T[];
}

export interface PagedData<T> extends ListData<T> {
  total: number;
}

// ---------- Identity ----------

export type Role = "student" | "researcher" | "faculty" | "librarian";

export interface User {
  user_id: string;
  name: string;
  email: string;
  role: Role;
  courses: string[];
  interests: string[];
}

/** ASSUMED shape of POST /auth/login `data`. */
export interface LoginData {
  access_token: string;
  token_type: "bearer";
  user: User;
}

// ---------- Catalog ----------

export type ResourceType = "book" | "ebook" | "journal" | "paper" | "dissertation" | "digital_resource";
export type ResourceLevel = "beginner" | "intermediate" | "advanced";
/** ASSUMED values. */
export type AccessLevel = "open" | "members" | "restricted";

export interface Resource {
  resource_id: string;
  title: string;
  authors: string[];
  type: ResourceType;
  description: string;
  topics: string[];
  level: ResourceLevel;
  access_level: AccessLevel;
  updated_at: string;
}

export interface ShelfLocation {
  branch: string;
  shelf: string;
  available_copies: number;
}

export interface Availability {
  resource_id: string;
  total_copies: number;
  available_copies: number;
  waitlist_count: number;
  locations: ShelfLocation[];
}

/** ASSUMED shape of GET /resources/{id}/content `data`. */
export interface ResourceContent {
  resource_id: string;
  format: "text" | "link";
  body: string | null;
  url: string | null;
}

export interface ResourceQuery {
  query?: string;
  limit?: number;
  type?: ResourceType;
  level?: ResourceLevel;
  updated_since?: string;
}

// ---------- Circulation ----------

/** ASSUMED values. */
export type LoanStatus = "active" | "overdue" | "returned";

export interface Loan {
  loan_id: string;
  resource_id: string;
  resource_title: string;
  borrowed_at: string;
  due_at: string;
  renewable: boolean;
  /** ASSUMED to be rupees (INR), as a number. */
  fine_amount: number;
  status: LoanStatus;
}

/** ASSUMED values. */
export type ReservationStatus = "queued" | "ready" | "fulfilled" | "cancelled";

export interface Reservation {
  reservation_id: string;
  resource_id: string;
  status: ReservationStatus;
  /** 1-based for queued holds; null otherwise. */
  queue_position: number | null;
}

// ---------- Analytics ----------

/** ASSUMED item shape for popular_resources. */
export interface PopularResource {
  resource_id: string;
  title: string;
  borrow_count: number;
  reservation_count: number;
}

export interface AnalyticsSummary {
  total_resources: number;
  active_loans: number;
  overdue_loans: number;
  active_reservations: number;
  popular_resources: PopularResource[];
}

// ---------- AI chat ----------

export type ChatOutcome = "answered" | "not_found" | "refused" | "needs_confirmation";

export interface ChatResource {
  resource_id: string;
  title: string;
  reason: string;
  /** Present only when the AI service verified it against live holdings. */
  available_copies?: number;
}

export interface Citation {
  resource_id: string;
  source_type: string;
  source_id: string;
  title: string;
}

export type ActionType = "reservation" | "renewal";

export interface ProposedAction {
  action_id: string;
  action_type: ActionType;
  resource_id?: string;
  loan_id?: string;
  description: string;
}

export interface ChatRequest {
  conversation_id: string | null;
  message: string;
}

export interface ChatResponse {
  conversation_id: string;
  outcome: ChatOutcome;
  assistant_message: string;
  intent: string;
  resources: ChatResource[];
  citations: Citation[];
  proposed_action: ProposedAction | null;
}

/** ASSUMED shape of POST /chat/actions/confirm `data`. */
export interface ConfirmActionResult {
  action_id: string;
  action_type: ActionType;
  transaction_status: "completed" | "rejected" | "failed";
  /** reservation_id or loan_id of the affected record. */
  transaction_id: string | null;
  message: string;
}

/** ASSUMED shape of GET /health on the AI service. */
export interface AiHealth {
  status: "ok" | "degraded" | "down";
}
