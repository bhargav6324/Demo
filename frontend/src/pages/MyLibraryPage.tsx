import { BookOpenCheck, Hourglass, Inbox, PackageCheck, RefreshCw } from "lucide-react";
import { useCallback, useState } from "react";
import { Link } from "react-router-dom";
import { useApi } from "../app/ApiProvider";
import { ConfirmActionDialog } from "../components/ConfirmActionDialog";
import { LoanCard } from "../components/LoanCard";
import { EmptyState, ErrorState, LoadingSkeleton } from "../components/states";
import { Badge, Button, Card, PageHeader, cx } from "../components/ui";
import { useAsync } from "../hooks/useAsync";
import { useRenewal } from "../hooks/useRenewal";
import { formatDate, formatINR, plural } from "../lib/format";
import type { Loan, Reservation, ReservationStatus } from "../types/models";

const RESERVATION_STATUS: Record<ReservationStatus, { label: string; tone: "success" | "warning" | "neutral" | "brand" }> = {
  ready: { label: "Ready for pickup", tone: "success" },
  queued: { label: "On waitlist", tone: "warning" },
  fulfilled: { label: "Collected", tone: "neutral" },
  cancelled: { label: "Cancelled", tone: "neutral" },
};

function SectionSkeleton() {
  return (
    <div className="space-y-3">
      {Array.from({ length: 2 }, (_, i) => (
        <Card key={i} className="p-5">
          <LoadingSkeleton lines={3} />
        </Card>
      ))}
    </div>
  );
}

function LoansSection({ loans, loading, error, reload }: { loans?: Loan[]; loading: boolean; error: unknown; reload(): void }) {
  const [confirming, setConfirming] = useState<Loan | null>(null);
  const { renew, pendingId } = useRenewal(reload);

  async function confirmRenewal() {
    if (!confirming) return;
    await renew(confirming);
    setConfirming(null);
  }

  return (
    <section aria-labelledby="loans-heading" className="space-y-4">
      <div className="flex items-baseline justify-between gap-2">
        <h2 id="loans-heading" className="text-lg font-semibold text-ink">
          Borrowed items
        </h2>
        {loans && <span className="text-sm text-ink-muted">{plural(loans.length, "item")}</span>}
      </div>

      {error && !loans ? (
        <ErrorState error={error} onRetry={reload} />
      ) : !loans ? (
        <SectionSkeleton />
      ) : loans.length === 0 ? (
        <EmptyState
          icon={Inbox}
          title="You have nothing on loan"
          description="Find something to read in the catalog — reserved copies appear here once you collect them."
          action={
            <Link to="/discover" className="text-sm font-semibold text-brand-700 hover:underline">
              Browse the catalog
            </Link>
          }
        />
      ) : (
        <div className={cx("space-y-3 transition-opacity", loading && "opacity-60")}>
          {loans.map((loan) => (
            <LoanCard
              key={loan.loan_id}
              loan={loan}
              pending={pendingId === loan.loan_id}
              disabled={pendingId !== null || loading}
              onRenew={() => setConfirming(loan)}
            />
          ))}
        </div>
      )}

      <ConfirmActionDialog
        open={!!confirming}
        title="Renew this loan?"
        description={
          confirming && (
            <>
              <span className="font-medium text-ink">“{confirming.resource_title}”</span> is currently due {formatDate(confirming.due_at)}. The
              library will confirm your new due date.
            </>
          )
        }
        confirmLabel="Confirm renewal"
        pending={pendingId !== null}
        onConfirm={confirmRenewal}
        onCancel={() => setConfirming(null)}
      />
    </section>
  );
}

