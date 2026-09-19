"""
Tests for authentication, JWT issuance, password hashing, and authorization derivation.
Verifies SEC-001: Protected endpoints without valid auth return 401 Unauthorized.
"""
from datetime import timedelta

import pytest
from app.auth import (
    create_access_token,
    verify_token,
    hash_password,
    verify_password,
    derive_authorization_context,
)
from app.models import User, Asset


def test_password_hashing():
    """Password hashing and bcrypt verification."""
    password = "StrongIndustrialPassword123!"
    hashed = hash_password(password)
    assert hashed != password
    assert verify_password(password, hashed) is True
    assert verify_password("WrongPassword!", hashed) is False


def test_jwt_token_lifecycle():
    """JWT creation, expiration, and payload decoding."""
    token = create_access_token(
        data={"sub": "user-uuid-001", "email": "tech@plant.test", "tenant_id": "demo"},
        expires_delta=timedelta(minutes=30),
    )
    assert isinstance(token, str)

    payload = verify_token(token)
    assert payload["sub"] == "user-uuid-001"
    assert payload["email"] == "tech@plant.test"
    assert payload["tenant_id"] == "demo"


@pytest.mark.asyncio
async def test_protected_endpoint_without_token_returns_401(async_client):
    """SEC-001: Attempting to call protected session endpoint without token returns 401."""
    resp = await async_client.post("/api/v1/session/initialize", json={})
    assert resp.status_code == 401
    assert "Not authenticated" in resp.text or "detail" in resp.json()


@pytest.mark.asyncio
async def test_login_and_token_retrieval(async_client, seed_test_user):
    """Technician can authenticate with credentials and obtain Bearer JWT."""
    login_data = {
        "username": "tech@industrial.test",
        "password": "SafePassword123!",
    }
    resp = await async_client.post("/api/v1/auth/token", data=login_data)
    assert resp.status_code == 200
    body = resp.json()
    assert "access_token" in body
    assert body["token_type"] == "bearer"
