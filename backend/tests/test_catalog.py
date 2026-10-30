from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.core.config import Settings
from app.main import create_app
from app.models import AuditLog, Holding, Reservation, Resource, ResourceContent, User
from app.schemas.common import SuccessResponse
from app.schemas.domain import Availability, Resource as ResourceSchema, ResourceContent as ContentSchema, ResourceList
from app.services.catalog import CatalogService
from app.services.seed import DEFAULT_AS_OF, DEMO_PASSWORD, seed_database


@pytest.fixture
def catalog_app(tmp_path):
    app = create_app(Settings(_env_file=None, environment="test", database_url=f"sqlite:///{tmp_path / 'catalog.db'}"))
    app.state.database.initialize()
    seed_database(app.state.database)
    return app


@pytest.fixture
def catalog_client(catalog_app):
    with TestClient(catalog_app) as client:
        yield client


def token(client, email="librarian@library.example"):
    response = client.post("/api/v1/auth/login", json={"email": email, "password": DEMO_PASSWORD})
    assert response.status_code == 200
    return {"Authorization": "Bearer " + response.json()["data"]["access_token"]}


def payload(**overrides):
    body = dict(title="New Synthetic Catalog Title", authors=["Synthetic Author"], type="book",
                description="Local test metadata", topics=["Python", "catalog testing"],
                level="beginner", access_level="public")
    return {**body, **overrides}


def error(response, status, code):
    assert response.status_code == status
    assert response.json()["status"] == "error"
    assert response.json()["error"]["code"] == code
    assert response.json()["trace_id"] == response.headers["x-trace-id"]


def test_public_catalog_pagination_and_total(catalog_client):
    first = catalog_client.get("/api/v1/resources", params={"limit": 10})
    second = catalog_client.get("/api/v1/resources", params={"limit": 10, "offset": 10})
    one = SuccessResponse[ResourceList].model_validate(first.json()).data
    two = SuccessResponse[ResourceList].model_validate(second.json()).data
    assert first.status_code == second.status_code == 200
    assert one.total == two.total == 30
    assert len(one.items) == len(two.items) == 10
    assert {r.resource_id for r in one.items}.isdisjoint({r.resource_id for r in two.items})
    assert one.items[0].resource_id == "res-001"
    assert catalog_client.get("/api/v1/resources", params={"offset": 100}).json()["data"] == {"items": [], "total": 30}


@pytest.mark.parametrize("query,expected", [
    ("pYtHoN", {"res-001", "res-013"}), ("Demo Author 01", {"res-001"}),
    ("RAG", {"res-017"}), ("res-025", {"res-025"}),
    ("not-an-actual-publication-xyz", set()), ("%", set()), ("_", set()),
    ("' OR 1=1 --", set()),
])
def test_search_title_authors_topics_identifiers_and_literal_characters(catalog_client, query, expected):
    response = catalog_client.get("/api/v1/resources", params={"query": query, "limit": 100})
    assert response.status_code == 200
    data = response.json()["data"]
    assert {r["resource_id"] for r in data["items"]} == expected
    assert data["total"] == len(expected)


def test_combined_filters_and_empty_search(catalog_client):
    response = catalog_client.get("/api/v1/resources", params={"query": "Python", "type": "book", "level": "beginner"})
    assert [r["resource_id"] for r in response.json()["data"]["items"]] == ["res-001"]
    assert catalog_client.get("/api/v1/resources", params={"query": "   ", "limit": 100}).json()["data"]["total"] == 30
    assert catalog_client.get("/api/v1/resources", params={"query": "Python", "type": "dissertation"}).json()["data"] == {"items": [], "total": 0}


@pytest.mark.parametrize("params", [
    {"limit": 0}, {"limit": 101}, {"offset": -1}, {"offset": 10**30},
    {"type": "unknown"}, {"level": "expert"}, {"updated_since": "not-a-date"},
    {"updated_since": "2026-10-30T00:00:00"}, {"query": "x" * 1001},
])
def test_catalog_filter_validation(catalog_client, params):
    error(catalog_client.get("/api/v1/resources", params=params), 422, "validation_error")


def test_full_metadata_does_not_expose_content(catalog_client):
    response = catalog_client.get("/api/v1/resources/res-007")
    resource = SuccessResponse[ResourceSchema].model_validate(response.json()).data
    assert resource.access_level == "restricted"
    assert "content" not in response.json()["data"]
    assert "source" not in response.json()["data"]


@pytest.mark.parametrize("suffix", ["", "/availability", "/content"])
def test_unknown_resource_returns_404(catalog_client, suffix):
    error(catalog_client.get("/api/v1/resources/not-present" + suffix), 404, "not_found")


