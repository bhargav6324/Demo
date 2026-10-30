"""Executes a previously proposed action after explicit user confirmation.

Checks: action exists and is unexpired, caller owns it, stored arguments
still pass schema/role validation. Then runs the tool with the action's
fixed idempotency key. The client can never change the tool or arguments."""
from datetime import datetime

from app.adapters.errors import ToolError
from app.auth.context import UserContext
from app.observability.trace import Trace
from app.orchestrator.actions import ActionStore
from app.schemas.chat import ConfirmActionData
from app.tools.executor import ToolExecutor
from app.tools.registry import ExecContext, ToolDeps


class ActionNotFound(Exception):
    """Unknown, expired or not owned by the caller (indistinguishable on purpose)."""


_FAILURE_TEXT = {
    ToolError.CONFLICT: "it conflicts with an existing loan or reservation",
    ToolError.NOT_RENEWABLE: "the loan is no longer eligible for renewal",
    ToolError.NOT_FOUND: "the item could not be found",
    ToolError.PERMISSION_DENIED: "you are not permitted to do this",
}


async def confirm_action(action_id: str, user: UserContext, actions: ActionStore, executor: ToolExecutor,
                         deps: ToolDeps, trace: Trace) -> ConfirmActionData:
    action = actions.get(action_id)
    if action is None or action.owner != user.user_id:
        raise ActionNotFound()
    if action.result is not None:
        return ConfirmActionData(**action.result)

    ec = ExecContext(user=user, deps=deps, idempotency_key=action.idempotency_key)
    result = await executor.execute(action.tool, action.args, ec, trace, confirmed=True)

    base = {"action_id": action.action_id, "action_type": action.action_type}
    if result.ok:
        d = result.data
        if action.action_type == "reservation":
            msg = (f"Reservation confirmed: '{action.title}' is being held for you to pick up."
                   if d["status"] == "active"
                   else f"You're on the waitlist for '{action.title}' at position {d['queue_position']}. "
                        "Positions can change when higher-priority patrons (faculty, then researchers) join.")
            data = ConfirmActionData(**base, transaction_status="completed", transaction_id=d["reservation_id"],
                                     reservation_id=d["reservation_id"], message=msg, details=d)
        else:
            due = datetime.fromisoformat(d["due_at"]).date()
            data = ConfirmActionData(**base, transaction_status="completed", transaction_id=d["loan_id"],
                                     loan_id=d["loan_id"], message=f"Renewed '{action.title}'. New due date: {due}.",
                                     details=d)
        action.result = data.model_dump(mode="json")
        return data

    code = result.error_code
    if code in ToolError.RETRYABLE:
        # Keep the action (same idempotency key) so the user can safely retry
        status = "failed"
        msg = "The library system is temporarily unavailable. Nothing was changed; please try confirming again."
    else:
        status = "rejected"
        actions.remove(action.action_id)
        reason = _FAILURE_TEXT.get(code, result.error["message"] if result.error else "an unexpected error")
        msg = f"Could not complete the {action.action_type} for '{action.title}': {reason}."
    return ConfirmActionData(**base, transaction_status=status,
                             loan_id=action.args.get("loan_id"), message=msg,
                             details={"error_code": code})
