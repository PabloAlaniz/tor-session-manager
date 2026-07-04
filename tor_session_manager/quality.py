"""
Circuit quality measurement.

Measures how good the *current* circuit is at the application level (through
the Tor SOCKS proxy): request latency and download throughput. This is the
input that circuit selection (Sprint 4) and best-circuit pooling (Sprint 5)
use to prefer fast circuits and drop slow ones.

The functions here are pure: they take a ``requests.Session`` (typically the
Tor-proxied one) so they can be unit-tested without a running Tor daemon.
"""

import logging
import statistics
import time
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class CircuitHealth:
    """A snapshot of measured circuit quality."""

    latency_ms: Optional[float] = None
    throughput_kbps: Optional[float] = None
    samples: int = 0
    measured_at: Optional[float] = None

    @property
    def ok(self) -> bool:
        """True if at least one metric was resolved."""
        return self.latency_ms is not None or self.throughput_kbps is not None


def measure_latency(session, url: str, timeout: float, samples: int = 3) -> float:
    """
    Measure request latency through ``session`` as the median of N samples.

    Args:
        session: A ``requests.Session`` (typically Tor-proxied).
        url: A lightweight endpoint to time.
        timeout: Per-request timeout in seconds.
        samples: Number of timed requests to take (default: 3). The median is
            returned so a single slow/fast outlier does not dominate.

    Returns:
        The median round-trip latency in milliseconds.
    """
    if samples < 1:
        raise ValueError("samples must be >= 1")

    timings = []
    for _ in range(samples):
        start = time.perf_counter()
        response = session.get(url, timeout=timeout)
        response.raise_for_status()
        elapsed_ms = (time.perf_counter() - start) * 1000
        timings.append(elapsed_ms)

    latency = statistics.median(timings)
    logger.debug("Measured latency: %.1f ms (%d samples)", latency, samples)
    return latency


def measure_throughput(session, url: str, timeout: float) -> float:
    """
    Measure download throughput through ``session`` in KB/s.

    Downloads the body at ``url`` (expected to be a known, fixed size) and
    divides the number of bytes received by the elapsed time.

    Args:
        session: A ``requests.Session`` (typically Tor-proxied).
        url: An endpoint returning a sizeable body (e.g. a fixed-size blob).
        timeout: Request timeout in seconds.

    Returns:
        The download throughput in kilobytes per second.
    """
    start = time.perf_counter()
    response = session.get(url, timeout=timeout)
    response.raise_for_status()
    num_bytes = len(response.content)
    elapsed = time.perf_counter() - start

    if elapsed <= 0:
        # Sub-resolution timing; avoid division by zero.
        logger.debug("Throughput measurement had non-positive elapsed time")
        return 0.0

    throughput = num_bytes / elapsed / 1024
    logger.debug(
        "Measured throughput: %.1f KB/s (%d bytes in %.3fs)",
        throughput,
        num_bytes,
        elapsed,
    )
    return throughput
