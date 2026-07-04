import pytest

from tor_session_manager.circuits import CircuitInfo, RelayInfo, parse_circuit
from tor_session_manager.client import TorClient
from tor_session_manager.exceptions import TorSessionError


class _FakeCircuit:
    def __init__(
        self,
        cid,
        status="BUILT",
        purpose="GENERAL",
        path=None,
        created="2026-07-04T00:00:00",
        build_flags=("IS_INTERNAL",),
    ):
        self.id = cid
        self.status = status
        self.purpose = purpose
        self.path = path or []
        self.created = created
        self.build_flags = build_flags


class _FakeController:
    """Fake stem controller for circuit introspection."""

    def __init__(self, circuits=None, network_status=None, countries=None):
        self._circuits = circuits or []
        # network_status: dict[fingerprint] -> object with .address/.nickname
        self._network_status = network_status or {}
        # countries: dict[address] -> country code (or Exception to raise)
        self._countries = countries or {}

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def authenticate(self, password=None):
        return None

    def get_circuits(self):
        return self._circuits

    def get_network_status(self, fingerprint):
        outcome = self._network_status.get(fingerprint)
        if isinstance(outcome, Exception):
            raise outcome
        if outcome is None:
            raise ValueError("no consensus entry")
        return outcome

    def get_info(self, key):
        assert key.startswith("ip-to-country/")
        address = key.split("/", 1)[1]
        outcome = self._countries.get(address)
        if isinstance(outcome, Exception):
            raise outcome
        if outcome is None:
            raise ValueError("unknown country")
        return outcome


class _Status:
    def __init__(self, address=None, nickname=None):
        self.address = address
        self.nickname = nickname


def _client_with(controller):
    client = TorClient()
    client._get_controller = lambda: controller  # type: ignore[assignment]
    return client


# --- parse_circuit -----------------------------------------------------------


def test_parse_circuit_builds_path_and_marks_exit():
    circuit = _FakeCircuit(
        "1",
        path=[("AAAA", "guard"), ("BBBB", "middle"), ("CCCC", "exitnode")],
    )
    controller = _FakeController(
        network_status={"CCCC": _Status(address="1.2.3.4", nickname="exitnode")},
        countries={"1.2.3.4": "de"},
    )

    info = parse_circuit(controller, circuit)

    assert isinstance(info, CircuitInfo)
    assert [r.fingerprint for r in info.path] == ["AAAA", "BBBB", "CCCC"]
    assert info.exit_relay.fingerprint == "CCCC"
    assert info.exit_relay.address == "1.2.3.4"
    assert info.exit_country == "de"
    # Non-exit hops are not resolved (no address lookup).
    assert info.path[0].address is None


def test_parse_circuit_tolerates_lookup_failures():
    circuit = _FakeCircuit("2", path=[("AAAA", "guard"), ("CCCC", "exit")])
    # No network status / country for the exit -> stays None, no raise.
    controller = _FakeController()

    info = parse_circuit(controller, circuit)

    assert info.exit_relay.fingerprint == "CCCC"
    assert info.exit_relay.address is None
    assert info.exit_country is None


def test_parse_circuit_empty_path_has_no_exit():
    info = parse_circuit(_FakeController(), _FakeCircuit("3", path=[]))
    assert info.exit_relay is None
    assert info.exit_country is None


# --- TorClient methods -------------------------------------------------------


def test_list_circuits_returns_all():
    circuits = [
        _FakeCircuit("1", path=[("AAAA", "a")]),
        _FakeCircuit("2", path=[("BBBB", "b")]),
    ]
    client = _client_with(_FakeController(circuits=circuits))
    result = client.list_circuits()
    assert [c.id for c in result] == ["1", "2"]


def test_get_circuit_info_picks_most_recent_built_general():
    circuits = [
        _FakeCircuit("1", created="2026-07-04T00:00:01", path=[("A", "a")]),
        _FakeCircuit("2", status="EXTENDING", path=[("B", "b")]),
        _FakeCircuit("3", purpose="HS_CLIENT_REND", path=[("C", "c")]),
        _FakeCircuit("4", created="2026-07-04T00:00:09", path=[("D", "d")]),
    ]
    client = _client_with(_FakeController(circuits=circuits))
    info = client.get_circuit_info()
    assert info.id == "4"  # newest BUILT/GENERAL


def test_get_circuit_info_by_id():
    circuits = [
        _FakeCircuit("1", path=[("A", "a")]),
        _FakeCircuit("7", path=[("B", "b")]),
    ]
    client = _client_with(_FakeController(circuits=circuits))
    assert client.get_circuit_info("7").id == "7"


def test_get_circuit_info_unknown_id_raises():
    client = _client_with(
        _FakeController(circuits=[_FakeCircuit("1", path=[("A", "a")])])
    )
    with pytest.raises(TorSessionError):
        client.get_circuit_info("999")


def test_get_circuit_info_raises_when_no_active_circuit():
    circuits = [_FakeCircuit("1", status="EXTENDING", path=[("A", "a")])]
    client = _client_with(_FakeController(circuits=circuits))
    with pytest.raises(TorSessionError):
        client.get_circuit_info()


def test_get_exit_country_of_active_circuit():
    circuits = [
        _FakeCircuit("1", path=[("AAAA", "guard"), ("CCCC", "exit")]),
    ]
    controller = _FakeController(
        circuits=circuits,
        network_status={"CCCC": _Status(address="9.9.9.9")},
        countries={"9.9.9.9": "nl"},
    )
    client = _client_with(controller)
    assert client.get_exit_country() == "nl"
