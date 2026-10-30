import {
  AlertTriangle,
  ArrowRight,
  BarChart3,
  BookMarked,
  BookOpen,
  CalendarClock,
  Compass,
  Hourglass,
  Sparkles,
  type LucideIcon,
} from "lucide-react";
import { Link, useNavigate } from "react-router-dom";
import { useApi } from "../app/ApiProvider";
import { useAuth, useCurrentUser } from "../app/AuthProvider";
import { ROLE_LABELS } from "../app/nav";
import { ResourceCard } from "../components/ResourceCard";
import { SearchBar } from "../components/SearchBar";
import { CardSkeleton, EmptyState, ErrorState, LoadingSkeleton } from "../components/states";
import { Badge, Card, cx } from "../components/ui";
import { useAsync } from "../hooks/useAsync";
import { daysUntil, formatDate, formatINR, relativeDue } from "../lib/format";
import type { Role } from "../types/models";

const ROLE_TAGLINES: Record<Role, string> = {
  student: "Find course reading, track your loans and get recommendations that explain themselves.",
  researcher: "Search papers and dissertations, and follow cited evidence back to the source.",
  faculty: "Discover teaching material and keep on top of your borrowing.",
  librarian: "Your own borrowing, plus collection demand and utilisation in Analytics.",
};

const SAMPLE_PROMPTS = [
  "Recommend a beginner Python book",
  "Find papers on retrieval-augmented generation",
  "Reserve a statistics book for me",
  "Can I renew my loans?",
];

function greeting() {
  const h = new Date().getHours();
  return h < 12 ? "Good morning" : h < 17 ? "Good afternoon" : "Good evening";
}

function StatTile({ icon: Icon, label, value, hint, tone }: { icon: LucideIcon; label: string; value: number | string; hint?: string; tone: string }) {
  return (
    <div className="flex items-start gap-3.5 rounded-2xl border border-slate-200 bg-white p-4 shadow-card">
      <span className={cx("grid h-10 w-10 flex-none place-items-center rounded-xl", tone)}>
        <Icon className="h-5 w-5" aria-hidden />
      </span>
      <div className="min-w-0">
        <p className="text-2xl font-bold leading-none text-ink">{value}</p>
        <p className="mt-1.5 text-sm font-medium text-ink-soft">{label}</p>
        {hint && <p className="mt-0.5 truncate text-xs text-ink-muted">{hint}</p>}
      </div>
    </div>
  );
}

function BorrowingOverview() {
  const { circulation } = useApi();
  const loans = useAsync(() => circulation.listLoans(), [circulation]);
  const reservations = useAsync(() => circulation.listReservations(), [circulation]);

  if (loans.error || reservations.error) {
    return (
      <ErrorState
        error={loans.error ?? reservations.error}
        onRetry={() => {
          loans.reload();
          reservations.reload();
        }}
      />
    );
  }
  if (!loans.data || !reservations.data) {
    return (
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {Array.from({ length: 4 }, (_, i) => (
          <div key={i} className="rounded-2xl border border-slate-200 bg-white p-4 shadow-card">
            <LoadingSkeleton lines={2} />
          </div>
        ))}
      </div>
    );
  }

  const active = loans.data;
  const overdue = active.filter((l) => l.status === "overdue");
  const dueSoon = active.filter((l) => l.status === "active" && daysUntil(l.due_at) <= 3);
  const fines = active.reduce((sum, l) => sum + l.fine_amount, 0);
  const activeHolds = reservations.data.filter((r) => r.status === "queued" || r.status === "ready");
  const ready = activeHolds.filter((r) => r.status === "ready").length;

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
      <StatTile icon={BookOpen} label="On loan" value={active.length} hint={active.length ? `Next: ${relativeDue(active[0].due_at)}` : "Nothing borrowed"} tone="bg-brand-50 text-brand-600" />
      <StatTile icon={CalendarClock} label="Due within 3 days" value={dueSoon.length} hint={dueSoon[0]?.resource_title} tone="bg-amber-50 text-amber-600" />
      <StatTile
        icon={AlertTriangle}
        label="Overdue"
        value={overdue.length}
        hint={fines > 0 ? `Fines: ${formatINR(fines)}` : "No fines"}
        tone={overdue.length ? "bg-red-50 text-red-600" : "bg-slate-100 text-slate-500"}
      />
      <StatTile icon={Hourglass} label="Reservations" value={activeHolds.length} hint={ready ? `${ready} ready for pickup` : "None ready yet"} tone="bg-accent-50 text-accent-600" />
    </div>
  );
}

