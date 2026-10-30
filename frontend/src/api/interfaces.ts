// The five client interfaces. Pages depend only on these; mock and HTTP
// implementations are interchangeable via configuration.
import type {
  AiHealth,
  AnalyticsSummary,
  Availability,
  ChatRequest,
  ChatResponse,
  ConfirmActionResult,
  Loan,
  LoginData,
  PagedData,
  Reservation,
  Resource,
  ResourceContent,
  ResourceQuery,
  User,
} from "../types/models";

export interface AuthClient {
  login(email: string, password: string): Promise<LoginData>;
  me(): Promise<User>;
  profile(): Promise<User>;
}

export interface CatalogClient {
  searchResources(query: ResourceQuery): Promise<PagedData<Resource>>;
  getResource(resourceId: string): Promise<Resource>;
  getAvailability(resourceId: string): Promise<Availability>;
  getContent(resourceId: string): Promise<ResourceContent>;
}

export interface CirculationClient {
  listLoans(): Promise<Loan[]>;
  renewLoan(loanId: string): Promise<Loan>;
  createReservation(resourceId: string): Promise<Reservation>;
  listReservations(): Promise<Reservation[]>;
}

export interface AnalyticsClient {
  getSummary(): Promise<AnalyticsSummary>;
}

export interface ChatClient {
  sendMessage(request: ChatRequest): Promise<ChatResponse>;
  confirmAction(actionId: string): Promise<ConfirmActionResult>;
  health(): Promise<AiHealth>;
}

export interface ApiClients {
  auth: AuthClient;
  catalog: CatalogClient;
  circulation: CirculationClient;
  analytics: AnalyticsClient;
  chat: ChatClient;
}

/** Injected by the auth layer so clients never own or log the token. */
export interface ClientContext {
  getToken(): string | null;
  /** Called on any 401 so the app can clear auth state. */
  onUnauthorized(): void;
}
