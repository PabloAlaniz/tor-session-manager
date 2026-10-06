import json

import pytest

from tor_session_manager import cli
from tor_session_manager.circuits import CircuitInfo, RelayInfo
from tor_session_manager.exceptions import TorSessionError
from tor_session_manager.quality import CircuitHealth


class _FakeClient:
    DEFAULT_CONTROL_PORT = 9051
    DEFAULT_SOCKS_PORT = 9050

    def __init__(self, *args, **kwargs):
        self.password = kwargs.get("password")

    def get_ip(self):
        return "1.2.3.4"

    def wait_for_new_ip(self, *a, **k):
        return "5.6.7.8"

    def get_exit_country(self, *a, **k):
        return "de"

    def is_ready(self):
        return True

    def list_circuits(self):
        return [object(), object()]

    def get_circuit_info(self, *a, **k):
        return CircuitInfo(
            id="1",
            status="BUILT",
            purpose="GENERAL",
            path=[
                RelayInfo(fingerprint="AAAA", nickname="guard"),
                RelayInfo(fingerprint="CCCC", nickname="exit", country="de"),
            ],
        )

    def benchmark(self, *a, **k):
        return CircuitHealth(latency_ms=42.0, throughput_kbps=500.0, samples=3)


@pytest.fixture(autouse=True)
def _patch_client(monkeypatch):
    monkeypatch.setattr(cli, "TorClient", _FakeClient)
    monkeypatch.setattr(cli, "collect_diagnostics", lambda client: _ready_diagnostics())


def _ready_diagnostics():
    return {
        "ready": True,
        "ip": "1.2.3.4",
        "checks": {
            "controller": {"status": "ok"},
            "authentication": {"status": "ok"},
            "bootstrap": {"status": "ok", "progress": 100},
            "socks": {"status": "ok"},
            "connectivity": {"status": "ok"},
        },
    }


def test_cli_ip(capsys):
    assert cli.main(["ip"]) == 0
    assert capsys.readouterr().out.strip() == "1.2.3.4"


def test_cli_ip_json(capsys):
    assert cli.main(["--json", "ip"]) == 0
    assert json.loads(capsys.readouterr().out) == {"ip": "1.2.3.4"}


def test_cli_rotate(capsys):
    assert cli.main(["rotate"]) == 0
    assert capsys.readouterr().out.strip() == "5.6.7.8"


def test_cli_country(capsys):
    assert cli.main(["country"]) == 0
    assert capsys.readouterr().out.strip() == "de"


def test_cli_circuit_human(capsys):
    assert cli.main(["circuit"]) == 0
    out = capsys.readouterr().out
    assert "Circuit 1" in out
    assert "guard -> exit" in out


