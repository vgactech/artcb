"""R297 — Mac is an official PBFT replica; N adapts when new replicas appear."""

from __future__ import annotations

from artcb.agent_context_contract import CONTRACT_VERSION, build_context_contract
from artcb.consensus.live_bft import n_f_q
from artcb.consensus.pbft_certification_matrix import new_matrix
from artcb.consensus.pbft_view import primary_of
from artcb.mac_node_access import mac_is_official_compute, mac_spec
from artcb.node_registry import (
    FOLLOW_MAIN_REMOTE_NODE_IDS,
    MAC_NODE_ID,
    NODE_SECRET_ALLOWLIST,
    NODES,
    OFFICIAL_COMPUTE_IPV4,
    OFFICIAL_COMPUTE_NODE_IDS,
    NodeSpec,
    follow_main_local_clone_ids,
    official_pbft_n_f_q,
    official_pbft_replica_ids,
    public_registry,
)


def test_seed_ipv4_stays_four_public_vms() -> None:
    assert OFFICIAL_COMPUTE_NODE_IDS == (
        "ovh-node-1",
        "ovh-node-2",
        "aws-node-3",
        "ovh-node-4",
    )
    assert FOLLOW_MAIN_REMOTE_NODE_IDS == OFFICIAL_COMPUTE_NODE_IDS
    assert MAC_NODE_ID not in OFFICIAL_COMPUTE_IPV4
    assert mac_spec().ssh_host not in OFFICIAL_COMPUTE_IPV4
    assert mac_is_official_compute() is False


def test_mac_is_official_replica_like_cloud() -> None:
    spec = mac_spec()
    assert spec.pbft_replica is True
    assert spec.follow_main is True
    assert spec.provider == "local-macos"
    assert spec.doppler_project == "artcb-1"
    assert MAC_NODE_ID in official_pbft_replica_ids()
    assert MAC_NODE_ID in follow_main_local_clone_ids()
    ids = official_pbft_replica_ids()
    assert ids == tuple(nid for nid, row in NODES.items() if row.pbft_replica)
    assert ids[-1] == MAC_NODE_ID
    assert official_pbft_n_f_q() == (5, 1, 3)
    assert n_f_q(5) == (5, 1, 3)
    assert primary_of(4) == MAC_NODE_ID
    assert primary_of(15) == ids[15 % len(ids)]
    matrix = new_matrix()
    assert matrix["replicas"] == list(ids)
    assert matrix["n"] == 5
    assert matrix["f"] == 1
    assert matrix["q"] == 3
    assert matrix["certified_100"] is False


def test_new_replica_from_anywhere_grows_n(monkeypatch) -> None:
    extra = dict(NODES)
    extra["user-clone-anywhere"] = NodeSpec(
        node_id="user-clone-anywhere",
        display_name="cloned user",
        provider="git-clone",
        doppler_project="artcb-user-clone",
        pbft_replica=True,
        follow_main=True,
    )
    monkeypatch.setattr("artcb.node_registry.NODES", extra)
    monkeypatch.setattr("src.artcb.node_registry.NODES", extra)
    ids = official_pbft_replica_ids()
    assert "user-clone-anywhere" in ids
    assert MAC_NODE_ID in ids
    assert official_pbft_n_f_q() == n_f_q(len(ids))
    assert len(ids) == 6
    assert official_pbft_n_f_q() == (6, 1, 3)


def test_context_contract_mac_is_replica_no_thinking() -> None:
    contract = build_context_contract(key_record={"label": "agent_test"})
    assert contract["version"] == CONTRACT_VERSION
    assert contract["includes_thinking"] is False
    assert contract["certified_100"] is False
    assert contract["pbft"]["mac_pbft_replica_role"] is True
    assert contract["pbft"]["mac_in_membership"] is True
    assert contract["pbft"]["n"] == 5
    assert contract["pbft"]["quorum"] == 3
    assert contract["pbft"]["mac_follow_main"] is True
    registry = public_registry()
    assert registry["mac_in_pbft_membership"] is True
    assert registry["official_pbft_replica_ids"][-1] == MAC_NODE_ID
    assert registry["pbft"]["n"] == 5


def test_mac_sudo_password_is_doppler_allowlisted_name_only() -> None:
    names = NODE_SECRET_ALLOWLIST[MAC_NODE_ID]
    assert "MAC_SUDO_PASSWORD" in names
    assert "KEY_API_STRIPE" not in names
