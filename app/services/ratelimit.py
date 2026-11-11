"""Request rate limiting with a pluggable backend.

* MemoryBackend  - per-process sliding window. Fine for development and a single instance.
* RedisBackend   - fixed window shared by all instances (needs REDIS_URL; untested here).
Per-account lockout (failed logins) is handled separately in the auth router.
"""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from typing import Callable, Protocol

from fastapi import HTTPException, Request

from ..config import settings
from ..utils import client_ip


class RateLimitBackend(Protocol):
    def hit(self, key: str, limit: int, window_seconds: int) -> tuple[bool, int]:
        """Record a hit. Returns (allowed, retry_after_seconds)."""


class MemoryBackend:
    def __init__(self) -> None:
        self._hits: dict[str, deque] = defaultdict(deque)
        self._lock = threading.Lock()

    def hit(self, key: str, limit: int, window_seconds: int) -> tuple[bool, int]:
        now = time.monotonic()
        with self._lock:
            q = self._hits[key]
            while q and now - q[0] >= window_seconds:
                q.popleft()
            if len(q) >= limit:
                return False, max(1, int(window_seconds - (now - q[0])))
            q.append(now)
            return True, 0

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


class RedisBackend:
    def __init__(self, url: str) -> None:
        import redis  # imported lazily so the dependency is only needed when selected

        self._r = redis.Redis.from_url(url, socket_timeout=2)

    def hit(self, key: str, limit: int, window_seconds: int) -> tuple[bool, int]:
        k = f"pepai:rl:{key}"
        count = self._r.incr(k)
        if count == 1:
            self._r.expire(k, window_seconds)
        if count > limit:
            ttl = self._r.ttl(k)
            return False, max(1, int(ttl if ttl and ttl > 0 else window_seconds))
        return True, 0


_backend: RateLimitBackend | None = None


def get_backend() -> RateLimitBackend:
    global _backend
    if _backend is None:
        _backend = RedisBackend(settings.redis_url) if settings.rate_limit_backend == "redis" else MemoryBackend()
    return _backend


def reset_backend() -> None:
    """Test helper."""
    global _backend
    _backend = None


def rate_limit(name: str, limit: Callable[[], int], window_seconds: int):
    """FastAPI dependency factory. `limit` is a callable so settings are read at request time."""

    def dependency(request: Request) -> None:
        if not settings.rate_limit_enabled:
            return
        allowed, retry = get_backend().hit(f"{name}:{client_ip(request)}", limit(), window_seconds)
        if not allowed:
            raise HTTPException(status_code=429, detail="Too many requests. Please wait and try again.",
                                headers={"Retry-After": str(retry)})

    return dependency


login_limit = rate_limit("login", lambda: settings.login_rate_limit_per_minute, 60)
register_limit = rate_limit("register", lambda: settings.register_rate_limit_per_hour, 3600)
sensitive_limit = rate_limit("sensitive", lambda: settings.sensitive_rate_limit_per_hour, 3600)
