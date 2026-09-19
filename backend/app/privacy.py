"""
Privacy and GDPR compliance endpoints for FieldOps Voice Copilot.

Implements Right to Erasure (Art. 17 GDPR) and Right to Access (Art. 15 GDPR).
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import AuditEvent, Feedback, Session, User

logger = logging.getLogger(__name__)


async def delete_user_data(user_id: str, db: AsyncSession) -> Dict[str, Any]:
    """
    Delete or anonymise all personal data for a user (GDPR Right to Erasure).

    Actions taken:
    - Soft-close all active sessions.
    - Anonymise audit events (set user_id = NULL, clear IP).
    - Delete feedback records.
    - Mark user as inactive (account is not hard-deleted to preserve audit trail integrity).

    Note: Raw audio is NEVER stored, so no audio deletion is required.

    Args:
        user_id: The user whose data should be erased.
        db: Async database session.

    Returns:
        Summary dict with counts of records affected.
    """
    # 1. Close active sessions
    sessions_result = await db.execute(
        update(Session)
        .where(Session.user_id == user_id, Session.is_active.is_(True))  # type: ignore[attr-defined]
        .values(is_active=False)
        .returning(Session.session_id)
    )
    closed_sessions = sessions_result.fetchall()

    # 2. Anonymise audit events — preserve event_type and timestamps for compliance
    audit_result = await db.execute(
        update(AuditEvent)
        .where(AuditEvent.user_id == user_id)
        .values(user_id=None, ip_address=None)
        .returning(AuditEvent.id)
    )
    anonymised_events = audit_result.fetchall()

    # 3. Delete feedback
    feedback_result = await db.execute(
        delete(Feedback).where(Feedback.user_id == user_id).returning(Feedback.id)
    )
    deleted_feedback = feedback_result.fetchall()

    # 4. Deactivate user (keep row for referential integrity)
    await db.execute(
        update(User)
        .where(User.id == user_id)
        .values(is_active=False, email=f"deleted-{user_id}@redacted.invalid")
    )

    summary = {
        "user_id": user_id,
        "sessions_closed": len(closed_sessions),
        "audit_events_anonymised": len(anonymised_events),
        "feedback_deleted": len(deleted_feedback),
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }
    logger.info("GDPR deletion completed for user_id=%s: %s", user_id[-8:], summary)
    return summary


async def export_user_data(user_id: str, db: AsyncSession) -> Dict[str, Any]:
    """
    Export all personal data for a user (GDPR Right to Access).

    Returns session metadata and audit records. Raw audio is never stored.

    Args:
        user_id: The user whose data should be exported.
        db: Async database session.

    Returns:
        JSON-serialisable dict with all user data.
    """
    # Fetch user
    user_result = await db.execute(select(User).where(User.id == user_id))
    user = user_result.scalar_one_or_none()

    if user is None:
        return {"error": "User not found"}

    # Fetch sessions
    sessions_result = await db.execute(select(Session).where(Session.user_id == user_id))
    sessions = sessions_result.scalars().all()

    # Fetch audit events (excluding anonymised ones for other users)
    audit_result = await db.execute(
        select(AuditEvent).where(AuditEvent.user_id == user_id)
    )
    audit_events = audit_result.scalars().all()

    # Fetch feedback
    feedback_result = await db.execute(select(Feedback).where(Feedback.user_id == user_id))
    feedbacks = feedback_result.scalars().all()

    return {
        "user": {
            "id": user.id,
            "email": user.email,
            "tenant_id": user.tenant_id,
            "site_ids": user.site_ids,
            "roles": user.roles,
            "created_at": user.created_at.isoformat(),
        },
        "sessions": [
            {
                "session_id": s.session_id,
                "livekit_room": s.livekit_room,
                "created_at": s.created_at.isoformat(),
                "expires_at": s.expires_at.isoformat() if s.expires_at else None,
                "is_active": s.is_active,
            }
            for s in sessions
        ],
        "audit_events": [
            {
                "id": e.id,
                "event_type": e.event_type,
                "event_data": e.event_data,
                "created_at": e.created_at.isoformat(),
                # IP address masked in export
                "ip_address": "redacted",
            }
            for e in audit_events
        ],
        "feedback": [
            {
                "id": f.id,
                "session_id": f.session_id,
                "turn_id": f.turn_id,
                "rating": f.rating,
                "comment": f.comment,
                "created_at": f.created_at.isoformat(),
            }
            for f in feedbacks
        ],
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "note": "Raw audio is never stored by FieldOps Voice Copilot.",
    }


async def purge_old_audit_events(db: AsyncSession) -> int:
    """
    Delete audit events older than AUDIT_RETENTION_DAYS configuration.

    This is intended to be called by a periodic background task.

    Args:
        db: Async database session.

    Returns:
        Number of records deleted.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=settings.AUDIT_RETENTION_DAYS)
    result = await db.execute(
        delete(AuditEvent)
        .where(AuditEvent.created_at < cutoff)
        .returning(AuditEvent.id)
    )
    deleted = result.fetchall()
    logger.info("Purged %d audit events older than %d days", len(deleted), settings.AUDIT_RETENTION_DAYS)
    return len(deleted)
