"""
Sliding-window in-memory rate limiter for agent sessions.

For multi-process deployments replace with a Redis-backed implementation.
"""

import asyncio
import logging
import time
from collections import defaultdict, deque

logger = logging.getLogger(__name__)

# Max sessions a single user may start within the window.
MAX_SESSIONS_PER_USER = 5
SESSION_WINDOW_SECS = 3600  # 1 hour

_lock = asyncio.Lock()
_session_timestamps: dict[str, deque[float]] = defaultdict(deque)


async def check_session_rate(user_id: str) -> bool:
    """
    Return True if the user is within the session rate limit and record
    the attempt. Return False if the limit is exceeded (nothing is recorded).

    Call this in entrypoint before starting the AgentSession.
    """
    now = time.monotonic()
    async with _lock:
        dq = _session_timestamps[user_id]
        cutoff = now - SESSION_WINDOW_SECS
        while dq and dq[0] < cutoff:
            dq.popleft()

        if len(dq) >= MAX_SESSIONS_PER_USER:
            logger.warning(
                "Session rate limit exceeded — user=%s sessions=%d window=%ds",
                user_id,
                len(dq),
                SESSION_WINDOW_SECS,
            )
            return False

        dq.append(now)
        return True
