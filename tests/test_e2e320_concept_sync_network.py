"""R320 — sync réseau du ConceptStore : C2-D cold-B via HTTP réel (ASGI).

R319 laissait C2-D en PARTIAL : un agent B « froid » recevait un ConceptPacket
(identifiants seulement) et ne pouvait rien reconstruire, parce que la définition
binaire (.arcb) restait sur le disque de A. La « synchronisation » du script R319
était un ``shutil.copytree`` local — pas une preuve réseau.

Ici : A publie un bundle binaire ACBN sur un nœud ARTCB (POST /concepts/publish),
B interroge ce nœud (GET /concepts/resolve) et ingère le binaire. Aucun texte
humain ne traverse le canal A→B.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from artcb.ir.concept import decode_concept_packet
from artcb.memory.agent_channel import AgentChannel
from artcb.memory.concept_store import ConceptStore
from artcb.memory.concept_sync import (
    ConceptBundleError,
    bundle_sha256,
    decode_concept_bundle,
    encode_concept_bundle,
    export_bundle,
    import_bundle,
)

TEXT = "Optimiser capacite sous charge IA."


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("ARTCB_DATA_DIR", str(tmp_path / "node"))
    monkeypatch.setenv("ARTCB_LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("ARTCB_ALLOW_MULTI_WALLET", "true")
    return TestClient(create_app())


def _session(client: TestClient, name: str) -> str:
    pwd = "pwd_r320_concepts"
    r = client.post("/api/v1/wallet/create", json={"name": name, "password": pwd})
    assert r.status_code == 200, r.text
    r = client.post("/api/v1/auth/login", json={"name": name, "password": pwd})
    assert r.status_code == 200, r.text
    return r.json()["session_token"]


# ── Format binaire ACBN ───────────────────────────────────────────────────────

def test_acbn_roundtrip_is_byte_exact() -> None:
    graphs = [("g1", b"\x00ARCB-blob-1"), ("g2", b"blob2" * 100)]
    data = encode_concept_bundle(graphs)
    assert data[:4] == b"ACBN"
    assert decode_concept_bundle(data) == graphs


def test_acbn_empty_bundle_is_valid() -> None:
    assert decode_concept_bundle(encode_concept_bundle([])) == []


@pytest.mark.parametrize(
    "corrupt",
    [
        b"",
        b"ACB",
        b"JSON" + b"\x00\x01" + b"\x00\x00\x00\x00",
        b"ACBN" + b"\x00\x63" + b"\x00\x00\x00\x00",       # version inconnue
        b"ACBN" + b"\x00\x01" + b"\x00\x00\x00\x01",       # count=1 mais tronqué
    ],
)
def test_acbn_rejects_corrupt_input(corrupt: bytes) -> None:
    with pytest.raises(ConceptBundleError):
        decode_concept_bundle(corrupt)


def test_acbn_carries_no_human_text(tmp_path: Path) -> None:
    a = AgentChannel(agent_id="a", store=ConceptStore(tmp_path / "a"))
    learn = a.learn_from_text("La voiture consomme beaucoup sous charge.")
    bundle = export_bundle(a.store, learn.concept_ids)
    assert b"voiture" not in bundle
    assert b"consomme" not in bundle


# ── Transfert direct A→B (sans réseau) : le bundle suffit ────────────────────

def test_cold_b_resolves_after_bundle_import(tmp_path: Path) -> None:
    a = AgentChannel(agent_id="a", store=ConceptStore(tmp_path / "a"))
    b = AgentChannel(agent_id="b", store=ConceptStore(tmp_path / "b"))
    learn = a.learn_from_text(TEXT)

    cold = b.receive_packet(learn.packet)
    assert cold.missing_concept_ids, "pré-condition : B est bien froid"

    report = b.ingest_bundle(a.export_bundle(learn.concept_ids))
    assert report["graphs"] >= 1

    warm = b.receive_packet(learn.packet)
    assert warm.requested_concept_ids == learn.concept_ids
    assert not warm.missing_concept_ids
    assert warm.found_graphs


def test_receive_packet_resolver_closes_the_gap(tmp_path: Path) -> None:
    """Le résolveur est appelé UNIQUEMENT pour les ConceptID manquants."""
    a = AgentChannel(agent_id="a", store=ConceptStore(tmp_path / "a"))
    b = AgentChannel(agent_id="b", store=ConceptStore(tmp_path / "b"))
    learn = a.learn_from_text(TEXT)
    asked: list[list[str]] = []

    def resolver(missing: list[str]) -> bytes:
        asked.append(missing)
        return a.export_bundle(missing)

    res = b.receive_packet(learn.packet, resolver=resolver)
    assert asked and asked[0], "le résolveur a bien été sollicité"
    assert not res.missing_concept_ids
    assert b.last_resolved_from_network >= 1

    # Deuxième passage : B sait déjà, donc aucun appel réseau.
    asked.clear()
    again = b.receive_packet(learn.packet, resolver=resolver)
    assert not asked
    assert not again.missing_concept_ids


def test_failing_resolver_stays_honest(tmp_path: Path) -> None:
    """Un réseau muet ne doit jamais produire un faux 'compris'."""
    a = AgentChannel(agent_id="a", store=ConceptStore(tmp_path / "a"))
    b = AgentChannel(agent_id="b", store=ConceptStore(tmp_path / "b"))
    learn = a.learn_from_text(TEXT)

    def broken(_missing: list[str]) -> bytes:
        raise ConnectionError("nœud injoignable")

    res = b.receive_packet(learn.packet, resolver=broken)
    assert res.missing_concept_ids
    assert b.last_resolved_from_network == 0


# ── Chemin réseau réel : publish → resolve via l'API du nœud ─────────────────

def test_publish_requires_bearer(client: TestClient, tmp_path: Path) -> None:
    a = AgentChannel(agent_id="a", store=ConceptStore(tmp_path / "a"))
    learn = a.learn_from_text(TEXT)
    r = client.post(
        "/api/v1/concepts/publish",
        content=a.export_bundle(learn.concept_ids),
        headers={"Content-Type": "application/octet-stream"},
    )
    assert r.status_code == 401
    assert r.json()["detail"] == "concept_publish_requires_bearer"


def test_publish_rejects_garbage(client: TestClient) -> None:
    tok = _session(client, "pub_garbage")
    r = client.post(
        "/api/v1/concepts/publish",
        content=b"{\"json\": \"not a bundle\"}",
        headers={
            "Content-Type": "application/octet-stream",
            "Authorization": f"Bearer {tok}",
        },
    )
    assert r.status_code == 400
    assert r.json()["detail"].startswith("invalid_bundle")


def test_c2_d_cold_b_over_network(client: TestClient, tmp_path: Path) -> None:
    """C2-D : A publie, B froid résout par le réseau, B comprend."""
    a = AgentChannel(agent_id="a", store=ConceptStore(tmp_path / "agent_a"))
    b = AgentChannel(agent_id="b", store=ConceptStore(tmp_path / "agent_b"))
    learn = a.learn_from_text(TEXT)

    # Aucun texte humain dans le paquet A→B.
    assert b"capacite" not in learn.packet
    assert decode_concept_packet(learn.packet) == learn.concept_ids

    # B froid : il ne peut rien reconstruire.
    assert b.receive_packet(learn.packet).missing_concept_ids

    # A publie le bundle binaire sur le nœud.
    tok = _session(client, "agent_a_pub")
    bundle = a.export_bundle(learn.concept_ids)
    pub = client.post(
        "/api/v1/concepts/publish",
        content=bundle,
        headers={
            "Content-Type": "application/octet-stream",
            "Authorization": f"Bearer {tok}",
            "X-ARTCB-Agent-Id": "agent_a",
        },
    )
    assert pub.status_code == 200, pub.text
    body = pub.json()
    assert body["bundle_sha256"] == bundle_sha256(bundle)
    assert body["graphs"] >= 1
    assert isinstance(body["ts_ns"], int) and body["ts_ns"] > 1_000_000_000_000_000_000
    assert isinstance(body["dur_ns"], int)

    # B résout via le réseau (lecture publique : pas de clé requise).
    def http_resolver(missing: list[str]) -> bytes:
        resp = client.get("/api/v1/concepts/resolve", params={"ids": ",".join(missing)})
        assert resp.status_code == 200, resp.text
        assert resp.headers["content-type"].startswith("application/octet-stream")
        assert resp.headers["X-ARTCB-Concept-Missing"] == ""
        assert resp.headers["X-ARTCB-Bundle-Sha256"] == bundle_sha256(resp.content)
        return resp.content

    res = b.receive_packet(learn.packet, resolver=http_resolver)
    assert not res.missing_concept_ids, "C2-D : B doit tout résoudre après le réseau"
    assert res.found_graphs
    assert b.last_resolved_from_network >= 1

    # B a réellement appris : plus besoin du réseau.
    assert not b.receive_packet(learn.packet).missing_concept_ids


def test_resolve_unknown_concept_is_honest(client: TestClient) -> None:
    r = client.get("/api/v1/concepts/resolve", params={"ids": "Kdeadbeefdeadbeef"})
    assert r.status_code == 200
    assert r.headers["X-ARTCB-Concept-Missing"] == "Kdeadbeefdeadbeef"
    assert decode_concept_bundle(r.content) == []


def test_concept_stats_and_meta(client: TestClient, tmp_path: Path) -> None:
    a = AgentChannel(agent_id="a", store=ConceptStore(tmp_path / "a"))
    learn = a.learn_from_text(TEXT)
    tok = _session(client, "stats_pub")
    client.post(
        "/api/v1/concepts/publish",
        content=a.export_bundle(learn.concept_ids),
        headers={
            "Content-Type": "application/octet-stream",
            "Authorization": f"Bearer {tok}",
        },
    )
    stats = client.get("/api/v1/concepts/stats")
    assert stats.status_code == 200
    assert stats.json()["concept_count"] >= 1

    meta = client.get(f"/api/v1/concepts/{learn.concept_ids[0]}")
    assert meta.status_code == 200
    assert meta.json()["concept_id"] == learn.concept_ids[0]
    assert client.get("/api/v1/concepts/Knot_a_real_concept").status_code == 404


def test_import_bundle_is_idempotent(tmp_path: Path) -> None:
    a = AgentChannel(agent_id="a", store=ConceptStore(tmp_path / "a"))
    learn = a.learn_from_text(TEXT)
    bundle = a.export_bundle(learn.concept_ids)
    store_b = ConceptStore(tmp_path / "b")
    first = import_bundle(store_b, bundle)
    count_after_first = store_b.concept_count()
    second = import_bundle(store_b, bundle)
    assert first["bundle_sha256"] == second["bundle_sha256"]
    assert store_b.concept_count() == count_after_first