function DueNext() {
  const { circulation } = useApi();
  const { data, error, reload } = useAsync(() => circulation.listLoans(), [circulation]);

  return (
    <Card className="p-5">
      <div className="flex items-center justify-between">
        <h2 className="font-semibold text-ink">Due next</h2>
        <Link to="/my-library" className="text-sm font-semibold text-brand-700 hover:underline">
          My Library
        </Link>
      </div>
      {error ? (
        <ErrorState error={error} onRetry={reload} className="mt-4 !py-6" />
      ) : !data ? (
        <LoadingSkeleton lines={3} className="mt-4" />
      ) : data.length === 0 ? (
        <p className="mt-4 text-sm text-ink-muted">You have no items on loan.</p>
      ) : (
        <ul className="mt-3 divide-y divide-slate-100">
          {data.slice(0, 3).map((loan) => (
            <li key={loan.loan_id} className="flex items-center gap-3 py-3">
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium text-ink">{loan.resource_title}</p>
                <p className="text-xs text-ink-muted">Due {formatDate(loan.due_at)}</p>
              </div>
              <Badge tone={loan.status === "overdue" ? "danger" : daysUntil(loan.due_at) <= 3 ? "warning" : "neutral"}>{relativeDue(loan.due_at)}</Badge>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

function Recommended({ interests }: { interests: string[] }) {
  const { catalog } = useApi();
  const query = interests.join(" ");
  const { data, error, loading, reload } = useAsync(() => catalog.searchResources({ query: query || undefined, limit: 4 }), [catalog, query]);

  return (
    <section aria-labelledby="recommended-heading">
      <div className="mb-3 flex flex-wrap items-end justify-between gap-2">
        <div>
          <h2 id="recommended-heading" className="text-lg font-semibold text-ink">
            {interests.length ? "Picked for your interests" : "From the catalog"}
          </h2>
          {interests.length > 0 && <p className="text-sm text-ink-muted">Based on your profile: {interests.join(", ")}</p>}
        </div>
        <Link to={`/discover${query ? `?q=${encodeURIComponent(query)}` : ""}`} className="inline-flex items-center gap-1 text-sm font-semibold text-brand-700 hover:underline">
          See more <ArrowRight className="h-4 w-4" aria-hidden />
        </Link>
      </div>
      {error ? (
        <ErrorState error={error} onRetry={reload} />
      ) : loading && !data ? (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          <CardSkeleton count={2} />
        </div>
      ) : data && data.items.length === 0 ? (
        <EmptyState title="No matches for your interests yet" description="Update your interests or browse the full catalog." />
      ) : (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          {data?.items.map((r) => <ResourceCard key={r.resource_id} resource={r} />)}
        </div>
      )}
    </section>
  );
}

function AssistantCard() {
  const navigate = useNavigate();
  return (
    <Card className="relative overflow-hidden border-0 bg-gradient-to-br from-brand-700 via-brand-600 to-accent-600 p-5 text-white">
      <div className="pointer-events-none absolute -right-10 -top-10 h-40 w-40 rounded-full bg-white/10 blur-2xl" aria-hidden />
      <div className="relative">
        <span className="grid h-10 w-10 place-items-center rounded-xl bg-white/15 ring-1 ring-white/25">
          <Sparkles className="h-5 w-5" aria-hidden />
        </span>
        <h2 className="mt-3 text-lg font-semibold">Ask the library assistant</h2>
        <p className="mt-1 text-sm text-brand-50/90">Answers cite catalog records. Reservations and renewals always ask you to confirm first.</p>
        <div className="mt-4 flex flex-col gap-2">
          {SAMPLE_PROMPTS.slice(0, 3).map((prompt) => (
            <button
              key={prompt}
              onClick={() => navigate("/assistant", { state: { prompt } })}
              className="group flex items-center justify-between rounded-lg bg-white/10 px-3 py-2 text-left text-sm ring-1 ring-white/15 transition hover:bg-white/20"
            >
              <span className="truncate">“{prompt}”</span>
              <ArrowRight className="h-4 w-4 flex-none opacity-60 transition group-hover:translate-x-0.5 group-hover:opacity-100" aria-hidden />
            </button>
          ))}
        </div>
      </div>
    </Card>
  );
}

function QuickActions() {
  const { hasRole } = useAuth();
  const actions: { to: string; icon: LucideIcon; title: string; text: string }[] = [
    { to: "/discover", icon: Compass, title: "Browse catalog", text: "Filter by type and level" },
    { to: "/my-library", icon: BookMarked, title: "Renew a loan", text: "Check due dates and fines" },
    { to: "/assistant", icon: Sparkles, title: "Ask the assistant", text: "Natural-language search" },
  ];
  if (hasRole("librarian")) actions.push({ to: "/analytics", icon: BarChart3, title: "View analytics", text: "Demand and utilisation" });

  return (
    <section aria-labelledby="quick-actions-heading">
      <h2 id="quick-actions-heading" className="mb-3 text-lg font-semibold text-ink">
        Quick actions
      </h2>
      <div className={cx("grid grid-cols-1 gap-3 sm:grid-cols-2", actions.length > 3 ? "lg:grid-cols-4" : "lg:grid-cols-3")}>
        {actions.map(({ to, icon: Icon, title, text }) => (
          <Link
            key={to}
            to={to}
            className="group flex items-center gap-3 rounded-2xl border border-slate-200 bg-white p-4 shadow-card transition hover:-translate-y-0.5 hover:border-brand-200 hover:shadow-lift"
          >
            <span className="grid h-10 w-10 flex-none place-items-center rounded-xl bg-brand-50 text-brand-600 transition group-hover:bg-brand-600 group-hover:text-white">
              <Icon className="h-5 w-5" aria-hidden />
            </span>
            <span className="min-w-0">
              <span className="block text-sm font-semibold text-ink">{title}</span>
              <span className="block truncate text-xs text-ink-muted">{text}</span>
            </span>
          </Link>
        ))}
      </div>
    </section>
  );
}

export function DashboardPage() {
  const user = useCurrentUser();
  const navigate = useNavigate();
  const firstName = user.name.replace(/^(dr|prof)\.?\s+/i, "").split(" ")[0];
  const interests = user.interests.length ? user.interests : user.courses;

  return (
    <div className="space-y-8">
      <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-card sm:p-8">
        <div className="flex flex-wrap items-center gap-2">
          <p className="text-sm font-semibold text-accent-700">{greeting()}</p>
          <Badge tone="brand">{ROLE_LABELS[user.role]}</Badge>
        </div>
        <h1 className="mt-1 text-2xl font-bold tracking-tight text-ink sm:text-3xl">Welcome back, {firstName}</h1>
        <p className="mt-1.5 max-w-2xl text-ink-soft">{ROLE_TAGLINES[user.role]}</p>
        <SearchBar
          size="lg"
          className="mt-6 max-w-2xl"
          placeholder="Search books, papers, journals…"
          onSearch={(q) => navigate(q ? `/discover?q=${encodeURIComponent(q)}` : "/discover")}
        />
        {interests.length > 0 && (
          <div className="mt-3 flex flex-wrap items-center gap-2 text-sm">
            <span className="text-ink-muted">Try:</span>
            {interests.slice(0, 4).map((topic) => (
              <Link
                key={topic}
                to={`/discover?q=${encodeURIComponent(topic)}`}
                className="rounded-full border border-slate-200 px-3 py-1 text-ink-soft transition hover:border-brand-300 hover:bg-brand-50 hover:text-brand-700"
              >
                {topic}
              </Link>
            ))}
          </div>
        )}
      </section>

      <section aria-labelledby="borrowing-heading" className="space-y-3">
        <h2 id="borrowing-heading" className="text-lg font-semibold text-ink">
          Borrowing overview
        </h2>
        <BorrowingOverview />
      </section>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,1fr)_320px]">
        <Recommended interests={interests} />
        <div className="space-y-6">
          <AssistantCard />
          <DueNext />
        </div>
      </div>

      <QuickActions />
    </div>
  );
}
