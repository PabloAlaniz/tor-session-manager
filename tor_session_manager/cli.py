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
from typing import Optional

from . import __version__
from .client import TorClient
from .exceptions import TorSessionError


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tor-session",
        description="Manage Tor sessions and rotate circuits from the shell.",
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )
    parser.add_argument(
        "--control-port", type=int, default=TorClient.DEFAULT_CONTROL_PORT
    )
    parser.add_argument("--socks-port", type=int, default=TorClient.DEFAULT_SOCKS_PORT)
    parser.add_argument("--password", default=None)
    parser.add_argument(
        "--json", action="store_true", help="Emit machine-readable JSON output."
    )

    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("ip", help="Print the current public exit IP.")
    sub.add_parser("rotate", help="Rotate the circuit and print the new IP.")
    sub.add_parser("circuit", help="Print info about the active circuit.")
    sub.add_parser("country", help="Print the exit relay's country code.")
    sub.add_parser("benchmark", help="Benchmark the current circuit.")
    sub.add_parser("status", help="Print a full status snapshot.")
    return parser


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
        "ready": client.is_ready(),
        "ip": None,
        "exit_country": None,
        "num_circuits": None,
        "health": None,
    }
    if snapshot["ready"]:
        try:
            snapshot["ip"] = client.get_ip()
        except TorSessionError:
            pass
        try:
            snapshot["exit_country"] = client.get_exit_country()
        except TorSessionError:
            pass
        try:
            snapshot["num_circuits"] = len(client.list_circuits())
        except TorSessionError:
            pass
        snapshot["health"] = client.benchmark().as_dict()

    if as_json:
        print(json.dumps(snapshot))
    else:
        print(f"ready: {snapshot['ready']}")
        print(f"ip: {snapshot['ip']}")
        print(f"exit_country: {snapshot['exit_country']}")
        print(f"num_circuits: {snapshot['num_circuits']}")
    return 0


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
    except TorSessionError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
