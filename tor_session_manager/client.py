"""
Tor Session Manager - Client module

A Python client for managing Tor circuits and sessions programmatically.
"""

import logging
import time
from contextlib import contextmanager
from typing import Optional

import requests
from stem import Signal
from stem.control import Controller

from .circuits import CircuitInfo, parse_circuit
from .exceptions import (
    TorConnectionError,
    TorNotReadyError,
    TorSessionError,
)
from .ip_checkers import fetch_ip_with_fallback
from .quality import CircuitHealth, measure_latency, measure_throughput

logger = logging.getLogger(__name__)


def _retry_with_backoff(fn, attempts: int = 4, base_delay: float = 2.0):
    """
    Call ``fn`` retrying transient failures with exponential backoff.

    Waits ``base_delay * 2**i`` seconds between attempts (2, 4, 8, 16 ...).
    Re-raises the last exception if all attempts fail.

    Args:
        fn: Zero-argument callable to execute.
        attempts: Maximum number of attempts (default: 4).
        base_delay: Base delay in seconds for the backoff (default: 2.0).

    Returns:
        Whatever ``fn`` returns on the first success.
    """
    last_exc: Optional[Exception] = None
    for i in range(attempts):
        try:
            return fn()
        except Exception as e:  # noqa: BLE001 - retried and re-raised below
            last_exc = e
            if i < attempts - 1:
                delay = base_delay * (2**i)
                logger.debug(
                    "Attempt %d/%d failed (%s); retrying in %.1fs",
                    i + 1,
                    attempts,
                    e,
                    delay,
                )
                time.sleep(delay)
    assert last_exc is not None
    raise last_exc


