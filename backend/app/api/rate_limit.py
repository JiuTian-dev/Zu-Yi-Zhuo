"""Small process-local sliding-window limiter for REST mutation requests."""

from collections import defaultdict, deque
from math import ceil
from threading import RLock
import time


WINDOW_SECONDS = 60.0
DEFAULT_MAX_MUTATIONS_PER_MINUTE = 600


class MutationRateLimiter:
    """Bound mutation bursts without adding a shared infrastructure dependency."""

    def __init__(self, max_requests: int, *, clock=time.monotonic) -> None:
        if max_requests <= 0:
            raise ValueError("max_requests must be a positive integer")
        self.max_requests = max_requests
        self._clock = clock
        self._requests: dict[str, deque[float]] = defaultdict(deque)
        self._lock = RLock()

    def allow(self, client_key: str) -> tuple[bool, int]:
        """Return whether a request is allowed and a useful retry delay."""
        now = self._clock()
        with self._lock:
            requests = self._requests[client_key]
            cutoff = now - WINDOW_SECONDS
            while requests and requests[0] <= cutoff:
                requests.popleft()
            if len(requests) >= self.max_requests:
                retry_after = max(1, ceil(requests[0] + WINDOW_SECONDS - now))
                return False, retry_after
            requests.append(now)
            return True, 0


__all__ = (
    "DEFAULT_MAX_MUTATIONS_PER_MINUTE",
    "MutationRateLimiter",
    "WINDOW_SECONDS",
)
