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
        pass

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
