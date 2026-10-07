import hmac
import logging
import re
import time
import threading
from typing import Optional

from fastapi import Header, HTTPException, Request, status

from app.config import settings

_USER_ID_RE = re.compile(r"^[a-zA-Z0-9._@-]{1,64}$")
_log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Rate limiter — Redis for production, in-memory for local dev
# ---------------------------------------------------------------------------

class _InMemoryRateLimiter:
    """Thread-safe sliding-window rate limiter (single process only)."""

    def __init__(self, max_requests: int, window_seconds: int):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._hits: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        now = time.time()
        with self._lock:
            recent = [t for t in self._hits.get(key, []) if now - t < self.window_seconds]
            if len(recent) >= self.max_requests:
                self._hits[key] = recent
                return False
            recent.append(now)
            self._hits[key] = recent
            return True


class _RedisRateLimiter:
    """Sliding-window rate limiter backed by Redis sorted sets.

    Works across multiple Cloud Run instances because all share
    the same Redis key space.
    """

    def __init__(self, max_requests: int, window_seconds: int, redis_url: str):
        import redis as _redis

        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._redis = _redis.from_url(redis_url, decode_responses=True)
        _log.info("Rate limiter using Redis backend")

    def allow(self, key: str) -> bool:
        rkey = f"ratelimit:{key}"
        now = time.time()
        pipe = self._redis.pipeline(transaction=True)
        cutoff = now - self.window_seconds
        pipe.zremrangebyscore(rkey, "-inf", cutoff)
        pipe.zcard(rkey)
        pipe.zadd(rkey, {str(now): now})
        pipe.expire(rkey, self.window_seconds + 1)
        try:
            results = pipe.execute()
        except Exception as exc:
            _log.warning("Redis rate limiter unavailable (%s); allowing request for this check", exc)
            return True
        count = results[1]  # zcard result (before the zadd)
        return count < self.max_requests


def _build_rate_limiter():
    """Pick the right backend based on available configuration."""
    max_req = settings.RATE_LIMIT_REQUESTS
    window = settings.RATE_LIMIT_WINDOW_SECONDS

    # Local development should remain usable even when a production Redis URL
    # is present in .env. Cloud Run production uses Redis for shared limits.
    if settings.is_production and settings.REDIS_URL:
        try:
            return _RedisRateLimiter(max_req, window, settings.REDIS_URL)
        except Exception as exc:
            _log.warning("Redis rate limiter init failed (%s), falling back to in-memory", exc)

    if settings.is_production:
        _log.warning(
            "Using in-memory rate limiter in production — "
            "limits will NOT be shared across instances. Set REDIS_URL to fix."
        )
    return _InMemoryRateLimiter(max_req, window)


rate_limiter = _build_rate_limiter()


def _extract_api_key(
    x_api_key: Optional[str],
    authorization: Optional[str],
) -> str:
    if x_api_key:
        return x_api_key.strip()
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return ""


def authenticate(
    request: Request,
    x_api_key: Optional[str] = Header(default=None, alias="X-API-Key"),
    authorization: Optional[str] = Header(default=None),
    x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
    x_debug_key: Optional[str] = Header(default=None, alias="X-Debug-Key"),
) -> dict:
    expected = settings.API_KEY
    if expected:
        presented = _extract_api_key(x_api_key, authorization)
        if not hmac.compare_digest(presented, expected):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or missing API key.",
            )
    elif settings.is_production:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API authentication is not configured.",
        )

    user_id = (x_user_id or "").strip()
    if user_id:
        if not _USER_ID_RE.match(user_id):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="X-User-Id must be 1-64 characters: letters, numbers, . _ @ -",
            )
    elif settings.is_production:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="X-User-Id is required.",
        )
    else:
        user_id = "dev-local"

    client_ip = request.client.host if request.client else "unknown"
    bucket = f"{user_id}:{client_ip}"
    if not rate_limiter.allow(bucket):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded. Please wait and try again.",
        )

    debug_ok = (
        bool(settings.DEBUG_KEY)
        and isinstance(x_debug_key, str)
        and hmac.compare_digest(x_debug_key, settings.DEBUG_KEY)
    )
    if settings.is_production:
        include_internal = debug_ok
    else:
        include_internal = debug_ok or not settings.DEBUG_KEY or settings.SHOW_INTERNAL_DETAILS
    return {
        "user_id": user_id,
        "thread_id": f"user:{user_id}",
        "include_internal": include_internal,
    }
