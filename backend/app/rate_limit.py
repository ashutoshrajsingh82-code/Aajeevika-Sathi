"""Small process-local rate limiter for abuse-sensitive API endpoints.

This is suitable for a single-process demo/development deployment only.
Production deployments should use a shared limiter such as Redis/API-gateway
rate limiting so limits apply consistently across workers and instances.
"""
from collections import defaultdict, deque
from threading import Lock
from time import monotonic

from fastapi import HTTPException, Request


class RateLimiter:
    def __init__(self, limit: int, window_seconds: int = 60):
        if limit < 1 or window_seconds < 1:
            raise ValueError("Rate-limit values must be positive")
        self.limit = int(limit)
        self.window_seconds = int(window_seconds)
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def allow(self, key: str) -> bool:
        now = monotonic()
        cutoff = now - self.window_seconds

        with self._lock:
            events = self._events[key]
            while events and events[0] <= cutoff:
                events.popleft()

            if len(events) >= self.limit:
                return False

            events.append(now)

            if len(self._events) > 10000:
                stale = [
                    item
                    for item, values in self._events.items()
                    if not values or values[-1] <= cutoff
                ]
                for item in stale:
                    self._events.pop(item, None)

            return True


def client_key(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def enforce_rate_limit(
    limiter: RateLimiter,
    request: Request,
    *,
    bucket: str,
) -> None:
    key = f"{bucket}:{client_key(request)}"
    if not limiter.allow(key):
        raise HTTPException(
            status_code=429,
            detail="Too many requests. Please try again later.",
            headers={"Retry-After": str(limiter.window_seconds)},
        )
