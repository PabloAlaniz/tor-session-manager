import pytest

from tor_session_manager import quality
from tor_session_manager.client import TorClient
from tor_session_manager.quality import (
    CircuitHealth,
    measure_latency,
    measure_throughput,
)


class _Resp:
    def __init__(self, content=b"", raise_status=False):
        self.content = content
        self._raise_status = raise_status

    def raise_for_status(self):
        if self._raise_status:
            raise RuntimeError("bad status")


class _Session:
    def __init__(self, response=None, on_get=None):
        self._response = response or _Resp()
        self._on_get = on_get
        self.calls = 0

    def get(self, url, timeout=None):
        self.calls += 1
        if self._on_get is not None:
            return self._on_get(url)
        return self._response

    def close(self):
        pass


def _perf_counter_sequence(monkeypatch, values):
    """Patch quality.time.perf_counter to yield the given values in order."""
    it = iter(values)
    monkeypatch.setattr(quality.time, "perf_counter", lambda: next(it))


# --- measure_latency ---------------------------------------------------------


def test_measure_latency_returns_median_ms(monkeypatch):
    # Three samples: start/stop pairs -> deltas 0.010, 0.030, 0.020 s.
    _perf_counter_sequence(
        monkeypatch,
        [0.0, 0.010, 1.0, 1.030, 2.0, 2.020],
    )
    session = _Session(_Resp())
    latency = measure_latency(session, "http://x", timeout=5, samples=3)
    assert latency == pytest.approx(20.0)  # median of 10, 30, 20 ms
    assert session.calls == 3


def test_measure_latency_rejects_zero_samples():
    with pytest.raises(ValueError):
        measure_latency(_Session(), "http://x", timeout=5, samples=0)


# --- measure_throughput ------------------------------------------------------


def test_measure_throughput_kbps(monkeypatch):
    # 102400 bytes in 0.1s -> 102400 / 0.1 / 1024 = 1000 KB/s
    _perf_counter_sequence(monkeypatch, [0.0, 0.1])
    session = _Session(_Resp(content=b"x" * 102400))
    kbps = measure_throughput(session, "http://x", timeout=5)
    assert kbps == pytest.approx(1000.0)


def test_measure_throughput_guards_zero_elapsed(monkeypatch):
    _perf_counter_sequence(monkeypatch, [5.0, 5.0])  # zero elapsed
    session = _Session(_Resp(content=b"x" * 1024))
    assert measure_throughput(session, "http://x", timeout=5) == 0.0


# --- CircuitHealth -----------------------------------------------------------


def test_circuit_health_ok_flag():
    assert CircuitHealth(latency_ms=10.0).ok is True
    assert CircuitHealth(throughput_kbps=5.0).ok is True
    assert CircuitHealth().ok is False


# --- TorClient.benchmark -----------------------------------------------------


def test_benchmark_combines_metrics(monkeypatch):
    client = TorClient()
    monkeypatch.setattr(TorClient, "measure_latency", lambda self, **kw: 42.0)
    monkeypatch.setattr(TorClient, "measure_throughput", lambda self, **kw: 500.0)
    monkeypatch.setattr(quality.time, "time", lambda: 1234.5, raising=False)

    health = client.benchmark(samples=4)
    assert isinstance(health, CircuitHealth)
    assert health.latency_ms == 42.0
    assert health.throughput_kbps == 500.0
    assert health.samples == 4
    assert health.measured_at is not None
    assert health.ok is True


def test_client_measure_latency_uses_session(monkeypatch):
    _perf_counter_sequence(monkeypatch, [0.0, 0.05])  # 50 ms, single sample
    client = TorClient()
    client._session = _Session(_Resp())
    assert client.measure_latency(samples=1) == pytest.approx(50.0)


def test_client_measure_throughput_uses_session(monkeypatch):
    _perf_counter_sequence(monkeypatch, [0.0, 0.1])
    client = TorClient()
    client._session = _Session(_Resp(content=b"x" * 102400))
    assert client.measure_throughput() == pytest.approx(1000.0)


def test_benchmark_tolerates_failed_metric(monkeypatch):
    client = TorClient()
    monkeypatch.setattr(TorClient, "measure_latency", lambda self, **kw: 15.0)

    def _boom(self, **kw):
        raise RuntimeError("throughput endpoint down")

    monkeypatch.setattr(TorClient, "measure_throughput", _boom)

    health = client.benchmark()
    assert health.latency_ms == 15.0
    assert health.throughput_kbps is None
    assert health.ok is True  # still ok because latency resolved
