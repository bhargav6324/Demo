import { BookmarkPlus, CircleCheck, CircleX, RefreshCcw, RotateCw } from "lucide-react";
import { useRef, useState } from "react";
import { Link } from "react-router-dom";
import { toApiError, type ApiError } from "../../api";
import { useApi } from "../../app/ApiProvider";
import type { ConfirmActionResult, ProposedAction } from "../../types/models";
import { ConfirmActionDialog } from "../ConfirmActionDialog";
import { Button, cx } from "../ui";

type State =
  | { kind: "idle" }
  | { kind: "pending" }
  | { kind: "done"; result: ConfirmActionResult }
  | { kind: "error"; error: ApiError }
  | { kind: "dismissed" };

/**
 * Shows an AI-proposed action. Nothing happens until the user confirms; the
 * outcome shown comes only from the structured confirmation result.
 */
export function ProposedActionCard({ action }: { action: ProposedAction }) {
  const { chat } = useApi();
  const [state, setState] = useState<State>({ kind: "idle" });
  const [dialogOpen, setDialogOpen] = useState(false);
  const inFlight = useRef(false);
  const Icon = action.action_type === "renewal" ? RefreshCcw : BookmarkPlus;
  const noun = action.action_type === "renewal" ? "renewal" : "reservation";
  const title = action.action_type === "renewal" ? "Renewal" : "Reservation";

  async function confirm() {
    if (inFlight.current) return;
    inFlight.current = true;
    setState({ kind: "pending" });
    try {
      const result = await chat.confirmAction(action.action_id);
      setState({ kind: "done", result });
    } catch (err) {
      setState({ kind: "error", error: toApiError(err) });
    } finally {
      inFlight.current = false;
      setDialogOpen(false);
    }
  }

  if (state.kind === "done") {
    const ok = state.result.transaction_status === "completed";
    return (
      <div
        role="status"
        className={cx("rounded-xl border p-3.5", ok ? "border-emerald-200 bg-emerald-50" : "border-amber-200 bg-amber-50")}
      >
        <p className={cx("flex items-center gap-2 text-sm font-semibold", ok ? "text-emerald-800" : "text-amber-900")}>
          {ok ? <CircleCheck className="h-4 w-4" aria-hidden /> : <CircleX className="h-4 w-4" aria-hidden />}
          {ok ? `${title} confirmed` : `${title} not completed`}
        </p>
        <p className="mt-1 text-sm text-ink-soft">{state.result.message}</p>
        <div className="mt-2 flex flex-wrap items-center gap-3 text-xs text-ink-muted">
          {state.result.transaction_id && (
            <span>
              Reference: <code className="font-mono text-ink-soft">{state.result.transaction_id}</code>
            </span>
          )}
          {ok && (
            <Link to="/my-library" className="font-semibold text-brand-700 hover:underline">
              View in My Library
            </Link>
          )}
        </div>
      </div>
    );
  }

  if (state.kind === "dismissed") {
    return <p className="text-xs italic text-ink-muted">You dismissed this {noun}. Nothing was changed.</p>;
  }

  return (
    <div className="rounded-xl border border-brand-200 bg-brand-50/60 p-3.5">
      <div className="flex items-start gap-3">
        <span className="grid h-9 w-9 flex-none place-items-center rounded-lg bg-white text-brand-600 ring-1 ring-brand-100">
          <Icon className="h-4 w-4" aria-hidden />
        </span>
        <div className="min-w-0 flex-1">
          <p className="text-xs font-semibold uppercase tracking-wider text-brand-700">Needs your confirmation</p>
          <p className="mt-0.5 text-sm font-medium text-ink">{action.description}</p>
          <p className="mt-0.5 text-xs text-ink-muted">Nothing has been changed yet. Eligibility is re-checked when you confirm.</p>
        </div>
      </div>

      {state.kind === "error" && (
        <p role="alert" className="mt-3 rounded-lg bg-white px-3 py-2 text-sm text-red-700 ring-1 ring-red-200">
          {state.error.message}
          {state.error.traceId && <span className="ml-1 text-xs text-ink-muted">(trace {state.error.traceId})</span>}
        </p>
      )}

      <div className="mt-3 flex flex-wrap gap-2">
        {/* Only transient failures may be retried; conflicts/not-found are final. */}
        {(state.kind !== "error" || state.error.isRetryable) && (
        <Button size="sm" onClick={() => setDialogOpen(true)} disabled={state.kind === "pending"}>
          {state.kind === "error" && state.error.isRetryable ? (
            <>
              <RotateCw className="h-3.5 w-3.5" aria-hidden /> Try again
            </>
          ) : (
            `Review ${noun}`
          )}
        </Button>
        )}
        <Button size="sm" variant="ghost" onClick={() => setState({ kind: "dismissed" })} disabled={state.kind === "pending"}>
          Dismiss
        </Button>
      </div>

      <ConfirmActionDialog
        open={dialogOpen}
        title={action.action_type === "renewal" ? "Confirm renewal?" : "Confirm reservation?"}
        description={action.description}
        confirmLabel={action.action_type === "renewal" ? "Confirm renewal" : "Confirm reservation"}
        pending={state.kind === "pending"}
        onConfirm={confirm}
        onCancel={() => setDialogOpen(false)}
      />
    </div>
  );
}
