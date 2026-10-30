import { ArrowUpRight, BookOpen, FileText, Globe, GraduationCap, Newspaper, ScrollText, type LucideIcon } from "lucide-react";
import { Link } from "react-router-dom";
import { LEVEL_LABELS, TYPE_LABELS } from "../lib/labels";
import type { Resource, ResourceLevel, ResourceType } from "../types/models";
import { LiveAvailabilityBadge } from "./AvailabilityBadge";
import { Badge, cx } from "./ui";

export const TYPE_ICONS: Record<ResourceType, LucideIcon> = {
  book: BookOpen,
  ebook: BookOpen,
  journal: Newspaper,
  paper: FileText,
  dissertation: GraduationCap,
  digital_resource: Globe,
};

const TYPE_TINTS: Record<ResourceType, string> = {
  book: "from-brand-500 to-brand-700",
  ebook: "from-sky-500 to-brand-600",
  journal: "from-accent-500 to-accent-700",
  paper: "from-indigo-500 to-brand-700",
  dissertation: "from-violet-500 to-indigo-700",
  digital_resource: "from-teal-400 to-accent-600",
};

export const LEVEL_TONES: Record<ResourceLevel, "success" | "brand" | "danger"> = {
  beginner: "success",
  intermediate: "brand",
  advanced: "danger",
};

/** Generated spine-style cover; no external images needed. */
export function ResourceCover({ type, className }: { type: ResourceType; className?: string }) {
  const Icon = TYPE_ICONS[type] ?? ScrollText;
  return (
    <span className={cx("grid flex-none place-items-center rounded-xl bg-gradient-to-br text-white shadow-sm", TYPE_TINTS[type], className)}>
      <Icon className="h-1/2 w-1/2" aria-hidden />
    </span>
  );
}

export function ResourceCard({ resource }: { resource: Resource }) {
  return (
    <article className="group relative flex flex-col rounded-2xl border border-slate-200 bg-white p-5 shadow-card transition duration-200 hover:-translate-y-0.5 hover:border-brand-200 hover:shadow-lift">
      <div className="flex items-start gap-4">
        <ResourceCover type={resource.type} className="h-14 w-11" />
        <div className="min-w-0 flex-1">
          <div className="mb-1.5 flex flex-wrap items-center gap-1.5">
            <span className="text-xs font-medium text-ink-muted">{TYPE_LABELS[resource.type] ?? resource.type}</span>
            <Badge tone={LEVEL_TONES[resource.level] ?? "neutral"} className="!px-2 !py-0 text-[11px]">
              {LEVEL_LABELS[resource.level] ?? resource.level}
            </Badge>
          </div>
          <h3 className="line-clamp-2 font-semibold leading-snug text-ink">
            <Link to={`/discover/${encodeURIComponent(resource.resource_id)}`} className="after:absolute after:inset-0 focus:outline-none">
              {resource.title}
            </Link>
          </h3>
          <p className="mt-0.5 truncate text-sm text-ink-soft">{resource.authors.join(", ")}</p>
        </div>
        <ArrowUpRight className="h-4 w-4 flex-none text-ink-muted opacity-0 transition group-hover:opacity-100" aria-hidden />
      </div>

      <p className="mt-3 line-clamp-2 text-sm text-ink-soft">{resource.description}</p>

      <div className="mt-3 flex flex-wrap gap-1.5">
        {resource.topics.slice(0, 3).map((topic) => (
          <span key={topic} className="rounded-md bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-600">
            {topic}
          </span>
        ))}
      </div>

      <div className="mt-auto pt-4">
        <div className="flex items-center justify-between gap-2 border-t border-slate-100 pt-3.5">
          <LiveAvailabilityBadge resourceId={resource.resource_id} resourceType={resource.type} />
          <span className="text-xs font-semibold text-brand-700 opacity-0 transition group-hover:opacity-100" aria-hidden>
            View details
          </span>
        </div>
      </div>
    </article>
  );
}
