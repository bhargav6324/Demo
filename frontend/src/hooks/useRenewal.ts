import { useCallback, useRef, useState } from "react";
import { toApiError } from "../api";
import { useApi } from "../app/ApiProvider";
import { useToast } from "../app/ToastProvider";
import { formatDate } from "../lib/format";
import type { Loan } from "../types/models";

/**
 * Renews a loan through CirculationClient. One request per user action (ref
 * guard); eligibility is decided by the backend, and `onSettled` refreshes data
 * after both success and conflict so the UI reflects the server's state.
 */
export function useRenewal(onSettled?: () => void) {
  const { circulation } = useApi();
  const toast = useToast();
  const inFlight = useRef(false);
  const [pendingId, setPendingId] = useState<string | null>(null);

  const renew = useCallback(
    async (loan: Loan): Promise<Loan | null> => {
      if (inFlight.current) return null;
      inFlight.current = true;
      setPendingId(loan.loan_id);
      try {
        const updated = await circulation.renewLoan(loan.loan_id);
        toast("success", `Renewed “${updated.resource_title}”. New due date: ${formatDate(updated.due_at)}.`);
        return updated;
      } catch (err) {
        const apiErr = toApiError(err);
        if (!apiErr.isUnauthorized) toast(apiErr.isConflict ? "warning" : "error", apiErr.message);
        return null;
      } finally {
        inFlight.current = false;
        setPendingId(null);
        onSettled?.();
      }
    },
    [circulation, onSettled, toast],
  );

  return { renew, pendingId };
}
