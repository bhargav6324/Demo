import { AlertCircle, Bot, RotateCw, SearchX, ShieldAlert } from "lucide-react";
import { Link } from "react-router-dom";
import type { ApiError } from "../../api";
import type { ChatResponse } from "../../types/models";
import { cx } from "../ui";
import { CitationList } from "./CitationList";
import { ProposedActionCard } from "./ProposedActionCard";
import { RecommendationCard } from "./RecommendationCard";

export type ChatEntry =
  | { id: string; role: "user"; text: string; status: "sending" | "sent" | "failed"; error?: ApiError }
  | { id: string; role: "assistant"; response: ChatResponse };

function AssistantAvatar() {
  return (
    <span className="grid h-8 w-8 flex-none place-items-center rounded-full bg-gradient-to-br from-brand-600 to-accent-500 text-white shadow-sm" aria-hidden>
      <Bot className="h-4 w-4" />
    </span>
  );
}

export function UserMessage({ entry, onRetry }: { entry: Extract<ChatEntry, { role: "user" }>; onRetry(): void }) {
  return (
    <div className="flex flex-col items-end gap-1.5">
      <div
        className={cx(
          "max-w-[85%] whitespace-pre-wrap break-words rounded-2xl rounded-br-md px-4 py-2.5 text-[15px] shadow-sm sm:max-w-[70%]",
          entry.status === "failed" ? "bg-red-50 text-red-900 ring-1 ring-red-200" : "bg-brand-600 text-white",
        )}
      >
        {entry.text}
      </div>
      {entry.status === "failed" && (
        <div role="alert" className="flex flex-wrap items-center justify-end gap-2 text-xs text-red-700">
          <AlertCircle className="h-3.5 w-3.5" aria-hidden />
          <span>{entry.error?.message ?? "Message not delivered."}</span>
          <button onClick={onRetry} className="inline-flex items-center gap-1 rounded-md px-2 py-1 font-semibold text-brand-700 hover:bg-brand-50">
            <RotateCw className="h-3 w-3" aria-hidden /> Retry
          </button>
        </div>
      )}
    </div>
  );
}

/** Renders the structured AI response. Behaviour depends only on `outcome`, never on the prose. */
export function AssistantMessage({ response }: { response: ChatResponse }) {
  const { outcome } = response;
  return (
    <div className="flex items-start gap-3">
      <AssistantAvatar />
      <div className="min-w-0 flex-1 space-y-3" data-outcome={outcome}>
        {outcome === "refused" ? (
          <div className="flex gap-2.5 rounded-2xl rounded-tl-md border border-amber-200 bg-amber-50 px-4 py-3">
            <ShieldAlert className="mt-0.5 h-4 w-4 flex-none text-amber-600" aria-hidden />
            <div>
              <p className="text-sm font-semibold text-amber-900">I can't help with that</p>
              <p className="mt-0.5 text-[15px] text-ink-soft">{response.assistant_message}</p>
            </div>
          </div>
        ) : outcome === "not_found" ? (
          <div className="flex gap-2.5 rounded-2xl rounded-tl-md border border-slate-200 bg-white px-4 py-3 shadow-sm">
            <SearchX className="mt-0.5 h-4 w-4 flex-none text-ink-muted" aria-hidden />
            <div>
              <p className="text-sm font-semibold text-ink">No matching resources</p>
              <p className="mt-0.5 text-[15px] text-ink-soft">{response.assistant_message}</p>
              <Link to="/discover" className="mt-2 inline-block text-sm font-semibold text-brand-700 hover:underline">
                Browse the catalog instead
              </Link>
            </div>
          </div>
        ) : (
          <div className="w-fit max-w-full whitespace-pre-wrap break-words rounded-2xl rounded-tl-md border border-slate-200 bg-white px-4 py-2.5 text-[15px] text-ink shadow-sm">
            {response.assistant_message}
          </div>
        )}

        {outcome !== "refused" && response.resources.length > 0 && (
          <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-2 xl:grid-cols-3" aria-label="Recommended resources" role="list">
            {response.resources.map((r) => (
              <div role="listitem" key={r.resource_id}>
                <RecommendationCard resource={r} />
              </div>
            ))}
          </div>
        )}

        {outcome !== "refused" && <CitationList citations={response.citations} />}

        {outcome === "needs_confirmation" && response.proposed_action && <ProposedActionCard action={response.proposed_action} />}
      </div>
    </div>
  );
}

export function TypingIndicator() {
  return (
    <div className="flex items-start gap-3" role="status" aria-label="Assistant is typing">
      <AssistantAvatar />
      <div className="flex items-center gap-1 rounded-2xl rounded-tl-md border border-slate-200 bg-white px-4 py-3.5 shadow-sm">
        {[0, 150, 300].map((delay) => (
          <span key={delay} className="h-2 w-2 animate-bounce rounded-full bg-brand-400" style={{ animationDelay: `${delay}ms` }} />
        ))}
      </div>
    </div>
  );
}
