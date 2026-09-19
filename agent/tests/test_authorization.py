"""
Unit tests for Pre-Retrieval Authorization Scope Verification.
Verifies FR-003: Unauthorized asset retrieval requests are blocked before retrieval.
"""
import pytest
from agent.src.authorization import (
    verify_retrieval_scope,
    build_moss_metadata_filter,
    AuthorizationDeniedError,
)
from agent.src.normalizer import normalize_query


def test_authorized_asset_access(sample_auth_context):
    """Technician querying their assigned asset CP-204 should pass."""
    constraints = verify_retrieval_scope(
        auth_context=sample_auth_context,
        requested_asset_id="CP-204",
        requested_model="CP-200",
    )
    assert constraints["tenant_id"] == "demo"
    assert constraints["model"] == "CP-200"


def test_unauthorized_asset_blocked(sample_auth_context):
    """Technician attempting to query an unassigned asset (CP-991) must be rejected."""
    with pytest.raises(AuthorizationDeniedError) as exc_info:
        verify_retrieval_scope(
            auth_context=sample_auth_context,
            requested_asset_id="CP-991",
        )
    assert "CP-991" in str(exc_info.value)
    assert "not in your assigned maintenance scope" in str(exc_info.value)


def test_user_speech_cannot_expand_authorization(sample_auth_context):
    """A user attempting to elevate by asking for another site is blocked."""
    with pytest.raises(AuthorizationDeniedError) as exc_info:
        verify_retrieval_scope(
            auth_context=sample_auth_context,
            requested_site_id="SITE-FORBIDDEN",
        )
    assert "SITE-FORBIDDEN" in str(exc_info.value)


def test_moss_metadata_filter_generation(sample_auth_context):
    """Metadata filter is correctly built with tenant and model constraints in official Moss syntax."""
    q = normalize_query("CP-200 E17")
    constraints = verify_retrieval_scope(
        auth_context=sample_auth_context,
        requested_model=q.model,
    )
    moss_filter = build_moss_metadata_filter(constraints, q)

    assert "$and" in moss_filter
    conds = moss_filter["$and"]
    assert {"field": "tenant_id", "condition": {"$eq": "demo"}} in conds
    assert {"field": "model", "condition": {"$eq": "CP-200"}} in conds
