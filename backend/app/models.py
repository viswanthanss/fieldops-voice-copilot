"""
SQLAlchemy ORM models for FieldOps Voice Copilot.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _uuid() -> str:
    """Generate a new UUID4 string."""
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    """Shared declarative base for all models."""


class User(Base):
    """
    Represents a field technician or admin user.

    Attributes:
        id: Primary key (UUID string).
        email: Unique user e-mail address.
        hashed_password: bcrypt-hashed password.
        tenant_id: Organisation/tenant identifier for multi-tenancy.
        site_ids: JSON list of site IDs the user is authorised to access.
        roles: JSON list of role strings, e.g. ["technician", "supervisor"].
        is_active: Whether the user account is enabled.
        created_at: Timestamp of account creation.
    """

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    site_ids: Mapped[List[Any]] = mapped_column(JSON, nullable=False, default=list)
    roles: Mapped[List[Any]] = mapped_column(JSON, nullable=False, default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    sessions: Mapped[List["Session"]] = relationship("Session", back_populates="user", lazy="select")
    audit_events: Mapped[List["AuditEvent"]] = relationship(
        "AuditEvent", back_populates="user", lazy="select"
    )
    feedbacks: Mapped[List["Feedback"]] = relationship("Feedback", back_populates="user", lazy="select")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<User id={self.id!r} email={self.email!r}>"


class Asset(Base):
    """
    Represents an industrial asset (machine, sensor, equipment).

    Attributes:
        asset_id: Primary key — external/domain asset identifier.
        tenant_id: Owning tenant.
        site_id: Physical site where the asset is located.
        equipment_type: High-level category, e.g. "compressor".
        model: Manufacturer model string.
        status: Operational status, e.g. "operational", "maintenance".
        authorized_roles: JSON list of roles allowed to access this asset.
    """

    __tablename__ = "assets"

    asset_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    site_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    equipment_type: Mapped[str] = mapped_column(String(128), nullable=False)
    model: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(64), nullable=False, default="operational")
    authorized_roles: Mapped[List[Any]] = mapped_column(JSON, nullable=False, default=list)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Asset asset_id={self.asset_id!r} site_id={self.site_id!r}>"


class Session(Base):
    """
    A LiveKit voice session for a user interacting with the copilot.

    Attributes:
        session_id: Primary key (UUID string).
        user_id: FK to User.
        tenant_id: Owning tenant (denormalised for fast queries).
        livekit_room: LiveKit room name.
        auth_context: JSON blob — derived auth context (see auth.derive_authorization_context).
        created_at: When the session was created.
        expires_at: When the session expires.
        is_active: Whether the session is still live.
    """

    __tablename__ = "sessions"

    session_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    livekit_room: Mapped[str] = mapped_column(String(256), nullable=False)
    auth_context: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    user: Mapped["User"] = relationship("User", back_populates="sessions")
    audit_events: Mapped[List["AuditEvent"]] = relationship(
        "AuditEvent", back_populates="session", lazy="select"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Session session_id={self.session_id!r} user_id={self.user_id!r}>"


class AuditEvent(Base):
    """
    Immutable server-side audit record for every significant operation.

    Attributes:
        id: Auto-increment PK.
        session_id: FK to Session (nullable — some events happen outside a session).
        user_id: FK to User (nullable — can be anonymised via GDPR deletion).
        event_type: One of the EVENT_TYPES constants.
        event_data: Arbitrary JSON payload.
        created_at: Timestamp.
        ip_address: Client IP (for security audit).
    """

    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("sessions.session_id"), nullable=True, index=True
    )
    user_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True, index=True
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    event_data: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    ip_address: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    session: Mapped[Optional["Session"]] = relationship("Session", back_populates="audit_events")
    user: Mapped[Optional["User"]] = relationship("User", back_populates="audit_events")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<AuditEvent id={self.id} type={self.event_type!r}>"


class Feedback(Base):
    """
    Per-turn feedback from the technician (thumbs up/down + optional comment).

    Attributes:
        id: Auto-increment PK.
        session_id: FK to Session.
        turn_id: Identifies which conversation turn this feedback is for.
        rating: Numeric rating (1-5) or simple 1/0 for thumbs.
        comment: Optional free-text comment.
        created_at: Timestamp.
        user_id: FK to User.
    """

    __tablename__ = "feedback"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("sessions.session_id"), nullable=False, index=True
    )
    user_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True, index=True
    )
    turn_id: Mapped[str] = mapped_column(String(64), nullable=False)
    rating: Mapped[int] = mapped_column(Integer, nullable=False)
    comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    user: Mapped[Optional["User"]] = relationship("User", back_populates="feedbacks")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Feedback id={self.id} session={self.session_id!r} rating={self.rating}>"