function ReservationsSection({ reservations, error, reload }: { reservations?: Reservation[]; error: unknown; reload(): void }) {
  const { catalog } = useApi();
  const ids = reservations?.map((r) => r.resource_id).join(",") ?? "";
  // The reservation contract has no title, so resolve titles via the catalog.
  const titles = useAsync(async () => {
    const unique = [...new Set(ids.split(",").filter(Boolean))];
    const settled = await Promise.allSettled(unique.map((id) => catalog.getResource(id)));
    return Object.fromEntries(unique.map((id, i) => [id, settled[i].status === "fulfilled" ? settled[i].value.title : null]));
  }, [catalog, ids]);

  return (
    <section aria-labelledby="reservations-heading" className="space-y-4">
      <div className="flex items-baseline justify-between gap-2">
        <h2 id="reservations-heading" className="text-lg font-semibold text-ink">
          Reservations
        </h2>
        {reservations && <span className="text-sm text-ink-muted">{plural(reservations.length, "reservation")}</span>}
      </div>

      {error && !reservations ? (
        <ErrorState error={error} onRetry={reload} />
      ) : !reservations ? (
        <SectionSkeleton />
      ) : reservations.length === 0 ? (
        <EmptyState icon={Hourglass} title="No reservations" description="Reserve a title from its catalog page and it will appear here." />
      ) : (
        <Card className="divide-y divide-slate-100">
          {reservations.map((r) => {
            const status = RESERVATION_STATUS[r.status] ?? { label: r.status, tone: "neutral" as const };
            const title = titles.data?.[r.resource_id];
            return (
              <div key={r.reservation_id} className="flex flex-wrap items-center gap-3 p-4 sm:flex-nowrap sm:px-5" aria-label={title ?? r.resource_id}>
                <span
                  className={cx(
                    "grid h-10 w-10 flex-none place-items-center rounded-xl",
                    r.status === "ready" ? "bg-emerald-50 text-emerald-600" : "bg-amber-50 text-amber-600",
                  )}
                  aria-hidden
                >
                  {r.status === "ready" ? <PackageCheck className="h-5 w-5" /> : <Hourglass className="h-5 w-5" />}
                </span>
                <div className="min-w-0 flex-1">
                  {titles.loading && !titles.data ? (
                    <span className="block h-4 w-48 animate-pulse rounded bg-slate-100" />
                  ) : (
                    <Link to={`/discover/${encodeURIComponent(r.resource_id)}`} className="font-medium text-ink hover:text-brand-700 hover:underline">
                      {title ?? r.resource_id}
                    </Link>
                  )}
                  <p className="text-xs text-ink-muted">
                    Reference <span className="font-mono">{r.reservation_id}</span>
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  {r.status === "queued" && r.queue_position !== null && (
                    <span className="text-sm font-semibold text-ink">#{r.queue_position} in queue</span>
                  )}
                  <Badge tone={status.tone}>{status.label}</Badge>
                </div>
              </div>
            );
          })}
        </Card>
      )}
    </section>
  );
}

export function MyLibraryPage() {
  const { circulation } = useApi();
  const loans = useAsync(() => circulation.listLoans(), [circulation]);
  const reservations = useAsync(() => circulation.listReservations(), [circulation]);
  const refresh = useCallback(() => {
    loans.reload();
    reservations.reload();
  }, [loans, reservations]);

  const overdue = loans.data?.filter((l) => l.status === "overdue") ?? [];
  const fines = loans.data?.reduce((sum, l) => sum + l.fine_amount, 0) ?? 0;
  const ready = reservations.data?.filter((r) => r.status === "ready").length ?? 0;

  return (
    <div className="space-y-8">
      <PageHeader
        eyebrow="Account"
        title="My Library"
        description="Your borrowed items, due dates and reservations — straight from the library system."
        actions={
          <Button variant="secondary" size="sm" onClick={refresh} disabled={loans.loading || reservations.loading}>
            <RefreshCw className={cx("h-4 w-4", (loans.loading || reservations.loading) && "animate-spin")} aria-hidden /> Refresh
          </Button>
        }
      />

      {(overdue.length > 0 || ready > 0) && (
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
          {overdue.length > 0 && (
            <div role="note" className="flex items-start gap-3 rounded-2xl border border-red-200 bg-red-50 p-4">
              <BookOpenCheck className="mt-0.5 h-5 w-5 flex-none text-red-600" aria-hidden />
              <div>
                <p className="font-semibold text-red-900">{plural(overdue.length, "overdue item")}</p>
                <p className="text-sm text-red-800">
                  Please return {overdue.length === 1 ? "it" : "them"} soon.{fines > 0 && ` Outstanding fines: ${formatINR(fines)}.`}
                </p>
              </div>
            </div>
          )}
          {ready > 0 && (
            <div role="note" className="flex items-start gap-3 rounded-2xl border border-emerald-200 bg-emerald-50 p-4">
              <PackageCheck className="mt-0.5 h-5 w-5 flex-none text-emerald-600" aria-hidden />
              <div>
                <p className="font-semibold text-emerald-900">{plural(ready, "reservation")} ready for pickup</p>
                <p className="text-sm text-emerald-800">Collect from the library desk.</p>
              </div>
            </div>
          )}
        </div>
      )}

      <LoansSection loans={loans.data} loading={loans.loading} error={loans.error} reload={loans.reload} />
      <ReservationsSection reservations={reservations.data} error={reservations.error} reload={reservations.reload} />
    </div>
  );
}
