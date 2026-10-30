// Real HTTP implementations. All envelope parsing and error mapping lives here,
// so a contract change only touches this file.
import axios, { AxiosError, type AxiosInstance } from "axios";
import { config } from "../../config";
import type {
  AiHealth,
  AnalyticsSummary,
  ApiEnvelope,
  Availability,
  ChatRequest,
  ChatResponse,
  ConfirmActionResult,
  ListData,
  Loan,
  LoginData,
  PagedData,
  Reservation,
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

const seg = (value: string) => encodeURIComponent(value);

function createTransport(baseUrl: string, ctx: ClientContext): AxiosInstance {
  const instance = axios.create({
    baseURL: `${baseUrl}${config.apiPrefix}`,
    timeout: config.requestTimeoutMs,
    headers: { Accept: "application/json" },
    withCredentials: false,
  });
  instance.interceptors.request.use((req) => {
    const token = ctx.getToken();
    if (token) req.headers.set("Authorization", `Bearer ${token}`);
    return req;
  });
  return instance;
}

function toApiError(err: unknown): ApiError {
  if (err instanceof ApiError) return err;
  const axErr = err as AxiosError<ApiEnvelope<unknown>>;
  if (axErr?.isAxiosError) {
    if (axErr.response) {
      const body = axErr.response.data;
      const status = axErr.response.status;
      if (body && typeof body === "object" && body.status === "error" && body.error) {
        return new ApiError(body.error.code, body.error.message, status, body.trace_id ?? null);
      }
      const code = status === 401 ? "unauthorized" : status === 403 ? "forbidden" : status === 404 ? "not_found" : "internal_error";
      return new ApiError(code, "The service returned an unexpected response.", status);
    }
    if (axErr.code === "ECONNABORTED" || axErr.code === "ETIMEDOUT") {
      return new ApiError("timeout", "The request timed out. Please retry.");
    }
    return new ApiError("network_error", "Cannot reach the service. Check that it is running and retry.");
  }
  return new ApiError("internal_error", "Something went wrong. Please try again.");
}

/** Unwrap the {status, data, trace_id} envelope; map failures to ApiError. */
function makeCaller(ctx: ClientContext) {
  return async function call<T>(request: Promise<{ data: ApiEnvelope<T> }>, opts: { notifyUnauthorized?: boolean } = {}): Promise<T> {
    try {
      const { data: body } = await request;
      if (body?.status === "success") return body.data;
      if (body?.status === "error") throw new ApiError(body.error.code, body.error.message, null, body.trace_id);
      throw new ApiError("internal_error", "The service returned an unexpected response.");
    } catch (err) {
      const apiErr = toApiError(err);
      if (apiErr.isUnauthorized && opts.notifyUnauthorized !== false) ctx.onUnauthorized();
      throw apiErr;
    }
  };
}

class HttpAuthClient implements AuthClient {
  constructor(
    private http: AxiosInstance,
    private call: ReturnType<typeof makeCaller>,
  ) {}
  login(email: string, password: string) {
    // A 401 here means bad credentials, not an expired session.
    return this.call<LoginData>(this.http.post("/auth/login", { email, password }), { notifyUnauthorized: false });
  }
  me() {
    return this.call<User>(this.http.get("/auth/me"));
  }
  profile() {
    return this.call<User>(this.http.get("/me/profile"));
  }
}

class HttpCatalogClient implements CatalogClient {
  constructor(
    private http: AxiosInstance,
    private call: ReturnType<typeof makeCaller>,
  ) {}
  searchResources(query: ResourceQuery) {
    const params = Object.fromEntries(Object.entries(query).filter(([, v]) => v !== undefined && v !== ""));
    return this.call<PagedData<Resource>>(this.http.get("/resources", { params }));
  }
  getResource(resourceId: string) {
    return this.call<Resource>(this.http.get(`/resources/${seg(resourceId)}`));
  }
  getAvailability(resourceId: string) {
    return this.call<Availability>(this.http.get(`/resources/${seg(resourceId)}/availability`));
  }
  getContent(resourceId: string) {
    return this.call<ResourceContent>(this.http.get(`/resources/${seg(resourceId)}/content`));
  }
}

class HttpCirculationClient implements CirculationClient {
  constructor(
    private http: AxiosInstance,
    private call: ReturnType<typeof makeCaller>,
  ) {}
  async listLoans() {
    return (await this.call<ListData<Loan>>(this.http.get("/me/loans"))).items;
  }
  renewLoan(loanId: string) {
    return this.call<Loan>(this.http.post(`/loans/${seg(loanId)}/renew`, {}));
  }
  createReservation(resourceId: string) {
    return this.call<Reservation>(this.http.post("/reservations", { resource_id: resourceId }));
  }
  async listReservations() {
    return (await this.call<ListData<Reservation>>(this.http.get("/me/reservations"))).items;
  }
}

class HttpAnalyticsClient implements AnalyticsClient {
  constructor(
    private http: AxiosInstance,
    private call: ReturnType<typeof makeCaller>,
  ) {}
  getSummary() {
    return this.call<AnalyticsSummary>(this.http.get("/analytics/summary"));
  }
}

class HttpChatClient implements ChatClient {
  constructor(
    private http: AxiosInstance,
    private call: ReturnType<typeof makeCaller>,
  ) {}
  sendMessage(request: ChatRequest) {
    return this.call<ChatResponse>(this.http.post("/chat/messages", request));
  }
  confirmAction(actionId: string) {
    return this.call<ConfirmActionResult>(this.http.post("/chat/actions/confirm", { action_id: actionId }));
  }
  health() {
    return this.call<AiHealth>(this.http.get("/health"), { notifyUnauthorized: false });
  }
}

export function createHttpClients(ctx: ClientContext): ApiClients {
  const backend = createTransport(config.backendUrl, ctx);
  const ai = createTransport(config.aiUrl, ctx);
  const call = makeCaller(ctx);
  return {
    auth: new HttpAuthClient(backend, call),
    catalog: new HttpCatalogClient(backend, call),
    circulation: new HttpCirculationClient(backend, call),
    analytics: new HttpAnalyticsClient(backend, call),
    chat: new HttpChatClient(ai, call),
  };
}
