from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    JSON, CheckConstraint, ForeignKey, ForeignKeyConstraint, Index, Integer,
    String, Text, UniqueConstraint, text,
)
from sqlalchemy.ext.mutable import MutableList
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UTCDateTime, new_id, utc_now


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("role IN ('student','faculty','researcher','librarian')", name="valid_role"),
        CheckConstraint("email = lower(email)", name="normalized_email"),
    )

    user_id: Mapped[str] = mapped_column(String(128), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str] = mapped_column(String(254), unique=True)
    password_hash: Mapped[str] = mapped_column(String(512))
    role: Mapped[str] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)
    profile: Mapped["UserProfile"] = relationship(back_populates="user", uselist=False)
    loans: Mapped[list["Loan"]] = relationship(back_populates="user")
    reservations: Mapped[list["Reservation"]] = relationship(back_populates="user")


class UserProfile(Base):
    __tablename__ = "user_profiles"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.user_id"), primary_key=True)
    courses: Mapped[list[str]] = mapped_column(MutableList.as_mutable(JSON), default=list)
    interests: Mapped[list[str]] = mapped_column(MutableList.as_mutable(JSON), default=list)
    user: Mapped[User] = relationship(back_populates="profile")


class Resource(Base):
    __tablename__ = "resources"
    __table_args__ = (
        CheckConstraint("type IN ('book','journal','paper','ebook','dissertation')", name="valid_type"),
        CheckConstraint("level IN ('beginner','intermediate','advanced')", name="valid_level"),
        CheckConstraint("access_level IN ('public','authenticated','restricted')", name="valid_access"),
        Index("ix_resources_type_level", "type", "level"),
    )

    resource_id: Mapped[str] = mapped_column(String(128), primary_key=True, default=new_id)
    title: Mapped[str] = mapped_column(String(1000), index=True)
    authors: Mapped[list[str]] = mapped_column(MutableList.as_mutable(JSON))
    type: Mapped[str] = mapped_column(String(20))
    description: Mapped[str] = mapped_column(Text)
    topics: Mapped[list[str]] = mapped_column(MutableList.as_mutable(JSON))
    level: Mapped[str] = mapped_column(String(20))
    access_level: Mapped[str] = mapped_column(String(20))
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now, onupdate=utc_now, index=True)
    holdings: Mapped[list["Holding"]] = relationship(back_populates="resource")
    content: Mapped["ResourceContent | None"] = relationship(back_populates="resource", uselist=False)


class ResourceContent(Base):
    __tablename__ = "resource_contents"

    resource_id: Mapped[str] = mapped_column(ForeignKey("resources.resource_id"), primary_key=True)
    content: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(1000))
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now, onupdate=utc_now)
    resource: Mapped[Resource] = relationship(back_populates="content")


class Holding(Base):
    __tablename__ = "holdings"
    __table_args__ = (
        UniqueConstraint("resource_id", "branch", "shelf"),
        UniqueConstraint("holding_id", "resource_id"),
        CheckConstraint("total_copies >= 0", name="nonnegative_total"),
        CheckConstraint("available_copies >= 0 AND available_copies <= total_copies", name="valid_available"),
    )

    holding_id: Mapped[str] = mapped_column(String(128), primary_key=True, default=new_id)
    resource_id: Mapped[str] = mapped_column(ForeignKey("resources.resource_id"), index=True)
    branch: Mapped[str] = mapped_column(String(200))
    shelf: Mapped[str] = mapped_column(String(100))
    total_copies: Mapped[int] = mapped_column(Integer)
    available_copies: Mapped[int] = mapped_column(Integer)
    resource: Mapped[Resource] = relationship(back_populates="holdings")


