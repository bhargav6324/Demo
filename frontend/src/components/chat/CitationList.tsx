import { BookText } from "lucide-react";
import { Link } from "react-router-dom";
import type { Citation } from "../../types/models";

/** Sources the AI response is grounded in, linked back to catalog records. */
export function CitationList({ citations }: { citations: Citation[] }) {
  if (!citations.length) return null;
  return (
    <div className="rounded-xl border border-slate-200 bg-slate-50/70 p-3">
      <p className="mb-2 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-ink-muted">
        <BookText className="h-3.5 w-3.5" aria-hidden /> Sources
      </p>
      <ol className="space-y-1.5" aria-label="Sources">
        {citations.map((c, i) => (
          <li key={`${c.resource_id}-${c.source_id}-${i}`} className="flex items-baseline gap-2 text-sm">
            <span className="grid h-5 w-5 flex-none place-items-center rounded-full bg-white text-[11px] font-semibold text-brand-700 ring-1 ring-slate-200">
              {i + 1}
            </span>
            <span className="min-w-0">
              <Link to={`/discover/${encodeURIComponent(c.resource_id)}`} className="font-medium text-ink hover:text-brand-700 hover:underline">
                {c.title}
              </Link>
              <span className="ml-1.5 text-xs text-ink-muted">
                {c.source_type} · <span className="font-mono">{c.source_id}</span>
              </span>
            </span>
          </li>
        ))}
      </ol>
    </div>
  );
}
