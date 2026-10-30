import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.errors import APIError
from app.main import create_app
from app.schemas.domain import LoginRequest


@pytest.fixture
def app():
    application = create_app(Settings(_env_file=None, environment="test"))

    @application.post("/test/validation")
    def validate_login(body: LoginRequest):
        return {}

    @application.get("/test/failure")
    def fail():
        raise RuntimeError("sensitive-password-token")

    @application.get("/test/unauthorized")
    def unauthorized():
        raise HTTPException(401, "Authentication required", headers={"WWW-Authenticate": "Bearer"})

    @application.get("/test/conflict")
    def conflict():
        raise APIError(409, "duplicate_reservation", "A reservation already exists")

    return application


@pytest.fixture
def client(app):
    with TestClient(app) as instance:
        yield instance
