"""
Asset management for FieldOps Voice Copilot.

CRITICAL: All asset lookups enforce site-level authorization — a user
can only see assets whose site_id is within their own site_ids list.
"""
from __future__ import annotations

import logging
from typing import List, Optional

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Asset, User

logger = logging.getLogger(__name__)


async def get_asset(asset_id: str, user: User, db: AsyncSession) -> Asset:
    """
    Retrieve a single asset, enforcing site-level authorization.

    SECURITY: The query explicitly filters by both ``tenant_id`` and
    ``site_id IN user.site_ids`` so a user can never access an asset
    outside their authorised sites, regardless of what asset_id they supply.

    Args:
        asset_id: The asset identifier to look up.
        user: The authenticated user requesting access.
        db: Async database session.

    Returns:
        The matching Asset ORM object.

    Raises:
        HTTPException 404: If asset does not exist or is outside the user's sites.
    """
    result = await db.execute(
        select(Asset).where(
            Asset.asset_id == asset_id,
            Asset.tenant_id == user.tenant_id,
            Asset.site_id.in_(user.site_ids),  # type: ignore[attr-defined]
        )
    )
    asset = result.scalar_one_or_none()

    if asset is None:
        # Return 404 rather than 403 to avoid leaking asset existence to
        # callers who are not authorized (security-by-obscurity complement).
        logger.warning(
            "Asset access denied: asset_id=%s user_id=%s",
            asset_id,
            user.id[-8:],
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Asset not found or not accessible",
        )

    logger.info("Asset access granted: asset_id=%s user_id=%s", asset_id, user.id[-8:])
    return asset


async def list_assets(user: User, db: AsyncSession) -> List[Asset]:
    """
    List all assets visible to a user within their authorised sites.

    Args:
        user: The authenticated user.
        db: Async database session.

    Returns:
        List of Asset ORM objects accessible to the user.
    """
    result = await db.execute(
        select(Asset).where(
            Asset.tenant_id == user.tenant_id,
            Asset.site_id.in_(user.site_ids),  # type: ignore[attr-defined]
        )
    )
    return list(result.scalars().all())


async def create_asset(
    asset_id: str,
    tenant_id: str,
    site_id: str,
    equipment_type: str,
    model: str,
    status: str,
    authorized_roles: List[str],
    requesting_user: User,
    db: AsyncSession,
) -> Asset:
    """
    Create a new asset record. Restricted to admin users.

    Args:
        asset_id: Unique asset identifier.
        tenant_id: Tenant this asset belongs to.
        site_id: Physical site of the asset.
        equipment_type: High-level equipment category.
        model: Manufacturer model string.
        status: Initial operational status.
        authorized_roles: Roles permitted to access this asset.
        requesting_user: The user performing the creation (must have admin role).
        db: Async database session.

    Returns:
        The newly created Asset ORM object.

    Raises:
        HTTPException 403: If the requesting user is not an admin.
        HTTPException 409: If an asset with the same asset_id already exists.
    """
    if "admin" not in requesting_user.roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required to create assets",
        )

    # Check for duplicate
    existing = await db.execute(select(Asset).where(Asset.asset_id == asset_id))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=409,
            detail=f"Asset '{asset_id}' already exists",
        )

    asset = Asset(
        asset_id=asset_id,
        tenant_id=tenant_id,
        site_id=site_id,
        equipment_type=equipment_type,
        model=model,
        status=status,
        authorized_roles=authorized_roles,
    )
    db.add(asset)
    await db.flush()
    logger.info("Asset created: asset_id=%s by user=%s", asset_id, requesting_user.id[-8:])
    return asset