class Loan(Base):
    __tablename__ = "loans"
    __table_args__ = (
        ForeignKeyConstraint(["holding_id", "resource_id"], ["holdings.holding_id", "holdings.resource_id"]),
        CheckConstraint("status IN ('active','returned','overdue')", name="valid_status"),
        CheckConstraint("due_at >= borrowed_at", name="valid_due_date"),
        CheckConstraint("renewal_count >= 0", name="nonnegative_renewals"),
        CheckConstraint("fine_amount_minor >= 0", name="nonnegative_fine"),
        CheckConstraint("(status = 'returned' AND returned_at IS NOT NULL AND returned_at >= borrowed_at) OR (status IN ('active','overdue') AND returned_at IS NULL)", name="return_consistency"),
        Index("ix_loans_user_status", "user_id", "status"),
        Index("ix_loans_status_due", "status", "due_at"),
    )

    loan_id: Mapped[str] = mapped_column(String(128), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.user_id"))
    resource_id: Mapped[str] = mapped_column(ForeignKey("resources.resource_id"), index=True)
    holding_id: Mapped[str] = mapped_column(String(128))
    borrowed_at: Mapped[datetime] = mapped_column(UTCDateTime())
    due_at: Mapped[datetime] = mapped_column(UTCDateTime())
    returned_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    renewal_count: Mapped[int] = mapped_column(Integer, default=0)
    fine_amount_minor: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20))
    user: Mapped[User] = relationship(back_populates="loans")

    @property
    def fine_amount(self) -> Decimal:
        return Decimal(self.fine_amount_minor) / Decimal(100)


class Reservation(Base):
    __tablename__ = "reservations"
    __table_args__ = (
        ForeignKeyConstraint(["allocated_holding_id", "resource_id"], ["holdings.holding_id", "holdings.resource_id"]),
        CheckConstraint("status IN ('active','waitlisted','cancelled','fulfilled')", name="valid_status"),
        CheckConstraint("(status = 'waitlisted' AND queue_position IS NOT NULL AND queue_position > 0 AND allocated_holding_id IS NULL) OR (status = 'active' AND queue_position IS NULL AND allocated_holding_id IS NOT NULL) OR (status IN ('cancelled','fulfilled') AND queue_position IS NULL AND allocated_holding_id IS NULL)", name="allocation_consistency"),
        Index("uq_reservations_open_user_resource", "user_id", "resource_id", unique=True,
              sqlite_where=text("status IN ('active','waitlisted')")),
        Index("uq_reservations_waitlist_position", "resource_id", "queue_position", unique=True,
              sqlite_where=text("status = 'waitlisted'")),
        Index("ix_reservations_resource_status", "resource_id", "status"),
        Index("ix_reservations_status", "status"),
    )

    reservation_id: Mapped[str] = mapped_column(String(128), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.user_id"), index=True)
    resource_id: Mapped[str] = mapped_column(ForeignKey("resources.resource_id"))
    status: Mapped[str] = mapped_column(String(20))
    queue_position: Mapped[int | None] = mapped_column(Integer)
    allocated_holding_id: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)
    user: Mapped[User] = relationship(back_populates="reservations")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    audit_id: Mapped[str] = mapped_column(String(128), primary_key=True, default=new_id)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.user_id"), index=True)
    action: Mapped[str] = mapped_column(String(100))
    result: Mapped[str] = mapped_column(String(100))
    trace_id: Mapped[str] = mapped_column(String(128), index=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now, index=True)


class IdempotencyRecord(Base):
    __tablename__ = "idempotency_records"
    __table_args__ = (
        UniqueConstraint("user_id", "operation", "key"),
        CheckConstraint("length(request_hash) = 64", name="sha256_length"),
        CheckConstraint("status_code >= 200 AND status_code < 300", name="success_status"),
    )

    idempotency_id: Mapped[str] = mapped_column(String(128), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.user_id"))
    operation: Mapped[str] = mapped_column(String(255))
    key: Mapped[str] = mapped_column(String(128))
    request_hash: Mapped[str] = mapped_column(String(64))
    status_code: Mapped[int] = mapped_column(Integer)
    response_data: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)
