from collections import defaultdict
from collections.abc import Callable
import logging
import time

from fastapi import HTTPException


logger = logging.getLogger("obsygpt.auth.rate_limit")

MAX_TRACKED_KEYS = 10_000


class AuthRateLimiter:
    def __init__(self, max_attempts: int = 10, window_seconds: int = 300, now: Callable[[], float] | None = None):
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self.now = now or time.time
        self.attempts: dict[str, list[float]] = defaultdict(list)

    def check(self, key: str) -> None:
        current_time = self.now()
        window_start = current_time - self.window_seconds
        recent_attempts = [attempt_time for attempt_time in self.attempts[key] if attempt_time > window_start]
        if len(recent_attempts) >= self.max_attempts:
            self.attempts[key] = recent_attempts
            raise HTTPException(status_code=429, detail="Too many authentication attempts. Please try again later.")
        recent_attempts.append(current_time)
        self.attempts[key] = recent_attempts
        self._cleanup(current_time)

    def _cleanup(self, current_time: float) -> None:
        """Drops expired keys so the tracker cannot grow without bound.

        Runs probabilistically (1/50 checks) to keep the hot path cheap; exact
        timing is irrelevant for garbage collection.
        """
        if len(self.attempts) < MAX_TRACKED_KEYS and (hash(current_time) & 63) != 0:
            return
        window_start = current_time - self.window_seconds
        expired = [key for key, times in self.attempts.items() if not any(t > window_start for t in times)]
        for key in expired:
            del self.attempts[key]
        if expired:
            logger.debug("Rate limiter cleanup removed %d expired keys", len(expired))
