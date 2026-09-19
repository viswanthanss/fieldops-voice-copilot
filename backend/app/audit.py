"""
Audit event logging for FieldOps Voice Copilot.

SECURITY: Audit records are ALWAYS generated server-side.
Browser/client-submitted audit records are NEVER trusted.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditEvent

logger = logging.getLogger(__name__)

# ── Event type constants ──────────────────────────────────────────────────────
SESSION_INIT = "SESSION_INIT"
ASSET_ACCESS = "ASSET_ACCESS"
ASSET_DENIED = "ASSET_DENIED"
QUERY_SUBMITTED = "QUERY_SUBMITTED"
EVIDENCE_GATE_PASS = "EVIDENCE_GATE_PASS"
EVIDENCE_GATE_FAIL = "EVIDENCE_GATE_FAIL"
GROUNDING_PASS = "GROUNDING_PASS"
GROUNDING_FAIL = "GROUNDING_FAIL"
FEEDBACK_SUBMITTED = "FEEDBACK_SUBMITTED"
DATA_DELETION_REQUEST = "DATA_DELETION_REQUEST"
DATA_EXPORT_REQUEST = "DATA_EXPORT_REQUEST"
USER_REGISTERED = "USER_REGISTERED"
LOGIN_SUCCESS = "LOGIN_SUCCESS"
LOGIN_FAILURE = "LOGIN_FAILURE"

ALL_EVENT_TYPES = {
    SESSION_INIT,
    ASSET_ACCESS,
    ASSET_DENIED,
    QUERY_SUBMITTED,
    EVIDENCE_GATE_PASS,
    EVIDENCE_GATE_FAIL,
    GROUNDING_PASS,
    GROUNDING_FAIL,
    FEEDBACK_SUBMITTED,
    DATA_DELETION_REQUEST,
    DATA_EXPORT_REQUEST,
    USER_REGISTERED,
    LOGIN_SUCCESS,
    LOGIN_FAILURE,
}


async def log_event(
    db: AsyncSession,
    event_type: str,
    user_id: Optional[str] = None,
    session_id: Optional[str] = None,
    event_data: Optional[Dict[str, Any]] = None,
    ip_address: Optional[str] = None,
) -> AuditEvent:
    """
    Persist a server-side audit event to the database.

    This function is the ONLY authorised path for writing audit records. It
    must never be called with data sourced directly from the client.

    Args:
        db: Async database session.
        event_type: One of the event type constants defined in this module.
        user_id: ID of the acting user (may be None before auth is resolved).
        session_id: Active session ID (may be None for auth events).
        event_data: Arbitrary JSON-serialisable payload describing the event.
        ip_address: Client IP address for security auditing.

    Returns:
        The persisted AuditEvent ORM object.
    """
    if event_type not in ALL_EVENT_TYPES:
        logger.warning("Unknown audit event type: %s — logging anyway.", event_type)

    event = AuditEvent(
        event_type=event_type,
        user_id=user_id,
        session_id=session_id,
        event_data=event_data or {},
        ip_address=ip_address,
    )
    db.add(event)
    await db.flush()  # get the auto-generated id without committing the outer transaction

    logger.info(
        "AUDIT event_type=%s user_id=%s session_id=%s",
        event_type,
        # Mask user_id in logs for PII protection — only show last 8 chars
        (user_id[-8:] if user_id else "anonymous"),
        (session_id[-8:] if session_id else "none"),
    )
    return event
