import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, beforeAll, beforeEach } from "vitest";
import { resetMockDb } from "../api/mock/db";

// jsdom lacks ResizeObserver, which Recharts' ResponsiveContainer needs.
globalThis.ResizeObserver ??= class {
  observe() {}
  unobserve() {}
  disconnect() {}
} as unknown as typeof ResizeObserver;

// Warm the lazily-loaded Analytics chunk so findBy* timeouts measure the UI, not module transform.
beforeAll(async () => {
  await import("../pages/AnalyticsPage");
}, 30_000);

beforeEach(() => {
  resetMockDb();
});

afterEach(() => {
  cleanup();
});
