"""Phase 221 — public commitment / transfer convergence + privacy (T-E47).

Scenario A: two local tips import DOMAIN_COMMITMENT without protocol_compatible.
Scenario B: after import the destination keeps the proof without the creator.
Scenario D: concurrent second propose is rejected (one canonical pending).
Scenario E/F: covered again (old controller / agent).
Salt: identical names do not share a public hash.
Transfer public block carries bindings, not wallet addresses.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from artcb.authz.anchor import anchor_public_commitment, commitment_public_symbols
from artcb.authz.domains import authority_binding, is_converging_public_event
from artcb.chain.manager import ChainManager
from artcb.p2p.public_archive import PublicBlockArchive
from artcb.p2p.sync import P2PSyncService
from artcb.wallet.manager import WalletManager
from api.main import create_app

TEST_PASSWORD = "monMotDePasse42!"


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("ARTCB_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("ARTCB_LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("ARTCB_NODE_ID", "node-paris")
    return TestClient(create_app())


def _user(name: str) -> dict:
    wallet = WalletManager().create_wallet(name=name, user_password=TEST_PASSWORD)
    return {"name": name, "address": wallet.address}


def _login(client: TestClient, name: str) -> dict:
    r = client.post("/api/v1/auth/login", json={"name": name, "password": TEST_PASSWORD})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['session_token']}"}


def test_scenario_a_and_b_converging_tip_without_protocol_flag(tmp_path: Path) -> None:
    key = tmp_path / "chain.key"
    path_a = tmp_path / "a" / "blocks.jsonl"
    path_b = tmp_path / "b" / "blocks.jsonl"
    chain_a = ChainManager(path_a, key_path=key, enable_security=False)
    chain_a.append_block(
        graph_id="genesis",
        graph_root="root0",
        pol_score=0.0,
        visibility="public",
        block_reward=0,
        source="authz_commitment",
    )
    path_b.parent.mkdir(parents=True)
    path_b.write_text(path_a.read_text(encoding="utf-8"), encoding="utf-8")
    chain_b = ChainManager(path_b, key_path=key, enable_security=False)
    assert chain_a.last_hash() == chain_b.last_hash()

    symbols = commitment_public_symbols(
        kind="org",
        domain_id="domain_demo",
        content_hash="ab" * 32,
        parent_id="ARTCB",
        issuer="artcb1alicexxxxxxxxxxxxxxxx",
        issued_at="2026-09-05T00:00:00Z",
    )
    anchor_public_commitment(chain_a, symbols=symbols)
    public = chain_a.list_blocks(visibility="public")
    assert any(is_converging_public_event(b) for b in public)

    svc = object.__new__(P2PSyncService)
    svc.chain = chain_b
    svc.archive = PublicBlockArchive(tmp_path / "b")
    svc.symbol_sync = None
    imported = svc.import_public_blocks(public, from_node_id="ovh1", extend_tip=False)
    assert imported >= 1
    # Scenario B: creator unused; destination still has the same tip.
    del chain_a
    assert chain_b.last_hash() == public[-1]["hash"]
    events = [(b.get("public_symbols") or {}).get("artcb_event") for b in chain_b.list_blocks(visibility="public")]
    assert "DOMAIN_COMMITMENT" in events


def test_salted_commitment_resists_name_collision(client: TestClient) -> None:
    _user("alice")
    h = _login(client, "alice")
    first = client.post("/api/v1/authz/orgs", json={"name": "Entreprise ABC"}, headers=h)
    second = client.post("/api/v1/authz/orgs", json={"name": "Entreprise ABC"}, headers=h)
    assert first.status_code == 200 and second.status_code == 200
    assert first.json()["content_hash"] != second.json()["content_hash"]
    assert "commitment_salt" not in first.json()
    chain = client.get("/api/v1/chain").json()
    blob = str(chain)
    assert "commitment_salt" not in blob


def test_transfer_public_block_hides_wallet_addresses(client: TestClient) -> None:
    alice = _user("alice")
    bob = _user("bob")
    h_a = _login(client, "alice")
    h_b = _login(client, "bob")
    org = client.post("/api/v1/authz/orgs", json={"name": "Privée"}, headers=h_a).json()
    proposed = client.post(
        f"/api/v1/authz/orgs/{org['organization_id']}/transfer",
        json={"new_controller": bob["address"], "reason": "SALE"},
        headers=h_a,
    )
    client.post("/api/v1/authz/transfers/accept", json={"tx_id": proposed.json()["tx_id"]}, headers=h_b)
    chain = client.get("/api/v1/chain").json()
    blocks = chain.get("blocks") or []
    xfers = [b for b in blocks if (b.get("public_symbols") or {}).get("artcb_event") == "ORG_CONTROL_TRANSFER"]
    assert xfers
    symbols = xfers[-1]["public_symbols"]
    assert symbols["reason"] == "SALE"
    assert symbols["old_authority_hash"] == authority_binding(alice["address"])
    assert symbols["new_authority_hash"] == authority_binding(bob["address"])
    assert alice["address"] not in str(xfers[-1])
    assert bob["address"] not in str(xfers[-1])
    assert "old_controller" not in symbols


def test_scenario_d_double_propose_rejected(client: TestClient) -> None:
    _user("alice")
    bob = _user("bob")
    carol = _user("carol")
    h_a = _login(client, "alice")
    org_id = client.post("/api/v1/authz/orgs", json={"name": "Race"}, headers=h_a).json()["organization_id"]
    first = client.post(
        f"/api/v1/authz/orgs/{org_id}/transfer",
        json={"new_controller": bob["address"], "reason": "SALE"},
        headers=h_a,
    )
    second = client.post(
        f"/api/v1/authz/orgs/{org_id}/transfer",
        json={"new_controller": carol["address"], "reason": "SALE"},
        headers=h_a,
    )
    assert first.status_code == 200
    assert second.status_code == 422
    assert "transfer_already_proposed" in second.text


def test_scenario_e_old_controller_cannot_propose_again(client: TestClient) -> None:
    alice = _user("alice")
    bob = _user("bob")
    carol = _user("carol")
    h_a = _login(client, "alice")
    h_b = _login(client, "bob")
    org_id = client.post("/api/v1/authz/orgs", json={"name": "Sold"}, headers=h_a).json()["organization_id"]
    proposed = client.post(
        f"/api/v1/authz/orgs/{org_id}/transfer",
        json={"new_controller": bob["address"], "reason": "SALE"},
        headers=h_a,
    )
    client.post("/api/v1/authz/transfers/accept", json={"tx_id": proposed.json()["tx_id"]}, headers=h_b)
    again = client.post(
        f"/api/v1/authz/orgs/{org_id}/transfer",
        json={"new_controller": carol["address"], "reason": "SALE"},
        headers=h_a,
    )
    assert again.status_code == 403
    auth = client.get(f"/api/v1/authz/orgs/{org_id}/authority").json()
    assert auth["controller_address"] == bob["address"]
    assert auth["founder_address"] == alice["address"]
