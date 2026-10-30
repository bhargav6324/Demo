import { AlertTriangle, BookCopy, BookOpen, FlaskConical, Hourglass, RefreshCw } from "lucide-react";
import { Link } from "react-router-dom";
import { useApi } from "../app/ApiProvider";
import { AnalyticsCard } from "../components/AnalyticsCard";
import { PopularResourcesChart } from "../components/PopularResourcesChart";
import { EmptyState, ErrorState, LoadingSkeleton } from "../components/states";
import { Badge, Button, Card, PageHeader, cx } from "../components/ui";
import { config } from "../config";
import { useAsync } from "../hooks/useAsync";
import type { AnalyticsSummary } from "../types/models";

function LoanHealth({ summary }: { summary: AnalyticsSummary }) {
  const { active_loans: active, overdue_loans: overdue } = summary;
  const share = active > 0 ? overdue / active : 0;
  const pct = Math.round(share * 100);
  const severity = share >= 0.25 ? "danger" : share >= 0.1 ? "warning" : "ok";
  return (
    <Card className="p-5">
      <h2 className="font-semibold text-ink">Loan health</h2>
      <p className="text-sm text-ink-muted">Share of active loans that are overdue</p>
      <p className="mt-4 text-3xl font-semibold tracking-tight text-ink">{pct}%</p>
      <div
        className={cx("mt-3 h-2.5 overflow-hidden rounded-full", severity === "danger" ? "bg-red-100" : severity === "warning" ? "bg-amber-100" : "bg-emerald-100")}
        role="meter"
        aria-label="Overdue share of active loans"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={pct}
      >
        <div
          className={cx("h-full rounded-full", severity === "danger" ? "bg-red-500" : severity === "warning" ? "bg-amber-500" : "bg-emerald-500")}
          style={{ width: `${pct}%` }}
        />
      </div>
      <p className="mt-2 flex items-center gap-1.5 text-sm text-ink-soft">
        {severity !== "ok" && <AlertTriangle className={cx("h-4 w-4", severity === "danger" ? "text-red-600" : "text-amber-600")} aria-hidden />}
        {overdue.toLocaleString()} of {active.toLocaleString()} active loans overdue
      </p>
    </Card>
  );
}

