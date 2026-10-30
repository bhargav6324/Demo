// The only place environment variables are read.
const env = import.meta.env;

export type ApiMode = "mock" | "real";

const trimSlash = (url: string) => url.replace(/\/+$/, "");

export const config = {
  apiMode: (env.VITE_API_MODE === "real" ? "real" : "mock") as ApiMode,
  backendUrl: trimSlash(env.VITE_BACKEND_URL || "http://localhost:8000"),
  aiUrl: trimSlash(env.VITE_AI_URL || "http://localhost:8001"),
  mockLatencyMs: Number(env.VITE_MOCK_LATENCY_MS ?? 350) || 0,
  /** One-click demo logins: on by default in mock mode; set to "true" to show them against a seeded backend. */
  showDemoLogins: env.VITE_SHOW_DEMO_LOGINS ? env.VITE_SHOW_DEMO_LOGINS === "true" : env.VITE_API_MODE !== "real",
  apiPrefix: "/api/v1",
  requestTimeoutMs: 25_000,
} as const;
