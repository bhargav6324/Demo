"""Google Gemini adapter (google-genai SDK) with native function calling.

Function-calling mode is ANY, so every turn is a structured function call;
the model ends a turn by calling `final_answer`. Automatic function calling
is disabled: the SDK never executes anything, the orchestrator does.

The sync SDK client runs in a worker thread: the async client binds to the
first event loop it sees, which breaks across loops (tests, eval runner)."""
import asyncio
import logging
import re
import time
import uuid

from google import genai
from google.genai import errors as genai_errors
from google.genai import types

from app.llm.base import LLMClient, LLMError, LLMResponse, ToolCall

logger = logging.getLogger("smartlibrary.llm")


def _retry_delay(err: Exception) -> float | None:
    """Seconds Gemini asks us to wait on a 429 (from RetryInfo.retryDelay), if present."""
    m = re.search(r"retryDelay['\"]?\s*:\s*['\"]?(\d+(?:\.\d+)?)s", str(err))
    return float(m.group(1)) if m else None


class GeminiClient(LLMClient):
    def __init__(self, api_key: str, model: str, temperature: float = 0.1,
                 max_retries: int = 2, max_retry_wait: float = 30.0, fallback_models: list[str] | None = None):
        if not api_key:
            raise ValueError("GEMINI_API_KEY is not set")
        self._client = genai.Client(api_key=api_key)
        self._model = model
        # Primary model first, then fallbacks (each free-tier model has its own daily quota)
        self._models = list(dict.fromkeys([model, *(fallback_models or [])]))
        self._exhausted_until: dict[str, float] = {}
        self._temperature = temperature
        self._max_retries = max_retries
        self._max_retry_wait = max_retry_wait

    @staticmethod
    def _to_contents(messages: list[dict]) -> list[types.Content]:
        contents: list[types.Content] = []
        pending_tool_parts: list[types.Part] = []

        def flush_tools():
            if pending_tool_parts:
                contents.append(types.Content(role="user", parts=list(pending_tool_parts)))
                pending_tool_parts.clear()

        for m in messages:
            if m["role"] == "tool":
                pending_tool_parts.append(
                    types.Part.from_function_response(name=m["name"], response=m["content"])
                )
                continue
            flush_tools()
            if m["role"] == "user":
                contents.append(types.Content(role="user", parts=[types.Part.from_text(text=m["content"])]))
            elif m.get("raw") is not None:
                # Replay the model's own turn verbatim (keeps thought signatures intact)
                contents.append(m["raw"])
            else:
                parts = [types.Part.from_text(text=m["content"])] if m.get("content") else []
                parts += [
                    types.Part(function_call=types.FunctionCall(name=c.name, args=c.args))
                    for c in m.get("tool_calls", [])
                ]
                if parts:
                    contents.append(types.Content(role="model", parts=parts))
        flush_tools()
        return contents

    async def generate(self, system: str, messages: list[dict], tools: list[dict]) -> LLMResponse:
        config = types.GenerateContentConfig(
            system_instruction=system,
            temperature=self._temperature,
            tools=[types.Tool(function_declarations=[
                types.FunctionDeclaration(
                    name=t["name"], description=t["description"], parameters_json_schema=t["parameters"]
                )
                for t in tools
            ])],
            tool_config=types.ToolConfig(
                function_calling_config=types.FunctionCallingConfig(mode=types.FunctionCallingConfigMode.ANY)
            ),
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        )
        contents = self._to_contents(messages)
        resp = await self._call_with_retry(contents, config)

        if not resp.candidates or resp.candidates[0].content is None:
            raise LLMError("Gemini returned no content")
        content = resp.candidates[0].content
        calls, texts = [], []
        for part in content.parts or []:
            if part.function_call is not None:
                fc = part.function_call
                calls.append(ToolCall(id=fc.id or uuid.uuid4().hex[:12], name=fc.name, args=dict(fc.args or {})))
            elif part.text and not part.thought:
                texts.append(part.text)
        return LLMResponse(text="".join(texts) or None, tool_calls=calls, raw=content)

    async def _call_with_retry(self, contents, config):
        """Try the primary model, then each fallback. A model whose quota is used up
        (429 with a long retry delay, e.g. the free tier's daily limit) is skipped
        until Gemini says it is available again."""
        last_error: LLMError | None = None
        for model in self._available_models():
            try:
                return await self._call_model(model, contents, config)
            except LLMError as e:
                last_error = e
                if e.code != "llm_rate_limited":
                    raise
                logger.warning("Gemini model %s is out of quota; trying the next fallback model", model)
        raise last_error or LLMError("All Gemini models are out of quota", code="llm_rate_limited")

    def _available_models(self) -> list[str]:
        now = time.monotonic()
        return [m for m in self._models if self._exhausted_until.get(m, 0) <= now]

    async def _call_model(self, model: str, contents, config):
        for attempt in range(self._max_retries + 1):
            try:
                return await asyncio.to_thread(
                    self._client.models.generate_content, model=model, contents=contents, config=config
                )
            except genai_errors.APIError as e:
                status = getattr(e, "code", None)
                retryable = status in (429, 500, 503)
                wait = _retry_delay(e) or 2.0 * (attempt + 1)
                if retryable and attempt < self._max_retries and wait <= self._max_retry_wait:
                    logger.warning("Gemini %s on %s, retrying in %.1fs (attempt %d)", status, model, wait, attempt + 1)
                    await asyncio.sleep(wait)
                    continue
                if status == 429:
                    # Remember the quota is gone so later requests go straight to a fallback
                    self._exhausted_until[model] = time.monotonic() + (_retry_delay(e) or 60.0)
                code = "llm_rate_limited" if status == 429 else "llm_unavailable"
                # Status code only: provider messages can be long and are not for end users
                raise LLMError(f"Gemini API error {status} ({model})", code=code) from e
            except Exception as e:  # noqa: BLE001 - network etc.
                raise LLMError(f"Gemini request failed: {type(e).__name__}") from e
