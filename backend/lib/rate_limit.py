"""In-memory per-IP token bucket rate limiter (stdlib only)."""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request, status


class RateLimiter:
    def __init__(self, rate: int, window_seconds: int) -> None:
        self.rate = rate
        self.window = float(window_seconds)
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, ip: str) -> bool:
        now = time.monotonic()
        cutoff = now - self.window
        with self._lock:
            hits = self._hits[ip]
            while hits and hits[0] < cutoff:
                hits.popleft()
            if len(hits) >= self.rate:
                return False
            hits.append(now)
            return True

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


def client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def rate_limit_dependency(limiter: RateLimiter):
    def _dep(request: Request) -> None:
        if not limiter.check(client_ip(request)):
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many requests",
                headers={"Retry-After": str(int(limiter.window))},
            )

    return _dep


AUTH_LIMITER = RateLimiter(rate=5, window_seconds=60)
