import { useCallback, useRef, useState } from "react";
import { toApiError } from "../api";
import { useApi } from "../app/ApiProvider";
import { useToast } from "../app/ToastProvider";
import type { Reservation } from "../types/models";

/**
 * Places a reservation through CirculationClient. A ref guard guarantees one
 * request per user action even if the button is clicked repeatedly. Success
 * messages come only from the returned Reservation, never from assumptions.
 */
export function useReservation(onSuccess?: (reservation: Reservation) => void) {
  const { circulation } = useApi();
  const toast = useToast();
  const inFlight = useRef(false);
  const [pending, setPending] = useState(false);

  const reserve = useCallback(
    async (resourceId: string, title: string): Promise<Reservation | null> => {
      if (inFlight.current) return null;
      inFlight.current = true;
      setPending(true);
      try {
        const reservation = await circulation.createReservation(resourceId);
        toast(
          "success",
          reservation.status === "ready"
            ? `Reserved “${title}”. A copy is being held for you.`
            : `Added to the waitlist for “${title}”${reservation.queue_position ? ` — position ${reservation.queue_position}` : ""}.`,
        );
        onSuccess?.(reservation);
        return reservation;
      } catch (err) {
        const apiErr = toApiError(err);
        if (!apiErr.isUnauthorized) toast(apiErr.isConflict ? "warning" : "error", apiErr.message);
        return null;
      } finally {
        inFlight.current = false;
        setPending(false);
      }
    },
    [circulation, onSuccess, toast],
  );

  return { reserve, pending };
}
