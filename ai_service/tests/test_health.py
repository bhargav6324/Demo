from app.llm.fake_llm import ScriptedLLM


def test_health_returns_success_envelope(make_app):
    client, _ = make_app(ScriptedLLM([]))
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "success"
    assert body["data"]["service"] == "smart-library-ai"
    assert body["data"]["status"] == "ok"  # frontend reads data.status: ok | degraded
    assert body["trace_id"]


def test_health_degraded_when_backend_down(make_app):
    client, services = make_app(ScriptedLLM([]))
    async def down():
        return False
    services.adapter.health = down
    data = client.get("/api/v1/health").json()["data"]
    assert data["status"] == "degraded" and data["backend_reachable"] is False


def test_unknown_route_uses_error_envelope(make_app):
    client, _ = make_app(ScriptedLLM([]))
    resp = client.get("/api/v1/nope")
    assert resp.status_code == 404
    assert resp.json()["status"] == "error"
