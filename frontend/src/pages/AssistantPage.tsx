import { ArrowUp, MessageSquarePlus, Sparkles } from "lucide-react";
import { useCallback, useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { toApiError } from "../api";
import { useApi } from "../app/ApiProvider";
import { AssistantMessage, TypingIndicator, UserMessage, type ChatEntry } from "../components/chat/ChatMessage";
import { Button, cx } from "../components/ui";
import { useAsync } from "../hooks/useAsync";

const SUGGESTIONS = [
  "Recommend a beginner Python book",
  "Find papers on retrieval-augmented generation",
  "Reserve a statistics book for me",
  "Can I renew my loans?",
  "Show me another user's loans",
  "Do you have books on quantum basket weaving?",
];

const MAX_LENGTH = 2000;
let entrySeq = 0;
const nextId = () => `m${++entrySeq}`;

function HealthIndicator() {
  const { chat } = useApi();
  const { data, error, loading } = useAsync(() => chat.health(), [chat]);
  const state = loading ? "checking" : error || data?.status === "down" ? "down" : data?.status === "degraded" ? "degraded" : "ok";
  const label = { checking: "Connecting…", ok: "Assistant online", degraded: "Limited mode", down: "Assistant unavailable" }[state];
  return (
    <span className="inline-flex items-center gap-1.5 text-xs font-medium text-ink-muted">
      <span
        className={cx(
          "h-2 w-2 rounded-full",
          state === "ok" ? "bg-emerald-500" : state === "degraded" ? "bg-amber-500" : state === "down" ? "bg-red-500" : "animate-pulse bg-slate-300",
        )}
        aria-hidden
      />
      {label}
    </span>
  );
}

export function AssistantPage() {
  const { chat } = useApi();
  const location = useLocation();
  const navigate = useNavigate();
  const [entries, setEntries] = useState<ChatEntry[]>([]);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const sendingRef = useRef(false);
  const endRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const conversationRef = useRef<string | null>(null);
  conversationRef.current = conversationId;

  /** Send (or resend) a user message. `retryId` reuses an existing failed bubble. */
  const send = useCallback(
    async (text: string, retryId?: string) => {
      const message = text.trim();
      if (!message || sendingRef.current) return;
      sendingRef.current = true;
      setSending(true);
      const id = retryId ?? nextId();
      setEntries((list) =>
        retryId
          ? list.map((e) => (e.id === retryId ? { id, role: "user", text: message, status: "sending" } : e))
          : [...list, { id, role: "user", text: message, status: "sending" }],
      );
      try {
        const response = await chat.sendMessage({ conversation_id: conversationRef.current, message });
        setConversationId(response.conversation_id);
        setEntries((list) => [
          ...list.map((e): ChatEntry => (e.id === id ? { id, role: "user", text: message, status: "sent" } : e)),
          { id: nextId(), role: "assistant", response },
        ]);
      } catch (err) {
        const error = toApiError(err);
        if (error.isUnauthorized) return; // the auth layer redirects to login
        setEntries((list) => list.map((e): ChatEntry => (e.id === id ? { id, role: "user", text: message, status: "failed", error } : e)));
      } finally {
        sendingRef.current = false;
        setSending(false);
        inputRef.current?.focus();
      }
    },
    [chat],
  );

  // A prompt handed over from the dashboard is sent once, then cleared from history state.
  const handedOff = useRef(false);
  useEffect(() => {
    const prompt = (location.state as { prompt?: string } | null)?.prompt;
    if (prompt && !handedOff.current) {
      handedOff.current = true;
      navigate(location.pathname, { replace: true, state: null });
      void send(prompt);
    }
  }, [location, navigate, send]);

  useEffect(() => {
    endRef.current?.scrollIntoView?.({ behavior: "smooth", block: "end" });
  }, [entries, sending]);

  function onSubmit(e?: FormEvent) {
    e?.preventDefault();
    if (!input.trim() || sending) return;
    const text = input;
    setInput("");
    void send(text);
  }

  function onKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      onSubmit();
    }
  }

  function newConversation() {
    setEntries([]);
    setConversationId(null);
    setInput("");
    inputRef.current?.focus();
  }

  return (
    <div className="flex h-[calc(100dvh-8rem)] min-h-[520px] flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-card sm:h-[calc(100dvh-10rem)]">
      {/* Header */}
      <header className="flex flex-none items-center gap-3 border-b border-slate-200 px-4 py-3 sm:px-5">
        <span className="grid h-9 w-9 place-items-center rounded-xl bg-gradient-to-br from-brand-600 to-accent-500 text-white">
          <Sparkles className="h-4 w-4" aria-hidden />
        </span>
        <div className="min-w-0 flex-1">
          <h1 className="text-base font-semibold text-ink">AI Assistant</h1>
          <HealthIndicator />
        </div>
        <Button variant="secondary" size="sm" onClick={newConversation} disabled={sending || entries.length === 0}>
          <MessageSquarePlus className="h-4 w-4" aria-hidden />
          <span className="hidden sm:inline">New conversation</span>
        </Button>
      </header>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto bg-slate-50/60 px-4 py-6 sm:px-6" aria-live="polite" aria-label="Conversation" role="log">
        {entries.length === 0 && !sending ? (
          <div className="mx-auto flex max-w-2xl flex-col items-center py-6 text-center">
            <span className="grid h-14 w-14 place-items-center rounded-2xl bg-gradient-to-br from-brand-600 to-accent-500 text-white shadow-lift">
              <Sparkles className="h-6 w-6" aria-hidden />
            </span>
            <h2 className="mt-4 text-xl font-semibold text-ink">How can I help you today?</h2>
            <p className="mt-1.5 max-w-md text-sm text-ink-soft">
              Ask about books, papers or your account. Answers cite catalog records, and I'll always ask before reserving or renewing anything.
            </p>
            <div className="mt-6 grid w-full grid-cols-1 gap-2 sm:grid-cols-2">
              {SUGGESTIONS.map((s) => (
                <button
                  key={s}
                  onClick={() => void send(s)}
                  className="rounded-xl border border-slate-200 bg-white px-4 py-3 text-left text-sm text-ink-soft shadow-sm transition hover:border-brand-300 hover:text-ink"
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        ) : (
          <div className="mx-auto max-w-3xl space-y-5">
            {entries.map((entry) =>
              entry.role === "user" ? (
                <UserMessage key={entry.id} entry={entry} onRetry={() => void send(entry.text, entry.id)} />
              ) : (
                <AssistantMessage key={entry.id} response={entry.response} />
              ),
            )}
            {sending && <TypingIndicator />}
          </div>
        )}
        <div ref={endRef} />
      </div>

      {/* Composer */}
      <form onSubmit={onSubmit} className="flex-none border-t border-slate-200 bg-white p-3 sm:p-4">
        <div className="mx-auto flex max-w-3xl items-end gap-2 rounded-2xl border border-slate-300 bg-white p-2 shadow-sm transition focus-within:border-brand-500 focus-within:ring-4 focus-within:ring-brand-500/15">
          <label htmlFor="chat-input" className="sr-only">
            Message the assistant
          </label>
          <textarea
            id="chat-input"
            ref={inputRef}
            rows={1}
            value={input}
            maxLength={MAX_LENGTH}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={onKeyDown}
            placeholder="Ask about a topic, a book, or your loans…"
            className="max-h-40 min-h-[40px] flex-1 resize-none bg-transparent px-2 py-2 text-[15px] text-ink placeholder:text-ink-muted focus:outline-none focus-visible:ring-0 focus-visible:ring-offset-0 [field-sizing:content]"
          />
          <Button type="submit" size="sm" className="h-10 w-10 !px-0" disabled={!input.trim() || sending} aria-label="Send message">
            <ArrowUp className="h-4 w-4" aria-hidden />
          </Button>
        </div>
        <p className="mx-auto mt-1.5 max-w-3xl px-1 text-[11px] text-ink-muted">Enter to send · Shift+Enter for a new line · Responses may be incomplete; check the cited sources.</p>
      </form>
    </div>
  );
}
