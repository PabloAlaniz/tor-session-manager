import time

import pytest
import requests

from tor_session_manager.client import TorClient, _retry_with_backoff
from tor_session_manager.exceptions import (
    AllIPCheckersFailedError,
    TorSessionError,
)
from tor_session_manager.ip_checkers import fetch_ip_with_fallback


class _Resp:
    def __init__(self, *, json_data=None, text=None, raise_status=False):
        self._json = json_data
        self.text = text if text is not None else ""
        self._raise_status = raise_status

    def raise_for_status(self):
        if self._raise_status:
            raise requests.HTTPError("bad status")

    def json(self):
        return self._json


class _ScriptedSession:
    """A session whose .get() returns/raises per-URL according to a script."""

    def __init__(self, script):
        # script: dict[url] -> _Resp or Exception instance to raise
        self._script = script
        self.calls = []

    def get(self, url, timeout=None):
        self.calls.append(url)
        outcome = self._script.get(url)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def test_fetch_ip_uses_first_checker():
    session = _ScriptedSession(
        {"https://api.ipify.org/?format=json": _Resp(json_data={"ip": "1.2.3.4"})}
    )
    assert fetch_ip_with_fallback(session, timeout=5) == "1.2.3.4"
    # Only the first checker should have been queried.
    assert session.calls == ["https://api.ipify.org/?format=json"]


def test_fetch_ip_falls_back_to_second_checker():
    session = _ScriptedSession(
        {
            "https://api.ipify.org/?format=json": requests.ConnectionError("down"),
            "https://ifconfig.me/ip": _Resp(text="5.6.7.8\n"),
        }
    )
    assert fetch_ip_with_fallback(session, timeout=5) == "5.6.7.8"
    assert session.calls[:2] == [
        "https://api.ipify.org/?format=json",
        "https://ifconfig.me/ip",
    ]


def test_fetch_ip_all_fail_raises():
    session = _ScriptedSession({})  # every URL -> None -> AttributeError-ish failure

    def always_raise(url, timeout=None):
        session.calls.append(url)
        raise requests.ConnectionError("no network")

    session.get = always_raise  # type: ignore[assignment]

    with pytest.raises(AllIPCheckersFailedError):
        fetch_ip_with_fallback(session, timeout=5)
    # All four checkers attempted.
    assert len(session.calls) == 4


def test_fetch_ip_rejects_garbage_and_falls_through():
    session = _ScriptedSession(
        {
            "https://api.ipify.org/?format=json": _Resp(json_data={"ip": "not-an-ip"}),
            "https://ifconfig.me/ip": _Resp(text="9.9.9.9"),
        }
    )
    assert fetch_ip_with_fallback(session, timeout=5) == "9.9.9.9"


def test_retry_with_backoff_succeeds_after_failures(monkeypatch):
    monkeypatch.setattr(time, "sleep", lambda s: None)
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise ValueError("transient")
        return "ok"

    assert _retry_with_backoff(flaky, attempts=4, base_delay=0.01) == "ok"
    assert calls["n"] == 3


def test_retry_with_backoff_reraises_last(monkeypatch):
    monkeypatch.setattr(time, "sleep", lambda s: None)

    def always_fail():
        raise ValueError("nope")

    with pytest.raises(ValueError):
        _retry_with_backoff(always_fail, attempts=3, base_delay=0.01)


class _FakeController:
    def __init__(self):
        self.signals = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def authenticate(self, password=None):
        return None

    def get_info(self, key):
        return "PROGRESS=100"

    def signal(self, sig):
        self.signals.append(sig)


def test_wait_for_new_ip_rotates_until_changed(monkeypatch):
    controller = _FakeController()
    monkeypatch.setattr(
        "tor_session_manager.client.Controller.from_port",
        lambda port: controller,
    )
    monkeypatch.setattr(time, "sleep", lambda s: None)

    ips = iter(["1.1.1.1", "1.1.1.1", "2.2.2.2"])
    monkeypatch.setattr(TorClient, "get_ip", lambda self: next(ips))

    client = TorClient(rotate_delay=0)
    # previous_ip captured as 1.1.1.1; first rotate -> 1.1.1.1 (same), second -> 2.2.2.2
    assert client.wait_for_new_ip(max_attempts=5) == "2.2.2.2"
    assert len(controller.signals) == 2


def test_wait_for_new_ip_raises_when_unchanged(monkeypatch):
    controller = _FakeController()
    monkeypatch.setattr(
        "tor_session_manager.client.Controller.from_port",
        lambda port: controller,
    )
    monkeypatch.setattr(time, "sleep", lambda s: None)
    monkeypatch.setattr(TorClient, "get_ip", lambda self: "1.1.1.1")

    client = TorClient(rotate_delay=0)
    with pytest.raises(TorSessionError):
        client.wait_for_new_ip(max_attempts=3)
    assert len(controller.signals) == 3
