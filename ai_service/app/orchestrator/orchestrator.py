"""Deterministic orchestration around the LLM.

The model proposes tool calls; this class validates and executes them,
bounds the loop, turns state-changing calls into pending actions, and
builds the final response from verified evidence only."""
import json
import logging
from dataclasses import dataclass
from datetime import date, datetime

from app.adapters.errors import ToolError
from app.auth.context import UserContext
from app.llm.base import FINAL_ANSWER, FINAL_ANSWER_DECLARATION, INTENTS, LLMClient
from app.observability.trace import Trace
from app.orchestrator.actions import ActionStore
from app.orchestrator.conversations import ConversationStore
from app.orchestrator.grounding import Evidence, build_citations, build_resources
from app.orchestrator.guardrails import PRIVACY_REFUSAL, is_other_user_account_request
from app.orchestrator.prompts import build_system_prompt, wrap_untrusted
from app.schemas.chat import ChatResponseData, ProposedAction
from app.tools.executor import ToolExecutor, ToolResult
from app.tools.registry import ExecContext, ToolDeps

logger = logging.getLogger("smartlibrary.orchestrator")

_INTENT_BY_TOOL = {
    "search_catalog": "search", "get_resource": "search", "semantic_search": "research",
    "get_resource_content": "research", "get_availability": "availability",
    "generate_recommendations": "recommendation", "get_user_profile": "account",
    "get_my_loans": "account", "get_my_reservations": "account",
    "create_reservation": "reservation", "renew_loan": "renewal",
    "get_library_analytics": "analytics",
}
_LOOKUP_INTENTS = {"search", "availability", "recommendation", "research", "reservation"}
_DENIAL_CODES = {ToolError.PERMISSION_DENIED, ToolError.UNAUTHORIZED}
_DENIAL_TEXT = {
    ToolError.PERMISSION_DENIED: "Sorry, that information isn't available for your role.",
    ToolError.UNAUTHORIZED: "Please sign in to access your library account.",
}
_ACTION_TOOLS = {"create_reservation", "renew_loan"}
_ACTION_DENIAL_TEXT = ("Reservations and renewals can only be made by students, faculty and researchers "
                       "for their own account; librarian accounts administer the library and can't place them.")
_OUTAGE_CODES = ToolError.RETRYABLE


@dataclass
class TurnState:
    results: list[ToolResult]
    evidence: Evidence
    proposal: ProposedAction | None = None


