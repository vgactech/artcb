"""R331 — next_reachable_view skips Mac without tunnel."""

from __future__ import annotations

from artcb.consensus.pbft_view import next_reachable_view, primary_of


def test_next_reachable_skips_mac_without_tunnel(monkeypatch) -> None:
    monkeypatch.delenv("ARTCB_MAC_TUNNEL_HEALTH_HTTP", raising=False)
    # view 18 → primary ovh-4; view 19 → mac; view 20 → ovh-1
    assert primary_of(19) == "mac-node-local"
    plan = next_reachable_view(18)
    assert plan["ok"] is True
    assert plan["target_view"] == 20
    assert plan["primary"] == "ovh-node-1"
    assert any(s.get("primary") == "mac-node-local" for s in plan["skipped"])
