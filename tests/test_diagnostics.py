import socket
import threading
import time
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from stem import SocketError
from stem.connection import AuthenticationFailure, IncorrectSocketType

from tor_session_manager import diagnostics
from tor_session_manager.exceptions import IPFetchError


@pytest.fixture
def checks(monkeypatch):
    client = SimpleNamespace(
        control_port=9151,
        socks_port=9150,
        password=None,
        get_ip=Mock(return_value="1.2.3.4"),
    )
    controller = Mock()
    controller.get_info.return_value = (
        'NOTICE BOOTSTRAP PROGRESS=100 TAG=done SUMMARY="Done"'
    )
    control_socket = Mock()
    connection = Mock()
    connection.__enter__ = Mock(return_value=connection)
    connection.__exit__ = Mock(return_value=False)
    connection.recv.return_value = b"\x05\x00"
    open_connection = Mock(return_value=connection)
    open_control = Mock(return_value=control_socket)
    create_controller = Mock(return_value=controller)
    monkeypatch.setattr(diagnostics, "_DiagnosticControlPort", open_control)
    monkeypatch.setattr(diagnostics, "Controller", create_controller)
    monkeypatch.setattr(diagnostics.socket, "create_connection", open_connection)
    return SimpleNamespace(
        client=client,
        controller=controller,
        connection=connection,
        open_connection=open_connection,
        open_control=open_control,
        create_controller=create_controller,
    )


def test_ready_requires_all_checks_and_closes_resources(checks):
    result = diagnostics.collect_diagnostics(checks.client)
    assert result["ready"] is True
    assert result["ip"] == "1.2.3.4"
    assert all(check["status"] == "ok" for check in result["checks"].values())
    assert result["checks"]["bootstrap"]["progress"] == 100
    checks.open_control.assert_called_once_with(port=9151)
    checks.controller.authenticate.assert_called_once_with()
    checks.controller.get_info.assert_called_once_with("status/bootstrap-phase")
    checks.controller.close.assert_called_once_with()
    checks.open_connection.assert_called_once_with(("127.0.0.1", 9150), timeout=3.0)
    checks.connection.sendall.assert_called_once_with(b"\x05\x01\x00")
    checks.connection.__exit__.assert_called_once()
    checks.client.get_ip.assert_called_once_with()


def test_unavailable_controller_does_not_hide_working_proxy(checks):
    checks.open_control.side_effect = SocketError("connection refused")
    result = diagnostics.collect_diagnostics(checks.client)
    assert result["ready"] is False
    assert result["checks"]["controller"] == {
        "status": "failed",
        "message": "connection refused",
    }
    assert result["checks"]["authentication"]["status"] == "not_checked"
    assert result["checks"]["bootstrap"]["status"] == "not_checked"
    assert result["checks"]["socks"]["status"] == "ok"
    assert result["checks"]["connectivity"]["status"] == "ok"
    checks.controller.authenticate.assert_not_called()


def test_authentication_failure_is_distinct_and_password_is_redacted(checks):
    checks.client.password = "private-value"
    checks.controller.authenticate.side_effect = AuthenticationFailure(
        "wrong password private-value"
    )
    result = diagnostics.collect_diagnostics(checks.client)
    assert result["ready"] is False
    assert result["checks"]["controller"]["status"] == "ok"
    assert result["checks"]["authentication"] == {
        "status": "failed",
        "message": "wrong password [redacted]",
    }
    assert result["checks"]["bootstrap"]["status"] == "not_checked"
    checks.controller.authenticate.assert_called_once_with(password="private-value")
    checks.controller.get_info.assert_not_called()
    checks.controller.close.assert_called_once_with()


def test_dropped_control_connection_is_not_reported_as_wrong_auth(checks):
    checks.controller.authenticate.side_effect = SocketError("connection lost")
    result = diagnostics.collect_diagnostics(checks.client)
    assert result["ready"] is False
    assert result["checks"]["controller"]["status"] == "failed"
    assert result["checks"]["authentication"]["status"] == "not_checked"
    checks.controller.close.assert_called_once_with()


def test_non_control_listener_is_not_reported_as_wrong_auth(checks):
    checks.controller.authenticate.side_effect = IncorrectSocketType(
        "not a control port"
    )
    result = diagnostics.collect_diagnostics(checks.client)
    assert result["ready"] is False
    assert result["checks"]["controller"]["status"] == "failed"
    assert result["checks"]["authentication"]["status"] == "not_checked"
    checks.controller.close.assert_called_once_with()


@pytest.mark.parametrize("progress", [0, 5, 80, 99])
def test_bootstrap_progress_is_reported_and_skips_connectivity(checks, progress):
    checks.controller.get_info.return_value = (
        f"NOTICE BOOTSTRAP PROGRESS={progress} TAG=starting"
    )
    result = diagnostics.collect_diagnostics(checks.client)
    assert result["ready"] is False
    assert result["checks"]["bootstrap"]["progress"] == progress
    assert result["checks"]["bootstrap"]["status"] == "failed"
    assert result["checks"]["socks"]["status"] == "ok"
    assert result["checks"]["connectivity"]["status"] == "not_checked"
    checks.client.get_ip.assert_not_called()


