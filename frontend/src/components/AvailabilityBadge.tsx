import { CircleCheck, CircleSlash, Clock, Globe, HelpCircle } from "lucide-react";
import { useApi } from "../app/ApiProvider";
import { useAsync } from "../hooks/useAsync";
import { isDigitalType } from "../lib/labels";
import type { Availability, ResourceType } from "../types/models";
import { Badge } from "./ui";

/** Renders availability exactly as reported by the API — no client-side stock math. */
export function AvailabilityBadge({
  availability,
  resourceType,
  loading,
  failed,
}: {
  availability?: Availability;
  resourceType: ResourceType;
  loading?: boolean;
  failed?: boolean;
}) {
  if (loading && !availability) {
    return <span className="inline-block h-5 w-24 animate-pulse rounded-full bg-slate-100" aria-label="Checking availability" />;
  }
  if (failed || !availability) {
    return (
      <Badge tone="neutral">
        <HelpCircle className="h-3 w-3" aria-hidden /> Availability unknown
      </Badge>
    );
  }
  if (availability.total_copies === 0 && isDigitalType(resourceType)) {
    return (
      <Badge tone="accent">
        <Globe className="h-3 w-3" aria-hidden /> Online access
      </Badge>
    );
  }
  if (availability.available_copies > 0) {
    return (
      <Badge tone="success">
        <CircleCheck className="h-3 w-3" aria-hidden /> {availability.available_copies} available
      </Badge>
    );
  }
  if (availability.total_copies > 0) {
    return (
      <Badge tone="warning">
        <Clock className="h-3 w-3" aria-hidden />
        {availability.waitlist_count > 0 ? `On loan · ${availability.waitlist_count} waiting` : "All copies on loan"}
      </Badge>
    );
  }
  return (
    <Badge tone="neutral">
      <CircleSlash className="h-3 w-3" aria-hidden /> No copies held
    </Badge>
  );
}

/** Self-loading variant for lists: one availability call per visible resource. */
export function LiveAvailabilityBadge({ resourceId, resourceType }: { resourceId: string; resourceType: ResourceType }) {
  const { catalog } = useApi();
  const { data, error, loading } = useAsync(() => catalog.getAvailability(resourceId), [catalog, resourceId]);
  return <AvailabilityBadge availability={data} resourceType={resourceType} loading={loading} failed={!!error} />;
}
