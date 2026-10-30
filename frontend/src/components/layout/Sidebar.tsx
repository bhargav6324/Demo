import { Library, LogIn, LogOut, X } from "lucide-react";
import { NavLink } from "react-router-dom";
import { navFor, NAV_ITEMS, ROLE_LABELS } from "../../app/nav";
import type { User } from "../../types/models";
import { cx } from "../ui";

function initials(name: string) {
  return name
    .replace(/^(dr|prof)\.?\s+/i, "")
    .split(/\s+/)
    .map((p) => p[0])
    .slice(0, 2)
    .join("")
    .toUpperCase();
}

export function Sidebar({
  user,
  open,
  onClose,
  onSignOut,
}: {
  user: User | null;
  open: boolean;
  onClose(): void;
  onSignOut?: () => void;
}) {
  const items = user ? navFor(user.role) : NAV_ITEMS;

  return (
    <>
      <div
        className={cx(
          "fixed inset-0 z-30 bg-slate-900/40 backdrop-blur-[2px] transition-opacity lg:hidden",
          open ? "opacity-100" : "pointer-events-none opacity-0",
        )}
        onClick={onClose}
        aria-hidden
      />
      <aside
        aria-label="Primary"
        className={cx(
          "fixed inset-y-0 left-0 z-40 flex w-72 flex-col border-r border-slate-200 bg-white transition-transform duration-300 lg:static lg:z-auto lg:w-64 lg:translate-x-0",
          open ? "translate-x-0 shadow-lift" : "-translate-x-full",
        )}
      >
        <div className="flex items-center gap-3 px-5 pb-6 pt-5">
          <span className="grid h-9 w-9 place-items-center rounded-xl bg-gradient-to-br from-brand-600 to-accent-500 text-white shadow-sm">
            <Library className="h-5 w-5" aria-hidden />
          </span>
          <div className="min-w-0">
            <p className="text-[15px] font-bold leading-tight tracking-tight text-ink">Smart Library</p>
            <p className="text-xs text-ink-muted">University portal</p>
          </div>
          <button className="ml-auto rounded-lg p-1.5 text-ink-muted hover:bg-slate-100 lg:hidden" aria-label="Close menu" onClick={onClose}>
            <X className="h-5 w-5" />
          </button>
        </div>

        <nav className="flex-1 space-y-1 overflow-y-auto px-3">
          <p className="px-3 pb-2 text-[11px] font-semibold uppercase tracking-wider text-ink-muted">Menu</p>
          {items.map(({ to, label, icon: Icon, roles }) => (
            <NavLink
              key={to}
              to={to}
              onClick={onClose}
              className={({ isActive }) =>
                cx(
                  "group flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors",
                  isActive ? "bg-brand-50 text-brand-700" : "text-ink-soft hover:bg-slate-50 hover:text-ink",
                )
              }
            >
              {({ isActive }) => (
                <>
                  <Icon className={cx("h-[18px] w-[18px]", isActive ? "text-brand-600" : "text-ink-muted group-hover:text-ink-soft")} aria-hidden />
                  <span className="flex-1">{label}</span>
                  {roles.length === 1 && <span className="text-[10px] font-semibold uppercase tracking-wide text-accent-700">{ROLE_LABELS[roles[0]]}</span>}
                </>
              )}
            </NavLink>
          ))}
        </nav>

        <div className="border-t border-slate-200 p-3">
          {user ? (
            <div className="flex items-center gap-3 rounded-xl p-2">
              <span className="grid h-9 w-9 flex-none place-items-center rounded-full bg-gradient-to-br from-brand-500 to-accent-500 text-xs font-bold text-white">
                {initials(user.name)}
              </span>
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-semibold text-ink" title={user.name}>
                  {user.name}
                </p>
                <p className="truncate text-xs text-ink-muted">{ROLE_LABELS[user.role]}</p>
              </div>
              {onSignOut && (
                <button
                  className="rounded-lg p-2 text-ink-muted hover:bg-slate-100 hover:text-ink"
                  aria-label="Sign out"
                  title="Sign out"
                  onClick={onSignOut}
                >
                  <LogOut className="h-4 w-4" />
                </button>
              )}
            </div>
          ) : (
            <div className="flex items-center gap-3 rounded-xl bg-slate-50 p-3 text-sm text-ink-soft">
              <LogIn className="h-4 w-4 text-ink-muted" aria-hidden />
              Not signed in
            </div>
          )}
        </div>
      </aside>
    </>
  );
}
