import { SearchX, SlidersHorizontal } from "lucide-react";
import { useSearchParams } from "react-router-dom";
import { useApi } from "../app/ApiProvider";
import { ResourceCard } from "../components/ResourceCard";
import { SearchBar } from "../components/SearchBar";
import { CardSkeleton, EmptyState, ErrorState } from "../components/states";
import { Button, cx, PageHeader } from "../components/ui";
import { useAsync } from "../hooks/useAsync";
import { isResourceLevel, isResourceType, LEVEL_LABELS, RESOURCE_LEVELS, RESOURCE_TYPES, TYPE_LABELS } from "../lib/labels";
import { plural } from "../lib/format";

const PAGE_SIZE = 24;

function FilterChip({ active, onClick, children }: { active: boolean; onClick(): void; children: string }) {
  return (
    <button
      type="button"
      aria-pressed={active}
      onClick={onClick}
      className={cx(
        "whitespace-nowrap rounded-full border px-3.5 py-1.5 text-sm font-medium transition",
        active ? "border-brand-600 bg-brand-600 text-white shadow-sm" : "border-slate-200 bg-white text-ink-soft hover:border-brand-300 hover:text-ink",
      )}
    >
      {children}
    </button>
  );
}

export function DiscoverPage() {
  const { catalog } = useApi();
  const [params, setParams] = useSearchParams();
  const query = params.get("q") ?? "";
  const typeParam = params.get("type");
  const levelParam = params.get("level");
  const type = isResourceType(typeParam) ? typeParam : undefined;
  const level = isResourceLevel(levelParam) ? levelParam : undefined;

  const { data, error, loading, reload } = useAsync(
    () => catalog.searchResources({ query: query || undefined, type, level, limit: PAGE_SIZE }),
    [catalog, query, type, level],
  );

  const update = (key: string, value: string | undefined) => {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    setParams(next, { replace: key !== "q" });
  };
  const clearAll = () => setParams(new URLSearchParams());
  const hasFilters = !!(query || type || level);

  return (
    <div className="space-y-6">
      <PageHeader eyebrow="Catalog" title="Discover" description="Search books, journals, papers, dissertations and e-resources across every branch." />

      <div className="space-y-4 rounded-2xl border border-slate-200 bg-white p-4 shadow-card sm:p-5">
        <SearchBar initialValue={query} onSearch={(q) => update("q", q)} />
        <div className="space-y-3">
          <div className="flex items-center gap-3">
            <span className="hidden w-14 flex-none text-xs font-semibold uppercase tracking-wider text-ink-muted sm:block">Type</span>
            <div className="flex min-w-0 flex-1 gap-2 overflow-x-auto pb-1" role="group" aria-label="Filter by resource type">
              <FilterChip active={!type} onClick={() => update("type", undefined)}>
                All types
              </FilterChip>
              {RESOURCE_TYPES.map((t) => (
                <FilterChip key={t} active={type === t} onClick={() => update("type", type === t ? undefined : t)}>
                  {TYPE_LABELS[t]}
                </FilterChip>
              ))}
            </div>
          </div>
          <div className="flex items-center gap-3">
            <span className="hidden w-14 flex-none text-xs font-semibold uppercase tracking-wider text-ink-muted sm:block">Level</span>
            <div className="flex min-w-0 flex-1 gap-2 overflow-x-auto pb-1" role="group" aria-label="Filter by level">
              <FilterChip active={!level} onClick={() => update("level", undefined)}>
                All levels
              </FilterChip>
              {RESOURCE_LEVELS.map((l) => (
                <FilterChip key={l} active={level === l} onClick={() => update("level", level === l ? undefined : l)}>
                  {LEVEL_LABELS[l]}
                </FilterChip>
              ))}
            </div>
          </div>
        </div>
      </div>

      <section aria-label="Search results" aria-busy={loading}>
        <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
          <h2 id="results-heading" className="text-sm font-medium text-ink-soft" aria-live="polite">
            {loading
              ? "Searching…"
              : data
                ? `${plural(data.total, "result")}${query ? ` for “${query}”` : ""}${data.total > data.items.length ? ` · showing first ${data.items.length}` : ""}`
                : ""}
          </h2>
          {hasFilters && (
            <Button variant="ghost" size="sm" onClick={clearAll}>
              <SlidersHorizontal className="h-4 w-4" aria-hidden /> Clear filters
            </Button>
          )}
        </div>

        {error ? (
          <ErrorState error={error} onRetry={reload} />
        ) : loading ? (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
            <CardSkeleton count={6} />
          </div>
        ) : data && data.items.length === 0 ? (
          <EmptyState
            icon={SearchX}
            title="No resources match your search"
            description="Try fewer keywords, a different spelling, or remove a filter. You can also ask the AI assistant."
            action={
              hasFilters ? (
                <Button variant="secondary" onClick={clearAll}>
                  Clear search and filters
                </Button>
              ) : undefined
            }
          />
        ) : (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
            {data?.items.map((resource) => <ResourceCard key={resource.resource_id} resource={resource} />)}
          </div>
        )}
      </section>
    </div>
  );
}
