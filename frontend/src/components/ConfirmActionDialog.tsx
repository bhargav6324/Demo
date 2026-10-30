import { AlertTriangle } from "lucide-react";
import { useEffect, useId, useRef, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { Button } from "./ui";

/**
 * Confirmation step before any state-changing action. While `pending`, it can't
 * be dismissed and the confirm button is disabled, so the action runs once.
 */
export function ConfirmActionDialog({
  open,
  title,
  description,
  confirmLabel = "Confirm",
  pending = false,
  onConfirm,
  onCancel,
  children,
}: {
  open: boolean;
  title: string;
  description?: ReactNode;
  confirmLabel?: string;
  pending?: boolean;
  onConfirm(): void;
  onCancel(): void;
  children?: ReactNode;
}) {
  const titleId = useId();
  const descId = useId();
  const confirmRef = useRef<HTMLButtonElement>(null);
  const previousFocus = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (!open) return;
    previousFocus.current = document.activeElement as HTMLElement | null;
    confirmRef.current?.focus();
    return () => previousFocus.current?.focus?.();
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !pending) onCancel();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, pending, onCancel]);

  if (!open) return null;

  // Portal to <body> so the overlay covers the whole viewport regardless of ancestors.
  return createPortal(
    <div className="fixed inset-0 z-50 flex items-end justify-center p-4 sm:items-center">
      <div className="absolute inset-0 bg-slate-900/40 backdrop-blur-[2px]" onClick={() => !pending && onCancel()} aria-hidden />
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={description ? descId : undefined}
        className="relative w-full max-w-md animate-fade-up rounded-2xl border border-slate-200 bg-white p-6 shadow-lift"
      >
        <div className="flex gap-4">
          <span className="grid h-10 w-10 flex-none place-items-center rounded-full bg-brand-50 text-brand-600">
            <AlertTriangle className="h-5 w-5" aria-hidden />
          </span>
          <div className="min-w-0 flex-1">
            <h2 id={titleId} className="text-base font-semibold text-ink">
              {title}
            </h2>
            {description && (
              <div id={descId} className="mt-1.5 text-sm text-ink-soft">
                {description}
              </div>
            )}
            {children && <div className="mt-4">{children}</div>}
          </div>
        </div>
        <div className="mt-6 flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
          <Button variant="secondary" onClick={onCancel} disabled={pending}>
            Cancel
          </Button>
          <Button ref={confirmRef} onClick={onConfirm} loading={pending}>
            {pending ? "Working…" : confirmLabel}
          </Button>
        </div>
      </div>
    </div>,
    document.body,
  );
}
