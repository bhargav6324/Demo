import { FlaskConical, Menu } from "lucide-react";
import { useState } from "react";
import { Outlet, useLocation } from "react-router-dom";
import { NAV_ITEMS } from "../../app/nav";
import { config } from "../../config";
import type { User } from "../../types/models";
import { Sidebar } from "./Sidebar";

export function AppLayout({ user, onSignOut }: { user: User | null; onSignOut?: () => void }) {
  const [menuOpen, setMenuOpen] = useState(false);
  const { pathname } = useLocation();
  const current = NAV_ITEMS.find((item) => pathname.startsWith(item.to));

  return (
    <div className="flex h-full">
      <a
        href="#main-content"
        className="sr-only z-50 rounded-lg bg-white px-4 py-2 text-sm font-semibold text-brand-700 shadow-lift focus:not-sr-only focus:fixed focus:left-4 focus:top-4"
      >
        Skip to main content
      </a>
      <Sidebar user={user} open={menuOpen} onClose={() => setMenuOpen(false)} onSignOut={onSignOut} />

      <div className="flex min-w-0 flex-1 flex-col overflow-y-auto">
        <header className="sticky top-0 z-20 flex h-16 flex-none items-center gap-3 border-b border-slate-200 bg-white/80 px-4 backdrop-blur-md sm:px-8">
          <button
            className="rounded-lg p-2 text-ink-soft hover:bg-slate-100 lg:hidden"
            aria-label="Open menu"
            onClick={() => setMenuOpen(true)}
          >
            <Menu className="h-5 w-5" />
          </button>
          <p className="truncate text-sm font-semibold text-ink">{current?.label ?? "Smart Library"}</p>
          {config.apiMode === "mock" && (
            <span
              className="ml-auto inline-flex items-center gap-1.5 rounded-full bg-amber-50 px-3 py-1 text-xs font-semibold text-amber-800 ring-1 ring-inset ring-amber-200"
              title="Using in-browser mock services. Set VITE_API_MODE=real to use the backend and AI services."
            >
              <FlaskConical className="h-3.5 w-3.5" aria-hidden />
              Mock data
            </span>
          )}
        </header>

        <main id="main-content" tabIndex={-1} className="mx-auto w-full max-w-6xl flex-1 animate-fade-up px-4 py-6 focus:outline-none sm:px-8 sm:py-8">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
