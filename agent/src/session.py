"""
Session State Abstraction for FieldOps Voice Copilot.

Provides a unified interface for active voice session state:
- InMemorySessionStore: Zero-dependency in-process storage for local development and tests.
- RedisSessionStore: Externalized short-lived session storage for horizontal multi-worker scaling.

Only short-lived metadata (auth context, current equipment, last N turn summaries) is stored.
Raw audio is NEVER persisted.
"""
from __future__ import annotations

import json
import time
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
import structlog

logger = structlog.get_logger(__name__)


class SessionStore(ABC):
    """Abstract interface for active voice session persistence."""

    @abstractmethod
    async def get(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve session data by session ID."""
        pass

    @abstractmethod
    async def set(self, session_id: str, data: Dict[str, Any], ttl_seconds: int = 3600) -> None:
        """Store session data with a time-to-live expiration."""
        pass

    @abstractmethod
    async def update(self, session_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Atomically update specific keys within an existing session."""
        pass

    @abstractmethod
    async def delete(self, session_id: str) -> bool:
        """Invalidate and remove a session."""
        pass


class InMemorySessionStore(SessionStore):
    """
    In-memory dictionary store for single-process development and testing.
    Automatically purges expired records on access.
    """

    def __init__(self) -> None:
        self._store: Dict[str, Dict[str, Any]] = {}
        self._expires: Dict[str, float] = {}

    async def get(self, session_id: str) -> Optional[Dict[str, Any]]:
        now = time.time()
        if session_id in self._expires and now > self._expires[session_id]:
            self._store.pop(session_id, None)
            self._expires.pop(session_id, None)
            return None
        return self._store.get(session_id)

    async def set(self, session_id: str, data: Dict[str, Any], ttl_seconds: int = 3600) -> None:
        self._store[session_id] = dict(data)
        self._expires[session_id] = time.time() + ttl_seconds

    async def update(self, session_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        current = await self.get(session_id)
        if current is None:
            return None
        current.update(updates)
        self._store[session_id] = current
        return current

    async def delete(self, session_id: str) -> bool:
        self._expires.pop(session_id, None)
        return self._store.pop(session_id, None) is not None


class RedisSessionStore(SessionStore):
    """
    Production-grade Redis session store for horizontal worker scaling.
    Enables workers to be completely stateless between utterances.
    """

    def __init__(self, redis_url: str) -> None:
        self._redis_url = redis_url
        self._client = None

    async def _get_client(self):
        if self._client is None:
            import redis.asyncio as aioredis  # type: ignore
            self._client = aioredis.from_url(
                self._redis_url,
                encoding="utf-8",
                decode_responses=True,
            )
        return self._client

    async def get(self, session_id: str) -> Optional[Dict[str, Any]]:
        try:
            client = await self._get_client()
            key = f"fieldops:session:{session_id}"
            raw = await client.get(key)
            if not raw:
                return None
            return json.loads(raw)
        except Exception as exc:
            logger.error("redis_session_get_failed", session_id=session_id, error=str(exc))
            return None

    async def set(self, session_id: str, data: Dict[str, Any], ttl_seconds: int = 3600) -> None:
        try:
            client = await self._get_client()
            key = f"fieldops:session:{session_id}"
            serialized = json.dumps(data)
            await client.setex(key, ttl_seconds, serialized)
        except Exception as exc:
            logger.error("redis_session_set_failed", session_id=session_id, error=str(exc))
            raise

    async def update(self, session_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        current = await self.get(session_id)
        if current is None:
            return None
        current.update(updates)
        await self.set(session_id, current)
        return current

    async def delete(self, session_id: str) -> bool:
        try:
            client = await self._get_client()
            key = f"fieldops:session:{session_id}"
            result = await client.delete(key)
            return result > 0
        except Exception as exc:
            logger.error("redis_session_delete_failed", session_id=session_id, error=str(exc))
            return False


def create_session_store(redis_url: str = "") -> SessionStore:
    """
    Factory function returning RedisSessionStore if REDIS_URL is configured,
    otherwise falling back to InMemorySessionStore for development.
    """
    if redis_url and redis_url.strip():
        logger.info("using_redis_session_store", redis_url=redis_url.split("@")[-1])
        return RedisSessionStore(redis_url.strip())
    
    logger.info("using_in_memory_session_store", mode="development")
    return InMemorySessionStore()
