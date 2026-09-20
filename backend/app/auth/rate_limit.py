from collections import defaultdict
from collections.abc import Callable
import time

from fastapi import HTTPException


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
