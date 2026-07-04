"""
Tor Session Manager - Programmatic Tor circuit rotation for Python.

A lightweight library for managing Tor sessions and rotating circuits,
designed for ethical web scraping, security research, and privacy testing.
"""

from .circuits import CircuitInfo, RelayInfo
from .client import TorClient, rotate_and_get_ip
from .exceptions import (
    AllIPCheckersFailedError,
    IPFetchError,
    TorConnectionError,
    TorNotReadyError,
    TorSessionError,
)
from .quality import CircuitHealth

__version__ = "1.3.0"
__author__ = "Pablo Alaniz"
__email__ = "pablo@culturainteractiva.com"

__all__ = [
    "TorClient",
    "rotate_and_get_ip",
    "CircuitInfo",
    "RelayInfo",
    "CircuitHealth",
    "TorSessionError",
    "TorConnectionError",
    "TorNotReadyError",
    "IPFetchError",
    "AllIPCheckersFailedError",
]
