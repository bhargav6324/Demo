"""Deterministic offline LLMs.

ScriptedLLM   - unit tests: replays an exact sequence of tool calls.
RuleBasedLLM  - LLM_PROVIDER=fake: keyword intent routing for offline demos
                without an API key. It decides *which tools to call*; every
                fact in its answers still comes from tool results."""
import re
import uuid
from typing import Callable

from app.llm.base import FINAL_ANSWER, LLMClient, LLMResponse, ToolCall


def call(name: str, **args) -> ToolCall:
    return ToolCall(id=uuid.uuid4().hex[:8], name=name, args=args)


def final(message: str, intent: str, resources: list[dict] | None = None, abstain: str = "none") -> ToolCall:
    return call(FINAL_ANSWER, message=message, intent=intent, resources=resources or [], abstain=abstain)


Step = list[ToolCall] | ToolCall | Callable[[list[dict]], LLMResponse]


class ScriptedLLM(LLMClient):
    """Each generate() call consumes the next step. A step may be a ToolCall,
    a list of ToolCalls (parallel calls) or a function of the messages."""

    def __init__(self, steps: list[Step]):
        self.steps = list(steps)
        self.requests: list[dict] = []  # what the orchestrator sent, for assertions

    async def generate(self, system, messages, tools):
        self.requests.append({"system": system, "messages": list(messages), "tools": [t["name"] for t in tools]})
        if not self.steps:
            return LLMResponse(text="(script exhausted)")
        step = self.steps.pop(0)
        if callable(step):
            return step(messages)
        calls = step if isinstance(step, list) else [step]
        return LLMResponse(tool_calls=calls)


# ---------------------------------------------------------------------------

_RES_ID = re.compile(r"\bres-\d+\b")
_LOAN_ID = re.compile(r"\bloan-\d+\b")
_OTHER_USER = re.compile(
    r"\b((u|user)-\d+|another (user|student|person)|other (user|student|people)|someone else|"
    r"[A-Z][a-z]+'s (loans?|borrow\w*|history|account|reservations?))", re.I)
_FILLER = re.compile(
    r"\b(is|are|the|a|an|book|books|available|availability|find|search|for|me|please|show|"
    r"can|i|you|do|have|there|any|on|about|reserve|hold|copy|copies|of|currently|it|that|"
    r"papers?|research|related|to|summari[sz]e)\b|[?.!]", re.I)


def _topic(text: str) -> str:
    return re.sub(r"\s+", " ", _FILLER.sub(" ", text)).strip() or text