class TorClient:
    """
    A client for managing Tor sessions and rotating circuits.
    
    Use cases:
        - Ethical web scraping with IP rotation
        - Security research and penetration testing
        - Privacy testing for applications
        - Academic network research
    
    Example:
        >>> with TorClient() as client:
        ...     print(f"Current IP: {client.get_ip()}")
        ...     client.rotate()
        ...     print(f"New IP: {client.get_ip()}")
    """
    
    DEFAULT_CONTROL_PORT = 9051
    DEFAULT_SOCKS_PORT = 9050
    DEFAULT_ROTATE_DELAY = 2.0
    IP_CHECK_URL = "https://api.ipify.org/?format=json"
    IP_CHECK_TIMEOUT = 30
    CIRCUIT_STATUS_BUILT = "BUILT"
    CIRCUIT_PURPOSE_GENERAL = "GENERAL"
    DEFAULT_LATENCY_URL = "https://httpbin.org/get"
    DEFAULT_THROUGHPUT_URL = "https://httpbin.org/bytes/102400"
    DEFAULT_MEASURE_TIMEOUT = 30
    
    def __init__(
        self,
        control_port: int = DEFAULT_CONTROL_PORT,
        socks_port: int = DEFAULT_SOCKS_PORT,
        password: Optional[str] = None,
        rotate_delay: float = DEFAULT_ROTATE_DELAY,
    ):
        """
        Initialize the Tor client.
        
        Args:
            control_port: Tor control port (default: 9051)
            socks_port: Tor SOCKS proxy port (default: 9050)
            password: Control port password if not using cookie auth
            rotate_delay: Seconds to wait after rotation (default: 2.0)
        """
        self.control_port = control_port
        self.socks_port = socks_port
        self.password = password
        self.rotate_delay = rotate_delay
        self._session: Optional[requests.Session] = None
    
    def __enter__(self) -> "TorClient":
        """Context manager entry - verifies Tor is ready."""
        if not self.is_ready():
            raise TorNotReadyError(
                "Tor is not ready. Ensure Tor is running and configured correctly."
            )
        self._session = self._create_session()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit - cleanup."""
        if self._session:
            self._session.close()
            self._session = None
    
    def _create_session(self) -> requests.Session:
        """Create a requests session configured to use Tor SOCKS proxy."""
        session = requests.Session()
        proxy_url = f"socks5h://127.0.0.1:{self.socks_port}"
        session.proxies = {
            "http": proxy_url,
            "https": proxy_url,
        }
        return session
    
    def _get_controller(self) -> Controller:
        """Get an authenticated Tor controller connection."""
        try:
            controller = Controller.from_port(port=self.control_port)
            if self.password:
                controller.authenticate(password=self.password)
            else:
                controller.authenticate()
            return controller
        except Exception as e:
            raise TorConnectionError(f"Failed to connect to Tor controller: {e}")
    
    def is_ready(self) -> bool:
        """
        Check if Tor is running and fully bootstrapped.
        
        Returns:
            True if Tor is ready, False otherwise.
        """
        try:
            with self._get_controller() as controller:
                status = controller.get_info("status/bootstrap-phase")
                is_ready = "PROGRESS=100" in status
                logger.debug(f"Tor bootstrap status: {status}")
                return is_ready
        except TorConnectionError:
            return False
        except Exception as e:
            logger.warning(f"Error checking Tor status: {e}")
            return False
    
    def rotate(self) -> None:
        """
        Request a new Tor circuit (new exit node = new IP).
        
        This sends the NEWNYM signal to Tor, which will use a new
        circuit for subsequent connections.
        
        Raises:
            TorConnectionError: If unable to connect to Tor controller.
        """
        logger.info("Requesting new Tor identity...")
        try:
            with self._get_controller() as controller:
                controller.signal(Signal.NEWNYM)
                logger.debug("NEWNYM signal sent successfully")
        except TorConnectionError:
            raise
        except Exception as e:
            raise TorConnectionError(f"Failed to rotate circuit: {e}")
        
        # Wait for the new circuit to be established
        time.sleep(self.rotate_delay)
        logger.info("Circuit rotation complete")
    
    def get_ip(self) -> str:
        """
        Get the current public IP address as seen through Tor.

        Tries several IP-check endpoints in order (see
        :data:`tor_session_manager.ip_checkers.IP_CHECKERS`) so a single
        service outage does not break IP resolution.

        Returns:
            The public IP address string.

        Raises:
            AllIPCheckersFailedError: If every IP checker fails.
            IPFetchError: For other IP resolution failures.
        """
        session = self._session or self._create_session()

        try:
            return fetch_ip_with_fallback(session, self.IP_CHECK_TIMEOUT)
        finally:
            if not self._session:
                session.close()

    def wait_for_new_ip(
        self,
        previous_ip: Optional[str] = None,
        max_attempts: int = 5,
    ) -> str:
        """
        Rotate the circuit until the exit IP actually changes.

        A single ``rotate()`` can occasionally reuse the same exit node, so
        the observed IP may not change. This method rotates repeatedly until
        it observes a different IP or runs out of attempts.

        Args:
            previous_ip: The IP to change away from. If None, it is captured
                with ``get_ip()`` before rotating.
            max_attempts: Maximum number of rotations to try (default: 5).

        Returns:
            The new (different) public IP address.

        Raises:
            TorSessionError: If the IP does not change after ``max_attempts``.
        """
        if previous_ip is None:
            previous_ip = self.get_ip()

        for attempt in range(1, max_attempts + 1):
            self.rotate()
            current_ip = self.get_ip()
            if current_ip != previous_ip:
                logger.info(
                    "New IP obtained after %d rotation(s): %s",
                    attempt,
                    current_ip,
                )
                return current_ip
            logger.debug(
                "IP unchanged after rotation %d/%d (%s)",
                attempt,
                max_attempts,
                current_ip,
            )

        raise TorSessionError(
            f"IP did not change after {max_attempts} rotation attempts "
            f"(still {previous_ip})"
        )
    
    @contextmanager
    def rotated_session(self):
        """
        Context manager that rotates the circuit before yielding.
        
        Example:
            >>> client = TorClient()
            >>> with client.rotated_session():
            ...     # Make requests with a fresh circuit
            ...     response = requests.get(url, proxies=client.proxies)
        
        Yields:
            The TorClient instance with a fresh circuit.
        """
        self.rotate()
        try:
            yield self
        finally:
            pass  # Circuit will be reused until next rotation
    
    def list_circuits(self) -> list:
        """
        List all Tor circuits currently known to the controller.

        Returns:
            A list of :class:`CircuitInfo` snapshots.

        Raises:
            TorConnectionError: If unable to connect to the Tor controller.
        """
        with self._get_controller() as controller:
            return [
                parse_circuit(controller, circuit)
                for circuit in controller.get_circuits()
            ]

    def get_circuit_info(self, circuit_id: Optional[str] = None) -> CircuitInfo:
        """
        Get details for a specific circuit, or the active one.

        When ``circuit_id`` is None, the "active" circuit is chosen: the most
        recently created circuit that is BUILT and of GENERAL purpose (the kind
        used to carry regular application traffic).

        Args:
            circuit_id: The circuit id to inspect, or None for the active one.

        Returns:
            A :class:`CircuitInfo` snapshot.

        Raises:
            TorSessionError: If the circuit id is not found, or no active
                circuit exists.
            TorConnectionError: If unable to connect to the Tor controller.
        """
        circuits = self.list_circuits()

        if circuit_id is not None:
            for circuit in circuits:
                if circuit.id == circuit_id:
                    return circuit
            raise TorSessionError(f"Circuit '{circuit_id}' not found")

        candidates = [
            c
            for c in circuits
            if c.status == self.CIRCUIT_STATUS_BUILT
            and c.purpose == self.CIRCUIT_PURPOSE_GENERAL
        ]
        if not candidates:
            raise TorSessionError("No active (BUILT/GENERAL) circuit found")

        # Most recently created wins; fall back to id order if 'created' is None.
        candidates.sort(key=lambda c: (c.created or "", c.id))
        return candidates[-1]

    def get_exit_country(self, circuit_id: Optional[str] = None) -> Optional[str]:
        """
        Get the ISO country code of a circuit's exit relay.

        Args:
            circuit_id: The circuit to inspect, or None for the active one.

        Returns:
            The exit relay's country code, or None if it cannot be resolved.

        Raises:
            TorSessionError: If no matching/active circuit exists.
            TorConnectionError: If unable to connect to the Tor controller.
        """
        return self.get_circuit_info(circuit_id).exit_country

    def measure_latency(
        self,
        url: Optional[str] = None,
        samples: int = 3,
        timeout: Optional[float] = None,
    ) -> float:
        """
        Measure request latency of the current circuit (median of N samples).

        Args:
            url: Endpoint to time (default: ``DEFAULT_LATENCY_URL``).
            samples: Number of timed requests (default: 3).
            timeout: Per-request timeout (default: ``DEFAULT_MEASURE_TIMEOUT``).

        Returns:
            Median round-trip latency in milliseconds.
        """
        session = self._session or self._create_session()
        try:
            return measure_latency(
                session,
                url or self.DEFAULT_LATENCY_URL,
                timeout or self.DEFAULT_MEASURE_TIMEOUT,
                samples=samples,
            )
        finally:
            if not self._session:
                session.close()

    def measure_throughput(
        self,
        url: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> float:
        """
        Measure download throughput of the current circuit in KB/s.

        Args:
            url: Endpoint returning a sizeable body
                (default: ``DEFAULT_THROUGHPUT_URL``).
            timeout: Request timeout (default: ``DEFAULT_MEASURE_TIMEOUT``).

        Returns:
            Download throughput in kilobytes per second.
        """
        session = self._session or self._create_session()
        try:
            return measure_throughput(
                session,
                url or self.DEFAULT_THROUGHPUT_URL,
                timeout or self.DEFAULT_MEASURE_TIMEOUT,
            )
        finally:
            if not self._session:
                session.close()

    def benchmark(
        self,
        latency_url: Optional[str] = None,
        throughput_url: Optional[str] = None,
        samples: int = 3,
    ) -> CircuitHealth:
        """
        Benchmark the current circuit's latency and throughput.

        Both measurements are best-effort: if one fails, its field is left
        None and the other is still reported.

        Args:
            latency_url: Override for the latency endpoint.
            throughput_url: Override for the throughput endpoint.
            samples: Number of latency samples (default: 3).

        Returns:
            A :class:`CircuitHealth` snapshot with ``measured_at`` set.
        """
        latency_ms: Optional[float] = None
        throughput_kbps: Optional[float] = None

        try:
            latency_ms = self.measure_latency(url=latency_url, samples=samples)
        except Exception as e:  # noqa: BLE001 - best-effort measurement
            logger.debug("Latency measurement failed: %s", e)

        try:
            throughput_kbps = self.measure_throughput(url=throughput_url)
        except Exception as e:  # noqa: BLE001 - best-effort measurement
            logger.debug("Throughput measurement failed: %s", e)

        return CircuitHealth(
            latency_ms=latency_ms,
            throughput_kbps=throughput_kbps,
            samples=samples,
            measured_at=time.time(),
        )

    @property
    def proxies(self) -> dict:
        """
        Get proxy configuration dict for use with requests.

        Returns:
            Dict with http and https proxy URLs.

        Example:
            >>> client = TorClient()
            >>> requests.get(url, proxies=client.proxies)
        """
        proxy_url = f"socks5h://127.0.0.1:{self.socks_port}"
        return {"http": proxy_url, "https": proxy_url}


def rotate_and_get_ip(
    control_port: int = TorClient.DEFAULT_CONTROL_PORT,
    socks_port: int = TorClient.DEFAULT_SOCKS_PORT,
) -> str:
    """
    Convenience function to rotate circuit and return new IP.
    
    Args:
        control_port: Tor control port
        socks_port: Tor SOCKS port
        
    Returns:
        The new public IP address.
    """
    with TorClient(control_port=control_port, socks_port=socks_port) as client:
        client.rotate()
        return client.get_ip()