@pytest.mark.parametrize(
    "phase", ["", "PROGRESS=1000", "PROGRESS=-1", "XPROGRESS=100", "PROGRESS=100x"]
)
def test_malformed_bootstrap_never_reports_ready(checks, phase):
    checks.controller.get_info.return_value = phase
    result = diagnostics.collect_diagnostics(checks.client)
    assert result["ready"] is False
    assert result["checks"]["bootstrap"]["status"] == "failed"
    assert result["checks"]["bootstrap"]["progress"] is None


def test_bootstrap_read_error_is_reported_and_controller_closed(checks):
    checks.controller.get_info.side_effect = SocketError("read timed out")
    result = diagnostics.collect_diagnostics(checks.client)
    assert result["checks"]["bootstrap"] == {
        "status": "failed",
        "message": "read timed out",
        "progress": None,
    }
    checks.controller.close.assert_called_once_with()


def test_cleanup_error_does_not_hide_diagnostic_results(checks):
    checks.controller.close.side_effect = SocketError("already closed")
    result = diagnostics.collect_diagnostics(checks.client)
    assert result["ready"] is True
    assert result["checks"]["bootstrap"]["progress"] == 100


@pytest.mark.parametrize(
    "error", [ConnectionRefusedError("refused"), socket.timeout("timed out")]
)
def test_socks_connect_failure_is_distinct_and_skips_public_traffic(checks, error):
    checks.open_connection.side_effect = error
    result = diagnostics.collect_diagnostics(checks.client)
    assert result["ready"] is False
    assert result["checks"]["controller"]["status"] == "ok"
    assert result["checks"]["socks"]["status"] == "failed"
    assert result["checks"]["connectivity"]["status"] == "not_checked"
    checks.client.get_ip.assert_not_called()


@pytest.mark.parametrize("reply", [b"", b"HT", b"\x04\x00", b"\x05\xff", b"\x05\x02"])
def test_open_listener_must_speak_socks5_no_auth(checks, reply):
    checks.connection.recv.return_value = reply
    result = diagnostics.collect_diagnostics(checks.client)
    assert result["ready"] is False
    assert result["checks"]["socks"]["status"] == "failed"
    checks.client.get_ip.assert_not_called()
    checks.connection.__exit__.assert_called_once()


def test_fragmented_socks_greeting_is_accepted(checks):
    checks.connection.recv.side_effect = [b"\x05", b"\x00"]
    assert diagnostics.collect_diagnostics(checks.client)["ready"] is True
    assert checks.connection.recv.call_count == 2


def test_socks_reply_timeout_is_reported_and_closed(checks):
    checks.connection.recv.side_effect = socket.timeout("reply timed out")
    result = diagnostics.collect_diagnostics(checks.client)
    assert result["checks"]["socks"] == {
        "status": "failed",
        "message": "reply timed out",
    }
    checks.connection.__exit__.assert_called_once()


def test_failed_proxied_connectivity_is_distinct(checks):
    checks.client.get_ip.side_effect = IPFetchError("all IP endpoints failed")
    result = diagnostics.collect_diagnostics(checks.client)
    assert result["ready"] is False
    assert result["ip"] is None
    assert result["checks"]["socks"]["status"] == "ok"
    assert result["checks"]["connectivity"] == {
        "status": "failed",
        "message": "all IP endpoints failed",
    }


def test_keyboard_interrupt_is_not_swallowed(checks):
    checks.controller.authenticate.side_effect = KeyboardInterrupt()
    with pytest.raises(KeyboardInterrupt):
        diagnostics.collect_diagnostics(checks.client)
    checks.controller.close.assert_called_once_with()


def test_control_socket_has_bounded_connect_and_io_timeout(monkeypatch):
    connection = Mock()
    create_connection = Mock(return_value=connection)
    monkeypatch.setattr(diagnostics.socket, "create_connection", create_connection)
    control_socket = diagnostics._DiagnosticControlPort(port=9151, connect=False)
    assert control_socket._make_socket() is connection
    create_connection.assert_called_once_with(("127.0.0.1", 9151), timeout=3.0)


def test_control_socket_timeout_uses_stem_error(monkeypatch):
    create_connection = Mock(side_effect=socket.timeout("timed out"))
    monkeypatch.setattr(diagnostics.socket, "create_connection", create_connection)
    control_socket = diagnostics._DiagnosticControlPort(connect=False)
    with pytest.raises(SocketError, match="timed out"):
        control_socket._make_socket()


def test_unresponsive_local_controller_times_out_without_public_traffic(monkeypatch):
    """Exercise real Stem timeout handling against a local silent listener."""
    release = threading.Event()
    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen(2)  # Stem can reconnect once while attempting PROTOCOLINFO.
    server.settimeout(2)

    def serve():
        with server:
            connection, _ = server.accept()
            with connection:
                release.wait(2)

    worker = threading.Thread(target=serve, daemon=True)
    worker.start()
    client = SimpleNamespace(
        control_port=server.getsockname()[1],
        socks_port=1,
        password=None,
        get_ip=Mock(),
    )
    monkeypatch.setattr(diagnostics, "DIAGNOSTIC_TIMEOUT", 0.1)
    monkeypatch.setattr(diagnostics, "_check_socks", lambda port: {"status": "failed"})
    try:
        start = time.monotonic()
        result = diagnostics.collect_diagnostics(client)
        assert time.monotonic() - start < 2
    finally:
        release.set()
        worker.join(timeout=3)

    assert not worker.is_alive()
    assert result["ready"] is False
    assert result["checks"]["controller"]["status"] == "failed"
    assert result["checks"]["authentication"]["status"] == "not_checked"
    client.get_ip.assert_not_called()
