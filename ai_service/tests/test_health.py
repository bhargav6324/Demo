from fastapi.testclient import TestClient

from app.main import app


def test_health_returns_success_envelope():
    resp = TestClient(app).get("/api/v1/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "success"
    assert body["data"]["service"] == "smart-library-ai"
    assert body["trace_id"]


def test_unknown_route_uses_error_envelope():
    resp = TestClient(app).get("/api/v1/nope")
    assert resp.status_code == 404
    assert resp.json()["status"] == "error"
