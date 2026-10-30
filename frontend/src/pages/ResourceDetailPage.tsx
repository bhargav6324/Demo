import { ArrowLeft, BookmarkPlus, CalendarClock, ExternalLink, FileSearch, Lock, MapPin, RefreshCw, Users } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { toApiError } from "../api";
import { useApi } from "../app/ApiProvider";
import { AvailabilityBadge } from "../components/AvailabilityBadge";
import { ConfirmActionDialog } from "../components/ConfirmActionDialog";
import { LEVEL_TONES, ResourceCover } from "../components/ResourceCard";
import { EmptyState, ErrorState, LoadingSkeleton } from "../components/states";
import { Badge, Button, Card, cx } from "../components/ui";
import { useAsync } from "../hooks/useAsync";
import { useReservation } from "../hooks/useReservation";
import { formatDate } from "../lib/format";
import { isDigitalType, LEVEL_LABELS, TYPE_LABELS } from "../lib/labels";
import type { Availability, Resource } from "../types/models";

const ACCESS_LABELS: Record<string, string> = { open: "Open to all", members: "Members only", restricted: "Restricted" };

function isSafeHttpsUrl(url: string | null): url is string {
  if (!url) return false;
  try {
    return new URL(url).protocol === "https:";
  } catch {
    return false;
  }
}

export function ResourceDetailPage() {
  const { resourceId = "" } = useParams();
  const { catalog } = useApi();
  const navigate = useNavigate();

  const resource = useAsync(() => catalog.getResource(resourceId), [catalog, resourceId]);
  const availability = useAsync(() => catalog.getAvailability(resourceId), [catalog, resourceId]);
  const content = useAsync(() => catalog.getContent(resourceId), [catalog, resourceId]);

  const back = (
    <button onClick={() => navigate(-1)} className="inline-flex items-center gap-1.5 text-sm font-medium text-ink-soft hover:text-ink">
      <ArrowLeft className="h-4 w-4" aria-hidden /> Back
    </button>
  );

  if (resource.loading && !resource.data) {
    return (
      <div className="space-y-6">
        {back}
        <Card className="p-6">
          <LoadingSkeleton lines={6} />
        </Card>
      </div>
    );
  }

  if (resource.error) {
    const err = toApiError(resource.error);
    return (
      <div className="space-y-6">
        {back}
        {err.isNotFound ? (
          <EmptyState
            icon={FileSearch}
            title="Resource not found"
            description="This resource doesn't exist or isn't available to your account."
            action={
              <Link to="/discover" className="text-sm font-semibold text-brand-700 hover:underline">
                Browse the catalog
              </Link>
            }
          />
        ) : (
          <ErrorState error={resource.error} onRetry={resource.reload} />
        )}
      </div>
    );
  }

  const r = resource.data!;
  const contentUrl = content.data?.url ?? null;

  return (
    <div className="space-y-6">
      {back}

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,1fr)_340px]">
        {/* Main details */}
        <div className="space-y-6">
          <Card className="p-6 sm:p-8">
            <div className="flex flex-col gap-6 sm:flex-row">
              <ResourceCover type={r.type} className="h-36 w-28 rounded-2xl" />
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge tone="neutral">{TYPE_LABELS[r.type] ?? r.type}</Badge>
                  <Badge tone={LEVEL_TONES[r.level] ?? "neutral"}>{LEVEL_LABELS[r.level] ?? r.level}</Badge>
                  {r.access_level !== "open" && (
                    <Badge tone="warning">
                      <Lock className="h-3 w-3" aria-hidden /> {ACCESS_LABELS[r.access_level] ?? r.access_level}
                    </Badge>
                  )}
                </div>
                <h1 className="mt-3 text-2xl font-bold tracking-tight text-ink sm:text-3xl">{r.title}</h1>
                <p className="mt-1.5 flex items-center gap-1.5 text-ink-soft">
                  <Users className="h-4 w-4 flex-none text-ink-muted" aria-hidden />
                  {r.authors.join(", ")}
                </p>
              </div>
            </div>

            <p className="mt-6 leading-relaxed text-ink-soft">{r.description}</p>

            <dl className="mt-6 grid gap-4 border-t border-slate-100 pt-6 sm:grid-cols-2">
              <div>
                <dt className="text-xs font-semibold uppercase tracking-wider text-ink-muted">Topics</dt>
                <dd className="mt-2 flex flex-wrap gap-1.5">
                  {r.topics.map((t) => (
                    <Link
                      key={t}
                      to={`/discover?q=${encodeURIComponent(t)}`}
                      className="rounded-md bg-slate-100 px-2 py-0.5 text-sm font-medium text-slate-700 hover:bg-brand-50 hover:text-brand-700"
                    >
                      {t}
                    </Link>
                  ))}
                </dd>
              </div>
              <div>
                <dt className="text-xs font-semibold uppercase tracking-wider text-ink-muted">Catalog record</dt>
                <dd className="mt-2 space-y-1 text-sm text-ink-soft">
                  <p className="flex items-center gap-1.5">
                    <CalendarClock className="h-4 w-4 text-ink-muted" aria-hidden /> Updated {formatDate(r.updated_at)}
                  </p>
                  <p className="font-mono text-xs text-ink-muted">{r.resource_id}</p>
                </dd>
              </div>
            </dl>
          </Card>

          {content.data?.body && (
            <Card className="p-6">
              <h2 className="text-sm font-semibold text-ink">Preview</h2>
              <p className="mt-1 text-xs text-ink-muted">Authorised excerpt supplied by the library</p>
              <blockquote className="mt-4 border-l-4 border-accent-400 pl-4 text-[15px] italic leading-relaxed text-ink-soft">{content.data.body}</blockquote>
            </Card>
          )}
        </div>

        {/* Availability & actions */}
        <AvailabilityPanel
          resource={r}
          availability={availability.data}
          loading={availability.loading}
          error={availability.error}
          onRefresh={availability.reload}
          onlineUrl={isSafeHttpsUrl(contentUrl) ? contentUrl : null}
        />
      </div>
    </div>
  );
}

