"""Phase 216 — Privacy enforcement & authorization engine (T-E43).

Avant : membership + visibility étaient un filtre de sélection, pas une ACL.
Après : authorize() sur les lectures ; GRANT/REVOKE versionnés ; DENY>ALLOW ;
plafond agent ; actor_address n'est plus une preuve.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from artcb.authz.engine import AuthorizationEngine
from artcb.authz.models import PolicyTx, Principal, ResourceRef
from artcb.groups.manager import GroupManager
from artcb.wallet.manager import WalletManager
from api.main import create_app

TEST_PASSWORD = "monMotDePasse42!"
DOC_X = "Document X confidentiel de C3 dans Sub2 — secret médical."
DOC_Y = "Document Y confidentiel de C3 dans Sub2 — secret financier."
DOC_C2 = "Notes privées de C2 — A3 ne doit jamais les voir."


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("ARTCB_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("ARTCB_LOG_DIR", str(tmp_path / "logs"))
    return TestClient(create_app())


def _create_user(client: TestClient, name: str) -> dict:
    wm = WalletManager()
    wallet = wm.create_wallet(name=name, user_password=TEST_PASSWORD)
    return {"name": name, "address": wallet.address}


def _login(client: TestClient, name: str) -> dict:
    r = client.post("/api/v1/auth/login", json={"name": name, "password": TEST_PASSWORD})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['session_token']}"}


def _store(client: TestClient, text: str, headers: dict, **extra) -> dict:
    enc = client.post("/api/v1/encode", json={"text": text})
    assert enc.status_code == 200, enc.text
    body = {"graph_id": enc.json()["graph_id"], **extra}
    r = client.post("/api/v1/store", json=body, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


# --------------------------------------------------------------------------- #
#  Moteur pur (sans HTTP) — DENY>ALLOW, plafond agent, least privilege
# --------------------------------------------------------------------------- #


def test_engine_deny_beats_allow(tmp_path: Path) -> None:
    groups = GroupManager(tmp_path / "groups")
    g = groups.create_group("C", "addr_c3")
    engine = AuthorizationEngine(groups=groups)
    resource = ResourceRef(visibility="group", group_id=g.group_id, resource_id="doc-x")
    a3 = Principal(address="addr_a3", kind="human", source="test")
    engine.set_policies(
        [
            PolicyTx(
                tx_id="g1",
                policy_version=1,
                effect="ALLOW",
                op="GRANT",
                subject="addr_a3",
                action="READ",
                resource=ResourceRef(group_id=g.group_id),
                issuer="addr_c3",
                issued_at="2026-09-04T00:00:00Z",
            ),
            PolicyTx(
                tx_id="d1",
                policy_version=2,
                effect="DENY",
                op="GRANT",
                subject="addr_a3",
                action="READ",
                resource=ResourceRef(group_id=g.group_id),
                issuer="addr_c3",
                issued_at="2026-09-04T00:00:01Z",
            ),
        ]
    )
    decision = engine.authorize(a3, "READ", resource)
    assert decision.effect == "DENY"
    assert decision.reason == "explicit_deny"


def test_engine_agent_cannot_exceed_human(tmp_path: Path) -> None:
    groups = GroupManager(tmp_path / "groups")
    engine = AuthorizationEngine(groups=groups)
    resource = ResourceRef(visibility="private", owner_address="addr_a3", resource_id="doc-x")
    agent = Principal(
        address="addr_a3",
        kind="agent",
        agent_id="agent-a3-01",
        parent_address="addr_a3",
        source="test",
    )
    engine.set_policies(
        [
            PolicyTx(
                tx_id="ag1",
                policy_version=1,
                effect="ALLOW",
                op="GRANT",
                subject="agent:agent-a3-01",
                action="READ",
                resource=ResourceRef(resource_id="doc-other"),
                issuer="addr_a3",
                issued_at="2026-09-04T00:00:00Z",
                subject_kind="agent",
                parent_subject="addr_a3",
            ),
        ]
    )
    # Human owns doc-x so human READ is ALLOW, but the agent grant is for another doc.
    decision = engine.authorize(agent, "READ", resource)
    assert decision.effect == "DENY"


def test_engine_subgroup_membership_is_not_parent_group(tmp_path: Path) -> None:
    groups = GroupManager(tmp_path / "groups")
    parent = groups.create_group("C", "addr_c3")
    groups.add_member_approved(parent.group_id, "addr_c3", "addr_c2", "contributor")
    sub = groups.create_subgroup(parent.group_id, "Sub2", "addr_c3")
    engine = AuthorizationEngine(groups=groups)
    resource = ResourceRef(
        visibility="group",
        group_id=parent.group_id,
        subgroup_id=sub.group_id,
        resource_id="doc-x",
        owner_address="addr_c3",
    )
    c2 = Principal(address="addr_c2", kind="human", source="test")
    c3 = Principal(address="addr_c3", kind="human", source="test")
    assert engine.authorize(c3, "READ", resource).allowed
    assert engine.authorize(c2, "READ", resource).effect == "DENY"


# --------------------------------------------------------------------------- #
#  HTTP P0 — private n'est plus lisible par graph_id / block_index
# --------------------------------------------------------------------------- #


def test_private_block_not_readable_without_identity(client: TestClient) -> None:
    owner = _create_user(client, "owner")
    headers = _login(client, "owner")
    stored = _store(
        client,
        "Mémo privé owner — ne doit pas fuir.",
        headers,
        visibility="private",
        wallet_name="owner",
        wallet_password=TEST_PASSWORD,
    )
    gid = stored["graph_id"]
    idx = stored["block_index"]

    assert client.get(f"/api/v1/graph/{gid}").status_code == 404
    assert client.get(f"/api/v1/chain/block/{idx}").status_code == 404
    assert client.get("/api/v1/chain").json()["count"] == 0
    search = client.post("/api/v1/search", json={"query": "privé", "graph_id": gid})
    assert search.json()["count"] == 0

    assert client.get(f"/api/v1/graph/{gid}", headers=headers).status_code == 200
    assert client.get(f"/api/v1/chain/block/{idx}", headers=headers).status_code == 200
    assert owner["address"]  # identity exists; unused beyond create


def test_unstored_graph_still_readable_after_encode(client: TestClient) -> None:
    """Working copy : pas encore gravé → graph_id reste un jeton de capacité."""
    enc = client.post("/api/v1/encode", json={"text": "Brouillon local avant gravure."})
    gid = enc.json()["graph_id"]
    assert client.get(f"/api/v1/graph/{gid}").status_code == 200
    dec = client.post("/api/v1/decode", json={"graph_id": gid})
    assert dec.status_code == 200


def test_actor_address_is_not_proof(client: TestClient) -> None:
    founder = _create_user(client, "founder")
    _create_user(client, "intruder")
    group = client.post(
        "/api/v1/groups",
        json={"name": "Org", "founder_address": founder["address"]},
        headers=_login(client, "founder"),
    ).json()
    enc = client.post("/api/v1/encode", json={"text": "Bloc groupe."})
    spoof = client.post(
        "/api/v1/store",
        json={
            "graph_id": enc.json()["graph_id"],
            "visibility": "group",
            "group_id": group["group_id"],
            "actor_address": founder["address"],
            "wallet_name": "intruder",
            "wallet_password": TEST_PASSWORD,
        },
    )
    assert spoof.status_code == 403
    assert spoof.json()["detail"] == "actor_address_mismatch"


# --------------------------------------------------------------------------- #
#  Scénario A3 → C3/Sub2/Document X  (pas Y, pas C2)
# --------------------------------------------------------------------------- #


def test_a3_grant_to_c3_sub2_document_x_not_y_not_c2(client: TestClient) -> None:
    a3 = _create_user(client, "A3")
    c2 = _create_user(client, "C2")
    c3 = _create_user(client, "C3")
    h_a3 = _login(client, "A3")
    h_c2 = _login(client, "C2")
    h_c3 = _login(client, "C3")

    org = client.post("/api/v1/authz/orgs", json={"name": "ORG A"}, headers=h_c3)
    assert org.status_code == 200, org.text

    group_a = client.post(
        "/api/v1/groups",
        json={"name": "Groupe A", "founder_address": a3["address"]},
        headers=h_a3,
    ).json()
    group_c = client.post(
        "/api/v1/groups",
        json={"name": "Groupe C", "founder_address": c3["address"]},
        headers=h_c3,
    ).json()
    client.post(
        f"/api/v1/groups/{group_c['group_id']}/members",
        json={"actor_address": c3["address"], "address": c2["address"]},
    )  # may 403 if direct invite disabled — C2 stays out of Sub2 either way

    sub2 = client.post(
        f"/api/v1/groups/{group_c['group_id']}/subgroups",
        json={"name": "Sub2"},
        headers=h_c3,
    )
    assert sub2.status_code == 200, sub2.text
    sub2_id = sub2.json()["group_id"]
    assert sub2.json()["parent_group_id"] == group_c["group_id"]

    stored_x = _store(
        client,
        DOC_X,
        h_c3,
        visibility="group",
        group_id=group_c["group_id"],
        subgroup_id=sub2_id,
        resource_id="doc-x",
        wallet_name="C3",
        wallet_password=TEST_PASSWORD,
    )
    stored_y = _store(
        client,
        DOC_Y,
        h_c3,
        visibility="group",
        group_id=group_c["group_id"],
        subgroup_id=sub2_id,
        resource_id="doc-y",
        wallet_name="C3",
        wallet_password=TEST_PASSWORD,
    )
    stored_c2 = _store(
        client,
        DOC_C2,
        h_c2,
        visibility="private",
        resource_id="doc-c2",
        wallet_name="C2",
        wallet_password=TEST_PASSWORD,
    )

    # A3 is a member of Groupe A, not of C/Sub2 — no implicit access.
    assert client.get(f"/api/v1/graph/{stored_x['graph_id']}", headers=h_a3).status_code == 404
    assert client.get(f"/api/v1/graph/{stored_y['graph_id']}", headers=h_a3).status_code == 404
    assert client.get(f"/api/v1/graph/{stored_c2['graph_id']}", headers=h_a3).status_code == 404
    assert client.get("/api/v1/chain", headers=h_a3).json()["count"] == 0

    grant = client.post(
        "/api/v1/authz/grants",
        headers=h_c3,
        json={
            "subject": a3["address"],
            "action": "READ",
            "resource": {"resource_id": "doc-x"},
        },
    )
    assert grant.status_code == 200, grant.text
    grant_id = grant.json()["tx_id"]
    assert grant.json()["policy_version"] >= 1
    assert grant.json()["op"] == "GRANT"

    got_x = client.get(f"/api/v1/graph/{stored_x['graph_id']}", headers=h_a3)
    assert got_x.status_code == 200, got_x.text
    assert "secret médical" in got_x.json()["source_text"]
    assert client.get(f"/api/v1/graph/{stored_y['graph_id']}", headers=h_a3).status_code == 404
    assert client.get(f"/api/v1/graph/{stored_c2['graph_id']}", headers=h_a3).status_code == 404
    assert client.get(f"/api/v1/chain/block/{stored_x['block_index']}", headers=h_a3).status_code == 200
    assert client.get(f"/api/v1/chain/block/{stored_y['block_index']}", headers=h_a3).status_code == 404

    # Agent of A3 has no mandate yet — cannot ride the human GRANT.
    agent_headers = {**h_a3, "X-ARTCB-Agent-Id": "agent-a3-01"}
    assert client.get(f"/api/v1/graph/{stored_x['graph_id']}", headers=agent_headers).status_code == 404

    agent_grant = client.post(
        "/api/v1/authz/grants",
        headers=h_c3,
        json={
            "subject": "agent-a3-01",
            "action": "READ",
            "subject_kind": "agent",
            "parent_subject": a3["address"],
            "resource": {"resource_id": "doc-x"},
        },
    )
    assert agent_grant.status_code == 200, agent_grant.text
    assert client.get(f"/api/v1/graph/{stored_x['graph_id']}", headers=agent_headers).status_code == 200
    assert client.get(f"/api/v1/graph/{stored_y['graph_id']}", headers=agent_headers).status_code == 404

    revoked = client.post(
        "/api/v1/authz/revoke",
        headers=h_c3,
        json={"grant_id": grant_id},
    )
    assert revoked.status_code == 200, revoked.text
    assert revoked.json()["op"] == "REVOKE"
    assert client.get(f"/api/v1/graph/{stored_x['graph_id']}", headers=h_a3).status_code == 404
    # Agent is clipped by the human ceiling after revoke.
    assert client.get(f"/api/v1/graph/{stored_x['graph_id']}", headers=agent_headers).status_code == 404

    assert group_a["group_id"]
    assert c2["address"]
