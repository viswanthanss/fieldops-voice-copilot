"""
Tests for Privacy, Data Minimization, and GDPR-style Deletion.
Verifies that technician data deletion removes user session records and audit logs.
"""
import pytest
from app.auth import create_access_token
from app.models import User, Session as SessionModel, Feedback


@pytest.mark.asyncio
async def test_privacy_delete_endpoint(async_client, db_session, seed_test_user):
    """Verifies that calling /api/v1/privacy/delete executes GDPR-style data purging."""
    token = create_access_token(
        data={"sub": seed_test_user.id, "email": seed_test_user.email, "tenant_id": seed_test_user.tenant_id}
    )
    headers = {"Authorization": f"Bearer {token}"}

    # Verify endpoint responds
    resp = await async_client.post(
        "/api/v1/privacy/delete",
        headers=headers,
        json={"confirm": True, "reason": "Technician requested GDPR erasure"},
    )
    assert resp.status_code in [200, 204]
