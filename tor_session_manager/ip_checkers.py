"""
IP checker endpoints with fallback support.

Fetching the public exit IP through Tor is a single point of failure if it
relies on one endpoint. This module tries several well-known "what is my IP"
services in order and returns the first successful result.
"""

import ipaddress
import logging
from typing import List, Optional, Tuple

import requests

from .exceptions import AllIPCheckersFailedError

logger = logging.getLogger(__name__)


# Each checker is (url, json_key). If json_key is None, the response body is
# treated as plain text containing the IP. Ordered by preference.
IPChecker = Tuple[str, Optional[str]]

IP_CHECKERS: List[IPChecker] = [
    ("https://api.ipify.org/?format=json", "ip"),
    ("https://ifconfig.me/ip", None),
    ("https://icanhazip.com", None),
    ("https://httpbin.org/ip", "origin"),
]


def _normalize_ip(raw: str) -> str:
    """
    Clean and validate a raw IP string returned by a checker.

    Some services (e.g. httpbin's ``origin``) may return a comma-separated
    list of addresses; we take the first one. Raises ValueError if the value
    is not a valid IP address.
    """
    candidate = raw.strip().split(",")[0].strip()
    # Raises ValueError for anything that is not a valid IPv4/IPv6 address.
    ipaddress.ip_address(candidate)
    return candidate


def fetch_ip_with_fallback(session: requests.Session, timeout: float) -> str:
    """
    Return the public IP by trying each checker in ``IP_CHECKERS`` in order.

    Args:
        session: A ``requests.Session`` (typically Tor-proxied) used for the
            HTTP calls.
        timeout: Per-request timeout in seconds.

    Returns:
        The public IP address as a string.

    Raises:
        AllIPCheckersFailedError: If every checker fails. The message includes
            the reason each checker failed.
    """
    errors: List[str] = []

    for url, json_key in IP_CHECKERS:
        try:
            response = session.get(url, timeout=timeout)
            response.raise_for_status()

            if json_key is not None:
                raw = response.json().get(json_key)
                if raw is None:
                    raise ValueError(f"missing key '{json_key}' in response")
            else:
                raw = response.text

            ip = _normalize_ip(str(raw))
            logger.debug("IP resolved via %s: %s", url, ip)
            return ip
        except Exception as e:  # noqa: BLE001 - we deliberately try the next checker
            logger.debug("IP checker %s failed: %s", url, e)
            errors.append(f"{url}: {e}")

    raise AllIPCheckersFailedError("All IP checkers failed:\n  " + "\n  ".join(errors))
