import type { ResourceLevel, ResourceType } from "../types/models";

export const TYPE_LABELS: Record<ResourceType, string> = {
  book: "Book",
  ebook: "E-book",
  journal: "Journal",
  paper: "Paper",
  dissertation: "Dissertation",
  digital_resource: "Digital resource",
};

export const LEVEL_LABELS: Record<ResourceLevel, string> = {
  beginner: "Beginner",
  intermediate: "Intermediate",
  advanced: "Advanced",
};

export const RESOURCE_TYPES = Object.keys(TYPE_LABELS) as ResourceType[];
export const RESOURCE_LEVELS = Object.keys(LEVEL_LABELS) as ResourceLevel[];

/** Digital types are accessed online rather than borrowed (presentation only). */
export function isDigitalType(type: ResourceType) {
  return type === "ebook" || type === "digital_resource";
}

export const isResourceType = (v: string | null): v is ResourceType => !!v && v in TYPE_LABELS;
export const isResourceLevel = (v: string | null): v is ResourceLevel => !!v && v in LEVEL_LABELS;
