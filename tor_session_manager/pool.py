"""
Circuit pool with best-circuit selection.

Keeps several Tor circuits alive in parallel, benchmarks them, and lets you use
the fastest — dropping slow or blocked ones. It ties together quality
measurement (Sprint 3) and exit steering (Sprint 4).

Each "lane" in the pool is a ``requests.Session`` carrying a distinct SOCKS
username/password. Tor's ``IsolateSOCKSAuth`` (on by default) routes streams
with different SOCKS credentials over *different* circuits, so each lane is an
independent circuit over the same SOCKS port — no control-port stream
attachment needed.
"""

import logging
from dataclasses import dataclass
from typing import List, Optional

import requests

from .ip_checkers import fetch_ip_with_fallback
from .quality import CircuitHealth, measure_latency, measure_throughput

logger = logging.getLogger(__name__)


@dataclass
class PooledCircuit:
    """One isolated circuit lane in a :class:`CircuitPool`."""

    name: str
    session: requests.Session
    health: Optional[CircuitHealth] = None
    exit_ip: Optional[str] = None

    @property
    def proxies(self) -> dict:
        """The proxy dict for this lane's isolated circuit."""
        return dict(self.session.proxies)


def _sort_key(circuit: PooledCircuit):
    """Rank key: lower latency first, higher throughput as tiebreak."""
    health = circuit.health
    latency = (
        health.latency_ms
        if health is not None and health.latency_ms is not None
        else float("inf")
    )
    throughput = (
        health.throughput_kbps
        if health is not None and health.throughput_kbps is not None
        else 0.0
    )
    return (latency, -throughput)


class CircuitPool:
    """
    A pool of isolated Tor circuits with best-circuit selection.

    Example:
        >>> with client.circuit_pool(size=4) as pool:
        ...     pool.build().benchmark()
        ...     best = pool.pin_fastest()
        ...     requests.get(url, proxies=pool.pinned_proxies)
    """

    def __init__(self, client, size: int = 3):
        """
        Args:
            client: The :class:`TorClient` this pool belongs to (used for the
                SOCKS port and measurement defaults).
            size: Number of circuit lanes to maintain.
        """
        self.client = client
        self.size = size
        self.circuits: List[PooledCircuit] = []
        self.pinned: Optional[PooledCircuit] = None
        self._counter = 0

    def _new_lane(self) -> PooledCircuit:
        """Create a new lane with a unique SOCKS credential (fresh circuit)."""
        self._counter += 1
        name = f"tsm{self._counter}"
        session = requests.Session()
        proxy_url = f"socks5h://{name}:{name}@127.0.0.1:{self.client.socks_port}"
        session.proxies = {"http": proxy_url, "https": proxy_url}
        return PooledCircuit(name=name, session=session)

    def build(self) -> "CircuitPool":
        """Create ``size`` fresh lanes, replacing any existing ones."""
        self.close()
        self.circuits = [self._new_lane() for _ in range(self.size)]
        self.pinned = None
        logger.info("Built circuit pool with %d lanes", len(self.circuits))
        return self

    def benchmark(
        self,
        latency_url: Optional[str] = None,
        throughput_url: Optional[str] = None,
        samples: int = 3,
    ) -> "CircuitPool":
        """
        Benchmark every lane, populating each one's ``health`` and ``exit_ip``.

        Measurements are best-effort per lane: a failing metric is left None.
        """
        latency_url = latency_url or self.client.DEFAULT_LATENCY_URL
        throughput_url = throughput_url or self.client.DEFAULT_THROUGHPUT_URL
        timeout = self.client.DEFAULT_MEASURE_TIMEOUT

        for circuit in self.circuits:
            latency_ms: Optional[float] = None
            throughput_kbps: Optional[float] = None
            try:
                latency_ms = measure_latency(
                    circuit.session, latency_url, timeout, samples=samples
                )
            except Exception as e:  # noqa: BLE001 - best-effort
                logger.debug("Lane %s latency failed: %s", circuit.name, e)
            try:
                throughput_kbps = measure_throughput(
                    circuit.session, throughput_url, timeout
                )
            except Exception as e:  # noqa: BLE001 - best-effort
                logger.debug("Lane %s throughput failed: %s", circuit.name, e)

            circuit.health = CircuitHealth(
                latency_ms=latency_ms,
                throughput_kbps=throughput_kbps,
                samples=samples,
            )

            try:
                circuit.exit_ip = fetch_ip_with_fallback(circuit.session, timeout)
            except Exception as e:  # noqa: BLE001 - best-effort
                logger.debug("Lane %s exit IP failed: %s", circuit.name, e)

        return self

    def ranked(self) -> List[PooledCircuit]:
        """Lanes ordered best-first (lowest latency, highest throughput)."""
        return sorted(self.circuits, key=_sort_key)

    def fastest(self) -> Optional[PooledCircuit]:
        """The best lane, or None if the pool is empty."""
        ranked = self.ranked()
        return ranked[0] if ranked else None

    def pin_fastest(self) -> Optional[PooledCircuit]:
        """Pin the fastest lane as the active circuit and return it."""
        self.pinned = self.fastest()
        if self.pinned is not None:
            logger.info(
                "Pinned fastest lane %s (exit %s)",
                self.pinned.name,
                self.pinned.exit_ip,
            )
        return self.pinned

    @property
    def pinned_proxies(self) -> Optional[dict]:
        """Proxy dict of the pinned lane, or None if nothing is pinned."""
        return self.pinned.proxies if self.pinned else None

    def drop(self, circuit: PooledCircuit) -> PooledCircuit:
        """
        Discard a lane and replace it with a fresh one (new circuit).

        Args:
            circuit: The lane to drop.

        Returns:
            The new replacement lane.

        Raises:
            ValueError: If the lane is not part of this pool.
        """
        if circuit not in self.circuits:
            raise ValueError("Circuit is not part of this pool")

        index = self.circuits.index(circuit)
        circuit.session.close()
        if self.pinned is circuit:
            self.pinned = None

        replacement = self._new_lane()
        self.circuits[index] = replacement
        logger.info("Dropped lane %s, replaced with %s", circuit.name, replacement.name)
        return replacement

    def prune(self, keep: int = 1) -> None:
        """Drop all but the best ``keep`` lanes (by rank)."""
        survivors = self.ranked()[:keep]
        for circuit in list(self.circuits):
            if circuit not in survivors:
                circuit.session.close()
                if self.pinned is circuit:
                    self.pinned = None
        self.circuits = survivors

    def close(self) -> None:
        """Close all lane sessions."""
        for circuit in self.circuits:
            circuit.session.close()
        self.circuits = []
        self.pinned = None

    def __enter__(self) -> "CircuitPool":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()