def test_cli_benchmark_json(capsys):
    assert cli.main(["--json", "benchmark"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["latency_ms"] == 42.0
    assert data["ok"] is True


def test_cli_status_json(capsys):
    assert cli.main(["--json", "status"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["ready"] is True
    assert data["ip"] == "1.2.3.4"
    assert data["exit_country"] == "de"
    assert data["num_circuits"] == 2
    assert data["health"]["latency_ms"] == 42.0


def test_cli_benchmark_human(capsys):
    assert cli.main(["benchmark"]) == 0
    out = capsys.readouterr().out
    assert "latency: 42 ms" in out
    assert "throughput: 500 KB/s" in out


def test_cli_benchmark_human_na(monkeypatch, capsys):
    class _NoMetrics(_FakeClient):
        def benchmark(self, *a, **k):
            return CircuitHealth()  # both None

    monkeypatch.setattr(cli, "TorClient", _NoMetrics)
    assert cli.main(["benchmark"]) == 0
    out = capsys.readouterr().out
    assert "latency: n/a" in out
    assert "throughput: n/a" in out


def test_cli_status_human(capsys):
    assert cli.main(["status"]) == 0
    out = capsys.readouterr().out
    assert "ready: True" in out
    assert "ip: 1.2.3.4" in out
    assert "num_circuits: 2" in out


def test_cli_error_returns_nonzero(monkeypatch, capsys):
    class _Boom(_FakeClient):
        def get_ip(self):
            raise TorSessionError("no tor")

    monkeypatch.setattr(cli, "TorClient", _Boom)
    assert cli.main(["ip"]) == 1
    assert "error:" in capsys.readouterr().err


@pytest.mark.parametrize("command", list(cli._COMMANDS))
@pytest.mark.parametrize("after_command", [False, True])
def test_common_options_before_or_after_command(
    monkeypatch, capsys, command, after_command
):
    received = {}

    class _ConfiguredClient(_FakeClient):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            received.update(kwargs)

    monkeypatch.setattr(cli, "TorClient", _ConfiguredClient)
    options = [
        "--json",
        "--control-port",
        "9151",
        "--socks-port",
        "9150",
        "--password",
        "test",
    ]
    argv = [command] + options if after_command else options + [command]
    assert cli.main(argv) == 0
    json.loads(capsys.readouterr().out)
    assert received == {"control_port": 9151, "socks_port": 9150, "password": "test"}


def test_common_options_can_straddle_command(monkeypatch, capsys):
    received = {}

    class _ConfiguredClient(_FakeClient):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            received.update(kwargs)

    monkeypatch.setattr(cli, "TorClient", _ConfiguredClient)
    assert (
        cli.main(["--json", "--control-port", "9151", "status", "--socks-port", "9150"])
        == 0
    )
    assert json.loads(capsys.readouterr().out)["ready"] is True
    assert received == {"control_port": 9151, "socks_port": 9150, "password": None}


@pytest.mark.parametrize("argv", [["--version"], ["status", "--version"]])
def test_version_option_before_or_after_command(capsys, argv):
    with pytest.raises(SystemExit) as error:
        cli.main(argv)
    assert error.value.code == 0
    assert capsys.readouterr().out.strip() == f"tor-session {cli.__version__}"


@pytest.mark.parametrize("option", ["--socks-port", "--control-port"])
@pytest.mark.parametrize("value", ["0", "-1", "65536", "word"])
def test_invalid_ports_are_argument_errors(capsys, option, value):
    with pytest.raises(SystemExit) as error:
        cli.main(["status", option, value])
    assert error.value.code == 2
    assert "port must be an integer from 1 to 65535" in capsys.readouterr().err


@pytest.mark.parametrize("as_json", [False, True])
def test_status_failure_is_reported_and_nonzero(monkeypatch, capsys, as_json):
    result = _ready_diagnostics()
    result["ready"] = False
    result["ip"] = None
    result["checks"]["bootstrap"] = {
        "status": "failed",
        "progress": 75,
        "message": "Tor is still bootstrapping.",
    }
    monkeypatch.setattr(cli, "collect_diagnostics", lambda client: result)

    class _NoDetails(_FakeClient):
        def benchmark(self):
            pytest.fail("Do not benchmark an unready client")

    monkeypatch.setattr(cli, "TorClient", _NoDetails)
    assert cli.main(["status"] + (["--json"] if as_json else [])) == 1
    output = capsys.readouterr()
    assert output.err == ""
    if as_json:
        data = json.loads(output.out)
        assert data["ready"] is False
        assert data["checks"]["bootstrap"]["progress"] == 75
        assert data["ip"] is None
        assert data["health"] is None
    else:
        assert "ready: False" in output.out
        assert "bootstrap: failed (75% Tor is still bootstrapping.)" in output.out


@pytest.mark.parametrize("as_json", [False, True])
def test_status_optional_detail_errors_are_visible(monkeypatch, capsys, as_json):
    class _PartialClient(_FakeClient):
        def get_exit_country(self):
            raise TorSessionError("country unavailable")

        def list_circuits(self):
            raise TorSessionError("circuits unavailable")

        def benchmark(self):
            raise TorSessionError("benchmark unavailable")

    monkeypatch.setattr(cli, "TorClient", _PartialClient)
    assert cli.main(["status"] + (["--json"] if as_json else [])) == 0
    output = capsys.readouterr()
    if as_json:
        data = json.loads(output.out)
        assert data["ready"] is True
        assert data["exit_country"] is None
        assert data["num_circuits"] is None
        assert data["health"] is None
        assert data["errors"] == {
            "exit_country": "country unavailable",
            "num_circuits": "circuits unavailable",
            "health": "benchmark unavailable",
        }
    else:
        assert "exit_country error: country unavailable" in output.out
        assert "num_circuits error: circuits unavailable" in output.out
        assert "health error: benchmark unavailable" in output.out


def test_status_empty_benchmark_is_reported(monkeypatch, capsys):
    class _NoMetrics(_FakeClient):
        def benchmark(self):
            return CircuitHealth()

    monkeypatch.setattr(cli, "TorClient", _NoMetrics)
    assert cli.main(["status", "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["health"]["ok"] is False
    assert data["errors"]["health"] == "No benchmark metric could be measured."


def test_cli_json_errors_stay_machine_readable_and_redact_password(monkeypatch, capsys):
    class _Boom(_FakeClient):
        def get_ip(self):
            raise TorSessionError("failed with password private-value")

    monkeypatch.setattr(cli, "TorClient", _Boom)
    assert cli.main(["ip", "--json", "--password", "private-value"]) == 1
    output = capsys.readouterr()
    assert output.err == ""
    assert json.loads(output.out) == {"error": "failed with password [redacted]"}
