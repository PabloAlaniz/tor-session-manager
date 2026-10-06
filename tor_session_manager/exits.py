"""
Exit node selection helpers.

Turns country codes and relay fingerprints into the ``ExitNodes`` value that
Tor's control port understands, so callers can steer which exit their traffic
leaves through — to dodge destination-side blocks (pick an allowed country or
a non-blocklisted relay) or to target a specific fast exit.

Pure helpers, testable without a running Tor daemon.
"""

import re
from typing import List, Optional

_COUNTRY_RE = re.compile(r"^[a-z]{2}$")


def normalize_country(cc: str) -> str:
    """
    Validate and normalize a 2-letter ISO country code.

    Args:
        cc: A country code such as "US" or "de".

    Returns:
        The lowercase 2-letter code.

    Raises:
        ValueError: If ``cc`` is not a 2-letter alphabetic code.
    """
    normalized = (cc or "").strip().lower()
    if not _COUNTRY_RE.match(normalized):
        raise ValueError(f"Invalid country code: {cc!r} (expected 2 letters)")
    return normalized


def _normalize_fingerprint(fingerprint: str) -> str:
    """Normalize a relay fingerprint to the ``$FINGERPRINT`` token form."""
    fp = (fingerprint or "").strip()
    if not fp:
        raise ValueError("Empty fingerprint")
    return fp if fp.startswith("$") else f"${fp}"


def format_exit_nodes(
    countries: Optional[List[str]] = None,
    fingerprints: Optional[List[str]] = None,
) -> str:
    """
    Build the ``ExitNodes`` config value from countries and/or fingerprints.

    Args:
        countries: ISO country codes; each becomes a ``{cc}`` token.
        fingerprints: Relay fingerprints; each becomes a ``$FINGERPRINT`` token.

    Returns:
        A comma-separated ``ExitNodes`` value (e.g. ``"{us},{de},$AAAA"``).

    Raises:
        ValueError: If no country or fingerprint is provided.
    """
    tokens: List[str] = []

    for country in countries or []:
        tokens.append("{%s}" % normalize_country(country))

    for fingerprint in fingerprints or []:
        tokens.append(_normalize_fingerprint(fingerprint))

    if not tokens:
        raise ValueError("At least one country or fingerprint is required")

    return ",".join(tokens)
