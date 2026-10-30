from datetime import datetime, timedelta, timezone
from typing import Annotated

import jwt
import pytest
from fastapi import Depends, HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.config import Settings
from app.main import create_app
from app.models import Loan, User, UserProfile
from app.schemas.common import SuccessResponse
from app.schemas.domain import LoginData, Profile, UserIdentity
from app.security.dependencies import CurrentUser, DatabaseSession
from app.security.passwords import hash_password
from app.security.permissions import require_librarian, require_owner
from app.services.seed import DEMO_PASSWORD, seed_database

# Test-only key; never used as a production or checked-in demo signing secret.
TEST_SECRET = "test-only-signing-key-with-at-least-64-bytes-not-used-by-the-real-app"


@pytest.fixture
def auth_app(tmp_path):
    app = create_app(Settings(
        _env_file=None, environment="test", database_url=f"sqlite:///{tmp_path / 'auth.db'}",
        jwt_secret=TEST_SECRET,
    ))
    app.state.database.initialize()
    seed_database(app.state.database)

    @app.get("/test/librarian")
    def librarian(user: Annotated[User, Depends(require_librarian)]):
        return {"user_id": user.user_id}

    @app.get("/test/owned-loans/{loan_id}")
    def owned(loan_id: str, user: CurrentUser, session: DatabaseSession):
        loan = session.get(Loan, loan_id)
        if loan is None:
            raise HTTPException(404, "Loan not found")
        require_owner(user, loan.user_id)
        return {"loan_id": loan.loan_id}

    return app


@pytest.fixture
def auth_client(auth_app):
    with TestClient(auth_app) as client:
        yield client


def login(client, email="student1@library.example"):
    response = client.post("/api/v1/auth/login", json={"email": email, "password": DEMO_PASSWORD})
    assert response.status_code == 200
    return response


def bearer(client, email="student1@library.example"):
    return {"Authorization": "Bearer " + login(client, email).json()["data"]["access_token"]}


def signed_token(app, overrides=None, remove=None, key=TEST_SECRET, algorithm="HS256"):
    now = datetime.now(timezone.utc)
    settings = app.state.settings
    claims = dict(sub="user-001", iat=now, nbf=now, exp=now + timedelta(minutes=5),
                  iss=settings.jwt_issuer, aud=settings.jwt_audience, type="access", jti="test-jti")
    claims.update(overrides or {})
    if remove:
        claims.pop(remove)
    return jwt.encode(claims, key, algorithm=algorithm)


def assert_unauthorized(response):
    assert response.status_code == 401
    body = response.json()
    assert body["status"] == "error"
    assert body["error"]["code"] == "unauthorized"
    assert response.headers["www-authenticate"] == "Bearer"
    assert body["trace_id"] == response.headers["x-trace-id"]


def test_login_token_identity_and_profile_contracts(auth_client, auth_app):
    response = login(auth_client, " STUDENT1@LIBRARY.EXAMPLE ")
    data = SuccessResponse[LoginData].model_validate(response.json()).data
    assert data.token_type == "bearer"
    assert data.expires_in == 3600
    assert data.user.user_id == "user-001" and data.user.role == "student"
    assert "password" not in response.text and "password_hash" not in response.text
    assert response.headers["cache-control"] == "no-store"
    claims = jwt.decode(data.access_token, TEST_SECRET, algorithms=["HS256"],
                        audience=auth_app.state.settings.jwt_audience, issuer=auth_app.state.settings.jwt_issuer)
    assert claims["sub"] == "user-001" and claims["type"] == "access"
    assert claims["exp"] - claims["iat"] == 3600
    assert "role" not in claims and "email" not in claims
    headers = {"Authorization": f"Bearer {data.access_token}"}
    me = auth_client.get("/api/v1/auth/me", headers=headers)
    identity = SuccessResponse[UserIdentity].model_validate(me.json()).data
    assert identity.user_id == "user-001"
    profile = auth_client.get("/api/v1/me/profile", headers=headers)
    assert SuccessResponse[Profile].model_validate(profile.json()).data.courses == ["CS101", "DS201"]
    assert me.headers["cache-control"] == profile.headers["cache-control"] == "no-store"


def test_invalid_password_and_unknown_account_have_same_error(auth_client, caplog):
    first = auth_client.post("/api/v1/auth/login", json={"email": "student1@library.example", "password": "wrong-password"})
    second = auth_client.post("/api/v1/auth/login", json={"email": "missing@library.example", "password": "wrong-password"})
    assert_unauthorized(first)
    assert_unauthorized(second)
    assert first.json()["error"] == second.json()["error"]
    assert "wrong-password" not in first.text + second.text + caplog.text


def test_unknown_account_still_checks_password(auth_client, monkeypatch):
    from app.services import auth
    calls = []
    monkeypatch.setattr(auth, "verify_password", lambda password, encoded: calls.append(encoded) or False)
    response = auth_client.post("/api/v1/auth/login", json={"email": "missing@library.example", "password": "wrong"})
    assert_unauthorized(response)
    assert calls == [auth.DUMMY_PASSWORD_HASH]


@pytest.mark.parametrize("headers", [{}, {"Authorization": "Basic abc"}, {"Authorization": "Bearer"},
                                     {"Authorization": "Bearer not-a-token"},
                                     {"Authorization": "Bearer " + "a" * 8193}])
def test_missing_or_invalid_bearer_returns_401(auth_client, headers):
    for endpoint in ("/api/v1/auth/me", "/api/v1/me/profile"):
        assert_unauthorized(auth_client.get(endpoint, headers=headers))


