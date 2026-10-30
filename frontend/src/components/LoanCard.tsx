import { BookOpen, CalendarDays, CircleCheck, CircleSlash, IndianRupee, RefreshCcw } from "lucide-react";
import { Link } from "react-router-dom";
import { daysUntil, formatDate, formatINR, relativeDue } from "../lib/format";
import type { Loan } from "../types/models";
import { Badge, Button, cx } from "./ui";

function dueTone(loan: Loan) {
  if (loan.status === "overdue") return "danger" as const;
  if (loan.status === "active" && daysUntil(loan.due_at) <= 3) return "warning" as const;
  return "neutral" as const;
}

export function LoanCard({ loan, pending, disabled, onRenew }: { loan: Loan; pending: boolean; disabled: boolean; onRenew(): void }) {
  const overdue = loan.status === "overdue";
  return (
    <article
      aria-label={loan.resource_title}
      className={cx(
        "flex flex-col gap-4 rounded-2xl border bg-white p-5 shadow-card sm:flex-row sm:items-center",
        overdue ? "border-red-200" : "border-slate-200",
      )}
    >
      <span
        className={cx(
          "grid h-14 w-11 flex-none place-items-center rounded-xl text-white shadow-sm",
          overdue ? "bg-gradient-to-br from-red-500 to-red-700" : "bg-gradient-to-br from-brand-500 to-brand-700",
        )}
        aria-hidden
      >
        <BookOpen className="h-5 w-5" />
      </span>

      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <h3 className="font-semibold text-ink">
            <Link to={`/discover/${encodeURIComponent(loan.resource_id)}`} className="hover:text-brand-700 hover:underline">
              {loan.resource_title}
            </Link>
          </h3>
          <Badge tone={dueTone(loan)}>{overdue ? "Overdue" : relativeDue(loan.due_at)}</Badge>
        </div>
        <dl className="mt-2 flex flex-wrap gap-x-5 gap-y-1 text-sm text-ink-soft">
          <div className="flex items-center gap-1.5">
            <dt className="sr-only">Borrowed</dt>
            <CalendarDays className="h-4 w-4 text-ink-muted" aria-hidden />
            <dd>Borrowed {formatDate(loan.borrowed_at)}</dd>
          </div>
          <div className="flex items-center gap-1.5">
            <dt className="sr-only">Due</dt>
            <dd className={cx("font-medium", overdue ? "text-red-700" : "text-ink")}>
              Due {formatDate(loan.due_at)}
              {overdue && <span className="font-normal"> · {relativeDue(loan.due_at)}</span>}
            </dd>
          </div>
          {loan.fine_amount > 0 && (
            <div className="flex items-center gap-1.5 text-red-700">
              <dt className="sr-only">Fine</dt>
              <IndianRupee className="h-4 w-4" aria-hidden />
              <dd className="font-semibold">Fine {formatINR(loan.fine_amount)}</dd>
            </div>
          )}
        </dl>
        <p className={cx("mt-2 flex items-center gap-1.5 text-xs font-medium", loan.renewable ? "text-emerald-700" : "text-ink-muted")}>
          {loan.renewable ? <CircleCheck className="h-3.5 w-3.5" aria-hidden /> : <CircleSlash className="h-3.5 w-3.5" aria-hidden />}
          {loan.renewable ? "Eligible for renewal" : "Not eligible for renewal"}
        </p>
      </div>

      <Button
        variant={loan.renewable ? "primary" : "secondary"}
        className="w-full sm:w-auto"
        onClick={onRenew}
        loading={pending}
        disabled={!loan.renewable || disabled}
        aria-label={`Renew ${loan.resource_title}`}
        title={loan.renewable ? undefined : "This loan can't be renewed"}
      >
        {!pending && <RefreshCcw className="h-4 w-4" aria-hidden />}
        {pending ? "Renewing…" : "Renew"}
      </Button>
    </article>
  );
}
