import asyncio

import pytest

pytest.importorskip("aiohttp")  # skip cleanly if the [async] extra is absent

from tor_session_manager import aio as aio_mod  # noqa: E402
from tor_session_manager.aio import AsyncResponse, TorClientAsync  # noqa: E402
from tor_session_manager.exceptions import (  # noqa: E402
    AllIPCheckersFailedError,
    BlockedResponseError,
)


class _FakeResp:
    def __init__(self, status=200, headers=None, body=b"", json_data=None):
        self.status = status
        self.headers = headers or {}
        self._body = body
        self._json = json_data

    def raise_for_status(self):
        if self.status >= 400:
            raise RuntimeError(f"HTTP {self.status}")

    async def read(self):
        return self._body

    async def text(self):
        return self._body.decode()

    async def json(self):
        return self._json


class _FakeCM:
    def __init__(self, resp):
        self._resp = resp

    async def __aenter__(self):
        if isinstance(self._resp, Exception):
            raise self._resp
        return self._resp

    async def __aexit__(self, *a):
        return False


class _FakeSession:
    """Fake aiohttp session: routes get/request to a scripted resolver."""

    def __init__(self, resolver):
        self._resolver = resolver
        self.calls = []

    def get(self, url, timeout=None, **kw):
        self.calls.append(url)
        return _FakeCM(self._resolver(url))

    def request(self, method, url, timeout=None, **kw):
        self.calls.append((method, url))
        return _FakeCM(self._resolver(url))

    async def close(self):
        pass


def _client(resolver):
    client = TorClientAsync()
    client._session = _FakeSession(resolver)
    return client


# --- get_ip ------------------------------------------------------------------


def test_get_ip_first_checker_ok():
    # First checker is ipify (json, key "ip").
    client = _client(lambda url: _FakeResp(json_data={"ip": "1.2.3.4"}))
    assert asyncio.run(client.get_ip()) == "1.2.3.4"


def test_get_ip_falls_back_to_second():
    def resolver(url):
        if "ipify" in url:
            return ConnectionError("down")
        return _FakeResp(body=b"5.6.7.8\n")  # ifconfig.me plain text

    assert asyncio.run(_client(resolver).get_ip()) == "5.6.7.8"


def test_get_ip_all_fail_raises():
    client = _client(lambda url: ConnectionError("no net"))
    with pytest.raises(AllIPCheckersFailedError):
        asyncio.run(client.get_ip())


# --- request -----------------------------------------------------------------


def test_request_materializes_response():
    client = _client(
        lambda url: _FakeResp(status=201, headers={"X": "y"}, body=b"hello")
    )
    resp = asyncio.run(client.request("http://x", method="POST"))
    assert isinstance(resp, AsyncResponse)
    assert resp.status_code == 201
    assert resp.headers == {"X": "y"}
    assert resp.text == "hello"
    assert resp.content == b"hello"


def test_require_session_without_context_raises():
    client = TorClientAsync()  # no session set
    with pytest.raises(RuntimeError):
        asyncio.run(client.get_ip())


# --- request_with_retry ------------------------------------------------------


def test_request_with_retry_rotates_until_clean(monkeypatch):
    responses = iter([_FakeResp(status=403), _FakeResp(status=200, body=b"ok")])
    client = _client(lambda url: next(responses))
    rotations = {"n": 0}

    async def _rotate():
        rotations["n"] += 1

    monkeypatch.setattr(client, "rotate", _rotate)

    resp = asyncio.run(client.request_with_retry("http://x", max_rotations=3))
    assert resp.status_code == 200
    assert rotations["n"] == 1


def test_request_with_retry_raises_when_always_blocked(monkeypatch):
    client = _client(lambda url: _FakeResp(status=403))

    async def _rotate():
        pass

    monkeypatch.setattr(client, "rotate", _rotate)

    with pytest.raises(BlockedResponseError) as exc:
        asyncio.run(client.request_with_retry("http://x", max_rotations=2))
    assert exc.value.reason == "http_403"


# --- measurements ------------------------------------------------------------


def test_measure_latency_median(monkeypatch):
    seq = iter([0.0, 0.010, 1.0, 1.030, 2.0, 2.020])
    monkeypatch.setattr(aio_mod.time, "perf_counter", lambda: next(seq))
    client = _client(lambda url: _FakeResp(body=b""))
    latency = asyncio.run(client.measure_latency(samples=3))
    assert latency == pytest.approx(20.0)


