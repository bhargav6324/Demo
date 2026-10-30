import { BarChart3, BookMarked, Compass, LayoutDashboard, Sparkles, type LucideIcon } from "lucide-react";
import type { Role } from "../types/models";

export interface NavItem {
  to: string;
  label: string;
  icon: LucideIcon;
  /** Roles that see this item. Hiding is UX only — the backend enforces access. */
  roles: Role[];
}

const ALL: Role[] = ["student", "researcher", "faculty", "librarian"];

export const NAV_ITEMS: NavItem[] = [
  { to: "/dashboard", label: "Dashboard", icon: LayoutDashboard, roles: ALL },
  { to: "/discover", label: "Discover", icon: Compass, roles: ALL },
  { to: "/assistant", label: "AI Assistant", icon: Sparkles, roles: ALL },
  { to: "/my-library", label: "My Library", icon: BookMarked, roles: ALL },
  { to: "/analytics", label: "Analytics", icon: BarChart3, roles: ["librarian"] },
];

export function navFor(role: Role): NavItem[] {
  return NAV_ITEMS.filter((item) => item.roles.includes(role));
}

/** Opt into React Router v7 behaviour now (silences upgrade warnings). */
export const ROUTER_FUTURE = { v7_startTransition: true, v7_relativeSplatPath: true } as const;

export const ROLE_LABELS: Record<Role, string> = {
  student: "Student",
  researcher: "Researcher",
  faculty: "Faculty",
  librarian: "Librarian",
};