function WaitlistDemand({ summary }: { summary: AnalyticsSummary }) {
  const waiting = summary.popular_resources.filter((r) => r.reservation_count > 0).sort((a, b) => b.reservation_count - a.reservation_count);
  return (
    <Card className="p-5">
      <h2 className="font-semibold text-ink">Reservation demand</h2>
      <p className="text-sm text-ink-muted">Popular titles with active reservations</p>
      {waiting.length === 0 ? (
        <p className="mt-4 text-sm text-ink-muted">No active reservations on popular titles.</p>
      ) : (
        <ul className="mt-3 divide-y divide-slate-100">
          {waiting.slice(0, 5).map((r) => (
            <li key={r.resource_id} className="flex items-center justify-between gap-3 py-2.5">
              <Link to={`/discover/${encodeURIComponent(r.resource_id)}`} className="min-w-0 truncate text-sm font-medium text-ink hover:text-brand-700 hover:underline">
                {r.title}
              </Link>
              <Badge tone="warning">
                <Hourglass className="h-3 w-3" aria-hidden /> {r.reservation_count}
              </Badge>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

function PopularTable({ summary }: { summary: AnalyticsSummary }) {
  const rows = [...summary.popular_resources].sort((a, b) => b.borrow_count - a.borrow_count);
  const max = Math.max(1, ...rows.map((r) => r.borrow_count));
  return (
    <Card className="overflow-hidden">
      <div className="border-b border-slate-200 px-5 py-4">
        <h2 className="font-semibold text-ink">Popular resources</h2>
        <p className="text-sm text-ink-muted">Ranked by borrow count, with current reservations</p>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[520px] text-sm">
          <caption className="sr-only">Popular resources ranked by borrow count</caption>
          <thead className="bg-slate-50 text-left text-xs font-semibold uppercase tracking-wider text-ink-muted">
            <tr>
              <th scope="col" className="w-12 px-5 py-2.5">
                #
              </th>
              <th scope="col" className="px-3 py-2.5">
                Title
              </th>
              <th scope="col" className="px-3 py-2.5 text-right">
                Borrows
              </th>
              <th scope="col" className="hidden w-40 px-3 py-2.5 md:table-cell">
                <span className="sr-only">Relative demand</span>
              </th>
              <th scope="col" className="px-5 py-2.5 text-right">
                Reservations
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {rows.map((r, i) => (
              <tr key={r.resource_id} className="transition-colors hover:bg-slate-50/70">
                <td className="px-5 py-3 font-medium text-ink-muted">{i + 1}</td>
                <td className="px-3 py-3">
                  <Link to={`/discover/${encodeURIComponent(r.resource_id)}`} className="font-medium text-ink hover:text-brand-700 hover:underline">
                    {r.title}
                  </Link>
                </td>
                <td className="px-3 py-3 text-right font-semibold tabular-nums text-ink">{r.borrow_count.toLocaleString()}</td>
                <td className="hidden px-3 py-3 md:table-cell" aria-hidden>
                  <div className="h-1.5 rounded-full bg-brand-100">
                    <div className="h-full rounded-full bg-brand-600" style={{ width: `${(r.borrow_count / max) * 100}%` }} />
                  </div>
                </td>
                <td className="px-5 py-3 text-right tabular-nums text-ink-soft">{r.reservation_count.toLocaleString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

export function AnalyticsPage() {
  const { analytics } = useApi();
  const { data, error, loading, reload } = useAsync(() => analytics.getSummary(), [analytics]);

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Librarian"
        title="Analytics"
        description="Collection demand and circulation at a glance."
        actions={
          <>
            {config.apiMode === "mock" && (
              <Badge tone="warning">
                <FlaskConical className="h-3 w-3" aria-hidden /> Fixture data
              </Badge>
            )}
            <Button variant="secondary" size="sm" onClick={reload} disabled={loading}>
              <RefreshCw className={cx("h-4 w-4", loading && "animate-spin")} aria-hidden /> Refresh
            </Button>
          </>
        }
      />

      {error && !data ? (
        <ErrorState error={error} onRetry={reload} />
      ) : !data ? (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {Array.from({ length: 4 }, (_, i) => (
            <Card key={i} className="p-5">
              <LoadingSkeleton lines={2} />
            </Card>
          ))}
        </div>
      ) : (
        <div className={cx("space-y-6 transition-opacity", loading && "opacity-70")}>
          <section aria-label="Key metrics" className="grid grid-cols-2 gap-3 sm:gap-4 xl:grid-cols-4">
            <AnalyticsCard icon={BookCopy} label="Total resources" value={data.total_resources} hint="Titles in the catalog" />
            <AnalyticsCard icon={BookOpen} label="Active loans" value={data.active_loans} hint="Currently borrowed" tone="accent" />
            <AnalyticsCard
              icon={AlertTriangle}
              label="Overdue loans"
              value={data.overdue_loans}
              hint={data.active_loans ? `${Math.round((data.overdue_loans / data.active_loans) * 100)}% of active loans` : "No active loans"}
              tone="danger"
            />
            <AnalyticsCard icon={Hourglass} label="Active reservations" value={data.active_reservations} hint="Queued or ready for pickup" tone="warning" />
          </section>

          <div className="grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
            <Card className="p-5">
              <h2 className="font-semibold text-ink">Most borrowed resources</h2>
              <p className="mb-4 text-sm text-ink-muted">Borrow count per title</p>
              {data.popular_resources.length ? (
                <PopularResourcesChart data={data.popular_resources} />
              ) : (
                <EmptyState title="No circulation data yet" description="Borrowing activity will appear here." className="!py-8" />
              )}
            </Card>
            <div className="space-y-6">
              <LoanHealth summary={data} />
              <WaitlistDemand summary={data} />
            </div>
          </div>

          {data.popular_resources.length > 0 && <PopularTable summary={data} />}
        </div>
      )}
    </div>
  );
}
