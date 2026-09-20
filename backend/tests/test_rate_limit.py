import pytest
from fastapi import HTTPException

from app.auth.rate_limit import AuthRateLimiter


def test_rate_limiter_allows_attempts_under_limit():
    limiter = AuthRateLimiter(max_attempts=3, window_seconds=60, now=lambda: 1000.0)

    limiter.check("login:127.0.0.1")
    limiter.check("login:127.0.0.1")
    limiter.check("login:127.0.0.1")


def test_rate_limiter_blocks_attempt_over_limit():
    limiter = AuthRateLimiter(max_attempts=2, window_seconds=60, now=lambda: 1000.0)

    limiter.check("login:127.0.0.1")
    limiter.check("login:127.0.0.1")

    with pytest.raises(HTTPException) as error:
        limiter.check("login:127.0.0.1")

    assert error.value.status_code == 429
    assert error.value.detail == "Too many authentication attempts. Please try again later."


def test_rate_limiter_expires_old_attempts():
    current_time = 1000.0
    limiter = AuthRateLimiter(max_attempts=1, window_seconds=60, now=lambda: current_time)

    limiter.check("register:127.0.0.1")
    current_time = 1061.0

    limiter.check("register:127.0.0.1")
