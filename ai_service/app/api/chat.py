import logging
import time

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.api.deps import get_optional_user, get_services
from app.auth.context import UserContext
from app.llm.base import LLMError
from app.observability.trace import Trace
from app.orchestrator.confirm import ActionNotFound, confirm_action
from app.orchestrator.conversations import ConversationAccessError
from app.schemas.chat import ChatRequest, ConfirmActionRequest
from app.schemas.envelope import ErrorBody, ErrorEnvelope, SuccessEnvelope
from app.services import Services

router = APIRouter(prefix="/chat", tags=["chat"])
logger = logging.getLogger("smartlibrary.api")


def _error(status: int, code: str, message: str, trace: Trace) -> JSONResponse:
    body = ErrorEnvelope(error=ErrorBody(code=code, message=message), trace_id=trace.trace_id)
    return JSONResponse(status_code=status, content=body.model_dump())


@router.post("/messages")
async def post_message(
    req: ChatRequest,
    user: UserContext | None = Depends(get_optional_user),
    services: Services = Depends(get_services),
):
    trace = Trace(user_id=user.user_id if user else None)
    started = time.perf_counter()
    if services.orchestrator is None:
        return _error(503, "llm_not_configured",
                      f"{services.llm_error}. Set GEMINI_API_KEY or LLM_PROVIDER=fake.", trace)
    try:
        data = await services.orchestrator.handle(user, req.conversation_id, req.message, trace)
    except ConversationAccessError as e:
        return _error(404, "conversation_not_found", str(e), trace)
    except LLMError as e:
        logger.error("trace=%s LLM failure: %s", trace.trace_id, e)
        if e.code == "llm_rate_limited":
            return _error(429, "llm_rate_limited",
                          "The AI assistant is receiving too many requests. Please wait a moment and try again.", trace)
        return _error(503, "llm_unavailable", "The AI assistant is temporarily unavailable. Please try again.", trace)

    logger.info("trace=%s outcome=%s intent=%s tools=%s latency_ms=%.0f", trace.trace_id, data.outcome,
                data.intent, trace.tool_names, (time.perf_counter() - started) * 1000)
    return SuccessEnvelope(data=data.model_dump(mode="json"), trace_id=trace.trace_id)


@router.post("/actions/confirm")
async def confirm(
    req: ConfirmActionRequest,
    user: UserContext | None = Depends(get_optional_user),
    services: Services = Depends(get_services),
):
    trace = Trace(user_id=user.user_id if user else None)
    if user is None:
        return _error(401, "unauthorized", "Sign in to confirm actions.", trace)
    try:
        data = await confirm_action(req.action_id, user, services.actions, services.executor, services.deps, trace)
    except ActionNotFound:
        return _error(404, "action_not_found", "This action does not exist or has expired. Please ask again.", trace)
    logger.info("trace=%s confirm action=%s status=%s", trace.trace_id, data.action_type, data.transaction_status)
    return SuccessEnvelope(data=data.model_dump(mode="json"), trace_id=trace.trace_id)
