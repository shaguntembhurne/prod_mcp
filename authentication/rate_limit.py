"""
In-memory rate limiter for OTP endpoints.

This module provides simple per-IP rate limiting backed by an in-memory
dictionary.  It is intentionally minimal.

LIMITATION: This only works correctly in a single-process deployment.
In production with multiple workers (gunicorn, uvicorn, etc.) each process
has its own counter so the effective limit is multiplied by the number of
workers.  Replace with a Redis-backed solution (e.g. django-ratelimit with
a cache backend) if you need accurate limiting across processes.
"""

import threading
import time
from collections import defaultdict, deque

_lock = threading.Lock()

# ip -> deque of timestamps (float, unix epoch)
_ip_requests: dict[str, deque] = defaultdict(deque)


def is_rate_limited(ip: str, max_requests: int, window_seconds: int) -> bool:
    """
    Return True if `ip` has exceeded `max_requests` in the last `window_seconds`.

    Thread-safe for a single process.
    """
    now = time.time()
    cutoff = now - window_seconds

    with _lock:
        q = _ip_requests[ip]
        # Drop timestamps outside the window.
        while q and q[0] < cutoff:
            q.popleft()

        if len(q) >= max_requests:
            return True

        q.append(now)
        return False