class Orchestrator:
    def __init__(self, llm: LLMClient, executor: ToolExecutor, deps: ToolDeps,
                 conversations: ConversationStore, actions: ActionStore, max_tool_calls: int):
        self.llm = llm
        self.executor = executor
        self.deps = deps
        self.conversations = conversations
        self.actions = actions
        self.max_tool_calls = max_tool_calls

    async def handle(self, user: UserContext | None, conversation_id: str | None, message: str,
                     trace: Trace) -> ChatResponseData:
        conv = self.conversations.get_or_create(conversation_id, user.user_id if user else None)

        if is_other_user_account_request(message):
            logger.info(json.dumps({"event": "guardrail", "trace_id": trace.trace_id, "rule": "other_user_account"}))
            response = ChatResponseData(conversation_id=conv.conversation_id, outcome="refused",
                                        assistant_message=PRIVACY_REFUSAL, intent="account")
            self.conversations.append(conv, message, PRIVACY_REFUSAL)
            return response

        system = build_system_prompt(user, date.today())
        messages = list(conv.messages) + [{"role": "user", "content": message}]
        tools = self.executor.registry.declarations() + [FINAL_ANSWER_DECLARATION]
        ec = ExecContext(user=user, deps=self.deps)
        state = TurnState(results=[], evidence=Evidence())

        final = await self._loop(system, messages, tools, ec, state, trace)
        response = self._compose(conv.conversation_id, final, state)

        note = f"\n[resources referenced: {', '.join(r.resource_id + ' ' + r.title for r in response.resources)}]" \
            if response.resources else ""
        self.conversations.append(conv, message, response.assistant_message + note)
        return response

    # ------------------------------------------------------------------ loop

    async def _loop(self, system, messages, tools, ec, state: TurnState, trace: Trace) -> dict | None:
        used = 0
        final_only = [FINAL_ANSWER_DECLARATION]
        # +1 round so the model can always write its answer after the last tool result
        for _ in range(self.max_tool_calls + 1):
            limit_reached = used >= self.max_tool_calls
            resp = await self.llm.generate(system, messages, final_only if limit_reached else tools)

            if not resp.tool_calls:
                # Model answered in plain text (no structured final) - accept as message only
                return {"message": resp.text or "", "intent": None, "resources": [], "abstain": "none"}

            messages.append({"role": "assistant", "content": resp.text, "tool_calls": resp.tool_calls, "raw": resp.raw})
            for tc in resp.tool_calls:
                if tc.name == FINAL_ANSWER:
                    return tc.args if isinstance(tc.args, dict) else {}

                if used >= self.max_tool_calls:
                    result = ToolResult(tc.name, tc.args, "rejected",
                                        error={"code": "tool_limit_reached",
                                               "message": "Tool call limit reached; answer with what you have."})
                    trace.record(tc.name, tc.args if isinstance(tc.args, dict) else {}, "rejected", "tool_limit_reached", 0)
                else:
                    used += 1
                    result = await self.executor.execute(tc.name, tc.args, ec, trace)
                    if result.status == "confirmation_required":
                        result = self._propose(ec.user, result, state)

                state.results.append(result)
                state.evidence.add(result)
                messages.append({"role": "tool", "tool_call_id": tc.id, "name": tc.name,
                                 "content": wrap_untrusted(result.for_llm())})
        logger.warning("trace=%s orchestrator loop ended without final_answer", trace.trace_id)
        return None

    def _propose(self, user: UserContext, result: ToolResult, state: TurnState) -> ToolResult:
        if state.proposal is not None:
            return ToolResult(result.tool, result.args, "rejected",
                              error={"code": "one_action_per_turn",
                                     "message": "Only one action can be proposed per message."})
        action_type, description = _describe_action(result)
        d = result.data or {}
        title = d["resource"]["title"] if action_type == "reservation" else d["loan"]["resource_title"]
        pending = self.actions.create(user.user_id, result.tool, result.args, action_type, description, title)
        state.proposal = ProposedAction(
            action_id=pending.action_id, action_type=action_type,
            resource_id=result.args.get("resource_id") if action_type == "reservation" else
            (result.data.get("loan", {}) or {}).get("resource_id"),
            loan_id=result.args.get("loan_id"),
            description=description,
        )
        result.data = {**(result.data or {}), "proposed_action": description}
        return result

    # ------------------------------------------------------------- response

    def _compose(self, conversation_id: str, final: dict | None, state: TurnState) -> ChatResponseData:
        final = final or {}
        abstain = final.get("abstain") or "none"
        intent = final.get("intent") if final.get("intent") in INTENTS else self._infer_intent(state)
        message = (final.get("message") or "").strip()

        results = state.results
        denied = next((r for r in results if r.error_code in _DENIAL_CODES), None)
        succeeded = [r for r in results if r.status in ("success", "confirmation_required")]
        outage = results and not succeeded and all(r.error_code in _OUTAGE_CODES for r in results if r.error)

        resources = build_resources(final.get("resources") or [], state.evidence,
                                    fallback=intent in _LOOKUP_INTENTS and abstain == "none")

        # For outcomes whose facts are fully known to code, the message is deterministic too,
        # so model text can never claim a transaction, permission or result that didn't happen.
        if state.proposal:
            outcome = "needs_confirmation"
            message = f"{state.proposal.description} Please confirm to proceed."
        elif denied or abstain in ("privacy", "unauthorized", "out_of_scope"):
            outcome = "refused"
            resources = []
            if denied:
                message = (_ACTION_DENIAL_TEXT if denied.tool in _ACTION_TOOLS
                           and denied.error_code == ToolError.PERMISSION_DENIED
                           else _DENIAL_TEXT[denied.error_code])
            elif abstain == "privacy":
                message = PRIVACY_REFUSAL
        elif outage:
            outcome = "answered"
            resources = []
            message = ("The library system is temporarily unavailable, so I can't verify that right now. "
                       "Please try again in a few minutes.")
        elif abstain == "not_found" or (intent in _LOOKUP_INTENTS and not resources and not succeeded_has_data(succeeded)):
            outcome = "not_found"
            resources = []
            message = ("I couldn't find that in the library's catalog or authorized sources, "
                       "so I can't provide details about it.")
        else:
            outcome = "answered"

        if not message:
            message = "I wasn't able to produce an answer for that request. Please try rephrasing."

        return ChatResponseData(
            conversation_id=conversation_id,
            outcome=outcome,
            assistant_message=message,
            intent=intent,
            resources=resources,
            citations=build_citations(resources, state.evidence) if outcome in ("answered", "needs_confirmation") else [],
            proposed_action=state.proposal,
        )

    @staticmethod
    def _infer_intent(state: TurnState) -> str:
        for r in reversed(state.results):
            if r.tool in _INTENT_BY_TOOL:
                return _INTENT_BY_TOOL[r.tool]
        return "general"


def succeeded_has_data(results: list[ToolResult]) -> bool:
    """True if any successful tool returned non-empty, non-catalog data (e.g. loans, analytics)."""
    for r in results:
        d = r.data or {}
        if r.tool in ("search_catalog", "semantic_search", "generate_recommendations"):
            continue
        if d and (not isinstance(d, dict) or d.get("items", True)):
            return True
    return False


def _describe_action(result: ToolResult) -> tuple[str, str]:
    """Deterministic confirmation text built from verified precheck data."""
    d = result.data or {}
    if result.tool == "create_reservation":
        title = d["resource"]["title"]
        a = d["availability"]
        if a["available_copies"] > 0 and a["waitlist_count"] == 0:
            branch = next((l["branch"] for l in a["locations"] if l["available_copies"] > 0), "the library")
            return "reservation", (f"Reserve '{title}'. {a['available_copies']} of {a['total_copies']} copies are "
                                   f"available now; one will be held for pickup at {branch}.")
        # The priority queue (faculty > researcher > student, FIFO within a role) means the
        # exact position is only known after the backend places the hold.
        situation = ("No copies are available now" if a["available_copies"] == 0
                     else "Copies are free, but other patrons are already waiting for them")
        return "reservation", (f"Reserve '{title}'. {situation}; {a['waitlist_count']} already waiting. "
                               "Your request joins the priority waitlist (faculty, then researchers, then "
                               "students) and the library confirms your position.")
    loan = d["loan"]
    new_due = datetime.fromisoformat(d["proposed_due_at"]).date()
    old_due = datetime.fromisoformat(loan["due_at"]).date()
    return "renewal", (f"Renew '{loan['resource_title']}' (loan {loan['loan_id']}) for "
                       f"{d.get('renewal_days', 14)} more days. Due date moves from {old_due} to {new_due}.")
