import pytest

from tor_session_manager import bridges as bridges_mod
from tor_session_manager.bridges import (
    Bridge,
    build_bridge_config,
    launch_bridged_tor,
    parse_bridge_line,
    transport_binary,
)
from tor_session_manager.exceptions import BridgeConfigError

OBFS4_LINE = (
    "obfs4 192.0.2.1:443 0123456789ABCDEF0123456789ABCDEF01234567 "
    "cert=abcdef iat-mode=0"
)


# --- parse_bridge_line -------------------------------------------------------


def test_parse_obfs4_line():
    b = parse_bridge_line(OBFS4_LINE)
    assert b.transport == "obfs4"
    assert b.address == "192.0.2.1:443"
    assert b.fingerprint == "0123456789ABCDEF0123456789ABCDEF01234567"
    assert b.args == "cert=abcdef iat-mode=0"


def test_parse_vanilla_bridge():
    b = parse_bridge_line("192.0.2.9:9001 0123456789ABCDEF0123456789ABCDEF01234567")
    assert b.transport is None
    assert b.address == "192.0.2.9:9001"
    assert b.fingerprint == "0123456789ABCDEF0123456789ABCDEF01234567"


def test_parse_snowflake_no_fingerprint():
    b = parse_bridge_line("snowflake 192.0.2.3:80")
    assert b.transport == "snowflake"
    assert b.address == "192.0.2.3:80"
    assert b.fingerprint is None


def test_parse_empty_raises():
    with pytest.raises(BridgeConfigError):
        parse_bridge_line("   ")


def test_parse_no_address_raises():
    with pytest.raises(BridgeConfigError):
        parse_bridge_line("obfs4 not-an-address")


def test_bridge_line_roundtrip():
    assert parse_bridge_line(OBFS4_LINE).line == OBFS4_LINE


# --- transport_binary --------------------------------------------------------


def test_transport_binary_from_path():
    assert transport_binary("obfs4", path="/opt/obfs4proxy") == "/opt/obfs4proxy"


def test_transport_binary_resolves_via_which(monkeypatch):
    monkeypatch.setattr(bridges_mod.shutil, "which", lambda name: f"/usr/bin/{name}")
    assert transport_binary("obfs4") == "/usr/bin/obfs4proxy"


def test_transport_binary_missing_raises(monkeypatch):
    monkeypatch.setattr(bridges_mod.shutil, "which", lambda name: None)
    with pytest.raises(BridgeConfigError):
        transport_binary("obfs4")


# --- build_bridge_config -----------------------------------------------------


def test_build_config_with_transport(monkeypatch):
    monkeypatch.setattr(bridges_mod.shutil, "which", lambda name: f"/usr/bin/{name}")
    config = build_bridge_config([OBFS4_LINE])
    assert config["UseBridges"] == "1"
    assert config["Bridge"] == [OBFS4_LINE]
    assert config["ClientTransportPlugin"] == ["obfs4 exec /usr/bin/obfs4proxy"]


def test_build_config_dedups_transports(monkeypatch):
    monkeypatch.setattr(bridges_mod.shutil, "which", lambda name: f"/usr/bin/{name}")
    config = build_bridge_config(
        [OBFS4_LINE, "obfs4 192.0.2.2:443 0123456789ABCDEF0123456789ABCDEF01234567"]
    )
    assert len(config["Bridge"]) == 2
    assert config["ClientTransportPlugin"] == ["obfs4 exec /usr/bin/obfs4proxy"]


def test_build_config_vanilla_no_plugin():
    config = build_bridge_config(
        ["192.0.2.9:9001 0123456789ABCDEF0123456789ABCDEF01234567"]
    )
    assert "ClientTransportPlugin" not in config


def test_build_config_uses_explicit_transport_path():
    config = build_bridge_config([OBFS4_LINE], transport_paths={"obfs4": "/opt/o4"})
    assert config["ClientTransportPlugin"] == ["obfs4 exec /opt/o4"]


def test_build_config_missing_binary_raises(monkeypatch):
    monkeypatch.setattr(bridges_mod.shutil, "which", lambda name: None)
    with pytest.raises(BridgeConfigError):
        build_bridge_config([OBFS4_LINE])


def test_build_config_empty_raises():
    with pytest.raises(BridgeConfigError):
        build_bridge_config([])


# --- launch_bridged_tor ------------------------------------------------------


def test_launch_bridged_tor_passes_config(monkeypatch):
    import stem.process

    captured = {}

    def fake_launch(config, tor_cmd, timeout, take_ownership):
        captured["config"] = config
        captured["tor_cmd"] = tor_cmd
        return "FAKE_PROC"

    monkeypatch.setattr(stem.process, "launch_tor_with_config", fake_launch)
    monkeypatch.setattr(bridges_mod.shutil, "which", lambda name: f"/usr/bin/{name}")

    proc = launch_bridged_tor(
        [OBFS4_LINE], socks_port=9150, control_port=9151, data_directory="/tmp/tordata"
    )

    assert proc == "FAKE_PROC"
    cfg = captured["config"]
    assert cfg["SocksPort"] == "9150"
    assert cfg["ControlPort"] == "9151"
    assert cfg["CookieAuthentication"] == "1"
    assert cfg["DataDirectory"] == "/tmp/tordata"
    assert cfg["UseBridges"] == "1"
    assert cfg["Bridge"] == [OBFS4_LINE]
    assert cfg["ClientTransportPlugin"] == ["obfs4 exec /usr/bin/obfs4proxy"]


def test_launch_bridged_tor_merges_extra_config(monkeypatch):
    import stem.process

    captured = {}
    monkeypatch.setattr(
        stem.process,
        "launch_tor_with_config",
        lambda config, tor_cmd, timeout, take_ownership: captured.update(config=config),
    )
    monkeypatch.setattr(bridges_mod.shutil, "which", lambda name: f"/usr/bin/{name}")

    launch_bridged_tor([OBFS4_LINE], extra_config={"Log": "notice stdout"})
    assert captured["config"]["Log"] == "notice stdout"
