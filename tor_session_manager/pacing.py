"""
Adaptive per-host rate limiting.

Hammering a host is both rude and a fast way to get blocked. ``RateLimiter``
paces requests per host: it enforces a minimum interval between requests to the
same host, and adapts — widening the interval when the host answers 429/503
(rate limited) and letting it decay back toward the minimum on healthy
responses.
"""

import logging
import time
from typing import Dict

logger = logging.getLogger(__name__)

# Statuses that signal we are going too fast.
_SLOW_DOWN_STATUS = {429, 503}


class RateLimiter:
    """Per-host adaptive pacing."""

    def __init__(
        self,
        min_interval: float = 1.0,
        backoff_factor: float = 2.0,
        max_interval: float = 60.0,
        decay: float = 0.5,
    ):
        """
        Args:
            min_interval: Baseline minimum seconds between requests to a host.
            backoff_factor: Multiplier applied to the interval on 429/503.
            max_interval: Upper bound for the per-host interval.
            decay: Multiplier applied on healthy responses (toward min).
        """
        self.min_interval = min_interval
        self.backoff_factor = backoff_factor
        self.max_interval = max_interval
        self.decay = decay
        self._interval: Dict[str, float] = {}
        self._last: Dict[str, float] = {}

    def interval_for(self, host: str) -> float:
        """Current interval for ``host`` (the baseline if unseen)."""
        return self._interval.get(host, self.min_interval)

    def acquire(self, host: str) -> None:
        """Block until enough time has passed since the last request to ``host``."""
        interval = self.interval_for(host)
        last = self._last.get(host)
        if last is not None:
            wait = interval - (time.monotonic() - last)
            if wait > 0:
                logger.debug("Pacing %s: sleeping %.2fs", host, wait)
                time.sleep(wait)
        self._last[host] = time.monotonic()

    def record(self, host: str, status: int) -> None:
        """Adapt the host's interval based on the response status."""
        current = self.interval_for(host)
        if status in _SLOW_DOWN_STATUS:
            self._interval[host] = min(current * self.backoff_factor, self.max_interval)
            logger.debug(
                "Host %s rate-limited (%d); interval -> %.2fs",
                host,
                status,
                self._interval[host],
            )
        else:
            self._interval[host] = max(self.min_interval, current * self.decay)
