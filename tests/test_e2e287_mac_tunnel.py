"""R287 — RFC1918 Mac LAN is not a cloud path; tunnel required and measured."""

from __future__ import annotations

from artcb.mac_node_access import (
    is_lan_only_host,
    is_rfc1918,
    mac_spec,
    select_cloud_remote,
)
from artcb.p2p.public_url import public_register_url_ok


def test_mac_tunnel_required_and_lan_rejected(monkeypatch) -> None:
    monkeypatch.setenv("ARTCB_ALLOW_LOCAL_PEERS", "0")
    spec = mac_spec()
    assert spec.tunnel_required is True
    assert spec.tunnel_ssh_host is None
    assert spec.tunnel_health_http is None
    assert is_rfc1918("10.234.49.2") is True
    assert is_lan_only_host("10.234.49.2") is True
    assert is_lan_only_host("luxiufengdeMacBook-Air.local") is True
    assert is_lan_only_host("152.228.144.34") is False
    ok, reason = public_register_url_ok("http://10.234.49.2:8001")
    assert ok is False
    assert reason == "private_or_loopback_forbidden"


def test_select_cloud_remote_refuses_rfc1918_disguised_as_tunnel() -> None:
    spec = mac_spec()
    denied = select_cloud_remote(spec, env={})
    assert denied["ok"] is False
    assert denied["reason"] == "rfc1918_requires_tunnel"
    assert denied["ssh_host"] is None
    fake = select_cloud_remote(spec, env={"ARTCB_MAC_TUNNEL_SSH_HOST": "10.234.49.2"})
    assert fake["ok"] is False
    assert fake["reason"] == "tunnel_host_is_lan_only"
    mdns = select_cloud_remote(spec, env={"ARTCB_MAC_TUNNEL_SSH_HOST": "luxiufengdeMacBook-Air.local"})
    assert mdns["ok"] is False
    public = select_cloud_remote(spec, env={"ARTCB_MAC_TUNNEL_SSH_HOST": "1.tcp.ngrok.io"})
    assert public["ok"] is True
    assert public["ssh_host"] == "1.tcp.ngrok.io"
    assert public["reason"] == "public_tunnel"
