"""
Bridges and pluggable transports — reaching Tor under censorship.

When an ISP or country blocks Tor itself, plain relays are unreachable. Bridges
(unlisted relays) combined with pluggable transports (obfs4, snowflake, meek,
webtunnel) obfuscate the traffic so it does not look like Tor.

``UseBridges``/``Bridge``/``ClientTransportPlugin`` are *launch-time* options —
they can't be toggled on an already-running Tor over the control port — so this
module parses/validates bridge lines and launches a managed Tor with the right
config via ``stem.process.launch_tor_with_config``.

The pluggable-transport binaries (obfs4proxy, snowflake-client, …) are not
bundled; they are resolved from PATH (or passed explicitly).
"""

import logging
import re
import shutil
from dataclasses import dataclass
from typing import Dict, List, Optional, Union

from .exceptions import BridgeConfigError

logger = logging.getLogger(__name__)

# Transport name -> default executable resolved from PATH.
KNOWN_TRANSPORTS: Dict[str, str] = {
    "obfs4": "obfs4proxy",
    "obfs3": "obfs4proxy",
    "meek_lite": "obfs4proxy",
    "meek": "meek-client",
    "snowflake": "snowflake-client",
    "webtunnel": "webtunnel-client",
    "conjure": "conjure-client",
}

_FINGERPRINT_RE = re.compile(r"^[A-Fa-f0-9]{40}$")
_ADDRESS_RE = re.compile(r"^\[?[0-9A-Fa-f.:]+\]?:\d+$")


@dataclass
class Bridge:
    """A parsed bridge line."""

    address: str
    transport: Optional[str] = None
    fingerprint: Optional[str] = None
    args: str = ""

    @property
    def line(self) -> str:
        """Reconstruct the ``Bridge`` config line."""
        parts: List[str] = []
        if self.transport:
            parts.append(self.transport)
        parts.append(self.address)
        if self.fingerprint:
            parts.append(self.fingerprint)
        if self.args:
            parts.append(self.args)
        return " ".join(parts)


def parse_bridge_line(line: str) -> Bridge:
    """
    Parse a bridge line into a :class:`Bridge`.

    Accepts both vanilla bridges (``IP:PORT [FINGERPRINT]``) and pluggable
    transport bridges (``TRANSPORT IP:PORT [FINGERPRINT] [args...]``).

    Raises:
        BridgeConfigError: If no address can be found in the line.
    """
    tokens = (line or "").strip().split()
    if not tokens:
        raise BridgeConfigError("Empty bridge line")

    transport: Optional[str] = None
    # A leading token that is not an address is the transport name.
    if not _ADDRESS_RE.match(tokens[0]):
        transport = tokens[0]
        tokens = tokens[1:]

    if not tokens or not _ADDRESS_RE.match(tokens[0]):
        raise BridgeConfigError(f"No valid address found in bridge line: {line!r}")

    address = tokens[0]
    tokens = tokens[1:]

    fingerprint: Optional[str] = None
    if tokens and _FINGERPRINT_RE.match(tokens[0]):
        fingerprint = tokens[0].upper()
        tokens = tokens[1:]

    args = " ".join(tokens)
    return Bridge(
        address=address, transport=transport, fingerprint=fingerprint, args=args
    )


def transport_binary(transport: str, path: Optional[str] = None) -> str:
    """
    Resolve the executable for a pluggable transport.

    Args:
        transport: Transport name (e.g. "obfs4", "snowflake").
        path: Explicit path to the binary (skips PATH lookup).

    Returns:
        The resolved executable path.

    Raises:
        BridgeConfigError: If the binary cannot be found.
    """
    if path:
        return path

    candidate = KNOWN_TRANSPORTS.get(transport, transport)
    resolved = shutil.which(candidate)
    if not resolved:
        raise BridgeConfigError(
            f"Pluggable transport binary for '{transport}' not found "
            f"(looked for '{candidate}' on PATH). Install it or pass an explicit "
            f"path via transport_paths."
        )
    return resolved


def _as_bridge(bridge: Union[str, Bridge]) -> Bridge:
    return bridge if isinstance(bridge, Bridge) else parse_bridge_line(bridge)


def build_bridge_config(
    bridges: List[Union[str, Bridge]],
    transport_paths: Optional[Dict[str, str]] = None,
) -> Dict[str, Union[str, List[str]]]:
    """
    Build the torrc options for the given bridges.

    Args:
        bridges: Bridge lines (strings) or :class:`Bridge` objects.
        transport_paths: Optional map ``transport -> binary path`` to override
            PATH resolution.

    Returns:
        A dict with ``UseBridges``, ``Bridge`` (list) and, if any transport is
        used, ``ClientTransportPlugin`` (list).

    Raises:
        BridgeConfigError: If no bridges are given or a transport binary is
            missing.
    """
    if not bridges:
        raise BridgeConfigError("At least one bridge is required")

    transport_paths = transport_paths or {}
    parsed = [_as_bridge(b) for b in bridges]

    config: Dict[str, Union[str, List[str]]] = {
        "UseBridges": "1",
        "Bridge": [b.line for b in parsed],
    }

    # One ClientTransportPlugin per distinct transport, order-preserving.
    plugins: List[str] = []
    seen = set()
    for bridge in parsed:
        if not bridge.transport or bridge.transport in seen:
            continue
        seen.add(bridge.transport)
        binary = transport_binary(
            bridge.transport, transport_paths.get(bridge.transport)
        )
        plugins.append(f"{bridge.transport} exec {binary}")

    if plugins:
        config["ClientTransportPlugin"] = plugins

    return config


def launch_bridged_tor(
    bridges: List[Union[str, Bridge]],
    transport_paths: Optional[Dict[str, str]] = None,
    socks_port: int = 9050,
    control_port: int = 9051,
    data_directory: Optional[str] = None,
    tor_cmd: str = "tor",
    timeout: int = 90,
    extra_config: Optional[Dict[str, Union[str, List[str]]]] = None,
    take_ownership: bool = True,
):
    """
    Launch a managed Tor process configured with the given bridges.

    Args:
        bridges: Bridge lines or :class:`Bridge` objects.
        transport_paths: Optional map ``transport -> binary path``.
        socks_port: SOCKS port for the launched Tor.
        control_port: Control port for the launched Tor.
        data_directory: Optional Tor data directory.
        tor_cmd: Tor executable (default: "tor").
        timeout: Seconds to wait for bootstrap.
        extra_config: Extra torrc options merged into the config.
        take_ownership: If True, Tor exits when this process does.

    Returns:
        The launched Tor ``subprocess.Popen`` (from stem).

    Raises:
        BridgeConfigError: If the bridge config is invalid or a PT binary is
            missing.
    """
    config: Dict[str, Union[str, List[str]]] = {
        "SocksPort": str(socks_port),
        "ControlPort": str(control_port),
        "CookieAuthentication": "1",
    }
    if data_directory:
        config["DataDirectory"] = data_directory

    config.update(build_bridge_config(bridges, transport_paths=transport_paths))

    if extra_config:
        config.update(extra_config)

    import stem.process

    logger.info("Launching bridged Tor with %d bridge(s)", len(config["Bridge"]))
    return stem.process.launch_tor_with_config(
        config=config,
        tor_cmd=tor_cmd,
        timeout=timeout,
        take_ownership=take_ownership,
    )
