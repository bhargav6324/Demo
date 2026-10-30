// Loading, empty and error states shared by every page.
import { RotateCw, SearchX, ServerCrash, ShieldAlert, WifiOff, type LucideIcon } from "lucide-react";
import type { ReactNode } from "react";
import { toApiError } from "../api";
import { Button, cx } from "./ui";

export function LoadingSkeleton({ lines = 3, className }: { lines?: number; className?: string }) {
  return (
    <div className={cx("space-y-3", className)} aria-busy="true" aria-label="Loading">
      {Array.from({ length: lines }, (_, i) => (
        <div
          key={i}
          className="h-4 animate-shimmer rounded-md bg-[length:200%_100%] bg-gradient-to-r from-slate-100 via-slate-200/70 to-slate-100"
          style={{ width: `${100 - ((i * 17) % 40)}%` }}
        />
      ))}
    </div>
  );
}

export function CardSkeleton({ count = 3 }: { count?: number }) {
  return (
    <>
      {Array.from({ length: count }, (_, i) => (
        <div key={i} className="rounded-2xl border border-slate-200 bg-white p-5 shadow-card">
          <LoadingSkeleton lines={4} />
        </div>
      ))}
    </>
  );
}

export function EmptyState({
  icon: Icon = SearchX,
  title,
  description,
  action,
  className,
}: {
  icon?: LucideIcon;
  title: string;
  description?: ReactNode;
  action?: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cx(
        "flex flex-col items-center rounded-2xl border border-dashed border-slate-300 bg-white px-6 py-12 text-center",
        className,
      )}
    >
      <span className="mb-4 grid h-12 w-12 place-items-center rounded-xl bg-brand-50 text-brand-600">
        <Icon className="h-6 w-6" aria-hidden />
      </span>
      <h2 className="text-base font-semibold text-ink">{title}</h2>
      {description && <p className="mt-1.5 max-w-md text-sm text-ink-soft">{description}</p>}
      {action && <div className="mt-5">{action}</div>}
    </div>
  );
}

/** Shows the backend's message (never raw bodies) plus trace ID, with optional retry. */
export function ErrorState({ error, onRetry, className }: { error: unknown; onRetry?: () => void; className?: string }) {
  const err = toApiError(error);
  const Icon = err.code === "network_error" || err.code === "timeout" ? WifiOff : err.isForbidden ? ShieldAlert : ServerCrash;
  const title =
    err.code === "network_error" || err.code === "timeout"
      ? "Connection problem"
      : err.isForbidden
        ? "Access denied"
        : err.isNotFound
          ? "Not found"
          : "Something went wrong";
  return (
    <div role="alert" className={cx("flex flex-col items-center rounded-2xl border border-red-200 bg-red-50/60 px-6 py-10 text-center", className)}>
      <span className="mb-3 grid h-11 w-11 place-items-center rounded-xl bg-white text-red-600 shadow-sm">
        <Icon className="h-5 w-5" aria-hidden />
      </span>
      <h2 className="text-base font-semibold text-ink">{title}</h2>
      <p className="mt-1 max-w-md text-sm text-ink-soft">{err.message}</p>
      {err.traceId && (
        <p className="mt-2 text-xs text-ink-muted">
          Trace ID: <code className="font-mono">{err.traceId}</code>
        </p>
      )}
      {onRetry && err.isRetryable && (
        <Button variant="secondary" size="sm" className="mt-4" onClick={onRetry}>
          <RotateCw className="h-4 w-4" aria-hidden /> Try again
        </Button>
      )}
    </div>
  );
}
