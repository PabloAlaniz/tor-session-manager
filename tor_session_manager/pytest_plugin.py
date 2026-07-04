"""
Pytest plugin: a ``tor_client`` fixture.

Registered via the ``pytest11`` entry point, so installing the package makes the
fixture available in any test suite. The fixture skips the test if Tor is not
running/ready, so suites don't hard-fail in environments without Tor.
"""

import pytest

from .client import TorClient


@pytest.fixture
def tor_client():
    """Yield a ready :class:`TorClient`, or skip if Tor is unavailable."""
    client = TorClient()
    if not client.is_ready():
        pytest.skip("Tor is not running/ready; skipping Tor-dependent test")
    with client:
        yield client
