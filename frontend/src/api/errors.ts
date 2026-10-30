/** Every client (mock or HTTP) throws this; pages never see transport details. */
export type ApiErrorCode =
  | "unauthorized"
  | "forbidden"
  | "not_found"
  | "conflict"
  | "validation_error"
  | "network_error"
  | "timeout"
  | "internal_error"
  | (string & {});

export class ApiError extends Error {
  constructor(
    public readonly code: ApiErrorCode,
    message: string,
    public readonly httpStatus: number | null = null,
    public readonly traceId: string | null = null,
  ) {
    super(message);
    this.name = "ApiError";
  }

  get isUnauthorized() {
    return this.code === "unauthorized" || this.httpStatus === 401;
  }
  get isForbidden() {
    return this.code === "forbidden" || this.httpStatus === 403;
  }
  get isNotFound() {
    return this.code === "not_found" || this.httpStatus === 404;
  }
  get isConflict() {
    return this.code === "conflict" || this.httpStatus === 409;
  }
  /** Transient failures where a retry button makes sense. */
  get isRetryable() {
    return this.code === "network_error" || this.code === "timeout" || (this.httpStatus ?? 0) >= 500;
  }
}

export function toApiError(err: unknown): ApiError {
  if (err instanceof ApiError) return err;
  return new ApiError("internal_error", "Something went wrong. Please try again.");
}