def test_availability_uses_live_inventory_and_waitlist(catalog_client, catalog_app):
    response = catalog_client.get("/api/v1/resources/res-001/availability")
    available = SuccessResponse[Availability].model_validate(response.json()).data
    assert (available.total_copies, available.available_copies) == (5, 4)
    assert len(available.locations) == 2
    unavailable = catalog_client.get("/api/v1/resources/res-002/availability").json()["data"]
    assert unavailable["available_copies"] == 0 and unavailable["waitlist_count"] == 2
    with catalog_app.state.database.write_session() as session:
        session.get(Holding, "hold-001").available_copies = 1
        session.get(Reservation, "reservation-003").status = "cancelled"
        session.get(Reservation, "reservation-003").queue_position = None
    refreshed = catalog_client.get("/api/v1/resources/res-001/availability")
    assert refreshed.json()["data"]["available_copies"] == 3
    assert catalog_client.get("/api/v1/resources/res-002/availability").json()["data"]["waitlist_count"] == 1
    assert refreshed.headers["cache-control"] == "no-store"


def test_content_access_matrix_and_audit(catalog_client, catalog_app):
    public = catalog_client.get("/api/v1/resources/res-001/content")
    assert public.status_code == 200
    content = SuccessResponse[ContentSchema].model_validate(public.json()).data
    assert "Synthetic" in content.content and content.source
    unauthenticated = catalog_client.get("/api/v1/resources/res-003/content")
    error(unauthenticated, 401, "unauthorized")
    assert unauthenticated.headers["www-authenticate"] == "Bearer"
    student = token(catalog_client, "student1@library.example")
    assert catalog_client.get("/api/v1/resources/res-003/content", headers=student).status_code == 200
    denied = catalog_client.get("/api/v1/resources/res-007/content", headers=student)
    error(denied, 403, "forbidden")
    librarian = token(catalog_client)
    assert catalog_client.get("/api/v1/resources/res-007/content", headers=librarian).status_code == 200
    with catalog_app.state.database.session() as session:
        log = session.scalar(select(AuditLog).where(AuditLog.trace_id == denied.json()["trace_id"]))
        assert log.user_id == "user-001" and log.action == "catalog.content" and log.result == "denied"
        log = session.scalar(select(AuditLog).where(AuditLog.trace_id == public.json()["trace_id"]))
        assert log.user_id is None and log.result == "success"


@pytest.mark.parametrize("authorization", ["Basic bad", "Bearer bad"])
def test_invalid_credentials_are_not_treated_as_anonymous_content(catalog_client, authorization):
    error(catalog_client.get("/api/v1/resources/res-001/content", headers={"Authorization": authorization}), 401, "unauthorized")


def test_librarian_create_patch_and_sync(catalog_client, catalog_app):
    librarian = token(catalog_client)
    created = catalog_client.post("/api/v1/resources", headers=librarian, json=payload())
    assert created.status_code == 201
    resource = created.json()["data"]
    resource_id = resource["resource_id"]
    assert resource_id and resource_id != "res-001"
    assert catalog_client.get(f"/api/v1/resources/{resource_id}").json()["data"] == resource
    availability = catalog_client.get(f"/api/v1/resources/{resource_id}/availability").json()["data"]
    assert availability["total_copies"] == availability["available_copies"] == 0
    assert availability["locations"] == []
    error(catalog_client.get(f"/api/v1/resources/{resource_id}/content"), 404, "not_found")
    # Strict greater-than excludes the exact boundary.
    assert catalog_client.get("/api/v1/resources", params={"updated_since": resource["updated_at"]}).json()["data"]["total"] == 0
    updated = catalog_client.patch(f"/api/v1/resources/{resource_id}", headers=librarian,
                                   json={"title": "Revised Synthetic Title", "topics": ["new topic"]})
    assert updated.status_code == 200
    newer = updated.json()["data"]
    assert newer["resource_id"] == resource_id and newer["authors"] == resource["authors"]
    assert datetime.fromisoformat(newer["updated_at"]) > datetime.fromisoformat(resource["updated_at"])
    changed = catalog_client.get("/api/v1/resources", params={"updated_since": resource["updated_at"]}).json()["data"]
    assert changed["total"] == 1 and changed["items"][0]["title"] == "Revised Synthetic Title"
    with catalog_app.state.database.session() as session:
        for response, action in [(created, "catalog.create"), (updated, "catalog.update")]:
            entry = session.scalar(select(AuditLog).where(AuditLog.trace_id == response.json()["trace_id"]))
            assert entry.user_id == "user-003" and entry.action == action and entry.result == "success"


