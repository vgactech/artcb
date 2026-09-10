"""R302 — live N is membership, not n_f_q(4). Seeds stay four IPv4s."""

from __future__ import annotations

from artcb.consensus.live_bft import n_f_q
from artcb.consensus.pbft_view import primary_of
from artcb.mac_node_access import is_lan_only_host
from artcb.node_registry import (
    MAC_NODE_ID,
    OFFICIAL_COMPUTE_NODE_IDS,
    _mac_public_tunnel_http,
    official_pbft_n_f_q,
    official_pbft_replica_ids,
    pbft_membership_vs_transport,
    pbft_reachable_http_map,
    seed_http_map,
)
from artcb.p2p.official_replica import replica_peer_allowed


def test_historical_four_formula_is_not_live_membership() -> None:
    assert n_f_q(4) == (4, 1, 3)
    assert official_pbft_n_f_q() == (5, 1, 3)
    assert official_pbft_n_f_q() != n_f_q(4)


def test_seeds_four_membership_five_mac_not_in_seed_http(monkeypatch) -> None:
    monkeypatch.delenv("ARTCB_MAC_TUNNEL_HEALTH_HTTP", raising=False)
    split = pbft_membership_vs_transport()
    assert split["official_compute_node_ids"] == list(OFFICIAL_COMPUTE_NODE_IDS)
    assert len(split["official_compute_node_ids"]) == 4
    assert MAC_NODE_ID in split["official_pbft_replica_ids"]
    assert split["mac_in_membership"] is True
    assert split["mac_in_seed_ids"] is False
    assert split["n_f_q"] == [5, 1, 3]
    assert split["n_f_q_historical_four"] == [4, 1, 3]
    assert split["certified_100"] is False
    seeds = seed_http_map()
    assert set(seeds) == set(OFFICIAL_COMPUTE_NODE_IDS)
    reachable = pbft_reachable_http_map()
    assert MAC_NODE_ID not in reachable
    assert _mac_public_tunnel_http() is None


def test_rfc1918_never_replica_peer_and_primary_mac_index() -> None:
    ids = official_pbft_replica_ids()
    assert ids[-1] == MAC_NODE_ID
    assert primary_of(4) == MAC_NODE_ID
    assert replica_peer_allowed("10.234.49.2") is False
    assert replica_peer_allowed("10.197.17.115") is False
    assert is_lan_only_host("10.234.49.2") is True
    assert is_lan_only_host("127.0.0.1:8001") is True


def test_exclusive_primary_mac_without_tunnel_is_unreachable(monkeypatch) -> None:
    """On a seed, view%5==4 would KeyError if hosts were seeds-only. Fail closed."""
    from artcb.consensus import pbft_exclusive

    monkeypatch.setattr(pbft_exclusive, "on_official_compute", lambda: True)
    monkeypatch.delenv("ARTCB_MAC_TUNNEL_HEALTH_HTTP", raising=False)

    class _Log:
        data_dir = None

    class _Engine:
        node_id = "ovh-node-1"
        pbft = type("P", (), {"view": 4})()
        pbft_log = _Log()

    out = pbft_exclusive.coordinate_public_finality(_Engine(), None, {})
    assert out["ok"] is False
    assert out["wrote"] is False
    assert out["reason"] == "primary_unreachable_transport"
    assert out["primary"] == MAC_NODE_ID
    assert MAC_NODE_ID not in out["reachable"]


def test_live_runners_do_not_claim_n_equals_four_as_membership() -> None:
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    for rel in (
        "scripts/run_live270_pbft_cert_matrix.py",
        "scripts/run_live271_close_not_proven.py",
    ):
        text = (root / rel).read_text(encoding="utf-8")
        assert "official_pbft_n_f_q()" in text
        assert "n_f_q_historical_four" in text
        assert "official_pbft_replica_ids()" in text
