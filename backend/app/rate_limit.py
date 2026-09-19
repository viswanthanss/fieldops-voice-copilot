"""
Rate limiting middleware for FieldOps Voice Copilot using slowapi.
"""
from __future__ import annotations

import logging

from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.config import settings

logger = logging.getLogger(__name__)


def rate_limit_key(request: Request) -> str:
    """
    Return the rate-limit key for a request.

    Uses the authenticated user's email when available (set by auth middleware),
    otherwise falls back to the client IP address. This prevents IP-based
    evasion by authenticated users while still protecting unauthenticated routes.

    Args:
        request: The incoming FastAPI request.

    Returns:
        A string key used by slowapi to bucket the rate limit.
    """
    # Auth middleware stores email in request.state.user_email after token validation
    user_email: str | None = getattr(request.state, "user_email", None)
    if user_email:
        return user_email
    return get_remote_address(request)


def get_rate_limiter() -> Limiter:
    """
    Create and return the configured slowapi Limiter instance.

    The default limit is driven by RATE_LIMIT_PER_MINUTE config.

    Returns:
        A slowapi Limiter instance wired to rate_limit_key.
    """
    limiter = Limiter(
        key_func=rate_limit_key,
        default_limits=[f"{settings.RATE_LIMIT_PER_MINUTE}/minute"],
        storage_uri=settings.REDIS_URL,  # None → in-memory
    )
    return limiter


# Module-level singleton used by the FastAPI app and route decorators
limiter: Limiter = get_rate_limiter()