def test_measure_throughput_kbps(monkeypatch):
    seq = iter([0.0, 0.1])
    monkeypatch.setattr(aio_mod.time, "perf_counter", lambda: next(seq))
    client = _client(lambda url: _FakeResp(body=b"x" * 102400))
    assert asyncio.run(client.measure_throughput()) == pytest.approx(1000.0)


def test_benchmark_combines(monkeypatch):
    seq = iter([0.0, 0.05, 1.0, 1.1])  # latency sample, then throughput
    monkeypatch.setattr(aio_mod.time, "perf_counter", lambda: next(seq))
    client = _client(lambda url: _FakeResp(body=b"x" * 102400))
    health = asyncio.run(client.benchmark(samples=1))
    assert health.latency_ms == pytest.approx(50.0)
    assert health.throughput_kbps is not None
    assert health.ok is True


# --- control plane -----------------------------------------------------------


def test_rotate_delegates_to_sync(monkeypatch):
    client = _client(lambda url: _FakeResp())
    calls = {"n": 0}
    monkeypatch.setattr(client._sync, "rotate", lambda: calls.__setitem__("n", 1))
    asyncio.run(client.rotate())
    assert calls["n"] == 1


def test_set_exit_country_delegates(monkeypatch):
    client = _client(lambda url: _FakeResp())
    seen = {}
    monkeypatch.setattr(
        client._sync,
        "set_exit_country",
        lambda country, strict: seen.update(country=country, strict=strict),
    )
    asyncio.run(client.set_exit_country("de", strict=False))
    assert seen == {"country": "de", "strict": False}


def test_new_circuit_verify_returns_ip(monkeypatch):
    client = _client(lambda url: _FakeResp())

    async def _set(**kw):
        client._set_called = kw

    async def _rotate():
        client._rotated = True

    async def _get_ip():
        return "7.7.7.7"

    monkeypatch.setattr(client, "set_exit_nodes", _set)
    monkeypatch.setattr(client, "rotate", _rotate)
    monkeypatch.setattr(client, "get_ip", _get_ip)

    ip = asyncio.run(client.new_circuit(exit_country="nl"))
    assert ip == "7.7.7.7"
    assert client._rotated is True


def test_new_circuit_verify_failure_raises(monkeypatch):
    from tor_session_manager.exceptions import TorSessionError

    client = _client(lambda url: _FakeResp())

    async def _rotate():
        pass

    async def _get_ip():
        raise AllIPCheckersFailedError("no route")

    monkeypatch.setattr(client, "rotate", _rotate)
    monkeypatch.setattr(client, "get_ip", _get_ip)

    with pytest.raises(TorSessionError):
        asyncio.run(client.new_circuit(exit_country="zz"))


def test_async_context_manager_lifecycle(monkeypatch):
    client = TorClientAsync()
    monkeypatch.setattr(client._sync, "is_ready", lambda: True)

    async def _run():
        async with client as c:
            assert c._session is not None
        assert client._session is None

    asyncio.run(_run())


def test_async_context_manager_not_ready(monkeypatch):
    from tor_session_manager.exceptions import TorNotReadyError

    client = TorClientAsync()
    monkeypatch.setattr(client._sync, "is_ready", lambda: False)

    async def _run():
        async with client:
            pass

    with pytest.raises(TorNotReadyError):
        asyncio.run(_run())


# --- gather_requests ---------------------------------------------------------


def test_gather_requests_concurrent_and_tolerant():
    def resolver(url):
        if url == "http://bad":
            return RuntimeError("boom")
        return _FakeResp(body=url.encode())

    client = _client(resolver)
    urls = ["http://a", "http://bad", "http://b"]
    results = asyncio.run(client.gather_requests(urls))
    assert results[0].text == "http://a"
    assert results[1] is None  # failed URL -> None, positions aligned
    assert results[2].text == "http://b"


def test_gather_requests_respects_semaphore():
    client = _client(lambda url: _FakeResp(body=b""))
    client.max_concurrency = 2
    # 5 URLs, concurrency 2 — just assert all complete without error.
    results = asyncio.run(client.gather_requests([f"http://{i}" for i in range(5)]))
    assert len(results) == 5
    assert all(r is not None for r in results)