def test_students_cannot_create_or_patch_and_denial_is_audited(catalog_client, catalog_app):
    student = token(catalog_client, "student1@library.example")
    for response in [catalog_client.post("/api/v1/resources", json=payload(), headers=student),
                     catalog_client.patch("/api/v1/resources/res-001", json={"title": "Unauthorized change"}, headers=student)]:
        error(response, 403, "forbidden")
        with catalog_app.state.database.session() as session:
            log = session.scalar(select(AuditLog).where(AuditLog.trace_id == response.json()["trace_id"]))
            assert log.result == "denied" and log.user_id == "user-001"
    with catalog_app.state.database.session() as session:
        assert session.scalar(select(func.count()).select_from(Resource)) == 30
        assert session.get(Resource, "res-001").title == "Python Programming Foundations"
    error(catalog_client.post("/api/v1/resources", json=payload()), 401, "unauthorized")


@pytest.mark.parametrize("patch", [{}, {"title": None}, {"title": "   "}, {"authors": []},
                                   {"resource_id": "res-999"}, {"updated_at": "2026-11-01T00:00:00Z"},
                                   {"access_level": "unknown"}])
def test_patch_validation(catalog_client, patch):
    error(catalog_client.patch("/api/v1/resources/res-001", headers=token(catalog_client), json=patch), 422, "validation_error")


def test_missing_patch_target_and_timestamp_timezone_boundary(catalog_client):
    librarian = token(catalog_client)
    error(catalog_client.patch("/api/v1/resources/missing", headers=librarian, json={"title": "X"}), 404, "not_found")
    # Same instant as the seed anchor, represented with an offset.
    exact = catalog_client.get("/api/v1/resources", params={"updated_since": "2026-10-30T05:30:00+05:30"})
    assert exact.json()["data"]["total"] == 0
    before = (DEFAULT_AS_OF - timedelta(microseconds=1)).isoformat()
    assert catalog_client.get("/api/v1/resources", params={"updated_since": before}).json()["data"]["total"] == 30


def test_access_level_changes_take_effect_without_code_changes(catalog_client):
    assert catalog_client.get("/api/v1/resources/res-001/content").status_code == 200
    librarian = token(catalog_client)
    response = catalog_client.patch("/api/v1/resources/res-001", headers=librarian, json={"access_level": "restricted"})
    assert response.status_code == 200
    error(catalog_client.get("/api/v1/resources/res-001/content"), 401, "unauthorized")
    error(catalog_client.get("/api/v1/resources/res-001/content", headers=token(catalog_client, "student1@library.example")), 403, "forbidden")
    assert catalog_client.get("/api/v1/resources/res-001/content", headers=librarian).status_code == 200


def test_write_transaction_rechecks_role_from_database(catalog_app):
    database = catalog_app.state.database
    with database.session() as session:
        stale_librarian = session.get(User, "user-003")
    with database.write_session() as session:
        session.get(User, "user-003").role = "student"
    from fastapi import HTTPException
    from app.schemas.domain import ResourceCreate
    with pytest.raises(HTTPException) as failure:
        CatalogService(database).create(ResourceCreate(**payload()), stale_librarian, "role-recheck")
    assert failure.value.status_code == 403


def test_catalog_write_and_audit_are_atomic(catalog_client, catalog_app, monkeypatch):
    from app.repositories.library import AuditRepository
    librarian = token(catalog_client)
    def fail_audit(self, record):
        raise RuntimeError("simulated audit failure")
    monkeypatch.setattr(AuditRepository, "add", fail_audit)
    error(catalog_client.post("/api/v1/resources", headers=librarian, json=payload()), 500, "internal_error")
    with catalog_app.state.database.session() as session:
        assert session.scalar(select(func.count()).select_from(Resource)) == 30


def test_catalog_openapi_exposes_optional_content_auth_and_offset(catalog_app):
    schema = catalog_app.openapi()
    parameters = schema["paths"]["/api/v1/resources"]["get"]["parameters"]
    assert "offset" in {p["name"] for p in parameters}
    security = schema["paths"]["/api/v1/resources/{resource_id}/content"]["get"]["security"]
    assert {} in security and {"HTTPBearer": []} in security and len(security) == 2


def test_sync_clock_remains_monotonic_when_fixture_dates_are_ahead(catalog_client, monkeypatch):
    from app.services import catalog
    monkeypatch.setattr(catalog, "utc_now", lambda: DEFAULT_AS_OF - timedelta(days=1))
    librarian = token(catalog_client)
    created = catalog_client.post("/api/v1/resources", headers=librarian, json=payload())
    assert created.status_code == 201
    first_stamp = datetime.fromisoformat(created.json()["data"]["updated_at"])
    assert first_stamp == DEFAULT_AS_OF + timedelta(microseconds=1)
    patched = catalog_client.patch("/api/v1/resources/res-001", headers=librarian, json={"title": "Later change"})
    second_stamp = datetime.fromisoformat(patched.json()["data"]["updated_at"])
    assert second_stamp == first_stamp + timedelta(microseconds=1)
    changed = catalog_client.get("/api/v1/resources", params={"updated_since": first_stamp.isoformat()}).json()["data"]
    assert changed["total"] == 1 and changed["items"][0]["resource_id"] == "res-001"
