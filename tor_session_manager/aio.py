"""
Async Tor client for concurrent scraping.

``TorClientAsync`` mirrors the sync :class:`TorClient` but runs the data plane
(get_ip, request, benchmark, parallel fetching) on ``aiohttp``, enabling
concurrent requests through Tor. The control plane (rotate, readiness, exit
selection) stays on the synchronous ``stem`` client and is exposed via
``asyncio.to_thread`` wrappers.

Requires the ``[async]`` extra: ``pip install tor-session-manager[async]``.
"""

import asyncio
import logging
import statistics
import time
from dataclasses import dataclass, field
from typing import List, Optional

import aiohttp
from aiohttp_socks import ProxyConnector

from .blocking import detect_block
from .client import TorClient
from .exceptions import AllIPCheckersFailedError, BlockedResponseError
from .ip_checkers import IP_CHECKERS, _normalize_ip
from .quality import CircuitHealth

logger = logging.getLogger(__name__)


@dataclass
class AsyncResponse:
    """A fully-read response snapshot from :class:`TorClientAsync`.

    Exposes ``status_code``/``headers``/``text`` so it plugs straight into
    :func:`tor_session_manager.blocking.detect_block`.
    """

    status_code: int
    headers: dict = field(default_factory=dict)
    text: str = ""
    content: bytes = b""