function AvailabilityPanel({
  resource,
  availability,
  loading,
  error,
  onRefresh,
  onlineUrl,
}: {
  resource: Resource;
  availability?: Availability;
  loading: boolean;
  error: unknown;
  onRefresh(): void;
  onlineUrl: string | null;
}) {
  const [confirming, setConfirming] = useState(false);
  const { reserve, pending } = useReservation(() => onRefresh());
  const digital = isDigitalType(resource.type);
  const canReserve = !!availability && availability.total_copies > 0;
  const hasCopyFree = !!availability && availability.available_copies > 0;

  async function confirm() {
    await reserve(resource.resource_id, resource.title);
    setConfirming(false);
  }

  return (
    <aside className="space-y-4 lg:sticky lg:top-24 lg:self-start" aria-label="Availability">
      <Card className="p-5">
        <div className="flex items-center justify-between">
          <h2 className="font-semibold text-ink">Availability</h2>
          <button
            onClick={onRefresh}
            disabled={loading}
            aria-label="Refresh availability"
            className="rounded-md p-1.5 text-ink-muted transition hover:bg-slate-100 hover:text-ink disabled:opacity-50"
          >
            <RefreshCw className={cx("h-4 w-4", loading && "animate-spin")} />
          </button>
        </div>

        {error && !availability ? (
          <ErrorState error={error} onRetry={onRefresh} className="mt-4 !px-4 !py-6" />
        ) : (
          <>
            <div className="mt-3">
              <AvailabilityBadge availability={availability} resourceType={resource.type} loading={loading} />
            </div>

            {availability && availability.total_copies > 0 && (
              <>
                <dl className="mt-4 grid grid-cols-3 divide-x divide-slate-100 rounded-xl border border-slate-200 text-center">
                  {[
                    ["Available", availability.available_copies],
                    ["Total", availability.total_copies],
                    ["Waitlist", availability.waitlist_count],
                  ].map(([label, value]) => (
                    <div key={label} className="px-2 py-3">
                      <dd className="text-xl font-bold text-ink">{value}</dd>
                      <dt className="text-xs text-ink-muted">{label}</dt>
                    </div>
                  ))}
                </dl>

                <h3 className="mt-5 text-xs font-semibold uppercase tracking-wider text-ink-muted">Locations</h3>
                <ul className="mt-2 space-y-2">
                  {availability.locations.map((loc) => (
                    <li key={`${loc.branch}-${loc.shelf}`} className="flex items-center gap-3 rounded-lg bg-slate-50 px-3 py-2.5">
                      <MapPin className="h-4 w-4 flex-none text-accent-600" aria-hidden />
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-sm font-medium text-ink">{loc.branch}</p>
                        <p className="text-xs text-ink-muted">Shelf {loc.shelf}</p>
                      </div>
                      <span className={cx("text-xs font-semibold", loc.available_copies > 0 ? "text-emerald-700" : "text-ink-muted")}>
                        {loc.available_copies > 0 ? `${loc.available_copies} on shelf` : "None free"}
                      </span>
                    </li>
                  ))}
                </ul>
              </>
            )}

            <div className="mt-5 space-y-2">
              {canReserve && (
                <Button className="w-full" onClick={() => setConfirming(true)} disabled={pending || loading}>
                  <BookmarkPlus className="h-4 w-4" aria-hidden />
                  {hasCopyFree ? "Reserve a copy" : "Join waitlist"}
                </Button>
              )}
              {onlineUrl && (
                <a
                  href={onlineUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex h-10 w-full items-center justify-center gap-2 rounded-lg border border-slate-200 bg-white text-sm font-semibold text-ink shadow-sm transition hover:bg-slate-50"
                >
                  <ExternalLink className="h-4 w-4" aria-hidden /> Open online
                </a>
              )}
              {!canReserve && !onlineUrl && availability && (
                <p className="text-sm text-ink-muted">{digital ? "Online access link is not available yet." : "This title has no physical copies to reserve."}</p>
              )}
            </div>
          </>
        )}
      </Card>
      <p className="px-1 text-xs text-ink-muted">Availability is read live from the library system and re-checked when you reserve.</p>

      <ConfirmActionDialog
        open={confirming}
        title={hasCopyFree ? "Reserve this title?" : "Join the waitlist?"}
        description={
          <>
            <span className="font-medium text-ink">“{resource.title}”</span>{" "}
            {hasCopyFree
              ? "will be held for you if a copy is still free when you confirm."
              : "has no free copies right now. You'll be added to the waitlist; check My Library for your position."}
          </>
        }
        confirmLabel={hasCopyFree ? "Confirm reservation" : "Join waitlist"}
        pending={pending}
        onConfirm={confirm}
        onCancel={() => setConfirming(false)}
      />
    </aside>
  );
}
