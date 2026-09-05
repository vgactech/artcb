"""Phase 218 — Domain Registry: a node hosts, the founder owns.

Alice creates an organisation from the API without installing a node.
The receiving process stores the Genesis body locally and publishes a
Domain Manifest (id + founder + hash + authorised hosts). Export / import
is founder-authorised and re-checks canonical_hash. The four official
nodes do not automatically receive the private body.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from artcb.authz.domains import REPLICATION_MATRIX, canonical_hash
from artcb.authz.registry import (
    DomainHashMismatch,
    build_export_bundle,
    verify_export_bundle,
)
from artcb.wallet.manager import WalletManager
from api.main import create_app

TEST_PASSWORD = "monMotDePasse42!"


def _boot(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, node_id: str) -> TestClient:
    monkeypatch.setenv("ARTCB_DATA_DIR", str(tmp_path / node_id / "data"))
    monkeypatch.setenv("ARTCB_LOG_DIR", str(tmp_path / node_id / "logs"))
    monkeypatch.setenv("ARTCB_NODE_ID", node_id)
    return TestClient(create_app())


def _user(name: str) -> dict:
    wallet = WalletManager().create_wallet(name=name, user_password=TEST_PASSWORD)
    return {"name": name, "address": wallet.address}


def _login(client: TestClient, name: str) -> dict:
    r = client.post("/api/v1/auth/login", json={"name": name, "password": TEST_PASSWORD})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['session_token']}"}


def test_matrix_says_node_hosts_does_not_own() -> None:
    assert REPLICATION_MATRIX["DOMAIN_MANIFEST"]["content"] == "id+founder+genesis_hash+authorized_nodes"
    assert REPLICATION_MATRIX["DOMAIN_BODY"]["replication"] == "org_domain_nodes"
    assert "ne le possède pas" in REPLICATION_MATRIX["DOMAIN_BODY"]["cest_a_dire"]


def test_alice_creates_org_without_being_a_node(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    client = _boot(tmp_path, monkeypatch, "node-paris")
    alice = _user("alice")
    headers = _login(client, "alice")
    created = client.post(
        "/api/v1/authz/orgs",
        json={"name": "ACME", "storage_mode": "artcb_managed"},
        headers=headers,
    )
    assert created.status_code == 200, created.text
    body = created.json()
    assert body["founder_address"] == alice["address"]
    assert body["ownership"]["node_owns_domain"] is False
    assert body["ownership"]["hosting_node_id"] == "node-paris"
    assert body["domain"]["domain_id"].startswith("domain_")
    assert body["domain"]["storage_mode"] == "artcb_managed"
    assert body["domain"]["authorized_nodes"] == ["node-paris"]
    assert body["domain"]["commitment_anchored_on_chain"] is True
    assert body["founder_address"] != body["ownership"]["hosting_node_id"]


def test_create_org_without_session_is_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    client = _boot(tmp_path, monkeypatch, "node-paris")
    r = client.post("/api/v1/authz/orgs", json={"name": "Nope"})
    assert r.status_code == 401


def test_public_registry_has_hash_not_body(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    client = _boot(tmp_path, monkeypatch, "node-paris")
    _user("alice")
    headers = _login(client, "alice")
    created = client.post("/api/v1/authz/orgs", json={"name": "ORG A"}, headers=headers)
    assert created.status_code == 200
    domain_id = created.json()["domain"]["domain_id"]

    public = client.get("/api/v1/authz/domains")
    assert public.status_code == 200
    blob = public.json()
    assert blob["contains_private_data"] is False
    assert blob["node_owns_domain"] is False
    assert blob["count"] == 1
    view = blob["domains"][0]
    assert view["genesis_hash"] == created.json()["content_hash"]
    assert "genesis_body" not in view
    assert "members" not in view
    assert "allowed_actions" not in view

    anonymous_body = client.get(f"/api/v1/authz/domains/{domain_id}/body")
    assert anonymous_body.status_code == 401

    locate = client.get(f"/api/v1/authz/domains/{domain_id}/locate")
    assert locate.json()["hosted_here"] is True
    assert locate.json()["node_owns_domain"] is False


def test_non_founder_cannot_export(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    client = _boot(tmp_path, monkeypatch, "node-paris")
    _user("alice")
    _user("bob")
    h_alice = _login(client, "alice")
    h_bob = _login(client, "bob")
    created = client.post("/api/v1/authz/orgs", json={"name": "ACME"}, headers=h_alice)
    domain_id = created.json()["domain"]["domain_id"]
    denied = client.post(f"/api/v1/authz/domains/{domain_id}/export", headers=h_bob)
    assert denied.status_code == 403
    exported = client.post(f"/api/v1/authz/domains/{domain_id}/export", headers=h_alice)
    assert exported.status_code == 200
    assert exported.json()["kind"] == "artcb_domain_export"
    assert exported.json()["export_hash"]
    verify_export_bundle(exported.json())


def test_tampered_body_fails_hash_check() -> None:
    from artcb.authz.registry import DomainManifest

    manifest = DomainManifest(
        domain_id="domain_test",
        domain_type="organization",
        subject_id="org_test",
        founder_address="artcb1alice",
        genesis_hash=canonical_hash({"organization_id": "org_test", "name": "ACME"}),
        hosting_node_id="node-a",
        authorized_nodes=["node-a"],
        created_at="2026-09-04T00:00:00Z",
    )
    body = {"organization_id": "org_test", "name": "ACME", "content_hash": manifest.genesis_hash}
    bundle = build_export_bundle(manifest, body, exported_by="artcb1alice")
    bundle["genesis_body"]["name"] = "HACKED"
    with pytest.raises(DomainHashMismatch):
        verify_export_bundle(bundle)


def test_body_stays_on_creating_node_until_import(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client_a = _boot(tmp_path, monkeypatch, "node-a")
    alice = _user("alice")
    h_a = _login(client_a, "alice")
    created = client_a.post(
        "/api/v1/authz/orgs",
        json={"name": "ACME", "storage_mode": "hybrid", "authorized_nodes": ["node-b"]},
        headers=h_a,
    )
    assert created.status_code == 200, created.text
    assert created.json()["domain"]["authorized_nodes"][0] == "node-a"
    assert "node-b" in created.json()["domain"]["authorized_nodes"]
    assert created.json()["domain"]["body_replicated"] is False
    domain_id = created.json()["domain"]["domain_id"]
    org_hash = created.json()["content_hash"]
    bundle = client_a.post(f"/api/v1/authz/domains/{domain_id}/export", headers=h_a).json()

    src = tmp_path / "node-a" / "data" / "wallets"
    dst = tmp_path / "node-b" / "data" / "wallets"
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src, dst)

    client_b = _boot(tmp_path, monkeypatch, "node-b")
    public_b = client_b.get("/api/v1/authz/domains")
    assert public_b.json()["count"] == 0
    assert client_b.get("/api/v1/authz/orgs").json()["count"] == 0

    h_b = _login(client_b, "alice")
    spoofed = dict(bundle)
    spoofed_body = dict(bundle["genesis_body"])
    spoofed_body["name"] = "HACKED"
    spoofed["genesis_body"] = spoofed_body
    bad = client_b.post("/api/v1/authz/domains/import", json={"bundle": spoofed}, headers=h_b)
    assert bad.status_code == 422

    imported = client_b.post("/api/v1/authz/domains/import", json={"bundle": bundle}, headers=h_b)
    assert imported.status_code == 200, imported.text
    assert imported.json()["imported"] is True
    assert imported.json()["ownership"]["node_owns_domain"] is False
    assert imported.json()["ownership"]["hosting_node_id"] == "node-b"
    assert imported.json()["commitment_anchored_on_chain"] is True

    orgs_b = client_b.get("/api/v1/authz/orgs").json()["orgs"]
    assert orgs_b[0]["content_hash"] == org_hash
    locate_b = client_b.get(f"/api/v1/authz/domains/{domain_id}/locate").json()
    assert locate_b["hosted_here"] is True

    orgs_a = client_a.get("/api/v1/authz/orgs").json()["orgs"]
    assert orgs_a[0]["content_hash"] == org_hash
    assert alice["address"]


def test_add_replica_is_intent_not_copy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    client = _boot(tmp_path, monkeypatch, "node-paris")
    _user("alice")
    headers = _login(client, "alice")
    created = client.post("/api/v1/authz/orgs", json={"name": "ACME"}, headers=headers)
    domain_id = created.json()["domain"]["domain_id"]
    replica = client.post(
        f"/api/v1/authz/domains/{domain_id}/replicas",
        json={"node_id": "node-frankfurt"},
        headers=headers,
    )
    assert replica.status_code == 200
    assert replica.json()["body_copied"] is False
    assert "node-frankfurt" in replica.json()["domain"]["authorized_nodes"]
    assert replica.json()["domain"]["body_replicated"] is False


def test_group_gets_a_domain_manifest(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    client = _boot(tmp_path, monkeypatch, "node-paris")
    alice = _user("alice")
    headers = _login(client, "alice")
    org = client.post("/api/v1/authz/orgs", json={"name": "ORG A"}, headers=headers)
    group = client.post(
        "/api/v1/groups",
        json={
            "name": "Groupe X",
            "founder_address": alice["address"],
            "organization_id": org.json()["organization_id"],
        },
        headers=headers,
    )
    assert group.status_code == 200, group.text
    assert group.json()["domain"]["domain_type"] == "group"
    assert group.json()["ownership"]["node_owns_domain"] is False
    commits = client.get("/api/v1/authz/commitments").json()
    kinds = {row["kind"] for row in commits["commitments"]}
    assert "domain" in kinds
    assert commits["contains_private_data"] is False


def test_unknown_storage_mode_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    client = _boot(tmp_path, monkeypatch, "node-paris")
    _user("alice")
    headers = _login(client, "alice")
    r = client.post(
        "/api/v1/authz/orgs",
        json={"name": "ACME", "storage_mode": "everywhere"},
        headers=headers,
    )
    assert r.status_code == 422
