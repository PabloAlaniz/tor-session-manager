"""Offline routing regression tests: never contact Tor or external endpoints."""

import asyncio
import socket

import pytest
import requests
from requests.adapters import BaseAdapter

from tor_session_manager.client import TorClient
from tor_session_manager.exceptions import AllIPCheckersFailedError


@pytest.fixture(autouse=True)
def no_external_dns(monkeypatch):
    original = socket.getaddrinfo

    def local_only(host, *args, **kwargs):
        assert host == "127.0.0.1", "Unexpected local DNS lookup: %s" % host
        return original(host, *args, **kwargs)

    monkeypatch.setattr(socket, "getaddrinfo", local_only)


@pytest.fixture(params=["", "*", "target.invalid"])
def hostile_environment(monkeypatch, request):
    for name in (
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "http_proxy",
        "https_proxy",
        "all_proxy",
    ):
        monkeypatch.setenv(name, "http://environment-proxy.invalid:8080")
    monkeypatch.setenv("NO_PROXY", request.param)
    monkeypatch.setenv("no_proxy", request.param)


@pytest.mark.parametrize("lane", [False, True])
@pytest.mark.parametrize("scheme", ["http", "https"])
def test_environment_cannot_replace_tor_even_on_redirect(
    hostile_environment, lane, scheme
):
    client = TorClient(socks_port=19050)
    session = (
        client.circuit_pool(1)._new_lane().session if lane else client._create_session()
    )
    calls = []

    class Adapter(BaseAdapter):
        def send(self, request, **kwargs):
            calls.append(kwargs["proxies"])
            response = requests.Response()
            response.status_code = 302 if len(calls) == 1 else 200
            response.headers["Location"] = f"{scheme}://redirect.invalid/final"
            response.url = request.url
            response.request = request
            response._content = b""
            return response

        def close(self):
            pass

    session.mount(f"{scheme}://", Adapter())
    try:
        assert session.trust_env is False
        assert session.get(f"{scheme}://target.invalid/start").status_code == 200
        assert len(calls) == 2
        assert all(proxies == session.proxies for proxies in calls)
        assert all(value.startswith("socks5h://") for value in session.proxies.values())
    finally:
        session.close()


@pytest.mark.parametrize("scheme", ["http", "https"])
def test_unavailable_tor_never_connects_to_target_or_env_proxy(
    monkeypatch, hostile_environment, scheme
):
    connections = []

    def refused(sock, address):
        connections.append(address)
        raise ConnectionRefusedError("offline SOCKS proxy")

    monkeypatch.setattr(socket.socket, "connect", refused)
    with pytest.raises(requests.ConnectionError):
        TorClient(socks_port=19050).request(f"{scheme}://target.invalid/", timeout=0.1)
    assert connections
    assert all(address == ("127.0.0.1", 19050) for address in connections)


def test_ip_checker_fallback_never_falls_back_to_direct(
    monkeypatch, hostile_environment
):
    connections = []

    def refused(sock, address):
        connections.append(address)
        raise ConnectionRefusedError("offline SOCKS proxy")

    monkeypatch.setattr(socket.socket, "connect", refused)
    with pytest.raises(AllIPCheckersFailedError):
        TorClient(socks_port=19050).get_ip()
    assert len(connections) >= 2
    assert all(address == ("127.0.0.1", 19050) for address in connections)


@pytest.mark.parametrize(
    "proxies", [None, {}, {"http": None}, {"https": "http://other.invalid"}]
)
def test_per_request_proxy_overrides_rejected(proxies):
    with pytest.raises(ValueError, match="proxy overrides"):
        TorClient().request("https://target.invalid", proxies=proxies)


def test_async_environment_policy(monkeypatch):
    aio = pytest.importorskip("tor_session_manager.aio")
    seen = {}
    monkeypatch.setattr(
        aio.ProxyConnector,
        "from_url",
        lambda url, **kwargs: seen.update(url=url, **kwargs),
    )
    monkeypatch.setattr(
        aio.aiohttp, "ClientSession", lambda **kwargs: seen.update(**kwargs)
    )
    aio.TorClientAsync(socks_port=19050)._new_session()
    assert seen == {
        "url": "socks5://127.0.0.1:19050",
        "rdns": True,
        "connector": None,
        "trust_env": False,
    }


@pytest.mark.parametrize("key", ["proxy", "proxy_auth"])
def test_async_proxy_overrides_rejected(key):
    aio = pytest.importorskip("tor_session_manager.aio")
    with pytest.raises(ValueError, match="proxy overrides"):
        asyncio.run(
            aio.TorClientAsync().request("https://target.invalid", **{key: None})
        )


def test_pool_unavailable_tor_never_connects_direct(monkeypatch, hostile_environment):
    connections = []

    def refused(sock, address):
        connections.append(address)
        raise ConnectionRefusedError("offline SOCKS proxy")

    monkeypatch.setattr(socket.socket, "connect", refused)
    with TorClient(socks_port=19050).circuit_pool(1)._new_lane().session as session:
        with pytest.raises(requests.ConnectionError):
            session.get("https://target.invalid", timeout=0.1)
    assert connections
    assert all(address == ("127.0.0.1", 19050) for address in connections)


def test_async_unavailable_tor_never_connects_direct(monkeypatch, hostile_environment):
    aio = pytest.importorskip("tor_session_manager.aio")
    connections = []

    def refused(sock, address):
        connections.append(address)
        raise ConnectionRefusedError("offline SOCKS proxy")

    monkeypatch.setattr(socket.socket, "connect", refused)

    async def run():
        client = aio.TorClientAsync(socks_port=19050)
        client._session = client._new_session()
        try:
            with pytest.raises(
                pytest.importorskip("aiohttp_socks").ProxyConnectionError
            ):
                await client.request("https://target.invalid", timeout=0.1)
        finally:
            await client._session.close()

    asyncio.run(run())
    assert connections
    assert all(address == ("127.0.0.1", 19050) for address in connections)


def test_implicit_credentials_and_ca_bundle_are_disabled(monkeypatch):
    monkeypatch.setenv("REQUESTS_CA_BUNDLE", "/environment/ca.pem")
    monkeypatch.setenv("CURL_CA_BUNDLE", "/environment/curl-ca.pem")

    def unexpected_netrc(*args, **kwargs):
        pytest.fail("Implicit .netrc credentials must not be loaded")

    monkeypatch.setattr(requests.sessions, "get_netrc_auth", unexpected_netrc)
    session = TorClient()._create_session()
    try:
        prepared = session.prepare_request(
            requests.Request("GET", "https://target.invalid")
        )
        assert "Authorization" not in prepared.headers
        settings = session.merge_environment_settings(
            prepared.url, {}, None, None, None
        )
        assert settings["verify"] is True
        explicit = session.merge_environment_settings(
            prepared.url, {}, None, "/explicit/ca.pem", None
        )
        assert explicit["verify"] == "/explicit/ca.pem"
    finally:
        session.close()
