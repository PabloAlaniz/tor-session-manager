"""
Circuit introspection helpers.

Turns the raw circuit objects returned by ``stem`` into small, friendly
dataclasses that expose which relays make up a circuit and where its exit
node is located. This is the visibility foundation that later sprints
(exit selection, quality measurement, best-circuit pooling) build on.
"""

import logging
from dataclasses import dataclass, field
from typing import List, Optional

logger = logging.getLogger(__name__)


@dataclass
class RelayInfo:
    """A single relay (hop) in a Tor circuit."""

    fingerprint: str
    nickname: Optional[str] = None
    address: Optional[str] = None
    country: Optional[str] = None


@dataclass
class CircuitInfo:
    """A snapshot of a Tor circuit and its relays."""

    id: str
    status: str
    purpose: Optional[str]
    path: List[RelayInfo] = field(default_factory=list)
    build_flags: Optional[tuple] = None
    created: Optional[str] = None

    @property
    def exit_relay(self) -> Optional[RelayInfo]:
        """The last hop of the circuit (the exit node), or None if empty."""
        return self.path[-1] if self.path else None

    @property
    def exit_country(self) -> Optional[str]:
        """Country code of the exit relay, if resolved."""
        exit_relay = self.exit_relay
        return exit_relay.country if exit_relay else None


def _resolve_relay(controller, fingerprint: str, nickname: Optional[str]) -> RelayInfo:
    """
    Build a RelayInfo, best-effort resolving the relay's address and country.

    Lookups are tolerant: if the consensus entry or the GeoIP lookup is
    unavailable, the corresponding field stays None instead of raising.
    """
    address: Optional[str] = None
    country: Optional[str] = None

    try:
        status_entry = controller.get_network_status(fingerprint)
        address = getattr(status_entry, "address", None)
        if not nickname:
            nickname = getattr(status_entry, "nickname", None)
    except Exception as e:  # noqa: BLE001 - resolution is best-effort
        logger.debug("Could not resolve network status for %s: %s", fingerprint, e)

    if address:
        try:
            country = controller.get_info("ip-to-country/%s" % address)
        except Exception as e:  # noqa: BLE001 - GeoIP is best-effort
            logger.debug("Could not resolve country for %s: %s", address, e)

    return RelayInfo(
        fingerprint=fingerprint,
        nickname=nickname,
        address=address,
        country=country,
    )


def parse_circuit(controller, circuit) -> CircuitInfo:
    """
    Convert a stem circuit object into a :class:`CircuitInfo`.

    Only the exit relay's address/country are resolved (the expensive
    lookups), since that is what callers care about; intermediate hops keep
    just their fingerprint/nickname from the circuit path.

    Args:
        controller: An authenticated stem ``Controller``.
        circuit: A circuit object from ``controller.get_circuits()`` with
            ``.id``, ``.status``, ``.purpose``, ``.path``, ``.build_flags``
            and ``.created`` attributes.

    Returns:
        A populated :class:`CircuitInfo`.
    """
    raw_path = list(getattr(circuit, "path", []) or [])
    path: List[RelayInfo] = []

    for index, hop in enumerate(raw_path):
        fingerprint, nickname = hop
        is_exit = index == len(raw_path) - 1
        if is_exit:
            path.append(_resolve_relay(controller, fingerprint, nickname))
        else:
            path.append(RelayInfo(fingerprint=fingerprint, nickname=nickname))

    return CircuitInfo(
        id=circuit.id,
        status=circuit.status,
        purpose=getattr(circuit, "purpose", None),
        path=path,
        build_flags=getattr(circuit, "build_flags", None),
        created=getattr(circuit, "created", None),
    )
