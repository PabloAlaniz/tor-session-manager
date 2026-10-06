import pytest

from tor_session_manager.client import TorClient
from tor_session_manager.exceptions import IPFetchError, TorSessionError
from tor_session_manager.exits import format_exit_nodes, normalize_country


class _FakeController:
    """Fake stem controller that records set_conf/reset_conf/signal calls."""

    def __init__(self):
        self.conf = {}
        self.reset = []
        self.signals = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def authenticate(self, password=None):
        return None

    def set_conf(self, param, value):
        self.conf[param] = value

    def reset_conf(self, *params):
        self.reset.extend(params)

    def signal(self, sig):
        self.signals.append(sig)


def _client_with(controller, monkeypatch, ip="1.2.3.4"):
    client = TorClient(rotate_delay=0)
    client._get_controller = lambda: controller  # type: ignore[assignment]
    monkeypatch.setattr(TorClient, "get_ip", lambda self: ip)
    return client


# --- pure helpers ------------------------------------------------------------


def test_normalize_country_valid():
    assert normalize_country("US") == "us"
    assert normalize_country(" de ") == "de"


@pytest.mark.parametrize("bad", ["usa", "u", "", "1a", None])
def test_normalize_country_invalid(bad):
    with pytest.raises(ValueError):
        normalize_country(bad)


def test_format_exit_nodes_country():
    assert format_exit_nodes(countries=["us"]) == "{us}"


def test_format_exit_nodes_fingerprint_gets_dollar():
    assert format_exit_nodes(fingerprints=["ABC"]) == "$ABC"
    assert format_exit_nodes(fingerprints=["$ABC"]) == "$ABC"


def test_format_exit_nodes_combined():
    assert (
        format_exit_nodes(countries=["us", "DE"], fingerprints=["ABC"])
        == "{us},{de},$ABC"
    )


def test_format_exit_nodes_empty_raises():
    with pytest.raises(ValueError):
        format_exit_nodes()


# --- TorClient exit selection ------------------------------------------------


def test_set_exit_country_sets_conf(monkeypatch):
    controller = _FakeController()
    client = _client_with(controller, monkeypatch)
    client.set_exit_country("us")
    assert controller.conf["ExitNodes"] == "{us}"
    assert controller.conf["StrictNodes"] == "1"


def test_set_exit_nodes_non_strict(monkeypatch):
    controller = _FakeController()
    client = _client_with(controller, monkeypatch)
    client.set_exit_nodes(countries=["de"], strict=False)
    assert controller.conf["StrictNodes"] == "0"


def test_reset_exit_nodes(monkeypatch):
    controller = _FakeController()
    client = _client_with(controller, monkeypatch)
    client.reset_exit_nodes()
    assert controller.reset == ["ExitNodes", "StrictNodes"]


def test_new_circuit_applies_constraint_rotates_and_returns_ip(monkeypatch):
    controller = _FakeController()
    client = _client_with(controller, monkeypatch, ip="9.9.9.9")
    result = client.new_circuit(exit_country="nl")
    assert controller.conf["ExitNodes"] == "{nl}"
    assert len(controller.signals) == 1  # rotated
    assert result == "9.9.9.9"


def test_new_circuit_no_verify_returns_none(monkeypatch):
    controller = _FakeController()
    client = _client_with(controller, monkeypatch)
    assert client.new_circuit(exit_country="nl", verify=False) is None


def test_new_circuit_raises_when_exit_unusable(monkeypatch):
    controller = _FakeController()
    client = TorClient(rotate_delay=0)
    client._get_controller = lambda: controller  # type: ignore[assignment]

    def _boom(self):
        raise IPFetchError("no route")

    monkeypatch.setattr(TorClient, "get_ip", _boom)

    with pytest.raises(TorSessionError):
        client.new_circuit(exit_country="zz")


def test_pinned_exit_sets_and_always_resets(monkeypatch):
    controller = _FakeController()
    client = _client_with(controller, monkeypatch)

    with client.pinned_exit(countries=["de"]):
        assert controller.conf["ExitNodes"] == "{de}"
        assert len(controller.signals) == 1  # rotated inside

    assert controller.reset == ["ExitNodes", "StrictNodes"]


def test_pinned_exit_resets_on_exception(monkeypatch):
    controller = _FakeController()
    client = _client_with(controller, monkeypatch)

    with pytest.raises(RuntimeError):
        with client.pinned_exit(countries=["de"]):
            raise RuntimeError("boom")

    assert controller.reset == ["ExitNodes", "StrictNodes"]
