import json
from datetime import timezone
from pathlib import Path
from uuid import UUID

import pytest
from pydantic import ValidationError

from app.api.contract import create_contract_app
from app.core.config import Settings
from app.main import create_app
from app.schemas.common import ErrorResponse, HealthData, SuccessResponse
from app.schemas.domain import Resource, ResourcePatch


def assert_error(response, code, status):
    assert response.status_code == status
    body = ErrorResponse.model_validate(response.json())
    assert body.error.code == code
    assert body.trace_id == response.headers["x-trace-id"]
    UUID(body.trace_id)
    return body


def test_health_is_enveloped_and_has_unique_server_trace(client):
    first = client.get("/api/v1/health", headers={"X-Trace-ID": "untrusted"})
    second = client.get("/api/v1/health")
    assert first.status_code == 200
    body = SuccessResponse[HealthData].model_validate(first.json())
    assert body.data.status == "ok"
    assert body.trace_id == first.headers["x-trace-id"]
    UUID(body.trace_id)
    assert body.trace_id != second.json()["trace_id"]


@pytest.mark.parametrize("method,path,status,code", [
    ("get", "/api/v1/missing", 404, "not_found"),
    ("post", "/api/v1/health", 405, "method_not_allowed"),
    ("get", "/test/conflict", 409, "duplicate_reservation"),
])
def test_http_and_business_errors_use_shared_contract(client, method, path, status, code):
    assert_error(getattr(client, method)(path), code, status)


def test_authentication_error_retains_bearer_challenge(client):
    response = client.get("/test/unauthorized")
    assert_error(response, "unauthorized", 401)
    assert response.headers["www-authenticate"] == "Bearer"


@pytest.mark.parametrize("payload", [
    {"email": "bad-sensitive-email", "password": "sensitive-password-token"},
    {"email": "demo@example.com"},
    {"email": "demo@example.com", "password": "sensitive-password-token", "user_id": "other-user"},
])
def test_validation_never_echoes_sensitive_inputs(client, payload):
    response = client.post("/test/validation", json=payload)
    assert_error(response, "validation_error", 422)
    assert "sensitive" not in response.text
    assert "demo@example.com" not in response.text


def test_unhandled_errors_are_sanitized_traceable_and_visible_to_browser(client, caplog):
    response = client.get("/test/failure", headers={"Origin": "http://localhost:5173"})
    body = assert_error(response, "internal_error", 500)
    assert "sensitive-password-token" not in response.text + caplog.text
    assert body.trace_id in caplog.text
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert "X-Trace-ID" in response.headers["access-control-expose-headers"]


def test_cors_allows_frontend_authentication_and_idempotency_headers(client):
    response = client.options("/api/v1/reservations", headers={
        "Origin": "http://localhost:3000",
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "Authorization, Content-Type, Idempotency-Key",
    })
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
    rejected = client.options("/api/v1/health", headers={
        "Origin": "https://untrusted.example", "Access-Control-Request-Method": "GET",
    })
    assert rejected.status_code == 400
    assert "access-control-allow-origin" not in rejected.headers


def test_environment_overrides_dotenv_and_cors_is_validated(tmp_path, monkeypatch):
    dotenv = tmp_path / ".env"
    dotenv.write_text("LIBRARY_APP_NAME=From dotenv\n")
    monkeypatch.setenv("LIBRARY_APP_NAME", "From environment")
    monkeypatch.setenv("LIBRARY_CORS_ORIGINS", '["http://localhost:8080"]')
    settings = Settings(_env_file=dotenv)
    assert settings.app_name == "From environment"
    assert settings.cors_origins == ["http://localhost:8080"]
    with pytest.raises(ValidationError):
        Settings(_env_file=None, cors_origins=["*"])


def test_timestamp_contract_normalizes_utc_and_rejects_naive_dates():
    values = dict(resource_id="res-001", title="Python", authors=["Author"], type="book",
                  description="Intro", topics=["Python"], level="beginner", access_level="public")
    resource = Resource(**values, updated_at="2026-10-30T12:00:00+05:30")
    assert resource.updated_at.tzinfo == timezone.utc
    assert resource.updated_at.hour == 6
    assert resource.model_dump(mode="json")["updated_at"].endswith("Z")
    with pytest.raises(ValidationError):
        Resource(**values, updated_at="2026-10-30T12:00:00")


@pytest.mark.parametrize("payload", [{}, {"title": None}, {"resource_id": "res-002"}])
def test_patch_rejects_empty_null_and_server_owned_fields(payload):
    with pytest.raises(ValidationError):
        ResourcePatch.model_validate(payload)


def test_draft_contract_covers_all_operations_without_exposing_runtime_stubs():
    runtime = create_app(Settings(_env_file=None)).openapi()
    assert set(runtime["paths"]) == {
        "/api/v1/health", "/api/v1/auth/login", "/api/v1/auth/me", "/api/v1/me/profile",
        "/api/v1/resources", "/api/v1/resources/{resource_id}",
        "/api/v1/resources/{resource_id}/availability", "/api/v1/resources/{resource_id}/content",
        "/api/v1/me/loans", "/api/v1/me/reservations", "/api/v1/reservations", "/api/v1/loans/{loan_id}/renew"
    }
    draft = create_contract_app().openapi()
    operations = [op for path in draft["paths"].values() for method, op in path.items()
                  if method in {"get", "post", "patch"}]
    assert len(operations) == 15
    assert len({op["operationId"] for op in operations}) == 15
    for operation in operations:
        assert operation["responses"]["422"]["content"]["application/json"]["schema"] == {
            "$ref": "#/components/schemas/ErrorResponse"
        }
    for path in ("/api/v1/reservations", "/api/v1/loans/{loan_id}/renew"):
        operation = draft["paths"][path]["post"]
        key = next(p for p in operation["parameters"] if p["name"] == "Idempotency-Key")
        assert key["required"] is True and key["in"] == "header"
        assert operation["security"] == [{"HTTPBearer": []}]
    assert "security" not in draft["paths"]["/api/v1/auth/login"]["post"]
    for path, method in [("/api/v1/analytics/summary", "get"), ("/api/v1/resources", "post")]:
        assert draft["paths"][path][method]["security"]


def test_exported_contract_matches_current_schemas():
    exported = json.loads(Path("docs/openapi.draft.json").read_text())
    assert exported == create_contract_app().openapi()
