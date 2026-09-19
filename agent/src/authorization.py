"""
Authorization Context Verification for FieldOps Voice Copilot.

Enforces tenant, site, and asset authorization boundaries before any retrieval occurs.
The client/spoken utterance can never expand the server-derived authorization scope.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional
import structlog

logger = structlog.get_logger(__name__)


class AuthorizationDeniedError(Exception):
    """Raised when a technician requests documentation for an asset or site outside their authorized scope."""
    def __init__(self, message: str, asset_id: Optional[str] = None, site_id: Optional[str] = None):
        super().__init__(message)
        self.asset_id = asset_id
        self.site_id = site_id


def verify_retrieval_scope(
    auth_context: Dict[str, Any],
    requested_asset_id: Optional[str] = None,
    requested_site_id: Optional[str] = None,
    requested_model: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Verify that the requested equipment is strictly within the authenticated user's scope.

    CRITICAL SECURITY INVARIANT:
    User speech or client parameters cannot elevate privileges or expand the server-derived
    auth_context. If an asset is named that is not in the technician's allowed assets,
    retrieval is blocked immediately before Moss is invoked.

    Args:
        auth_context: Signed, server-derived authorization context dictionary.
                      Expected keys: tenant_id, site_ids, asset_ids, roles, user_id.
        requested_asset_id: Optional asset ID parsed from technician's query (e.g. CP-991).
        requested_site_id: Optional site ID parsed from query.
        requested_model: Optional model parsed from query (e.g. CP-200).

    Returns:
        Approved metadata constraints dict for Moss retrieval filtering.

    Raises:
        AuthorizationDeniedError: If the asset or site is not authorized.
    """
    tenant_id = auth_context.get("tenant_id")
    if not tenant_id:
        raise AuthorizationDeniedError("No tenant ID present in authorization context.")

    authorized_sites: List[str] = auth_context.get("site_ids", [])
    authorized_assets: List[str] = auth_context.get("asset_ids", [])
    roles: List[str] = auth_context.get("roles", [])

    # 1. Verify Site Authorization (if a site was explicitly specified)
    if requested_site_id and authorized_sites:
        if requested_site_id not in authorized_sites:
            logger.warning(
                "unauthorized_site_access_blocked",
                user_id=auth_context.get("user_id"),
                requested_site=requested_site_id,
                authorized_sites=authorized_sites,
            )
            raise AuthorizationDeniedError(
                f"Site '{requested_site_id}' is not in your authorized work locations.",
                site_id=requested_site_id,
            )

    # 2. Verify Asset Authorization
    # If the user has specific asset constraints, check that the requested asset is permitted
    if requested_asset_id and authorized_assets:
        # Check direct match or site-prefixed match
        is_permitted = False
        for allowed in authorized_assets:
            if allowed.upper() == requested_asset_id.upper() or allowed.upper().endswith(f"/{requested_asset_id.upper()}"):
                is_permitted = True
                break
        
        if not is_permitted:
            logger.warning(
                "unauthorized_asset_access_blocked",
                user_id=auth_context.get("user_id"),
                requested_asset=requested_asset_id,
                authorized_assets=authorized_assets,
            )
            raise AuthorizationDeniedError(
                f"Asset '{requested_asset_id}' is not in your assigned maintenance scope.",
                asset_id=requested_asset_id,
            )

    # 3. Build Authorized Retrieval Constraints (passed to Moss metadata filter)
    # The filter bounds the search to the user's tenant and requested equipment
    approved_constraints: Dict[str, Any] = {
        "tenant_id": tenant_id,
    }

    if requested_model:
        approved_constraints["model"] = requested_model

    return approved_constraints


def build_moss_metadata_filter(
    approved_constraints: Dict[str, Any],
    normalized_query: Any,
) -> Dict[str, Any]:
    """
    Constructs a structured metadata filter dict for Moss QueryOptions.

    Moss metadata filter syntax uses field/condition expressions:
      {"field": "model", "condition": {"$eq": "CP-200"}}
    Multiple constraints are joined using "$and":
      {"$and": [{"field": "tenant_id", "condition": {"$eq": "demo"}}, ...]}
    """
    conditions: List[Dict[str, Any]] = []

    tenant_id = approved_constraints.get("tenant_id")
    if tenant_id:
        conditions.append({
            "field": "tenant_id",
            "condition": {"$eq": tenant_id},
        })

    model = approved_constraints.get("model")
    if not model and hasattr(normalized_query, "model") and normalized_query.model:
        model = normalized_query.model

    if model:
        conditions.append({
            "field": "model",
            "condition": {"$eq": model},
        })

    if not conditions:
        return {}
    if len(conditions) == 1:
        return conditions[0]
    return {"$and": conditions}