class TorClientAsync:
    """
    Async client for managing Tor sessions and concurrent requests.

    Example:
        >>> async with TorClientAsync() as client:
        ...     ip = await client.get_ip()
        ...     responses = await client.gather_requests(urls)
    """

    def __init__(
        self,
        control_port: int = TorClient.DEFAULT_CONTROL_PORT,
        socks_port: int = TorClient.DEFAULT_SOCKS_PORT,
        password: Optional[str] = None,
        rotate_delay: float = TorClient.DEFAULT_ROTATE_DELAY,
        max_concurrency: int = 10,
    ):
        self._sync = TorClient(
            control_port=control_port,
            socks_port=socks_port,
            password=password,
            rotate_delay=rotate_delay,
        )
        self.socks_port = socks_port
        self.max_concurrency = max_concurrency
        self._session: Optional[aiohttp.ClientSession] = None

    # -- lifecycle ------------------------------------------------------------

    def _new_session(self) -> aiohttp.ClientSession:
        # rdns=True routes DNS resolution through Tor (equivalent to socks5h),
        # avoiding DNS leaks. aiohttp_socks does not accept the socks5h scheme.
        connector = ProxyConnector.from_url(
            f"socks5://127.0.0.1:{self.socks_port}", rdns=True
        )
        return aiohttp.ClientSession(connector=connector)

    async def __aenter__(self) -> "TorClientAsync":
        ready = await asyncio.to_thread(self._sync.is_ready)
        if not ready:
            from .exceptions import TorNotReadyError

            raise TorNotReadyError(
                "Tor is not ready. Ensure Tor is running and configured correctly."
            )
        self._session = self._new_session()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        if self._session is not None:
            await self._session.close()
            self._session = None

    def _require_session(self) -> aiohttp.ClientSession:
        if self._session is None:
            raise RuntimeError(
                "TorClientAsync must be used as an async context manager "
                "(`async with TorClientAsync() as client:`)"
            )
        return self._session

    # -- control plane (delegated to the sync client via threads) ------------

    async def is_ready(self) -> bool:
        return await asyncio.to_thread(self._sync.is_ready)

    async def rotate(self) -> None:
        await asyncio.to_thread(self._sync.rotate)

    async def set_exit_country(self, country: str, strict: bool = True) -> None:
        await asyncio.to_thread(self._sync.set_exit_country, country, strict)

    async def set_exit_nodes(
        self, countries=None, fingerprints=None, strict: bool = True
    ) -> None:
        await asyncio.to_thread(
            self._sync.set_exit_nodes, countries, fingerprints, strict
        )

    async def reset_exit_nodes(self) -> None:
        await asyncio.to_thread(self._sync.reset_exit_nodes)

    async def new_circuit(
        self,
        exit_country: Optional[str] = None,
        exit_fingerprint: Optional[str] = None,
        strict: bool = True,
        verify: bool = True,
    ) -> Optional[str]:
        if exit_country or exit_fingerprint:
            await self.set_exit_nodes(
                countries=[exit_country] if exit_country else None,
                fingerprints=[exit_fingerprint] if exit_fingerprint else None,
                strict=strict,
            )
        await self.rotate()
        if not verify:
            return None
        try:
            return await self.get_ip()
        except AllIPCheckersFailedError as e:
            from .exceptions import TorSessionError

            raise TorSessionError(
                "Could not establish a working circuit with the requested exit "
                "constraints (the country may have no usable exit nodes): %s" % e
            )

    # -- data plane (aiohttp) -------------------------------------------------

    async def get_ip(self) -> str:
        """Resolve the public exit IP, trying each checker in order."""
        session = self._require_session()
        errors: List[str] = []
        for url, json_key in IP_CHECKERS:
            try:
                async with session.get(
                    url,
                    timeout=aiohttp.ClientTimeout(total=self._sync.IP_CHECK_TIMEOUT),
                ) as response:
                    response.raise_for_status()
                    if json_key is not None:
                        raw = (await response.json()).get(json_key)
                        if raw is None:
                            raise ValueError(f"missing key '{json_key}' in response")
                    else:
                        raw = await response.text()
                    return _normalize_ip(str(raw))
            except Exception as e:  # noqa: BLE001 - try the next checker
                errors.append(f"{url}: {e}")
        raise AllIPCheckersFailedError(
            "All IP checkers failed:\n  " + "\n  ".join(errors)
        )

    async def request(
        self,
        url: str,
        method: str = "GET",
        timeout: Optional[float] = None,
        **kwargs,
    ) -> AsyncResponse:
        """Make a request through Tor and return a materialized response."""
        session = self._require_session()
        client_timeout = aiohttp.ClientTimeout(
            total=timeout or self._sync.IP_CHECK_TIMEOUT
        )
        async with session.request(
            method, url, timeout=client_timeout, **kwargs
        ) as response:
            content = await response.read()
            return AsyncResponse(
                status_code=response.status,
                headers=dict(response.headers),
                text=content.decode(errors="replace"),
                content=content,
            )

    async def request_with_retry(
        self,
        url: str,
        method: str = "GET",
        max_rotations: int = 3,
        markers=None,
        statuses=None,
        timeout: Optional[float] = None,
        **kwargs,
    ) -> AsyncResponse:
        """Like :meth:`request` but rotates the exit when blocked."""
        reason = None
        response = None
        for attempt in range(max_rotations + 1):
            response = await self.request(url, method=method, timeout=timeout, **kwargs)
            reason = detect_block(response, markers=markers, statuses=statuses)
            if reason is None:
                return response
            if attempt < max_rotations:
                logger.info("Response blocked (%s); rotating exit and retrying", reason)
                await self.rotate()
        raise BlockedResponseError(
            f"Still blocked after {max_rotations} rotation(s): {reason}",
            reason=reason,
            response=response,
        )

    async def measure_latency(
        self,
        url: Optional[str] = None,
        samples: int = 3,
        timeout: Optional[float] = None,
    ) -> float:
        """Measure request latency (median of N samples) in milliseconds."""
        if samples < 1:
            raise ValueError("samples must be >= 1")
        url = url or self._sync.DEFAULT_LATENCY_URL
        timings = []
        for _ in range(samples):
            start = time.perf_counter()
            await self.request(
                url, timeout=timeout or self._sync.DEFAULT_MEASURE_TIMEOUT
            )
            timings.append((time.perf_counter() - start) * 1000)
        return statistics.median(timings)

    async def measure_throughput(
        self,
        url: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> float:
        """Measure download throughput in KB/s."""
        url = url or self._sync.DEFAULT_THROUGHPUT_URL
        start = time.perf_counter()
        response = await self.request(
            url, timeout=timeout or self._sync.DEFAULT_MEASURE_TIMEOUT
        )
        elapsed = time.perf_counter() - start
        if elapsed <= 0:
            return 0.0
        return len(response.content) / elapsed / 1024

    async def benchmark(
        self,
        latency_url: Optional[str] = None,
        throughput_url: Optional[str] = None,
        samples: int = 3,
    ) -> CircuitHealth:
        """Benchmark the current circuit (best-effort latency + throughput)."""
        latency_ms: Optional[float] = None
        throughput_kbps: Optional[float] = None
        try:
            latency_ms = await self.measure_latency(url=latency_url, samples=samples)
        except Exception as e:  # noqa: BLE001 - best-effort
            logger.debug("Latency measurement failed: %s", e)
        try:
            throughput_kbps = await self.measure_throughput(url=throughput_url)
        except Exception as e:  # noqa: BLE001 - best-effort
            logger.debug("Throughput measurement failed: %s", e)
        return CircuitHealth(
            latency_ms=latency_ms,
            throughput_kbps=throughput_kbps,
            samples=samples,
            measured_at=time.time(),
        )

    async def gather_requests(
        self,
        urls,
        method: str = "GET",
        **kwargs,
    ) -> List[Optional[AsyncResponse]]:
        """
        Fetch many URLs concurrently through Tor.

        Concurrency is bounded by ``max_concurrency`` via a semaphore. A URL
        that errors resolves to ``None`` in its position (results stay aligned
        with ``urls``).
        """
        semaphore = asyncio.Semaphore(self.max_concurrency)

        async def _fetch(url):
            async with semaphore:
                try:
                    return await self.request(url, method=method, **kwargs)
                except Exception as e:  # noqa: BLE001 - tolerant per-URL
                    logger.debug("Request to %s failed: %s", url, e)
                    return None

        return await asyncio.gather(*(_fetch(url) for url in urls))
