import { CheckCircle2, Info, TriangleAlert, X, XCircle } from "lucide-react";
import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";

export type ToastTone = "success" | "info" | "warning" | "error";
type Toast = { id: number; tone: ToastTone; message: string };

type ToastApi = { push(tone: ToastTone, message: string): void; clearAll(): void };
const ToastContext = createContext<ToastApi | null>(null);

const ICONS = { success: CheckCircle2, info: Info, warning: TriangleAlert, error: XCircle };
const TONES: Record<ToastTone, string> = {
  success: "text-emerald-600",
  info: "text-brand-600",
  warning: "text-amber-600",
  error: "text-red-600",
};

let nextId = 1;

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);

  const dismiss = useCallback((id: number) => setToasts((list) => list.filter((t) => t.id !== id)), []);

  const push = useCallback(
    (tone: ToastTone, message: string) => {
      const id = nextId++;
      setToasts((list) => [...list.slice(-3), { id, tone, message }]);
      setTimeout(() => dismiss(id), 5000);
    },
    [dismiss],
  );

  const value = useMemo(() => ({ push, clearAll: () => setToasts([]) }), [push]);

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div className="pointer-events-none fixed bottom-4 right-4 z-50 flex w-[min(380px,calc(100vw-2rem))] flex-col gap-2" aria-live="polite">
        {toasts.map((t) => {
          const Icon = ICONS[t.tone];
          return (
            <div
              key={t.id}
              role="status"
              className="pointer-events-auto flex animate-fade-up items-start gap-3 rounded-xl border border-slate-200 bg-white p-3.5 pr-2 text-sm shadow-lift"
            >
              <Icon className={`mt-0.5 h-5 w-5 flex-none ${TONES[t.tone]}`} aria-hidden />
              <span className="flex-1 text-ink">{t.message}</span>
              <button
                className="rounded-md p-1 text-ink-muted hover:bg-slate-100 hover:text-ink"
                aria-label="Dismiss notification"
                onClick={() => dismiss(t.id)}
              >
                <X className="h-4 w-4" />
              </button>
            </div>
          );
        })}
      </div>
    </ToastContext.Provider>
  );
}

function useToastApi() {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error("useToast must be used inside ToastProvider");
  return ctx;
}

export function useToast() {
  return useToastApi().push;
}

/** Used on identity changes so one user's notifications never show for the next. */
export function useClearToasts() {
  return useToastApi().clearAll;
}
