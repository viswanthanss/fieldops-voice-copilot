"""
Session management for FieldOps Voice Copilot.

Initialises LiveKit sessions with server-derived authorization contexts.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.auth import derive_authorization_context
from app.config import settings
from app.models import Session as SessionModel, User

logger = logging.getLogger(__name__)


class SessionInfo:
    """Value object returned by initialize_session."""

    def __init__(
        self,
        session_id: str,
        livekit_token: str,
        livekit_url: str,
        auth_context: Dict[str, Any],
        expires_at: datetime,
    ) -> None:
        self.session_id = session_id
        self.livekit_token = livekit_token
        self.livekit_url = livekit_url
        self.auth_context = auth_context
        self.expires_at = expires_at

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a JSON-safe dict."""
        return {
            "session_id": self.session_id,
            "livekit_token": self.livekit_token,
            "livekit_url": self.livekit_url,
            "auth_context": self.auth_context,
            "expires_at": self.expires_at.isoformat(),
        }


def _build_livekit_token(room: str, user: User) -> str:
    """
    Generate a real LiveKit access token for a room using official livekit-api.

    Raises HTTPException if LiveKit configuration is missing or token generation fails.
    Never returns a placeholder or fake token.

    Args:
        room: LiveKit room name.
        user: Authenticated user — identity embedded in the token.

    Returns:
        Signed LiveKit JWT string.
    """
    if not settings.LIVEKIT_API_KEY or not settings.LIVEKIT_API_SECRET:
        logger.error("LiveKit credentials not configured: LIVEKIT_API_KEY or LIVEKIT_API_SECRET missing")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="LiveKit credentials are not configured on the server. Please set LIVEKIT_API_KEY and LIVEKIT_API_SECRET.",
        )

    try:
        from livekit.api import AccessToken, VideoGrants  # type: ignore

        token = (
            AccessToken(settings.LIVEKIT_API_KEY, settings.LIVEKIT_API_SECRET)
            .with_identity(user.id)
            .with_name(user.email)
            .with_grants(VideoGrants(room_join=True, room=room))
        )
        return token.to_jwt()
    except Exception as exc:
        logger.error("LiveKit token generation failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate real LiveKit access token: {str(exc)}",
        )


async def initialize_session(
    user: User,
    db: AsyncSession,
    asset_id: Optional[str] = None,
) -> SessionInfo:
    """
    Initialise a new voice session for a user.

    Steps (ORDER MATTERS — matches the architecture security pipeline):
    1. Derive authorization context server-side (asset scope enforced here).
    2. Generate LiveKit room name and access token.
    3. Persist the session record to the database.
    4. Return SessionInfo to the caller.

    Authorization is established BEFORE any LiveKit token is issued.

    Args:
        user: Authenticated user.
        db: Async database session.
        asset_id: Optional asset to scope this session to.

    Returns:
        SessionInfo containing session_id, livekit_token, livekit_url, auth_context.
    """
    # Step 1 — Derive auth context (asset scope validated inside)
    auth_context = await derive_authorization_context(user, db, asset_id=asset_id)

    # Step 2 — LiveKit room and token
    room_name = f"fieldops-{user.tenant_id}-{uuid.uuid4().hex[:8]}"
    livekit_token = _build_livekit_token(room_name, user)

    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    # Step 3 — Persist session
    session = SessionModel(
        user_id=user.id,
        tenant_id=user.tenant_id,
        livekit_room=room_name,
        auth_context=auth_context,
        expires_at=expires_at,
        is_active=True,
    )
    db.add(session)
    await db.flush()

    logger.info(
        "Session initialised: session_id=%s user=%s room=%s",
        session.session_id,
        user.id[-8:],
        room_name,
    )

    return SessionInfo(
        session_id=session.session_id,
        livekit_token=livekit_token,
        livekit_url=settings.LIVEKIT_URL,
        auth_context=auth_context,
        expires_at=expires_at,
    )


async def get_session(session_id: str, db: AsyncSession) -> SessionModel:
    """
    Retrieve an active session by ID.

    Args:
        session_id: The session UUID.
        db: Async database session.

    Returns:
        The SessionModel ORM object.

    Raises:
        HTTPException 404: If the session does not exist or is inactive.
    """
    result = await db.execute(
        select(SessionModel).where(
            SessionModel.session_id == session_id,
            SessionModel.is_active.is_(True),  # type: ignore[attr-defined]
        )
    )
    session = result.scalar_one_or_none()
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found or already closed",
        )
    return session


async def invalidate_session(session_id: str, db: AsyncSession) -> None:
    """
    Mark a session as inactive (soft-delete).

    Args:
        session_id: The session UUID to invalidate.
        db: Async database session.
    """
    session = await get_session(session_id, db)
    session.is_active = False
    db.add(session)
    await db.flush()
    logger.info("Session invalidated: session_id=%s", session_id[-8:])
