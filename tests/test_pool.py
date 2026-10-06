import pytest

from tor_session_manager import pool as pool_mod
from tor_session_manager.client import TorClient
from tor_session_manager.pool import CircuitPool, PooledCircuit
from tor_session_manager.quality import CircuitHealth


class _FakeSession:
    def __init__(self):
        self.proxies = {}
        self.closed = False

    def close(self):
        self.closed = True


@pytest.fixture
def fake_sessions(monkeypatch):
    """Replace pool.requests.Session with a fake and record instances."""
    created = []

    def _factory():
        s = _FakeSession()
        created.append(s)
        return s

    monkeypatch.setattr(pool_mod.requests, "Session", _factory)
    return created


def _pool(size=3):
    return CircuitPool(TorClient(socks_port=9050), size=size)


def test_build_creates_distinct_lanes(fake_sessions):
    pool = _pool(size=3).build()
    assert len(pool.circuits) == 3
    names = [c.name for c in pool.circuits]
    assert names == ["tsm1", "tsm2", "tsm3"]  # unique, monotonic
    # Each lane's proxy carries its own SOCKS credential.
    for c in pool.circuits:
        assert f"{c.name}:{c.name}@127.0.0.1:9050" in c.session.proxies["https"]


def test_benchmark_populates_health_and_exit_ip(fake_sessions, monkeypatch):
    pool = _pool(size=2).build()
    # Deterministic per-lane metrics keyed by lane order.
    latencies = {"tsm1": 30.0, "tsm2": 10.0}
    ips = {"tsm1": "1.1.1.1", "tsm2": "2.2.2.2"}

    def fake_latency(session, url, timeout, samples=3):
        name = session.proxies["https"].split("://")[1].split(":")[0]
        return latencies[name]

    monkeypatch.setattr(pool_mod, "measure_latency", fake_latency)
    monkeypatch.setattr(pool_mod, "measure_throughput", lambda s, u, t: 500.0)
    monkeypatch.setattr(
        pool_mod,
        "fetch_ip_with_fallback",
        lambda s, t: ips[s.proxies["https"].split("://")[1].split(":")[0]],
    )

    pool.benchmark(samples=2)
    by_name = {c.name: c for c in pool.circuits}
    assert by_name["tsm1"].health.latency_ms == 30.0
    assert by_name["tsm2"].health.latency_ms == 10.0
    assert by_name["tsm1"].exit_ip == "1.1.1.1"
    assert by_name["tsm2"].health.samples == 2


def test_benchmark_tolerates_failed_metric(fake_sessions, monkeypatch):
    pool = _pool(size=1).build()

    def _boom(*a, **k):
        raise RuntimeError("down")

    monkeypatch.setattr(pool_mod, "measure_latency", lambda s, u, t, samples=3: 12.0)
    monkeypatch.setattr(pool_mod, "measure_throughput", _boom)
    monkeypatch.setattr(pool_mod, "fetch_ip_with_fallback", _boom)

    pool.benchmark()
    c = pool.circuits[0]
    assert c.health.latency_ms == 12.0
    assert c.health.throughput_kbps is None
    assert c.exit_ip is None


def test_ranked_and_fastest_order_by_latency(fake_sessions):
    pool = _pool(size=3).build()
    pool.circuits[0].health = CircuitHealth(latency_ms=30.0)
    pool.circuits[1].health = CircuitHealth(latency_ms=None)  # no metric -> last
    pool.circuits[2].health = CircuitHealth(latency_ms=10.0)

    ranked = pool.ranked()
    assert [c.name for c in ranked] == ["tsm3", "tsm1", "tsm2"]
    assert pool.fastest().name == "tsm3"


def test_ranked_throughput_tiebreak(fake_sessions):
    pool = _pool(size=2).build()
    pool.circuits[0].health = CircuitHealth(latency_ms=10.0, throughput_kbps=100.0)
    pool.circuits[1].health = CircuitHealth(latency_ms=10.0, throughput_kbps=900.0)
    assert pool.fastest().name == "tsm2"  # higher throughput wins the tie


def test_pin_fastest_exposes_proxies(fake_sessions):
    pool = _pool(size=2).build()
    pool.circuits[0].health = CircuitHealth(latency_ms=50.0)
    pool.circuits[1].health = CircuitHealth(latency_ms=5.0)

    pinned = pool.pin_fastest()
    assert pinned.name == "tsm2"
    assert pool.pinned_proxies == pinned.proxies
    assert "tsm2:tsm2@" in pool.pinned_proxies["https"]


def test_pinned_proxies_none_when_unpinned(fake_sessions):
    pool = _pool(size=1).build()
    assert pool.pinned_proxies is None


def test_drop_replaces_lane_and_closes_old(fake_sessions):
    pool = _pool(size=2).build()
    old = pool.circuits[0]
    replacement = pool.drop(old)
    assert old.session.closed is True
    assert old not in pool.circuits
    assert replacement in pool.circuits
    assert replacement.name == "tsm3"  # fresh credential


def test_drop_clears_pin_when_dropping_pinned(fake_sessions):
    pool = _pool(size=2).build()
    pool.circuits[0].health = CircuitHealth(latency_ms=5.0)
    pool.circuits[1].health = CircuitHealth(latency_ms=50.0)
    pinned = pool.pin_fastest()
    pool.drop(pinned)
    assert pool.pinned is None


def test_drop_foreign_circuit_raises(fake_sessions):
    pool = _pool(size=1).build()
    foreign = PooledCircuit(name="x", session=_FakeSession())
    with pytest.raises(ValueError):
        pool.drop(foreign)


def test_prune_keeps_best(fake_sessions):
    pool = _pool(size=3).build()
    pool.circuits[0].health = CircuitHealth(latency_ms=30.0)
    pool.circuits[1].health = CircuitHealth(latency_ms=10.0)
    pool.circuits[2].health = CircuitHealth(latency_ms=20.0)
    dropped = [pool.circuits[0], pool.circuits[2]]

    pool.prune(keep=1)
    assert [c.name for c in pool.circuits] == ["tsm2"]
    assert all(c.session.closed for c in dropped)


def test_close_and_context_manager(fake_sessions):
    with _pool(size=2).build() as pool:
        sessions = [c.session for c in pool.circuits]
    assert all(s.closed for s in sessions)
    assert pool.circuits == []


def test_client_circuit_pool_factory(fake_sessions):
    client = TorClient(socks_port=9150)
    pool = client.circuit_pool(size=2)
    assert isinstance(pool, CircuitPool)
    assert pool.size == 2
    assert pool.client is client
