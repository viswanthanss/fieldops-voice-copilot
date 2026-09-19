"""
Pytest configuration for backend unit and integration tests.
Sets up an in-memory SQLite async database engine and FastAPI TestClient / AsyncClient.
"""
import sys
import pathlib
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

BACKEND_DIR = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import select
from app.config import settings
from app.db import create_tables, engine, AsyncSessionLocal
from app.main import app
from app.models import Base, User, Asset
from app.auth import hash_password


@pytest_asyncio.fixture(scope="session", autouse=True)
async def setup_test_db():
    """Initializes schema before running tests and tears down after."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def async_client():
    """Provides an async HTTP client connected to the FastAPI application."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


@pytest_asyncio.fixture
async def db_session():
    """Provides an isolated database session."""
    async with AsyncSessionLocal() as session:
        yield session


@pytest_asyncio.fixture
async def seed_test_user(db_session):
    """Seeds a standard test technician user or returns existing."""
    res = await db_session.execute(select(User).where(User.email == "tech@industrial.test"))
    existing = res.scalar_one_or_none()
    if existing is not None:
        return existing
    user = User(
        email="tech@industrial.test",
        hashed_password=hash_password("SafePassword123!"),
        tenant_id="demo",
        site_ids=["SITE-A"],
        roles=["technician"],
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()
    await db_session.commit()
    return user
