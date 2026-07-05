"""
Request fingerprint management.

Rotating the exit IP is not enough if every request carries the same
``User-Agent`` and header set — that fingerprint identifies the client across
IP changes. This module offers coherent browser header profiles (the UA and
its companion headers match a real browser) and a rotator to cycle through
them.

Note on TLS/JA3: ``requests`` uses the stdlib ``ssl`` module, so its TLS
handshake (JA3) fingerprint is fixed and cannot be changed here. Header
rotation is the application-level lever this library controls; a JA3-spoofing
transport (e.g. curl_cffi) is out of scope.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class HeaderProfile:
    """A coherent set of request headers mimicking a real browser."""

    name: str
    headers: Dict[str, str]


# Coherent profiles: each User-Agent is paired with headers that browser
# actually sends. Do not mix a Chrome UA with Firefox-style headers.
BROWSER_PROFILES: List[HeaderProfile] = [
    HeaderProfile(
        name="chrome-windows",
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
            ),
            "Accept": (
                "text/html,application/xhtml+xml,application/xml;q=0.9,"
                "image/avif,image/webp,image/apng,*/*;q=0.8"
            ),
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "sec-ch-ua": '"Chromium";v="125", "Not.A/Brand";v="24"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Upgrade-Insecure-Requests": "1",
        },
    ),
    HeaderProfile(
        name="firefox-linux",
        headers={
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64; rv:126.0) "
                "Gecko/20100101 Firefox/126.0"
            ),
            "Accept": (
                "text/html,application/xhtml+xml,application/xml;q=0.9,"
                "image/avif,image/webp,*/*;q=0.8"
            ),
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate, br",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
        },
    ),
    HeaderProfile(
        name="safari-macos",
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4.1 "
                "Safari/605.1.15"
            ),
            "Accept": (
                "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
            ),
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
        },
    ),
]


class HeaderRotator:
    """
    Cycle through browser header profiles.

    Round-robin by default (deterministic and testable). Pass ``shuffle=True``
    (optionally with an ``rng``) to randomize the order once at construction.
    """

    def __init__(self, profiles=None, shuffle: bool = False, rng=None):
        self.profiles: List[HeaderProfile] = list(
            BROWSER_PROFILES if profiles is None else profiles
        )
        if not self.profiles:
            raise ValueError("At least one header profile is required")
        if shuffle:
            import random

            (rng or random).shuffle(self.profiles)
        self._index = 0

    def next(self) -> Dict[str, str]:
        """Return the next profile's headers (a fresh copy each call)."""
        profile = self.profiles[self._index % len(self.profiles)]
        self._index += 1
        return dict(profile.headers)

    @property
    def current_name(self) -> Optional[str]:
        """Name of the profile returned by the most recent ``next()``."""
        if self._index == 0:
            return None
        return self.profiles[(self._index - 1) % len(self.profiles)].name