@pytest.mark.parametrize("overrides", [
    {"exp": 1}, {"sub": "missing-user"}, {"sub": ""}, {"sub": 123},
    {"iss": "different-issuer"}, {"aud": "different-api"}, {"type": "refresh"},
    {"iat": 4_102_444_800}, {"nbf": 4_102_444_800}, {"exp": {"invalid": True}},
])
def test_expired_wrong_scope_and_malformed_claims_are_rejected(auth_client, auth_app, overrides):
    token = signed_token(auth_app, overrides)
    assert_unauthorized(auth_client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}))


@pytest.mark.parametrize("claim", ["sub", "exp", "iat", "nbf", "iss", "aud", "type", "jti"])
def test_required_claims_cannot_be_omitted(auth_client, auth_app, claim):
    token = signed_token(auth_app, remove=claim)
    assert_unauthorized(auth_client.get("/api/v1/me/profile", headers={"Authorization": f"Bearer {token}"}))


@pytest.mark.parametrize("key,algorithm", [("wrong-test-signing-key-at-least-32-bytes", "HS256"),
                                            (TEST_SECRET, "HS384"), (None, "none")])
def test_wrong_signature_and_unapproved_algorithms_fail(auth_client, auth_app, key, algorithm):
    token = signed_token(auth_app, key=key, algorithm=algorithm)
    assert_unauthorized(auth_client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}))


def test_profile_ignores_attempts_to_select_another_user(auth_client):
    headers1 = bearer(auth_client)
    headers2 = bearer(auth_client, "student2@library.example")
    first = auth_client.get("/api/v1/me/profile?user_id=user-002", headers=headers1)
    second = auth_client.get("/api/v1/me/profile?user_id=user-001", headers=headers2)
    assert first.json()["data"]["courses"] == ["CS101", "DS201"]
    assert second.json()["data"]["courses"] == ["AI301", "SE202"]
    assert auth_client.get("/api/v1/auth/me?user_id=user-002", headers=headers1).json()["data"]["user_id"] == "user-001"


def test_role_and_ownership_permissions_are_enforced(auth_client):
    student = bearer(auth_client)
    librarian = bearer(auth_client, "librarian@library.example")
    assert_unauthorized(auth_client.get("/test/librarian"))
    denied = auth_client.get("/test/librarian", headers=student)
    assert denied.status_code == 403 and denied.json()["error"]["code"] == "forbidden"
    assert auth_client.get("/test/librarian", headers=librarian).status_code == 200
    assert auth_client.get("/test/owned-loans/loan-001", headers=student).status_code == 200
    assert auth_client.get("/test/owned-loans/loan-004", headers=student).status_code == 403
    assert auth_client.get("/test/owned-loans/loan-001", headers=librarian).status_code == 403


def test_roles_are_reloaded_instead_of_trusted_from_token(auth_client, auth_app):
    token = signed_token(auth_app, {"role": "librarian"})
    headers = {"Authorization": f"Bearer {token}"}
    assert auth_client.get("/test/librarian", headers=headers).status_code == 403
    with auth_app.state.database.write_session() as session:
        session.get(User, "user-001").role = "librarian"
    assert auth_client.get("/test/librarian", headers=headers).status_code == 200
    with auth_app.state.database.write_session() as session:
        session.get(User, "user-001").role = "student"
    assert auth_client.get("/test/librarian", headers=headers).status_code == 403


@pytest.mark.parametrize("role", ["faculty", "researcher"])
def test_other_supported_roles_can_authenticate(auth_client, auth_app, role):
    with auth_app.state.database.write_session() as session:
        user = User(user_id=f"user-{role}", name="Role Demo", email=f"{role}@library.example", role=role,
                    password_hash=hash_password(DEMO_PASSWORD))
        user.profile = UserProfile(courses=["Research"], interests=["RAG"])
        session.add(user)
    headers = bearer(auth_client, f"{role}@library.example")
    assert auth_client.get("/api/v1/auth/me", headers=headers).json()["data"]["role"] == role
    assert auth_client.get("/test/librarian", headers=headers).status_code == 403


def test_login_rejects_role_or_user_id_injection_without_echoing_password(auth_client, caplog):
    response = auth_client.post("/api/v1/auth/login", json={"email": "student1@library.example",
        "password": DEMO_PASSWORD, "role": "librarian", "user_id": "user-003"})
    assert response.status_code == 422
    assert DEMO_PASSWORD not in response.text + caplog.text
    success = login(auth_client)
    assert success.json()["data"]["access_token"] not in caplog.text


def test_deleted_subject_is_no_longer_authenticated(auth_client, auth_app):
    # A transient account avoids deleting seed users referenced by loans and audit data.
    with auth_app.state.database.write_session() as session:
        session.add(User(user_id="transient", name="Transient", email="transient@library.example",
                         role="student", password_hash=hash_password(DEMO_PASSWORD)))
    token = signed_token(auth_app, {"sub": "transient"})
    with auth_app.state.database.write_session() as session:
        session.delete(session.get(User, "transient"))
    assert_unauthorized(auth_client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}))


def test_config_requires_explicit_strong_secret_for_production(monkeypatch):
    monkeypatch.delenv("LIBRARY_JWT_SECRET", raising=False)
    with pytest.raises(ValidationError):
        Settings(_env_file=None, environment="production")
    with pytest.raises(ValidationError) as invalid_key:
        Settings(_env_file=None, jwt_secret="sensitive-short-key")
    assert "sensitive-short-key" not in str(invalid_key.value)
    settings = Settings(_env_file=None, environment="production", jwt_secret=TEST_SECRET)
    assert TEST_SECRET not in repr(settings)
    first = Settings(_env_file=None)
    second = Settings(_env_file=None)
    assert first.jwt_secret.get_secret_value() != second.jwt_secret.get_secret_value()
