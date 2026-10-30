// Contract tests for the real HTTP clients, using a fake axios adapter (no network).
import axios, { AxiosError, AxiosHeaders, type AxiosAdapter, type InternalAxiosRequestConfig } from "axios";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../api";
import { createHttpClients } from "../api/http/clients";

type Reply = { status: number; body?: unknown } | { network: "timeout" | "down" };
const calls: InternalAxiosRequestConfig[] = [];
const originalAdapter = axios.defaults.adapter;

function serve(reply: (config: InternalAxiosRequestConfig) => Reply) {
  const adapter: AxiosAdapter = async (config) => {
    calls.push(config);
    const r = reply(config);
    if ("network" in r) {
      throw new AxiosError(r.network, r.network === "timeout" ? "ECONNABORTED" : "ERR_NETWORK", config);
    }
    const response = { data: r.body, status: r.status, statusText: "", headers: {}, config, request: {} };
    if (r.status >= 200 && r.status < 300) return response;
    throw new AxiosError(`HTTP ${r.status}`, "ERR_BAD_RESPONSE", config, {}, response);
  };
  axios.defaults.adapter = adapter;
}

const ok = (data: unknown) => ({ status: 200, body: { status: "success", data, trace_id: "tr-1" } });
const fail = (status: number, code: string, message: string) => ({ status, body: { status: "error", error: { code, message }, trace_id: "tr-err" } });

function clients(token: string | null = "secret-token") {
  const onUnauthorized = vi.fn();
  return { api: createHttpClients({ getToken: () => token, onUnauthorized }), onUnauthorized };
}

afterEach(() => {
  axios.defaults.adapter = originalAdapter;
  calls.length = 0;
});

describe("HTTP clients", () => {
  it("unwraps the success envelope and sends the bearer token to the backend URL", async () => {
    serve(() => ok({ items: [], total: 0 }));
    const { api } = clients();
    await expect(api.catalog.searchResources({ query: "python", limit: 5, type: undefined })).resolves.toEqual({ items: [], total: 0 });
    const req = calls[0];
    expect(req.baseURL).toBe("http://localhost:8000/api/v1");
    expect(req.url).toBe("/resources");
    expect(req.params).toEqual({ query: "python", limit: 5 });
    expect(AxiosHeaders.from(req.headers).get("Authorization")).toBe("Bearer secret-token");
  });

  it("returns data.items for list endpoints and encodes path ids", async () => {
    serve(() => ok({ items: [{ loan_id: "loan-001" }] }));
    const { api } = clients();
    await expect(api.circulation.listLoans()).resolves.toEqual([{ loan_id: "loan-001" }]);
    await api.catalog.getAvailability("res/../x");
    expect(calls[1].url).toBe("/resources/res%2F..%2Fx/availability");
  });

  it("sends chat calls to the AI service", async () => {
    serve(() => ok({ action_id: "a1", action_type: "reservation", transaction_status: "completed", transaction_id: "r1", message: "ok" }));
    const { api } = clients();
    await api.chat.confirmAction("a1");
    expect(calls[0].baseURL).toBe("http://localhost:8001/api/v1");
    expect(calls[0].url).toBe("/chat/actions/confirm");
    expect(JSON.parse(calls[0].data as string)).toEqual({ action_id: "a1" });
  });

  it("maps error envelopes to ApiError with code, message, status and trace id", async () => {
    serve(() => fail(409, "conflict", "Already reserved."));
    const { api, onUnauthorized } = clients();
    const err = await api.circulation.createReservation("res-001").catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err).toMatchObject({ code: "conflict", message: "Already reserved.", httpStatus: 409, traceId: "tr-err" });
    expect(onUnauthorized).not.toHaveBeenCalled();
  });

  it("calls onUnauthorized on 401, except for login with bad credentials", async () => {
    serve(() => fail(401, "unauthorized", "Token expired."));
    const { api, onUnauthorized } = clients();
    await expect(api.auth.me()).rejects.toMatchObject({ code: "unauthorized" });
    expect(onUnauthorized).toHaveBeenCalledOnce();
    await expect(api.auth.login("a@b.edu", "x")).rejects.toMatchObject({ code: "unauthorized" });
    expect(onUnauthorized).toHaveBeenCalledOnce();
  });

  it("maps transport failures to retryable network_error / timeout", async () => {
    // axios.create() captures the adapter, so build fresh clients after each serve().
    serve(() => ({ network: "down" }));
    await expect(clients().api.analytics.getSummary()).rejects.toMatchObject({ code: "network_error", isRetryable: true });
    serve(() => ({ network: "timeout" }));
    await expect(clients().api.analytics.getSummary()).rejects.toMatchObject({ code: "timeout", isRetryable: true });
  });

  it("never surfaces raw non-envelope bodies", async () => {
    serve(() => ({ status: 500, body: "<html>Traceback: secret stack</html>" }));
    const { api } = clients();
    const err = await api.catalog.getResource("res-001").catch((e) => e);
    expect(err.message).toBe("The service returned an unexpected response.");
    expect(err.message).not.toContain("Traceback");
  });
});
