"""Model fallback when a Gemini model's quota is used up. No network: the SDK call is faked."""
import pytest
from google.genai import errors as genai_errors
from google.genai import types

from app.llm.base import LLMError
from app.llm.gemini_client import GeminiClient

DAILY_QUOTA_429 = {"error": {"code": 429, "message": "Quota exceeded", "status": "RESOURCE_EXHAUSTED",
                             "details": [{"@type": "type.googleapis.com/google.rpc.RetryInfo",
                                          "retryDelay": "58000s"}]}}


def _ok_response():
    part = types.Part(function_call=types.FunctionCall(name="final_answer", args={"message": "hi"}))
    return types.GenerateContentResponse(candidates=[types.Candidate(content=types.Content(role="model", parts=[part]))])


@pytest.fixture
def client(monkeypatch):
    calls = []
    exhausted = {"gemini-a"}

    def fake_generate(model, contents, config):
        calls.append(model)
        if model in exhausted:
            raise genai_errors.ClientError(429, DAILY_QUOTA_429)
        return _ok_response()

    c = GeminiClient("key", "gemini-a", fallback_models=["gemini-b", "gemini-c"])
    monkeypatch.setattr(c._client.models, "generate_content", fake_generate)
    return c, calls, exhausted


async def test_falls_back_when_primary_out_of_quota(client):
    c, calls, _ = client
    resp = await c.generate("sys", [{"role": "user", "content": "hi"}], [])
    assert resp.tool_calls[0].name == "final_answer"
    assert calls == ["gemini-a", "gemini-b"]


async def test_exhausted_model_is_skipped_on_later_requests(client):
    c, calls, _ = client
    await c.generate("sys", [{"role": "user", "content": "hi"}], [])
    calls.clear()
    await c.generate("sys", [{"role": "user", "content": "again"}], [])
    assert calls == ["gemini-b"]  # no wasted call to the exhausted model


async def test_all_models_exhausted_reports_rate_limited(client):
    c, _, exhausted = client
    exhausted.update({"gemini-b", "gemini-c"})
    with pytest.raises(LLMError) as e:
        await c.generate("sys", [{"role": "user", "content": "hi"}], [])
    assert e.value.code == "llm_rate_limited"
