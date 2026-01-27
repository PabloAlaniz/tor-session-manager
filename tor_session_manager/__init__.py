"""
Tor Session Manager - Programmatic Tor circuit rotation for Python.

A lightweight library for managing Tor sessions and rotating circuits,
designed for ethical web scraping, security research, and privacy testing.
"""

from .client import TorClient, rotate_and_get_ip
from .exceptions import (
    TorSessionError,
    TorConnectionError,
    TorNotReadyError,
    IPFetchError,
)

__version__ = "1.0.0"
__author__ = "Pablo Alaniz"
__email__ = "pablo@culturainteractiva.com"

__all__ = [
    "TorClient",
    "rotate_and_get_ip",
    "TorSessionError",
    "TorConnectionError", 
    "TorNotReadyError",
    "IPFetchError",
]
