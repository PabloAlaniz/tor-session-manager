import pytest

from tor_session_manager.blocking import detect_block
from tor_session_manager.client import TorClient
from tor_session_manager.exceptions import BlockedResponseError


class _Resp:
    def __init__(self, status_code=200, headers=None, text=""):
        self.status_code = status_code
        self.headers = headers or {}
        self.text = text


# --- detect_block ------------------------------------------------------------


def test_detect_block_clean_200():
    assert detect_block(_Resp(200, text="<html>hello</html>")) is None


def test_detect_block_403():
    assert detect_block(_Resp(403)) == "http_403"


def test_detect_block_429_rate_limited():
    assert detect_block(_Resp(429)) == "http_429_rate_limited"


def test_detect_block_cloudflare_503():
    resp = _Resp(503, headers={"Server": "cloudflare"})
    assert detect_block(resp) == "cloudflare_503"


def test_detect_block_challenge_body():
    resp = _Resp(200, text="<title>Just a Moment...</title>")
    assert detect_block(resp) == "challenge:just a moment..."


def test_detect_block_captcha_marker():
    resp = _Resp(200, text='<div class="g-recaptcha"></div>')
    assert detect_block(resp) == "challenge:g-recaptcha"


def test_detect_block_custom_statuses():
    # 418 is not a default block status, but can be added.
    assert detect_block(_Resp(418)) is None
    assert detect_block(_Resp(418), statuses={418}) == "http_418"


def test_detect_block_custom_markers():
    resp = _Resp(200, text="you shall not pass")
    assert detect_block(resp, markers=("you shall not pass",)) == (
        "challenge:you shall not pass"
    )


def test_detect_block_tolerates_missing_body():
    class _NoText:
        status_code = 200
        headers = {}

        @property
        def text(self):
            raise RuntimeError("no body")

    assert detect_block(_NoText()) is None


# --- request -----------------------------------------------------------------


def test_request_uses_tor_session():
    class _Session:
        def __init__(self):
            self.called = None

        def request(self, method, url, timeout, **kwargs):
            self.called = (method, url, timeout)
            return _Resp(200, text="via-tor")

    client = TorClient()
    client._session = _Session()
    resp = client.request("http://x", method="POST")
    assert resp.text == "via-tor"
    assert client._session.called == ("POST", "http://x", TorClient.IP_CHECK_TIMEOUT)


# --- request: header rotation + pacing (Sprint 9) ----------------------------


class _RecordingSession:
    def __init__(self, status=200):
        self.status = status
        self.last_headers = None

    def request(self, method, url, timeout, **kwargs):
        self.last_headers = kwargs.get("headers")
        return _Resp(self.status)


def test_request_injects_rotated_headers():
    client = TorClient(rotate_headers=True)
    client._session = _RecordingSession()
    client.request("http://x")
    assert "User-Agent" in client._session.last_headers


def test_request_does_not_override_explicit_headers():
    client = TorClient(rotate_headers=True)
    client._session = _RecordingSession()
    client.request("http://x", headers={"User-Agent": "MINE"})
    assert client._session.last_headers == {"User-Agent": "MINE"}


def test_request_paces_and_records(monkeypatch):
    client = TorClient(rate_limit=1.0)
    client._session = _RecordingSession(status=429)
    calls = {"acquire": [], "record": []}
    monkeypatch.setattr(
        client._rate_limiter, "acquire", lambda host: calls["acquire"].append(host)
    )
    monkeypatch.setattr(
        client._rate_limiter,
        "record",
        lambda host, status: calls["record"].append((host, status)),
    )
    client.request("http://example.com/path")
    assert calls["acquire"] == ["example.com"]
    assert calls["record"] == [("example.com", 429)]


# --- request_with_retry ------------------------------------------------------


def _client_with_responses(monkeypatch, responses):
    """A client whose .request() yields the given responses in order, counting rotations."""
    client = TorClient(rotate_delay=0)
    it = iter(responses)
    monkeypatch.setattr(TorClient, "request", lambda self, url, **kw: next(it))
    rotations = {"n": 0}

    def _rotate(self):
        rotations["n"] += 1

    monkeypatch.setattr(TorClient, "rotate", _rotate)
    return client, rotations


def test_request_with_retry_returns_first_clean(monkeypatch):
    client, rotations = _client_with_responses(monkeypatch, [_Resp(200, text="ok")])
    resp = client.request_with_retry("http://x")
    assert resp.text == "ok"
    assert rotations["n"] == 0


def test_request_with_retry_rotates_until_clean(monkeypatch):
    client, rotations = _client_with_responses(
        monkeypatch,
        [_Resp(403), _Resp(200, text="finally")],
    )
    resp = client.request_with_retry("http://x", max_rotations=3)
    assert resp.text == "finally"
    assert rotations["n"] == 1


def test_request_with_retry_raises_when_always_blocked(monkeypatch):
    client, rotations = _client_with_responses(
        monkeypatch,
        [_Resp(403), _Resp(403), _Resp(403)],  # max_rotations=2 -> 3 attempts
    )
    with pytest.raises(BlockedResponseError) as exc:
        client.request_with_retry("http://x", max_rotations=2)
    assert exc.value.reason == "http_403"
    assert exc.value.response is not None
    assert rotations["n"] == 2


# --- is_exit_blocklisted -----------------------------------------------------


def test_is_exit_blocklisted_reports_reason(monkeypatch):
    client = TorClient()
    monkeypatch.setattr(TorClient, "request", lambda self, url, **kw: _Resp(403))
    assert client.is_exit_blocklisted("http://x") == "http_403"


def test_is_exit_blocklisted_none_when_ok(monkeypatch):
    client = TorClient()
    monkeypatch.setattr(
        TorClient, "request", lambda self, url, **kw: _Resp(200, text="fine")
    )
    assert client.is_exit_blocklisted("http://x") is None
