import time
from types import SimpleNamespace

import pytest
import requests

from tor_session_manager.client import TorClient, rotate_and_get_ip
from tor_session_manager.exceptions import IPFetchError, TorConnectionError


class _FakeController:
    def __init__(self, bootstrap_status: str = "PROGRESS=100"):
        self._bootstrap_status = bootstrap_status
        self.signals = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def authenticate(self, password=None):
        return None

    def get_info(self, key: str):
        assert key == "status/bootstrap-phase"
        return self._bootstrap_status

    def signal(self, sig):
        self.signals.append(sig)


def test_is_ready_true(monkeypatch):
    def fake_from_port(port):
        return _FakeController("NOTICE BOOTSTRAP PROGRESS=100 TAG=done")

    monkeypatch.setattr(
        "tor_session_manager.client.Controller.from_port", fake_from_port
    )

    client = TorClient()
    assert client.is_ready() is True


def test_is_ready_false_when_not_bootstrapped(monkeypatch):
    def fake_from_port(port):
        return _FakeController("NOTICE BOOTSTRAP PROGRESS=50 TAG=loading")

    monkeypatch.setattr(
        "tor_session_manager.client.Controller.from_port", fake_from_port
    )

    client = TorClient()
    assert client.is_ready() is False


def test_rotate_sends_newnym_and_sleeps(monkeypatch):
    controller = _FakeController()

    def fake_from_port(port):
        return controller

    slept = {"seconds": None}

    def fake_sleep(seconds):
        slept["seconds"] = seconds

    monkeypatch.setattr(
        "tor_session_manager.client.Controller.from_port", fake_from_port
    )
    monkeypatch.setattr(time, "sleep", fake_sleep)

    client = TorClient(rotate_delay=1.23)
    client.rotate()

    # We don't want to import stem.Signal in tests; just assert we called .signal once
    assert len(controller.signals) == 1
    assert slept["seconds"] == pytest.approx(1.23)


def test_get_ip_success(monkeypatch):
    class _Resp:
        def raise_for_status(self):
            return None

        def json(self):
            return {"ip": "1.2.3.4"}

    class _Session:
        def __init__(self):
            self.closed = False

        def get(self, url, timeout):
            assert url == TorClient.IP_CHECK_URL
            assert timeout == TorClient.IP_CHECK_TIMEOUT
            return _Resp()

        def close(self):
            self.closed = True

    monkeypatch.setattr("tor_session_manager.client.requests.Session", _Session)

    client = TorClient()
    assert client.get_ip() == "1.2.3.4"


def test_get_ip_raises_ipfetcherror_on_request_exception(monkeypatch):
    class _Session:
        def get(self, url, timeout):
            raise requests.RequestException("boom")

        def close(self):
            pass

    monkeypatch.setattr("tor_session_manager.client.requests.Session", _Session)

    client = TorClient()
    with pytest.raises(IPFetchError):
        client.get_ip()


def test_rotate_and_get_ip_integration_with_mocks(monkeypatch):
    # Ensure the convenience function wires things together.
    controller = _FakeController("PROGRESS=100")

    def fake_from_port(port):
        return controller

    monkeypatch.setattr(
        "tor_session_manager.client.Controller.from_port", fake_from_port
    )

    class _Resp:
        def raise_for_status(self):
            return None

        def json(self):
            return {"ip": "9.9.9.9"}

    class _Session:
        def get(self, url, timeout):
            return _Resp()

        def close(self):
            pass

    monkeypatch.setattr("tor_session_manager.client.requests.Session", _Session)
    monkeypatch.setattr(time, "sleep", lambda s: None)

    assert rotate_and_get_ip() == "9.9.9.9"
    assert len(controller.signals) == 1
