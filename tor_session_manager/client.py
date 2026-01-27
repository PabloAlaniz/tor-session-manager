"""
Tor Session Manager - Client module

A Python client for managing Tor circuits and sessions programmatically.
"""

import time
import logging
from typing import Optional
from contextlib import contextmanager

import requests
from stem import Signal
from stem.control import Controller

from .exceptions import TorConnectionError, TorNotReadyError, IPFetchError


logger = logging.getLogger(__name__)


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
        
        Returns:
            The public IP address string.
            
        Raises:
            IPFetchError: If unable to determine the IP address.
        """
        session = self._session or self._create_session()
        
        try:
            response = session.get(
                self.IP_CHECK_URL,
                timeout=self.IP_CHECK_TIMEOUT
            )
            response.raise_for_status()
            ip = response.json().get("ip")
            logger.debug(f"Current IP: {ip}")
            return ip
        except requests.RequestException as e:
            raise IPFetchError(f"Failed to fetch IP address: {e}")
        finally:
            if not self._session:
                session.close()
    
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