class RuleBasedLLM(LLMClient):
    async def generate(self, system, messages, tools):
        user_text = next(m["content"] for m in reversed(messages) if m["role"] == "user")
        # Tool results gathered since the latest user message
        idx = max(i for i, m in enumerate(messages) if m["role"] == "user")
        results = {m["name"]: m["content"] for m in messages[idx + 1:] if m["role"] == "tool"}
        return LLMResponse(tool_calls=[self._next(user_text, results)])

    def _next(self, text: str, results: dict) -> ToolCall:
        low = text.lower()

        if _OTHER_USER.search(text) and re.search(r"loan|borrow|history|account|reserv", low):
            return final("I can't share another person's borrowing information. I can only show your own account.",
                         "account", abstain="privacy")

        if re.search(r"analytic|waitlist|demand|circulation|utili[sz]ation|catalog gap|overdue trend|"
                     r"most borrowed|borrowed the most|popular", low):
            if "get_library_analytics" not in results:
                return call("get_library_analytics")
            return self._summarize(results, "analytics", intent_hint="waitlist" if "waitlist" in low else None)

        if "renew" in low:
            if m := _LOAN_ID.search(text):
                if "renew_loan" not in results:
                    return call("renew_loan", loan_id=m.group())
                return self._summarize(results, "renewal")
            if "get_my_loans" not in results:
                return call("get_my_loans")
            renewable = [l for l in _ok(results, "get_my_loans").get("items", []) if l["renewable"] and l["status"] == "active"]
            if renewable and "renew_loan" not in results:
                return call("renew_loan", loan_id=renewable[0]["loan_id"])
            return self._summarize(results, "renewal")

        if re.search(r"\b(my loans|borrowed|due|my books|fines?|checked out)\b", low):
            if "get_my_loans" not in results:
                return call("get_my_loans")
            return self._summarize(results, "account")

        if re.search(r"\b(reserve|hold|book it)\b", low):
            rid = (m.group() if (m := _RES_ID.search(text)) else None) or _top_id(results)
            if rid is None and "search_catalog" not in results:
                return call("search_catalog", query=_topic(text))
            if rid and "create_reservation" not in results:
                return call("create_reservation", resource_id=rid)
            return self._summarize(results, "reservation")

        if re.search(r"\b(recommend|suggest)\w*", low):
            if "generate_recommendations" not in results:
                args = {"query": _topic(re.sub(r"(recommend|suggest)\w*", "", text, flags=re.I))}
                if "beginner" in low:
                    args["level"] = "beginner"
                if "available" in low:
                    args["available_only"] = True
                return call("generate_recommendations", **args)
            return self._summarize(results, "recommendation")

        if re.search(r"\bavailab", low):
            rid = (m.group() if (m := _RES_ID.search(text)) else None) or _top_id(results)
            if rid is None and "search_catalog" not in results:
                return call("search_catalog", query=_topic(text), limit=3)
            if rid and "get_availability" not in results:
                return call("get_availability", resource_id=rid)
            return self._summarize(results, "availability", only_top=True)

        if re.search(r"\b(papers?|research|summari[sz]e|compare)\b", low):
            if "semantic_search" not in results:
                return call("semantic_search", query=_topic(text), limit=5)
            return self._summarize(results, "research")

        if "search_catalog" not in results:
            return call("search_catalog", query=_topic(text))
        return self._summarize(results, "search")

    @staticmethod
    def _summarize(results: dict, intent: str, only_top: bool = False, intent_hint: str | None = None) -> ToolCall:
        """Compose an answer purely from tool output."""
        for name, r in results.items():
            if r.get("status") == "confirmation_required":
                return final("I've prepared this action. Please confirm to proceed.", intent)
            if r.get("status") == "error":
                code = r["error"]["code"]
                if code == "not_found":
                    return final("I couldn't find that in the library's records.", intent, abstain="not_found")
                return final(f"I couldn't complete that: {r['error']['message']}", intent)

        resources, lines = [], []
        for name, r in results.items():
            data = r.get("data") or {}
            items = data.get("items") or data.get("recommendations") or data.get("results") or []
            if name in ("get_my_loans", "get_my_reservations"):
                lines += [f"- {i.get('resource_title', i.get('resource_id'))} (due {i.get('due_at', '')[:10]}, status {i['status']})"
                          if "loan_id" in i else f"- {i['resource_id']}: {i['status']}" for i in items]
                continue
            if name == "get_library_analytics":
                if intent_hint == "waitlist":
                    lines += [f"- {w['title']}: {w['waitlist_count']} waiting" for w in data.get("longest_waitlists", [])]
                    lines = lines or ["- No titles currently have a waitlist."]
                else:
                    lines += [f"- {p['title']}: borrowed {p['loan_count']} times"
                              for p in data.get("popular_resources", [])]
                    lines.append(f"Active loans: {data.get('active_loans')}, overdue: {data.get('overdue_loans')}, "
                                 f"open holds: {data.get('active_reservations')}.")
                for row in data.get("longest_waitlists" if intent_hint == "waitlist" else "popular_resources", []):
                    resources.append({"resource_id": row["resource_id"], "reason": "From library analytics."})
                continue
            if name == "get_availability":
                lines.append(f"Available copies: {data['available_copies']} of {data['total_copies']} "
                             f"(waitlist {data['waitlist_count']}).")
                continue
            for i in items[: 1 if only_top else 5]:
                rid = i.get("resource_id")
                if rid and rid not in {r["resource_id"] for r in resources}:
                    resources.append({"resource_id": rid, "reason": i.get("reason") or f"Matches your query ({name})."})
                    lines.append(f"- {i.get('title', rid)}")

        if not lines:
            return final("I couldn't find matching resources in the library catalog.", intent, abstain="not_found")
        return final("Here is what I found:\n" + "\n".join(lines), intent, resources)


def _ok(results: dict, name: str) -> dict:
    r = results.get(name) or {}
    return r.get("data") or {} if r.get("status") == "success" else {}


def _top_id(results: dict) -> str | None:
    items = _ok(results, "search_catalog").get("items") or []
    return items[0]["resource_id"] if items else None
