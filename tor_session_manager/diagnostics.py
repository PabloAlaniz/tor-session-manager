"""Read-only checks used by the CLI's status command.

The control port and SOCKS port are checked separately: an open controller does
not prove that application traffic can use the proxy. The SOCKS probe performs
only a local protocol greeting; public connectivity uses the client's usual
proxied IP checker.
"""

import re
import socket

from stem import SocketError
from stem.connection import AuthenticationFailure, IncorrectSocketType
from stem.control import Controller
from stem.socket import ControlPort

DIAGNOSTIC_TIMEOUT = 3.0


class _DiagnosticControlPort(ControlPort):
    """Stem's default control socket has no timeout; bound this short probe."""

    def _make_socket(self):
        try:
            return socket.create_connection(
                (self.address, self.port), timeout=DIAGNOSTIC_TIMEOUT
            )
        except OSError as error:
            raise SocketError(str(error)) from error


def _check(status, message=None, **details):
    result = {"status": status}
    if message:
        result["message"] = message
    result.update(details)
    return result


def error_message(error, password=None):
    """Keep a supplied controller password out of diagnostic output."""
    message = str(error) or type(error).__name__
    if password:
        message = message.replace(password, "[redacted]")
    return message


def _check_controller(client, checks):
    try:
        controller = Controller(_DiagnosticControlPort(port=client.control_port))
    except Exception as error:
        checks["controller"] = _check("failed", error_message(error, client.password))
        return

    checks["controller"] = _check("ok")
    try:
        try:
            if client.password:
                controller.authenticate(password=client.password)
            else:
                controller.authenticate()
        except AuthenticationFailure as error:
            # Stem also wraps protocol/transport errors in AuthenticationFailure.
            # Those do not establish that authentication itself was rejected.
            failed_stage = (
                "controller"
                if isinstance(error, IncorrectSocketType)
                or isinstance(error.__context__, SocketError)
                or not controller.is_alive()
                else "authentication"
            )
            checks[failed_stage] = _check(
                "failed", error_message(error, client.password)
            )
            return
        except Exception as error:
            # A lost control connection does not establish bad credentials.
            checks["controller"] = _check(
                "failed", error_message(error, client.password)
            )
            return

        checks["authentication"] = _check("ok")
        try:
            phase = controller.get_info("status/bootstrap-phase")
            match = re.search(r"(?:^|\s)PROGRESS=(\d+)(?=\s|$)", phase)
            if match is None or not 0 <= int(match.group(1)) <= 100:
                raise ValueError("Controller returned no valid bootstrap progress.")
            progress = int(match.group(1))
            checks["bootstrap"] = _check(
                "ok" if progress == 100 else "failed",
                None if progress == 100 else "Tor is still bootstrapping.",
                progress=progress,
            )
        except Exception as error:
            checks["bootstrap"] = _check(
                "failed", error_message(error, client.password), progress=None
            )
    finally:
        try:
            controller.close()
        except Exception:
            # Cleanup must not hide the result of the diagnostic checks.
            pass


def _check_socks(port):
    try:
        with socket.create_connection(
            ("127.0.0.1", port), timeout=DIAGNOSTIC_TIMEOUT
        ) as connection:
            connection.sendall(b"\x05\x01\x00")
            reply = b""
            while len(reply) < 2:
                chunk = connection.recv(2 - len(reply))
                if not chunk:
                    raise OSError("SOCKS listener closed before replying.")
                reply += chunk
            if reply != b"\x05\x00":
                raise OSError(
                    "Listener did not accept the SOCKS5 no-authentication greeting."
                )
    except OSError as error:
        return _check("failed", error_message(error))
    return _check("ok")


def collect_diagnostics(client):
    """Return independent checks and readiness without hiding failed stages.

    ``ready`` requires control access, authentication, full bootstrap, a valid
    SOCKS5 listener, and a successful public IP lookup. A known incomplete
    bootstrap skips the public lookup. If the control port is unavailable, the
    SOCKS path is still tested so its condition is visible independently.
    """
    checks = {
        "controller": _check("not_checked"),
        "authentication": _check("not_checked"),
        "bootstrap": _check("not_checked", progress=None),
        "socks": _check("not_checked"),
        "connectivity": _check("not_checked"),
    }
    _check_controller(client, checks)
    checks["socks"] = _check_socks(client.socks_port)

    ip = None
    progress = checks["bootstrap"].get("progress")
    if checks["socks"]["status"] != "ok":
        checks["connectivity"] = _check("not_checked", "SOCKS check failed.")
    elif progress is not None and progress < 100:
        checks["connectivity"] = _check(
            "not_checked", "Tor has not finished bootstrapping."
        )
    else:
        try:
            ip = client.get_ip()
            checks["connectivity"] = _check("ok")
        except Exception as error:
            checks["connectivity"] = _check(
                "failed", error_message(error, client.password)
            )

    return {
        "ready": all(check["status"] == "ok" for check in checks.values()),
        "ip": ip,
        "checks": checks,
    }
