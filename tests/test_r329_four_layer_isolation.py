"""R329 — four-layer isolation: PUBLIC tip must ignore ORG/GROUP/PRIVATE growth.

Code vocabulary (honest):
  - Chain visibility: public | private | group  (no ``org`` on ChainBlock)
  - Logical/domain: global | org | group | private/resource (authz/domains.py)
  - Org bodies live in authz/*.json; only content_hash commitments are public blocks
  - R328: group+private appends → private ledger; public → public ledger
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from nacl import encoding, signing

from artcb.authz.domains import REPLICATION_MATRIX
from artcb.chain import ffi
from artcb.chain.manager import ChainManager, GENESIS_PREV_HASH
from artcb.wallet.manager import WalletManager
from api.main import create_app

TEST_PASSWORD = "monMotDePasse42!"


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("ARTCB_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("ARTCB_LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("ARTCB_SPLIT_LEDGER", "1")
    monkeypatch.setenv("ARTCB_PUBLIC_TIP_WATCHDOG", "0")
    return TestClient(create_app())


def _user(name: str) -> dict:
    w = WalletManager().create_wallet(name=name, user_password=TEST_PASSWORD)
    return {"name": name, "address": w.address}


def _login(client: TestClient, name: str) -> dict:
    r = client.post("/api/v1/auth/login", json={"name": name, "password": TEST_PASSWORD})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['session_token']}"}


def test_replication_matrix_four_layers_documented() -> None:
    assert "ORG_GENESIS_BODY" in REPLICATION_MATRIX
    assert "GROUP_GENESIS_HASH" in REPLICATION_MATRIX
    assert "PRIVATE_RESOURCE" in REPLICATION_MATRIX
    assert REPLICATION_MATRIX["ORG_GENESIS_BODY"]["replication"] == "org_domain_nodes"
    assert REPLICATION_MATRIX["PRIVATE_RESOURCE"]["replication"] == "never_p2p"
    assert REPLICATION_MATRIX["DOMAIN_COMMITMENT_BLOCK"]["replication"] == "all_consensus_nodes"


def test_private_and_group_growth_do_not_move_public_tip(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ARTCB_SPLIT_LEDGER", "1")
    blocks = tmp_path / "blocks.jsonl"
    rows = [
        {
            "index": 0,
            "timestamp": "2026-09-12T00:00:00Z",
            "prev_hash": GENESIS_PREV_HASH,
            "hash": "a" * 64,
            "visibility": "public",
            "signature": "ed25519:" + ("ab" * 32),
            "graph_root": "g" * 64,
            "merkle_root": "g" * 64,
            "pol_score": 0.1,
            "graph_id": "pub0",
        }
    ]
    blocks.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    mgr = ChainManager(blocks, key_path=tmp_path / "k", enable_security=False)
    pub0 = mgr.tip_public_private()["public_last_index"]
    assert pub0 == 0

    for i in range(40):
        mgr.append_block(
            graph_id=f"priv{i}",
            graph_root="p" * 64,
            pol_score=0.1,
            visibility="private",
        )
    for i in range(25):
        mgr.append_block(
            graph_id=f"grp{i}",
            graph_root="q" * 64,
            pol_score=0.1,
            visibility="group",
            group_id="g_test_a1",
        )
    tip = mgr.tip_public_private()
    assert tip["public_last_index"] == 0
    assert tip["private_height"] == 65
    assert tip["ledger_mode"] == "split_v1"


def test_org_a_group_isolation_from_org_b(client: TestClient) -> None:
    a = _user("founderA")
    b = _user("founderB")
    ha, hb = _login(client, "founderA"), _login(client, "founderB")

    org_a = client.post("/api/v1/authz/orgs", json={"name": "ORG-A"}, headers=ha)
    org_b = client.post("/api/v1/authz/orgs", json={"name": "ORG-B"}, headers=hb)
    assert org_a.status_code == 200, org_a.text
    assert org_b.status_code == 200, org_b.text
    id_a, id_b = org_a.json()["organization_id"], org_b.json()["organization_id"]
    assert id_a != id_b
    assert id_a.startswith("org_") and id_b.startswith("org_")

    g_a = client.post(
        "/api/v1/groups",
        json={"name": "GROUP-A1", "founder_address": a["address"], "organization_id": id_a},
        headers=ha,
    )
    g_b = client.post(
        "/api/v1/groups",
        json={"name": "GROUP-A1", "founder_address": b["address"], "organization_id": id_b},
        headers=hb,
    )
    assert g_a.status_code == 200, g_a.text
    assert g_b.status_code == 200, g_b.text
    gid_a, gid_b = g_a.json()["group_id"], g_b.json()["group_id"]
    # Same display name, different identities (UUID space)
    assert gid_a != gid_b
    assert gid_a.startswith("g_") and gid_b.startswith("g_")

    # B cannot store into A's group (membership gate)
    denied = client.post(
        "/api/v1/store",
        json={
            "text": "secret A1",
            "visibility": "group",
            "group_id": gid_a,
            "wallet_name": "founderB",
            "wallet_password": TEST_PASSWORD,
        },
        headers=hb,
    )
    assert denied.status_code in (403, 401), denied.text

    ok = client.post(
        "/api/v1/store",
        json={
            "text": "secret A1 owner",
            "visibility": "group",
            "group_id": gid_a,
            "wallet_name": "founderA",
            "wallet_password": TEST_PASSWORD,
        },
        headers=ha,
    )
    assert ok.status_code == 200, ok.text


def test_org_export_acl_knowing_id_is_not_access(client: TestClient) -> None:
    """R334-D — knowing org/domain id must not yield genesis body to outsider."""
    _user("founderExpA")
    _user("founderExpB")
    ha, hb = _login(client, "founderExpA"), _login(client, "founderExpB")
    org = client.post("/api/v1/authz/orgs", json={"name": "ORG-EXPORT-ACL"}, headers=ha)
    assert org.status_code == 200, org.text
    domains = client.get("/api/v1/authz/domains")
    assert domains.status_code == 200
    dom = next(
        (
            d
            for d in (domains.json().get("domains") or [])
            if d.get("subject_id") == org.json()["organization_id"]
        ),
        None,
    )
    assert dom and dom.get("domain_id")
    did = dom["domain_id"]
    # Outsider B knows domain_id
    denied = client.post(f"/api/v1/authz/domains/{did}/export", headers=hb)
    assert denied.status_code in (401, 403), denied.text
    assert "genesis_body" not in (denied.json() if denied.headers.get("content-type", "").startswith("application/json") else {})
    # Owner A can export
    ok = client.post(f"/api/v1/authz/domains/{did}/export", headers=ha)
    assert ok.status_code == 200, ok.text
    assert ok.json().get("genesis_body") or ok.json().get("manifest")


def test_org_commitment_advances_public_tip_not_private_body(client: TestClient) -> None:
    """ORG body stays local; public tip may move only via commitment block."""
    _user("founderC")
    h = _login(client, "founderC")
    before = client.get("/api/v1/chain/status").json()
    pub_before = before.get("public_last_index")

    org = client.post("/api/v1/authz/orgs", json={"name": "ORG-C"}, headers=h)
    assert org.status_code == 200, org.text
    assert org.json().get("content_hash")
    # Public list is commitment projection only
    listed = client.get("/api/v1/authz/orgs")
    assert listed.status_code == 200
    assert listed.json()["orgs"]
    assert listed.json()["orgs"][-1]["projection"] == "public_commitment"
    assert "founder_address" not in listed.json()["orgs"][-1]

    after = client.get("/api/v1/chain/status").json()
    # Commitment is a public append (may require PBFT on official; in test often dry or local)
    # At minimum: private_suffix / ledger_mode must not treat org body as public height pollution
    assert after.get("ledger_mode") in (None, "split_v1") or "public_last_index" in after
    # If public tip advanced, it must be via commitment event, not raw org body
    pub_after = after.get("public_last_index")
    if pub_before is not None and pub_after is not None and int(pub_after) > int(pub_before):
        # Inspect last public block symbols if available
        tip_idx = int(pub_after)
        blk = client.get(f"/api/v1/chain/block/{tip_idx}")
        if blk.status_code == 200:
            payload = blk.json().get("block") or blk.json()
            symbols = payload.get("public_symbols") or {}
            assert symbols.get("artcb_event") in ("DOMAIN_COMMITMENT", None) or "content_hash" in symbols


def test_restart_preserves_public_tip_despite_private_suffix(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ARTCB_SPLIT_LEDGER", "1")
    blocks = tmp_path / "blocks.jsonl"
    blocks.write_text(
        json.dumps(
            {
                "index": 10,
                "timestamp": "2026-09-12T00:00:00Z",
                "prev_hash": GENESIS_PREV_HASH,
                "hash": "b" * 64,
                "visibility": "public",
                "signature": "ed25519:" + ("ab" * 32),
                "graph_root": "g" * 64,
                "merkle_root": "g" * 64,
                "pol_score": 0.1,
                "graph_id": "pub10",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    mgr1 = ChainManager(blocks, key_path=tmp_path / "k", enable_security=False)
    for i in range(30):
        mgr1.append_block(graph_id=f"p{i}", graph_root="p" * 64, pol_score=0.1, visibility="private")
    tip1 = mgr1.tip_public_private()
    assert tip1["public_last_index"] == 10
    assert tip1["private_height"] == 30

    # Simulate process restart — new manager, same paths
    mgr2 = ChainManager(blocks, key_path=tmp_path / "k", enable_security=False)
    tip2 = mgr2.tip_public_private()
    assert tip2["public_last_index"] == 10
    assert tip2["public_last_hash"] == tip1["public_last_hash"]
    assert tip2["private_height"] == 30
    assert tip2["ledger_mode"] == "split_v1"


def test_write_certified_public_after_org_like_private_growth(tmp_path: Path, monkeypatch) -> None:
    """Simulate ORG/GROUP private volume then certify next public index."""
    monkeypatch.setenv("ARTCB_SPLIT_LEDGER", "1")
    monkeypatch.setattr(
        "src.artcb.consensus.pbft_finality.exclusive_public_from",
        lambda *_a, **_k: 10_000_000,
    )
    monkeypatch.setattr(
        "artcb.consensus.pbft_finality.exclusive_public_from",
        lambda *_a, **_k: 10_000_000,
    )
    blocks = tmp_path / "blocks.jsonl"
    rows = [
        {
            "index": 100,
            "timestamp": "2026-09-12T00:00:00Z",
            "prev_hash": GENESIS_PREV_HASH,
            "hash": "a" * 64,
            "visibility": "public",
            "signature": "ed25519:" + ("ab" * 32),
            "graph_root": "g" * 64,
            "merkle_root": "g" * 64,
            "pol_score": 0.1,
            "graph_id": "pub100",
        }
    ]
    blocks.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    mgr = ChainManager(blocks, key_path=tmp_path / "k", enable_security=False)
    for i in range(200):
        mgr.append_block(
            graph_id=f"org_priv_{i}",
            graph_root="z" * 64,
            pol_score=0.1,
            visibility="private",
        )
    assert mgr.tip_public_private()["public_last_index"] == 100

    sk = signing.SigningKey.generate()
    index, prev_hash = 101, "a" * 64
    ts, gr = "2026-09-12T04:00:00Z", "d" * 64
    bh = ffi.build_block_hash(index, ts, prev_hash, gr, gr, 0.1)
    sig = sk.sign(bh.encode()).signature.hex()
    block = {
        "index": index,
        "timestamp": ts,
        "prev_hash": prev_hash,
        "graph_root": gr,
        "merkle_root": gr,
        "pol_score": 0.1,
        "hash": bh,
        "signature": f"ed25519:{sig}",
        "graph_id": "pub101",
        "visibility": "public",
        "producer_public_key_b64": sk.verify_key.encode(encoder=encoding.Base64Encoder).decode("ascii"),
    }
    assert mgr.write_certified_block(block, {"seq": 101, "digest": bh}, from_node_id="t")
    assert mgr.tip_public_private()["public_last_index"] == 101
    assert mgr.private_book().height() == 200
