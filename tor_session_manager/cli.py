"""
Command-line interface for tor-session-manager.

Usage::

    tor-session ip
    tor-session rotate
    tor-session circuit
    tor-session country
    tor-session benchmark
    tor-session status --json
"""

import argparse
import json
import sys
from typing import Any, Callable, Dict, Optional

from . import __version__
from .client import TorClient
from .diagnostics import collect_diagnostics, error_message
from .exceptions import TorSessionError


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tor-session",
        description="Manage Tor sessions and rotate circuits from the shell.",
    )
    _add_common_arguments(parser)

    sub = parser.add_subparsers(dest="command", required=True)
    commands = {
        "ip": "Print the current public exit IP.",
        "rotate": "Rotate the circuit and print the new IP.",
        "circuit": "Print info about the active circuit.",
        "country": "Print the exit relay's country code.",
        "benchmark": "Benchmark the current circuit.",
        "status": "Check controller, authentication, bootstrap, and proxy connectivity.",
    }
    for command, help_text in commands.items():
        command_parser = sub.add_parser(command, help=help_text)
        # Suppressed subparser defaults preserve values supplied before the
        # command, while still accepting the same options after it.
        _add_common_arguments(command_parser, suppress_defaults=True)
    return parser


def _port(value):
    try:
        port = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError("port must be an integer from 1 to 65535")
    if not 1 <= port <= 65535:
        raise argparse.ArgumentTypeError("port must be an integer from 1 to 65535")
    return port


def _add_common_arguments(parser, suppress_defaults=False):
    def default(value):
        return argparse.SUPPRESS if suppress_defaults else value

    parser.add_argument(
        "--version", action="version", version=f"tor-session {__version__}"
    )
    parser.add_argument(
        "--control-port", type=_port, default=default(TorClient.DEFAULT_CONTROL_PORT)
    )
    parser.add_argument(
        "--socks-port", type=_port, default=default(TorClient.DEFAULT_SOCKS_PORT)
    )
    parser.add_argument("--password", default=default(None))
    parser.add_argument(
        "--json",
        action="store_true",
        default=default(False),
        help="Emit machine-readable JSON output.",
    )


def _emit(payload, as_json: bool, human: str) -> None:
    if as_json:
        print(json.dumps(payload))
    else:
        print(human)


def _cmd_ip(client: TorClient, as_json: bool) -> int:
    ip = client.get_ip()
    _emit({"ip": ip}, as_json, ip)
    return 0


def _cmd_rotate(client: TorClient, as_json: bool) -> int:
    ip = client.wait_for_new_ip()
    _emit({"ip": ip}, as_json, ip)
    return 0


def _cmd_circuit(client: TorClient, as_json: bool) -> int:
    info = client.get_circuit_info()
    if as_json:
        print(json.dumps(info.as_dict()))
    else:
        hops = " -> ".join(r.nickname or r.fingerprint for r in info.path)
        print(f"Circuit {info.id} [{info.status}] {hops} (exit: {info.exit_country})")
    return 0


def _cmd_country(client: TorClient, as_json: bool) -> int:
    country = client.get_exit_country()
    _emit({"exit_country": country}, as_json, country or "unknown")
    return 0


def _cmd_benchmark(client: TorClient, as_json: bool) -> int:
    health = client.benchmark()
    if as_json:
        print(json.dumps(health.as_dict()))
    else:
        lat = f"{health.latency_ms:.0f} ms" if health.latency_ms is not None else "n/a"
        thr = (
            f"{health.throughput_kbps:.0f} KB/s"
            if health.throughput_kbps is not None
            else "n/a"
        )
        print(f"latency: {lat} | throughput: {thr}")
    return 0


def _cmd_status(client: TorClient, as_json: bool) -> int:
    snapshot = {
        "version": __version__,
        **collect_diagnostics(client),
        "exit_country": None,
        "num_circuits": None,
        "health": None,
        "errors": {},
    }
    if snapshot["ready"]:
        details: Dict[str, Callable[[], Any]] = {
            "exit_country": client.get_exit_country,
            "num_circuits": lambda: len(client.list_circuits()),
            "health": lambda: client.benchmark().as_dict(),
        }
        for field, fetch in details.items():
            try:
                snapshot[field] = fetch()
            except Exception as error:
                snapshot["errors"][field] = error_message(error, client.password)
        if snapshot["health"] is not None and not snapshot["health"]["ok"]:
            snapshot["errors"]["health"] = "No benchmark metric could be measured."

    if as_json:
        print(json.dumps(snapshot))
    else:
        print(f"ready: {snapshot['ready']}")
        for name, check in snapshot["checks"].items():
            detail = check.get("message", "")
            progress = check.get("progress")
            if progress is not None:
                detail = f"{progress}% {detail}".strip()
            suffix = f" ({detail})" if detail else ""
            print(f"{name}: {check['status']}{suffix}")
        print(f"ip: {snapshot['ip']}")
        print(f"exit_country: {snapshot['exit_country']}")
        print(f"num_circuits: {snapshot['num_circuits']}")
        for field, detail_error in snapshot["errors"].items():
            print(f"{field} error: {detail_error}")
    return 0 if snapshot["ready"] else 1


_COMMANDS = {
    "ip": _cmd_ip,
    "rotate": _cmd_rotate,
    "circuit": _cmd_circuit,
    "country": _cmd_country,
    "benchmark": _cmd_benchmark,
    "status": _cmd_status,
}


def main(argv: Optional[list] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    client = TorClient(
        control_port=args.control_port,
        socks_port=args.socks_port,
        password=args.password,
    )
    try:
        return _COMMANDS[args.command](client, args.json)
    except TorSessionError as error:
        message = error_message(error, args.password)
        if args.json:
            print(json.dumps({"error": message}))
        else:
            print(f"error: {message}", file=sys.stderr)
        return 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
