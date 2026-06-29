"""
PHANTOM Result Store
Redis-backed cache for task results with TTL and in-memory fallback.
Gracefully degrades to in-memory when Redis is unavailable.
"""

from __future__ import annotations

import json
import time
from typing import Any, Dict, Optional, Tuple

from loguru import logger

from phantom.config import settings


class _InMemoryStore:
    """Thread-safe in-memory fallback cache with TTL support."""

    def __init__(self) -> None:
        self._store: Dict[str, Tuple[Any, float]] = {}  # key -> (value, expiry_time)

    def set(self, key: str, value: Any, ttl: int = 3600) -> None:
        expiry = time.time() + ttl
        self._store[key] = (value, expiry)

    def get(self, key: str) -> Optional[Any]:
        entry = self._store.get(key)
        if entry is None:
            return None
        value, expiry = entry
        if time.time() > expiry:
            del self._store[key]
            return None
        return value

    def delete(self, key: str) -> bool:
        if key in self._store:
            del self._store[key]
            return True
        return False

    def exists(self, key: str) -> bool:
        return self.get(key) is not None

    def clear_expired(self) -> int:
        now = time.time()
        expired = [k for k, (_, exp) in self._store.items() if now > exp]
        for k in expired:
            del self._store[k]
        return len(expired)

    @property
    def size(self) -> int:
        return len(self._store)


class ResultStore:
    """
    Cache layer for PHANTOM task results.

    Tries Redis first; automatically falls back to in-memory store
    if Redis is unavailable. All values are JSON-serialized.
    """

    def __init__(self) -> None:
        self._redis: Optional[Any] = None
        self._memory: _InMemoryStore = _InMemoryStore()
        self._connected = False
        self._default_ttl = settings.cache_ttl_seconds

    async def connect(self) -> bool:
        """
        Attempt to connect to Redis. Returns True if successful.
        Falls back silently to in-memory if Redis is not available.
        """
        try:
            import redis.asyncio as aioredis  # type: ignore

            self._redis = aioredis.from_url(
                settings.redis_url,
                encoding="utf-8",
                decode_responses=True,
                socket_connect_timeout=2,
                socket_timeout=2,
            )
            await self._redis.ping()
            self._connected = True
            logger.info("ResultStore connected to Redis: {}", settings.redis_url)
            return True
        except Exception as exc:
            logger.warning(
                "Redis unavailable ({}), using in-memory cache: {}",
                settings.redis_url,
                exc,
            )
            self._redis = None
            self._connected = False
            return False

    async def disconnect(self) -> None:
        """Close Redis connection."""
        if self._redis:
            try:
                await self._redis.aclose()
            except Exception:
                pass
        self._redis = None
        self._connected = False

    async def set(
        self,
        key: str,
        value: Any,
        ttl: Optional[int] = None,
    ) -> None:
        """
        Store a value under a key.

        Args:
            key: Cache key
            value: JSON-serializable value
            ttl: Time-to-live in seconds (default: settings.cache_ttl_seconds)
        """
        effective_ttl = ttl or self._default_ttl
        try:
            serialized = json.dumps(value, default=str)
            if self._redis and self._connected:
                await self._redis.setex(key, effective_ttl, serialized)
            else:
                self._memory.set(key, serialized, effective_ttl)
        except Exception as exc:
            logger.warning("Cache set failed for key '{}': {}", key, exc)
            self._memory.set(key, json.dumps(value, default=str), effective_ttl)

    async def get(self, key: str) -> Optional[Any]:
        """
        Retrieve a cached value.

        Returns:
            Deserialized value, or None if not found / expired.
        """
        try:
            if self._redis and self._connected:
                raw = await self._redis.get(key)
            else:
                raw = self._memory.get(key)

            if raw is None:
                return None

            return json.loads(raw)
        except Exception as exc:
            logger.debug("Cache get failed for key '{}': {}", key, exc)
            return None

    async def delete(self, key: str) -> bool:
        """Remove a key from the cache."""
        try:
            if self._redis and self._connected:
                deleted = await self._redis.delete(key)
                return bool(deleted)
            else:
                return self._memory.delete(key)
        except Exception:
            return False

    async def exists(self, key: str) -> bool:
        """Check whether a key exists in the cache."""
        try:
            if self._redis and self._connected:
                return bool(await self._redis.exists(key))
            else:
                return self._memory.exists(key)
        except Exception:
            return False

    async def set_task_result(self, task_id: str, result: Any) -> None:
        """Store a task result with the standard task key prefix."""
        await self.set(f"task:{task_id}", result)

    async def get_task_result(self, task_id: str) -> Optional[Any]:
        """Retrieve a task result by task ID."""
        return await self.get(f"task:{task_id}")

    async def set_page_cache(self, url: str, content: Any, ttl: int = 300) -> None:
        """Cache a page result by URL with a shorter TTL."""
        import hashlib
        url_hash = hashlib.md5(url.encode()).hexdigest()
        await self.set(f"page:{url_hash}", content, ttl=ttl)

    async def get_page_cache(self, url: str) -> Optional[Any]:
        """Retrieve a cached page result by URL."""
        import hashlib
        url_hash = hashlib.md5(url.encode()).hexdigest()
        return await self.get(f"page:{url_hash}")

    @property
    def is_connected(self) -> bool:
        """Whether Redis is currently connected."""
        return self._connected

    @property
    def backend(self) -> str:
        """Returns 'redis' or 'memory' based on current backend."""
        return "redis" if self._connected else "memory"

    async def health(self) -> Dict[str, Any]:
        """Return cache health status."""
        redis_ok = False
        if self._redis and self._connected:
            try:
                await self._redis.ping()
                redis_ok = True
            except Exception:
                redis_ok = False

        return {
            "backend": self.backend,
            "redis_connected": redis_ok,
            "memory_entries": self._memory.size,
        }
