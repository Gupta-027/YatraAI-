"""In-process sliding-window rate limiter.

Deliberately dependency-free: the demo runs as a single API process, so a Redis
hop would add operational cost without benefit. ``RateLimiter`` is swappable -
``check()`` is the only method the API layer uses.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

from yatraai.core.errors import RateLimitedError


class SlidingWindowRateLimiter:
    def __init__(self, window_seconds: float = 60.0) -> None:
        self.window = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str, limit: int) -> tuple[int, float]:
        """Record a hit. Returns ``(remaining, reset_in_seconds)``.

        Raises :class:`RateLimitedError` when ``limit`` is exceeded.
        """
        if limit <= 0:
            return 0, self.window
        now = time.monotonic()
        cutoff = now - self.window
        with self._lock:
            bucket = self._hits[key]
            while bucket and bucket[0] < cutoff:
                bucket.popleft()
            if len(bucket) >= limit:
                reset_in = max(0.0, bucket[0] + self.window - now)
                raise RateLimitedError(
                    "Too many requests. Please slow down.",
                    detail={"retry_after_seconds": round(reset_in, 1), "limit": limit},
                )
            bucket.append(now)
            return limit - len(bucket), self.window

    def reset(self, key: str | None = None) -> None:
        with self._lock:
            if key is None:
                self._hits.clear()
            else:
                self._hits.pop(key, None)


limiter = SlidingWindowRateLimiter()
