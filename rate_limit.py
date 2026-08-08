import time
from collections import defaultdict

from fastapi import HTTPException, Request, status

_WINDOW_SECONDS = 300  # 5 minutes
_MAX_REQUESTS = 10

_requests: dict[str, list[float]] = defaultdict(list)


def check_rate_limit(request: Request) -> None:
    """Simple in-memory sliding-window limiter, keyed by client IP.

    Fine for a single-instance deployment. If you scale to multiple
    instances, this needs to move to Redis (INCR + EXPIRE per key) —
    each instance would otherwise track its own counts independently
    and the effective limit becomes N x _MAX_REQUESTS.
    """
    ip = request.client.host if request.client else "unknown"
    now = time.time()
    window_start = now - _WINDOW_SECONDS

    recent = [t for t in _requests[ip] if t > window_start]
    if len(recent) >= _MAX_REQUESTS:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many questions — please wait a few minutes and try again.",
        )

    recent.append(now)
    _requests[ip] = recent