import { config } from "../config";
import { createHttpClients } from "./http/clients";
import type { ApiClients, ClientContext } from "./interfaces";
import { createMockClients } from "./mock/clients";

/** The single switch between mock and real services — driven by VITE_API_MODE. */
export function createApiClients(ctx: ClientContext): ApiClients {
  return config.apiMode === "real" ? createHttpClients(ctx) : createMockClients(ctx);
}

export { ApiError, toApiError } from "./errors";
export type * from "./interfaces";
