"""
Tor Session Manager - Programmatic Tor circuit rotation for Python.

A lightweight library for managing Tor sessions and rotating circuits,
designed for ethical web scraping, security research, and privacy testing.
"""

from .blocking import detect_block
from .bridges import Bridge, build_bridge_config, launch_bridged_tor, parse_bridge_line
from .circuits import CircuitInfo, RelayInfo
from .client import TorClient, rotate_and_get_ip
from .exceptions import (
    AllIPCheckersFailedError,
    BlockedResponseError,
    BridgeConfigError,
    IPFetchError,
    TorConnectionError,
    TorNotReadyError,
    TorSessionError,
)
from .pool import CircuitPool, PooledCircuit
from .quality import CircuitHealth

try:
    from .aio import AsyncResponse, TorClientAsync
except ImportError:
    # The async client requires the optional [async] extra (aiohttp,
    # aiohttp_socks). Expose a helpful placeholder instead of failing import.
    _ASYNC_IMPORT_HINT = (
        "TorClientAsync requires the optional async extra. "
        "Install it with: pip install tor-session-manager[async]"
    )

    class TorClientAsync:  # type: ignore[no-redef]
        def __init__(self, *args, **kwargs):
            raise ImportError(_ASYNC_IMPORT_HINT)

    AsyncResponse = None  # type: ignore[assignment,misc]

__version__ = "1.8.0"
__author__ = "Pablo Alaniz"
__email__ = "pablo@culturainteractiva.com"

__all__ = [
    "TorClient",
    "rotate_and_get_ip",
    "CircuitInfo",
    "RelayInfo",
    "CircuitHealth",
    "CircuitPool",
    "PooledCircuit",
    "TorClientAsync",
    "AsyncResponse",
    "detect_block",
    "Bridge",
    "parse_bridge_line",
    "build_bridge_config",
    "launch_bridged_tor",
    "TorSessionError",
    "TorConnectionError",
    "TorNotReadyError",
    "IPFetchError",
    "AllIPCheckersFailedError",
    "BlockedResponseError",
    "BridgeConfigError",
]
