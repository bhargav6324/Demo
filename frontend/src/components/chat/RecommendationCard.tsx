import { ArrowUpRight, CircleCheck, Clock, Lightbulb } from "lucide-react";
import { Link } from "react-router-dom";
import type { ChatResource } from "../../types/models";
import { Badge } from "../ui";

/** A resource the AI recommended. Availability is shown only if the AI service verified it. */
export function RecommendationCard({ resource }: { resource: ChatResource }) {
  const verified = typeof resource.available_copies === "number";
  return (
    <article className="group flex flex-col rounded-xl border border-slate-200 bg-white p-3.5 shadow-card transition hover:border-brand-200 hover:shadow-lift">
      <div className="flex items-start justify-between gap-2">
        <h4 className="text-sm font-semibold leading-snug text-ink">
          <Link to={`/discover/${encodeURIComponent(resource.resource_id)}`} className="hover:text-brand-700 hover:underline">
            {resource.title}
          </Link>
        </h4>
        <ArrowUpRight className="h-4 w-4 flex-none text-ink-muted transition group-hover:text-brand-600" aria-hidden />
      </div>
      <p className="mt-1.5 flex gap-1.5 text-xs leading-relaxed text-ink-soft">
        <Lightbulb className="mt-0.5 h-3.5 w-3.5 flex-none text-amber-500" aria-hidden />
        <span>
          <span className="sr-only">Why: </span>
          {resource.reason}
        </span>
      </p>
      <div className="mt-3">
        {verified ? (
          resource.available_copies! > 0 ? (
            <Badge tone="success">
              <CircleCheck className="h-3 w-3" aria-hidden /> {resource.available_copies} available
            </Badge>
          ) : (
            <Badge tone="warning">
              <Clock className="h-3 w-3" aria-hidden /> No copies free
            </Badge>
          )
        ) : (
          <Link to={`/discover/${encodeURIComponent(resource.resource_id)}`} className="text-xs font-semibold text-brand-700 hover:underline">
            Check availability
          </Link>
        )}
      </div>
    </article>
  );
}
