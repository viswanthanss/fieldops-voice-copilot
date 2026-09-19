"""
Tests for Session Initialization and LiveKit Token Generation.
Verifies FR-001 and strict configuration requirement (no placeholder tokens).
"""
import pytest
from app.auth import create_access_token
from app.config import settings


@pytest.mark.asyncio
async def test_session_initialize_requires_livekit_credentials(async_client, seed_test_user, monkeypatch):
    """
    Verifies that session initialization requires valid LIVEKIT_API_KEY and LIVEKIT_API_SECRET
    and does NOT silently return a fake placeholder token.
    """
    token = create_access_token(
        data={"sub": seed_test_user.id, "email": seed_test_user.email, "tenant_id": seed_test_user.tenant_id}
    )
    headers = {"Authorization": f"Bearer {token}"}

    # Case 1: Keys missing -> raises 503 error with clear instructions
    monkeypatch.setattr(settings, "LIVEKIT_API_KEY", "")
    monkeypatch.setattr(settings, "LIVEKIT_API_SECRET", "")

    resp = await async_client.post(
        "/api/v1/session/initialize",
        headers=headers,
        json={"asset_id": "CP-204"},
    )
    assert resp.status_code == 503
    assert "LiveKit credentials are not configured" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_session_initialize_with_credentials(async_client, seed_test_user, monkeypatch):
    """
    When credentials are provided, a real signed JWT is generated.
    """
    token = create_access_token(
        data={"sub": seed_test_user.id, "email": seed_test_user.email, "tenant_id": seed_test_user.tenant_id}
    )
    headers = {"Authorization": f"Bearer {token}"}

    monkeypatch.setattr(settings, "LIVEKIT_API_KEY", "devkey-test")
    monkeypatch.setattr(settings, "LIVEKIT_API_SECRET", "secret-must-be-long-enough-for-jwt-signing-test-1234567890")

    resp = await async_client.post(
        "/api/v1/session/initialize",
        headers=headers,
        json={"asset_id": "CP-204"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "session_id" in data
    assert "livekit_token" in data
    # Token must be a real JWT string, NOT a placeholder
    assert not data["livekit_token"].startswith("livekit-placeholder-")
    assert "auth_context" in data
    assert data["auth_context"]["tenant_id"] == "demo"
