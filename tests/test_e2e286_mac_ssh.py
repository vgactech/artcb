"""R286 — mac-node-local is observer-only; Doppler/SSH fail-closed; no secret leak."""

from __future__ import annotations

import ipaddress
import json

from artcb.mac_node_access import (
    MAC_NODE_ID,
    TOKEN_ENV,
    is_rfc1918,
    json_contains_private_key,
    looks_like_private_key,
    mac_is_official_compute,
    mac_spec,
    probe_mac_access,
)
from artcb.node_registry import NODES, OFFICIAL_COMPUTE_IPV4, OFFICIAL_COMPUTE_NODE_IDS


def test_mac_not_official_compute() -> None:
    spec = mac_spec()
    assert spec.node_id == MAC_NODE_ID
    assert spec.node_id not in OFFICIAL_COMPUTE_NODE_IDS
    assert spec.ssh_host == "10.234.49.2"
    assert spec.ssh_host not in OFFICIAL_COMPUTE_IPV4
    assert spec.doppler_project == "artcb-1"
    assert spec.doppler_config == "prd"
    assert spec.doppler_token_env == TOKEN_ENV
    assert spec.health_http == "http://10.234.49.2:8001"
    assert spec.ssh_user == "deyi"
    assert mac_is_official_compute() is False
    assert "mac-node-local" in NODES


def test_lan_is_rfc1918_not_public() -> None:
    assert is_rfc1918("10.234.49.2") is True
    assert is_rfc1918("152.228.144.34") is False
    assert ipaddress.ip_address("10.234.49.2").is_private is True


def test_probe_without_mac_token_does_not_invent_sha(monkeypatch) -> None:
    monkeypatch.delenv(TOKEN_ENV, raising=False)
    monkeypatch.delenv("DOPPLER_TOKEN", raising=False)
    result = probe_mac_access(write_key=False, tcp_timeout=0.2)
    dumped = json.dumps(result)
    assert "BEGIN" not in dumped
    assert result["token_present"] is False
    assert result["rfc1918"] is True
    assert result["official_compute"] is False
    assert result["certified_100"] is False
    assert result["verdict"]["mac_health_sha"] is None
    assert result["verdict"]["token_in_cursor_env"] == "FAIL"
    assert result["key_file"]["written"] is False
    assert json_contains_private_key(result) is False


def test_looks_like_private_key_does_not_match_public() -> None:
    assert looks_like_private_key("ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAA") is False
    assert looks_like_private_key("") is False
    fake = "-----BEGIN OPENSSH PRIVATE KEY-----\nabc\n-----END OPENSSH PRIVATE KEY-----"
    assert looks_like_private_key(fake) is True
    assert json_contains_private_key({"k": fake}) is True
    assert json_contains_private_key({"k": "timeout"}) is False
