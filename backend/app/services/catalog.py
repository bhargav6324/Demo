from datetime import timedelta

from fastapi import HTTPException

from app.core.database import Database
from app.models import AuditLog, Resource, User
from app.models.base import utc_now
from app.repositories.library import (
    AuditRepository, CirculationRepository, HoldingRepository, ResourceRepository, UserRepository,
)
from app.schemas.domain import (
    Availability, Location, Resource as ResourceSchema, ResourceContent, ResourceCreate,
    ResourceList, ResourcePatch,
)
from app.security.permissions import require_librarian
from app.security.tokens import unauthorized


def resource_data(resource: Resource) -> ResourceSchema:
    return ResourceSchema(**{field: getattr(resource, field) for field in ResourceSchema.model_fields})


def existing_resource(repository: ResourceRepository, resource_id: str) -> Resource:
    resource = repository.get(resource_id)
    if resource is None:
        raise HTTPException(404, "Resource not found")
    return resource


class CatalogService:
    def __init__(self, database: Database):
        self.database = database

    def search(self, **filters) -> ResourceList:
        with self.database.session() as session:
            items, total = ResourceRepository(session).search(**filters)
            return ResourceList(items=[resource_data(item) for item in items], total=total)

    def details(self, resource_id: str) -> ResourceSchema:
        with self.database.session() as session:
            return resource_data(existing_resource(ResourceRepository(session), resource_id))

    def availability(self, resource_id: str) -> Availability:
        with self.database.session() as session:
            existing_resource(ResourceRepository(session), resource_id)
            holdings = HoldingRepository(session).for_resource(resource_id)
            return Availability(
                resource_id=resource_id,
                total_copies=sum(item.total_copies for item in holdings),
                available_copies=sum(item.available_copies for item in holdings),
                waitlist_count=CirculationRepository(session).waitlist_count(resource_id),
                locations=[Location(branch=item.branch, shelf=item.shelf, available_copies=item.available_copies) for item in holdings],
            )

    def _audit(self, actor: User | None, action: str, result: str, trace_id: str):
        with self.database.write_session() as session:
            user_id = actor.user_id if actor and UserRepository(session).get(actor.user_id) else None
            AuditRepository(session).add(AuditLog(user_id=user_id, action=action, result=result, trace_id=trace_id))

    def content(self, resource_id: str, actor: User | None, trace_id: str) -> ResourceContent:
        try:
            with self.database.session() as session:
                repository = ResourceRepository(session)
                resource = existing_resource(repository, resource_id)
                user = UserRepository(session).get(actor.user_id) if actor else None
                if actor is not None and user is None:
                    raise unauthorized()
                if resource.access_level != "public" and user is None:
                    raise unauthorized("Bearer authentication is required")
                if resource.access_level == "restricted":
                    require_librarian(user)
                content = repository.content_record(resource_id)
                if content is None:
                    raise HTTPException(404, "Resource content not found")
                data = ResourceContent(resource_id=resource_id, content=content.content,
                                       source=content.source, updated_at=content.updated_at)
        except HTTPException as exc:
            self._audit(actor, "catalog.content", "not_found" if exc.status_code == 404 else "denied", trace_id)
            raise
        self._audit(actor, "catalog.content", "success", trace_id)
        return data

    def _write(self, actor: User, action: str, trace_id: str, operation) -> ResourceSchema:
        failure = None
        with self.database.write_session() as session:
            user = UserRepository(session).get(actor.user_id)
            try:
                if user is None:
                    raise unauthorized()
                require_librarian(user)
                repository = ResourceRepository(session)
                # A globally increasing catalog clock also handles fixed/future fixture dates.
                latest = repository.latest_updated_at()
                stamp = max(utc_now(), latest + timedelta(microseconds=1)) if latest else utc_now()
                resource = operation(repository, stamp)
                session.flush()
                data = resource_data(resource)
                result = "success"
            except HTTPException as exc:
                failure = exc
                result = "not_found" if exc.status_code == 404 else "denied"
            AuditRepository(session).add(AuditLog(user_id=user.user_id if user else None,
                                                 action=action, result=result, trace_id=trace_id))
        if failure:
            raise failure
        return data

    def create(self, body: ResourceCreate, actor: User, trace_id: str) -> ResourceSchema:
        def operation(repository, stamp):
            resource = Resource(**body.model_dump(), updated_at=stamp)
            repository.add(resource)
            return resource
        return self._write(actor, "catalog.create", trace_id, operation)

    def patch(self, resource_id: str, body: ResourcePatch, actor: User, trace_id: str) -> ResourceSchema:
        def operation(repository, stamp):
            resource = existing_resource(repository, resource_id)
            for field, value in body.model_dump(exclude_unset=True).items():
                setattr(resource, field, value)
            resource.updated_at = stamp
            return resource
        return self._write(actor, "catalog.update", trace_id, operation)
