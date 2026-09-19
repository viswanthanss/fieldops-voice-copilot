"""
JWT authentication and authorisation context derivation for FieldOps Voice Copilot.

Security invariants enforced here:
- Tokens are HS256 JWTs signed with SECRET_KEY.
- Authorization context is ALWAYS derived server-side from the database user record.
- A user cannot escalate scope by claiming an asset outside their authorised site_ids.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_db
from app.models import Asset, User

logger = logging.getLogger(__name__)

# ── Password hashing ──────────────────────────────────────────────────────────
_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# ── OAuth2 scheme ─────────────────────────────────────────────────────────────
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token")


# ── Password utilities ────────────────────────────────────────────────────────


def hash_password(plain: str) -> str:
    """
    Hash a plaintext password using bcrypt.

    Args:
        plain: The plaintext password.

    Returns:
        The bcrypt hash string.
    """
    return _pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    """
    Verify a plaintext password against a stored bcrypt hash.

    Args:
        plain: The plaintext password supplied by the user.
        hashed: The stored bcrypt hash.

    Returns:
        True if the password matches, False otherwise.
    """
    return _pwd_context.verify(plain, hashed)


# ── Token utilities ───────────────────────────────────────────────────────────


def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    """
    Create a signed JWT access token.

    Args:
        data: Claims to embed. Must include a ``sub`` field (user ID).
        expires_delta: Optional custom expiry; defaults to ACCESS_TOKEN_EXPIRE_MINUTES.

    Returns:
        Encoded JWT string.
    """
    to_encode = data.copy()
    now = datetime.now(timezone.utc)
    expire = now + (expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire, "iat": now})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def verify_token(token: str) -> Dict[str, Any]:
    """
    Decode and verify a JWT token.

    Args:
        token: Encoded JWT string.

    Returns:
        The decoded claims dictionary.

    Raises:
        HTTPException 401: If the token is invalid or expired.
    """
    credentials_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        if payload.get("sub") is None:
            raise credentials_exc
        return payload
    except JWTError:
        raise credentials_exc


# ── FastAPI dependency ────────────────────────────────────────────────────────


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    FastAPI dependency — resolves the current authenticated user from the JWT.

    Args:
        token: Bearer token extracted by OAuth2PasswordBearer.
        db: Async database session.

    Returns:
        The authenticated User ORM object.

    Raises:
        HTTPException 401: If token is invalid or user not found.
        HTTPException 403: If the user account is inactive.
    """
    payload = verify_token(token)
    user_id: str = payload["sub"]

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Inactive user")

    return user


# ── Authorisation context ─────────────────────────────────────────────────────


async def derive_authorization_context(
    user: User,
    db: AsyncSession,
    asset_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Derive the authorization context for a user, optionally scoped to a specific asset.

    CRITICAL SECURITY INVARIANT: A user can NEVER expand their scope beyond their
    own ``site_ids``. If ``asset_id`` is supplied and the asset's ``site_id`` is NOT
    in the user's ``site_ids``, the asset is excluded from the context and an ASSET_DENIED
    event should be logged by the caller.

    Args:
        user: Authenticated User ORM object.
        db: Async database session.
        asset_id: Optional asset to include in the context.

    Returns:
        Dict containing:
            - tenant_id
            - site_ids
            - asset_ids (list of assets visible to the user)
            - roles
            - permissions (derived from roles)
            - issued_at (ISO-8601 string)
            - expires_at (ISO-8601 string)
    """
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    # Resolve asset_ids the user is authorised to see (within their site_ids)
    asset_ids: List[str] = []
    if asset_id:
        result = await db.execute(
            select(Asset).where(
                Asset.asset_id == asset_id,
                Asset.tenant_id == user.tenant_id,
                Asset.site_id.in_(user.site_ids),  # type: ignore[attr-defined]
            )
        )
        asset = result.scalar_one_or_none()
        if asset is not None:
            asset_ids.append(asset.asset_id)
        # If asset not found within user's sites → asset_ids remains empty
        # Caller is responsible for logging ASSET_DENIED

    # Map roles → permissions
    permissions = _roles_to_permissions(user.roles)

    return {
        "tenant_id": user.tenant_id,
        "site_ids": list(user.site_ids),
        "asset_ids": asset_ids,
        "roles": list(user.roles),
        "permissions": permissions,
        "issued_at": now.isoformat(),
        "expires_at": expires_at.isoformat(),
    }


def _roles_to_permissions(roles: List[str]) -> List[str]:
    """
    Map a list of role strings to a list of permission strings.

    Args:
        roles: List of role names, e.g. ["technician", "supervisor"].

    Returns:
        Deduplicated list of permission strings.
    """
    role_permission_map: Dict[str, List[str]] = {
        "technician": ["asset:read", "session:create", "feedback:write"],
        "supervisor": ["asset:read", "asset:write", "session:create", "feedback:write", "audit:read"],
        "admin": [
            "asset:read",
            "asset:write",
            "asset:delete",
            "session:create",
            "feedback:write",
            "audit:read",
            "user:manage",
        ],
    }
    perms: set[str] = set()
    for role in roles:
        perms.update(role_permission_map.get(role, []))
    return sorted(perms)
