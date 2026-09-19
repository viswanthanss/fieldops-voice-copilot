"""
Async database engine and session factory for FieldOps Voice Copilot.
"""
from __future__ import annotations

import logging
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.models import Base

logger = logging.getLogger(__name__)

# ── Engine ────────────────────────────────────────────────────────────────────
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=(settings.ENVIRONMENT == "development"),
    future=True,
    # SQLite-specific: allow concurrent access from multiple coroutines
    connect_args={"check_same_thread": False} if "sqlite" in settings.DATABASE_URL else {},
)

# ── Session factory ───────────────────────────────────────────────────────────
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)


async def create_tables() -> None:
    """
    Create all database tables defined in the ORM models.

    This is used in development/testing. In production use Alembic migrations.
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables created/verified.")


async def seed_dev_data() -> None:
    """Seed initial development technician and assets if not present."""
    from sqlalchemy import select
    from app.models import User, Asset
    from app.auth import hash_password

    async with AsyncSessionLocal() as session:
        res = await session.execute(select(User).where(User.email == "tech@industrial.test"))
        if not res.scalar_one_or_none():
            user = User(
                email="tech@industrial.test",
                hashed_password=hash_password("SafePassword123!"),
                tenant_id="demo",
                site_ids=["SITE-A"],
                roles=["technician"],
                is_active=True,
            )
            session.add(user)

        res = await session.execute(select(Asset).where(Asset.asset_id == "CP-204"))
        if not res.scalar_one_or_none():
            session.add(
                Asset(
                    asset_id="CP-204",
                    tenant_id="demo",
                    site_id="SITE-A",
                    equipment_type="compressor",
                    model="CP-200",
                    status="operational",
                    authorized_roles=["technician"],
                )
            )

        res = await session.execute(select(Asset).where(Asset.asset_id == "CP-301"))
        if not res.scalar_one_or_none():
            session.add(
                Asset(
                    asset_id="CP-301",
                    tenant_id="demo",
                    site_id="SITE-A",
                    equipment_type="compressor",
                    model="CP-300",
                    status="operational",
                    authorized_roles=["technician"],
                )
            )

        await session.commit()
    logger.info("Development demo user and assets seeded.")


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency that provides an async database session.

    Yields:
        AsyncSession: SQLAlchemy async session, automatically closed on exit.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
