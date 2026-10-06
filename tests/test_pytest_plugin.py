from tor_session_manager import pytest_plugin
from tor_session_manager.client import TorClient


def test_plugin_defines_tor_client_fixture():
    # The fixture is registered via the pytest11 entry point; here we just
    # verify the module exposes it and its wrapped function is callable.
    assert hasattr(pytest_plugin, "tor_client")
    assert callable(pytest_plugin.tor_client.__wrapped__)


def test_tor_client_fixture_skips_when_not_ready(monkeypatch):
    import pytest

    monkeypatch.setattr(TorClient, "is_ready", lambda self: False)
    gen = pytest_plugin.tor_client.__wrapped__()
    with pytest.raises(pytest.skip.Exception):
        next(gen)
