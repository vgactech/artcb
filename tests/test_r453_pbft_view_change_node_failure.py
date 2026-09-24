"""R453 — Tests PBFT view-change + panne nœud (Issues #86 / #88).

Couverture :
  V01 — primary_of() : déterminisme et rotation modulo
  V02 — VIEW-CHANGE : émission + vérification cryptographique
  V03 — VIEW-CHANGE : rejet si vue non croissante (stale)
  V04 — VIEW-CHANGE : rejet si replica_id inconnu du registry
  V05 — Quorum VIEW-CHANGE : Q=3 replicas nécessaires pour NEW-VIEW
  V06 — Quorum VIEW-CHANGE : 2 replicas insuffisant (Q-1)
  V07 — NEW-VIEW : émission par le nouveau primaire
  V08 — NEW-VIEW : vérification correcte après quorum
  V09 — NEW-VIEW : rejet si primaire incorrect (replay)
  V10 — NEW-VIEW : rejet si digest VC incorrect
  V11 — install_new_view : avance d'état cohérente
  V12 — install_new_view : rejet si vue stale
  V13 — Panne primaire #88 : 1 nœud mort → quorum maintenu (N=4 F=1 Q=3)
  V14 — Panne primaire #88 : 2 nœuds morts → below_quorum=True
  V15 — next_reachable_view : skip vues dont le primaire est injoignable
  V16 — Ledger split public/privé : is_public_block() discrimine correctement
  V17 — Ledger split : ensure_split_ledgers() migration sans perte
  V18 — accept_view_change : double envoi même replica → dédupliqué
  V19 — VIEW-CHANGE : multi-vues simultanées → isolation correcte
  V20 — Liveness N=3 (nœud mort absent) : quorum toujours formable
  V21 — Liveness N=2 (2 nœuds morts) : below_quorum=True
  V22 — pbft_view_store snapshot expose processes_stay_up=True
  V23 — VIEW-CHANGE : signature corrompue → verify_view_change=False
  V24 — NEW-VIEW : clé PQC absente tolérée (D-032 fenêtre Ed25519)
  V25 — view_changes() filtre les lignes JSON invalides
"""

from __future__ import annotations

import base64
import json
import tempfile
from pathlib import Path
from typing import Any

import pytest

# ---------------------------------------------------------------------------
# Helpers d'import
# ---------------------------------------------------------------------------
from src.artcb.consensus.liveness import assess_liveness
from src.artcb.consensus.pbft_view import (
    PbftViewStore,
    primary_of,
    verify_new_view,
    verify_view_change,
    vc_digest,
    vc_message,
    next_reachable_view,
)
from src.artcb.consensus.replica_identity import (
    ReplicaKeyBinding,
    clear_test_replica_registry,
    install_test_replica_registry,
)
from src.artcb.chain.manager import ChainManager
from src.artcb.chain.split_ledger import (
    ensure_split_ledgers,
    is_public_block,
    public_blocks_path,
    private_blocks_path,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_chain(tmpdir: Path, *, replica_id: str = "ovh-node-2") -> tuple[ChainManager, PbftViewStore]:
    """Crée un ChainManager + PbftViewStore de test avec clés réelles."""
    blocks_p = tmpdir / "blocks.jsonl"
    blocks_p.touch()
    key_p = tmpdir / "chain.key"
    chain = ChainManager(blocks_p, key_p, enable_security=True)
    store = PbftViewStore(tmpdir, replica_id=replica_id)
    return chain, store


def _install_registry_for(*chains_and_ids: tuple[ChainManager, str]) -> None:
    """Installe un registry test avec les clés Ed25519 de chaque (chain, node_id)."""
    mapping: dict[str, Any] = {}
    for chain, nid in chains_and_ids:
        mapping[nid] = {
            "node_id": nid,
            "ed25519_b64": chain.public_key_b64,
            "pqc_b64": "",
            "activation_epoch": 0,
            "not_after_epoch": 0,
            "revoked": False,
            "require_pqc": False,
        }
    install_test_replica_registry(mapping)


@pytest.fixture(autouse=True)
def _clear_registry():
    """Nettoyer le registry de test après chaque test."""
    yield
    clear_test_replica_registry()


# ---------------------------------------------------------------------------
# V01 — primary_of() déterminisme et rotation
# ---------------------------------------------------------------------------

def test_v01_primary_of_determinism():
    """primary_of() doit être déterministe et couvrir toutes les replicas."""
    replicas = ["ovh-node-1", "ovh-node-2", "aws-node-3", "ovh-node-4", "mac-node-local"]
    seen = set()
    for v in range(len(replicas) * 2):
        p = primary_of(v)
        assert p in replicas, f"primary_of({v})={p} inconnu"
        seen.add(p)
    # Toutes les replicas doivent apparaître dans un cycle complet
    assert seen == set(replicas), f"Replicas non couvertes : {set(replicas) - seen}"
    # Déterminisme : même appel → même résultat
    for v in range(10):
        assert primary_of(v) == primary_of(v), "non-déterministe"


def test_v01b_primary_rotation_modulo():
    """primary_of(v) == primary_of(v + N)."""
    n = 5  # N actuel
    for v in range(n):
        assert primary_of(v) == primary_of(v + n), f"rotation brisée à v={v}"


# ---------------------------------------------------------------------------
# V02 — VIEW-CHANGE émission + vérification
# ---------------------------------------------------------------------------

def test_v02_emit_view_change_valid(tmp_path):
    chain, store = _make_chain(tmp_path, replica_id="ovh-node-2")
    _install_registry_for((chain, "ovh-node-2"))

    row = store.emit_view_change(
        chain, view=1, height=42, last_hash="a" * 64, reason="primary_unreachable"
    )

    assert row["kind"] == "view-change"
    assert row["view"] == 1
    assert row["from_view"] == 0
    assert row["height"] == 42
    assert row["replica_id"] == "ovh-node-2"
    assert verify_view_change(row), "verify_view_change doit retourner True"


# ---------------------------------------------------------------------------
# V03 — VIEW-CHANGE rejet vue stale
# ---------------------------------------------------------------------------

def test_v03_view_change_stale_view(tmp_path):
    chain, store = _make_chain(tmp_path, replica_id="ovh-node-2")
    _install_registry_for((chain, "ovh-node-2"))

    # Avancer à vue 2
    store.emit_view_change(chain, view=1, height=0, last_hash="0" * 64, reason="test")
    # Install new view pour avancer l'état
    _vc1 = store.view_changes(1)

    # Tenter d'émettre view=1 alors que la vue courante est toujours 0 (pas encore installée)
    # view=1 > 0 → OK pour la 1ère émission, donc tester view=0 qui est ≤ from_view=0
    with pytest.raises(ValueError, match="view_not_greater"):
        store.emit_view_change(chain, view=0, height=0, last_hash="0" * 64, reason="replay")


# ---------------------------------------------------------------------------
# V04 — VIEW-CHANGE rejet replica inconnu
# ---------------------------------------------------------------------------

def test_v04_view_change_unknown_replica(tmp_path, monkeypatch):
    """Avec binding enforced et registry vide, verify_view_change doit rejeter."""
    chain, store = _make_chain(tmp_path, replica_id="ovh-node-2")
    # Installer un registry vide (ovh-node-2 absent) + forcer binding_enforced=True
    _install_registry_for()  # registry test vide
    monkeypatch.setenv("ARTCB_REQUIRE_REPLICA_BINDING", "1")

    row = store.emit_view_change(
        chain, view=1, height=0, last_hash="0" * 64, reason="test"
    )
    # Binding enforced + replica absente du registry → unregistered_replica_key → rejet
    assert not verify_view_change(row), "binding enforced + registry vide doit rejeter"


# ---------------------------------------------------------------------------
# V05 — Quorum VIEW-CHANGE Q=3
# ---------------------------------------------------------------------------

def test_v05_view_change_quorum_q3(tmp_path):
    """Q=3 replicas → quorum atteint."""
    dirs = [tmp_path / f"n{i}" for i in range(1, 4)]
    for d in dirs:
        d.mkdir()

    replica_ids = ["ovh-node-2", "aws-node-3", "ovh-node-4"]
    chains = []
    for d, rid in zip(dirs, replica_ids):
        c, _s = _make_chain(d, replica_id=rid)
        chains.append((c, rid))

    _install_registry_for(*chains)

    # Créer un store centralisé (le primaire candidat ovh-node-2 vue 1)
    store = PbftViewStore(tmp_path / "n1", replica_id="ovh-node-2")

    # Chaque replica émet un VC
    vc_rows = []
    for (c, rid) in chains:
        s = PbftViewStore(tmp_path / f"n{replica_ids.index(rid)+1}", replica_id=rid)
        row = s.emit_view_change(c, view=1, height=10, last_hash="b" * 64, reason="primary_dead")
        store.accept_view_change(row)
        vc_rows.append(row)

    quorum = store.quorum_for(1)
    assert quorum["ok"], f"quorum attendu True, obtenu: {quorum}"
    assert quorum["count"] == 3


# ---------------------------------------------------------------------------
# V06 — Quorum insuffisant (Q-1 = 2)
# ---------------------------------------------------------------------------

def test_v06_quorum_insufficient_q_minus_1(tmp_path):
    """2 replicas (Q-1) → quorum non atteint."""
    dirs = [tmp_path / "n1", tmp_path / "n2"]
    for d in dirs:
        d.mkdir()

    replica_ids = ["ovh-node-2", "aws-node-3"]
    chains_and_ids = []
    for d, rid in zip(dirs, replica_ids):
        c, _ = _make_chain(d, replica_id=rid)
        chains_and_ids.append((c, rid))

    _install_registry_for(*chains_and_ids)

    store = PbftViewStore(tmp_path / "n1", replica_id="ovh-node-2")
    for (c, rid) in chains_and_ids:
        s = PbftViewStore(tmp_path / f"n{replica_ids.index(rid)+1}", replica_id=rid)
        row = s.emit_view_change(c, view=1, height=5, last_hash="c" * 64, reason="test")
        store.accept_view_change(row)

    quorum = store.quorum_for(1)
    assert not quorum["ok"], "2 replicas (Q-1) ne doit pas former quorum"
    assert quorum["count"] == 2


# ---------------------------------------------------------------------------
# V07 + V08 — NEW-VIEW émission et vérification
# ---------------------------------------------------------------------------

def test_v07_v08_new_view_emission_and_verify(tmp_path):
    """Quorum Q=3 → NEW-VIEW émis par le nouveau primaire (ovh-node-2 = view 1)."""
    replica_ids = ["ovh-node-2", "aws-node-3", "ovh-node-4"]
    chains_and_ids = []
    for i, rid in enumerate(replica_ids):
        d = tmp_path / f"n{i}"
        d.mkdir()
        c, _ = _make_chain(d, replica_id=rid)
        chains_and_ids.append((c, rid))

    _install_registry_for(*chains_and_ids)

    # Store du nouveau primaire = ovh-node-2 (primary_of(1))
    primary_chain, primary_rid = chains_and_ids[0]  # ovh-node-2
    assert primary_of(1) == "ovh-node-2", "primary_of(1) doit être ovh-node-2"

    primary_store = PbftViewStore(tmp_path / "n0", replica_id="ovh-node-2")

    vc_rows = []
    for i, (c, rid) in enumerate(chains_and_ids):
        d = tmp_path / f"n{i}"
        s = PbftViewStore(d, replica_id=rid)
        row = s.emit_view_change(c, view=1, height=20, last_hash="d" * 64, reason="primary_dead")
        primary_store.accept_view_change(row)
        vc_rows.append(row)

    result = primary_store.emit_new_view(primary_chain, view=1)
    assert result["ok"], f"NEW-VIEW attendu OK: {result}"
    nv = result["new_view"]
    assert nv["kind"] == "new-view"
    assert nv["view"] == 1
    assert nv["primary"] == "ovh-node-2"
    # Vérification indépendante
    assert verify_new_view(nv, result["view_changes"]), "verify_new_view doit retourner True"


# ---------------------------------------------------------------------------
# V09 — NEW-VIEW rejet primaire incorrect
# ---------------------------------------------------------------------------

def test_v09_new_view_wrong_primary(tmp_path):
    """NEW-VIEW avec primary != primary_of(view) doit échouer."""
    replica_ids = ["ovh-node-2", "aws-node-3", "ovh-node-4"]
    chains_and_ids = []
    for i, rid in enumerate(replica_ids):
        d = tmp_path / f"n{i}"
        d.mkdir()
        c, _ = _make_chain(d, replica_id=rid)
        chains_and_ids.append((c, rid))

    _install_registry_for(*chains_and_ids)

    primary_chain, _ = chains_and_ids[0]
    primary_store = PbftViewStore(tmp_path / "n0", replica_id="ovh-node-2")

    vc_rows = []
    for i, (c, rid) in enumerate(chains_and_ids):
        s = PbftViewStore(tmp_path / f"n{i}", replica_id=rid)
        row = s.emit_view_change(c, view=1, height=5, last_hash="e" * 64, reason="test")
        primary_store.accept_view_change(row)
        vc_rows.append(row)

    result = primary_store.emit_new_view(primary_chain, view=1)
    nv = result["new_view"]

    # Altérer le primary
    tampered = dict(nv)
    tampered["primary"] = "ovh-node-4"  # mauvais primaire
    assert not verify_new_view(tampered, vc_rows), "primary altéré doit échouer"


# ---------------------------------------------------------------------------
# V10 — NEW-VIEW rejet digest VC incorrect
# ---------------------------------------------------------------------------

def test_v10_new_view_wrong_digest(tmp_path):
    """NEW-VIEW avec vc_digest altéré doit échouer."""
    replica_ids = ["ovh-node-2", "aws-node-3", "ovh-node-4"]
    chains_and_ids = []
    for i, rid in enumerate(replica_ids):
        d = tmp_path / f"n{i}"
        d.mkdir()
        c, _ = _make_chain(d, replica_id=rid)
        chains_and_ids.append((c, rid))

    _install_registry_for(*chains_and_ids)
    primary_chain, _ = chains_and_ids[0]
    primary_store = PbftViewStore(tmp_path / "n0", replica_id="ovh-node-2")

    vc_rows = []
    for i, (c, rid) in enumerate(chains_and_ids):
        s = PbftViewStore(tmp_path / f"n{i}", replica_id=rid)
        row = s.emit_view_change(c, view=1, height=5, last_hash="f" * 64, reason="test")
        primary_store.accept_view_change(row)
        vc_rows.append(row)

    result = primary_store.emit_new_view(primary_chain, view=1)
    nv = dict(result["new_view"])

    # Altérer le digest
    nv["vc_digest"] = "00" * 32
    assert not verify_new_view(nv, vc_rows), "vc_digest altéré doit échouer"


# ---------------------------------------------------------------------------
# V11 — install_new_view : avance d'état
# ---------------------------------------------------------------------------

def test_v11_install_new_view_advances_state(tmp_path):
    """install_new_view doit mettre à jour view + primary dans le store."""
    replica_ids = ["ovh-node-2", "aws-node-3", "ovh-node-4"]
    chains_and_ids = []
    for i, rid in enumerate(replica_ids):
        d = tmp_path / f"n{i}"
        d.mkdir()
        c, _ = _make_chain(d, replica_id=rid)
        chains_and_ids.append((c, rid))

    _install_registry_for(*chains_and_ids)
    primary_chain, _ = chains_and_ids[0]
    primary_store = PbftViewStore(tmp_path / "n0", replica_id="ovh-node-2")

    assert primary_store.view == 0

    vc_rows = []
    for i, (c, rid) in enumerate(chains_and_ids):
        s = PbftViewStore(tmp_path / f"n{i}", replica_id=rid)
        row = s.emit_view_change(c, view=1, height=5, last_hash="a" * 64, reason="test")
        primary_store.accept_view_change(row)
        vc_rows.append(row)

    result = primary_store.emit_new_view(primary_chain, view=1)
    assert primary_store.view == 1, f"vue attendue 1, obtenue {primary_store.view}"
    assert primary_store.primary == "ovh-node-2"


# ---------------------------------------------------------------------------
# V12 — install_new_view rejet stale
# ---------------------------------------------------------------------------

def test_v12_install_new_view_stale(tmp_path):
    """Installer un NEW-VIEW pour une vue ≤ vue courante doit échouer."""
    replica_ids = ["ovh-node-2", "aws-node-3", "ovh-node-4"]
    chains_and_ids = []
    for i, rid in enumerate(replica_ids):
        d = tmp_path / f"n{i}"
        d.mkdir()
        c, _ = _make_chain(d, replica_id=rid)
        chains_and_ids.append((c, rid))

    _install_registry_for(*chains_and_ids)
    primary_chain, _ = chains_and_ids[0]
    primary_store = PbftViewStore(tmp_path / "n0", replica_id="ovh-node-2")

    vc_rows = []
    for i, (c, rid) in enumerate(chains_and_ids):
        s = PbftViewStore(tmp_path / f"n{i}", replica_id=rid)
        row = s.emit_view_change(c, view=1, height=5, last_hash="a" * 64, reason="test")
        primary_store.accept_view_change(row)
        vc_rows.append(row)

    primary_store.emit_new_view(primary_chain, view=1)
    assert primary_store.view == 1

    # Tenter de réinstaller vue=1 alors que vue courante=1
    result_stale = primary_store.install_new_view(
        primary_store._state.get("new_view") or {}, vc_rows
    )
    # install_new_view retourne ok=False si vue stale OU invalid
    assert not result_stale.get("ok"), "NEW-VIEW stale doit être refusé"


# ---------------------------------------------------------------------------
# V13 — Panne primaire #88 : 1 nœud mort → quorum maintenu (N=4 F=1)
# ---------------------------------------------------------------------------

def test_v13_one_node_dead_quorum_maintained():
    """1 nœud mort sur 4 → reachable=3 ≥ Q=3 → quorum maintenu."""
    report = assess_liveness(
        self_reachable=True,
        peer_reachable=[
            ("ovh-node-2", True, int(1e6)),
            ("aws-node-3", True, int(1e6)),
            ("ovh-node-4", False, None),  # mort
        ],
        include_self=True,
    )
    assert report.reachable == 3
    assert not report.below_quorum, "1 nœud mort sur 4 ne doit pas casser le quorum"
    assert not report.would_failover


# ---------------------------------------------------------------------------
# V14 — Panne 2 nœuds → below_quorum
# ---------------------------------------------------------------------------

def test_v14_two_nodes_dead_below_quorum():
    """2 nœuds morts sur 4 → reachable=2 < Q=3 → below_quorum=True."""
    report = assess_liveness(
        self_reachable=True,
        peer_reachable=[
            ("ovh-node-2", True, int(1e6)),
            ("aws-node-3", False, None),  # mort
            ("ovh-node-4", False, None),  # mort
        ],
        include_self=True,
    )
    assert report.reachable == 2
    assert report.below_quorum, "2 nœuds morts sur 4 doit déclencher below_quorum"


# ---------------------------------------------------------------------------
# V15 — next_reachable_view skip vues primaire injoignable
# ---------------------------------------------------------------------------

def test_v15_next_reachable_view_skips_unreachable(monkeypatch):
    """next_reachable_view doit sauter les vues dont le primaire est injoignable."""
    # primary_of(1)=ovh-node-2, primary_of(2)=aws-node-3 (joignable)
    reachable_map = {"aws-node-3": "http://1.2.3.4:8000"}

    # pbft_reachable_http_map est importée localement dans next_reachable_view
    # depuis src.artcb.node_registry — patcher là où elle est définie
    monkeypatch.setattr(
        "src.artcb.node_registry.pbft_reachable_http_map",
        lambda: reachable_map,
    )

    result = next_reachable_view(0)
    assert result["ok"], f"doit trouver une vue joignable: {result}"
    assert result["target_view"] == 2, f"vue cible attendue 2 (aws-node-3): {result}"
    assert result["primary"] == "aws-node-3"
    # ovh-node-2 (view=1) doit apparaître dans skipped
    skipped_views = [s["view"] for s in result["skipped"]]
    assert 1 in skipped_views, "view 1 (ovh-node-2) doit être dans skipped"


# ---------------------------------------------------------------------------
# V16 — Ledger split : is_public_block()
# ---------------------------------------------------------------------------

def test_v16_is_public_block_discrimination():
    """is_public_block() distingue correctement blocs publics/privés."""
    public_by_visibility = {"visibility": "public", "data": "test"}
    public_by_pbft_cert = {"pbft_cert": {"view": 1, "replicas": []}, "data": "test"}
    private_block = {"visibility": "private", "data": "secret"}
    unknown_block = {"data": "no_visibility"}

    assert is_public_block(public_by_visibility), "visibility=public → public"
    assert is_public_block(public_by_pbft_cert), "pbft_cert présent → public"
    assert not is_public_block(private_block), "visibility=private → privé"
    assert not is_public_block(unknown_block), "sans visibility → privé par défaut"


# ---------------------------------------------------------------------------
# V17 — Ledger split : ensure_split_ledgers()
# ---------------------------------------------------------------------------

def test_v17_ensure_split_ledgers_migration(tmp_path):
    """ensure_split_ledgers() migre sans perte : blocs publics → public/, privés → private/."""
    blocks_p = tmp_path / "blocks.jsonl"

    public_blk = {"height": 1, "visibility": "public", "data": "pub"}
    private_blk = {"height": 2, "visibility": "private", "data": "priv"}
    pbft_blk = {"height": 3, "pbft_cert": {"view": 0}, "data": "pbft"}

    with blocks_p.open("w") as f:
        f.write(json.dumps(public_blk) + "\n")
        f.write(json.dumps(private_blk) + "\n")
        f.write(json.dumps(pbft_blk) + "\n")

    result = ensure_split_ledgers(blocks_p)

    pub_p = public_blocks_path(blocks_p)
    priv_p = private_blocks_path(blocks_p)

    assert pub_p.is_file(), "public/blocks.jsonl doit exister"
    assert priv_p.is_file(), "private/blocks.jsonl doit exister"

    pub_blocks = [json.loads(l) for l in pub_p.read_text().splitlines() if l.strip()]
    priv_blocks = [json.loads(l) for l in priv_p.read_text().splitlines() if l.strip()]

    assert len(pub_blocks) == 2, f"2 blocs publics attendus, {len(pub_blocks)} obtenus"
    assert len(priv_blocks) == 1, f"1 bloc privé attendu, {len(priv_blocks)} obtenus"

    # Le fichier legacy doit être préservé
    assert blocks_p.is_file(), "legacy blocks.jsonl doit être préservé"


# ---------------------------------------------------------------------------
# V18 — accept_view_change dédupliqué (même replica)
# ---------------------------------------------------------------------------

def test_v18_accept_view_change_dedup(tmp_path):
    """Deux envois du même VC par la même replica → 1 seul enregistré (clé=replica_id)."""
    (tmp_path / "n0").mkdir()
    (tmp_path / "n1").mkdir()
    chain, _ = _make_chain(tmp_path / "n0", replica_id="ovh-node-2")
    _install_registry_for((chain, "ovh-node-2"))

    sender = PbftViewStore(tmp_path / "n1", replica_id="ovh-node-2")
    receiver = PbftViewStore(tmp_path / "n0", replica_id="aws-node-3")

    row = sender.emit_view_change(chain, view=1, height=5, last_hash="a" * 64, reason="test")
    receiver.accept_view_change(row)
    receiver.accept_view_change(row)  # doublon

    rows = receiver.view_changes(1)
    ids = [r["replica_id"] for r in rows]
    assert ids.count("ovh-node-2") == 1, "doublons doivent être dédupliqués"


# ---------------------------------------------------------------------------
# V19 — VIEW-CHANGE multi-vues : isolation
# ---------------------------------------------------------------------------

def test_v19_view_changes_multiview_isolation(tmp_path):
    """view_changes(v) ne retourne que les VC pour la vue v, pas les autres."""
    (tmp_path / "n0").mkdir()
    (tmp_path / "n1").mkdir()
    chain, _ = _make_chain(tmp_path / "n0", replica_id="ovh-node-2")
    _install_registry_for((chain, "ovh-node-2"))

    sender = PbftViewStore(tmp_path / "n1", replica_id="ovh-node-2")
    receiver = PbftViewStore(tmp_path / "n0", replica_id="aws-node-3")

    vc1 = sender.emit_view_change(chain, view=1, height=5, last_hash="a" * 64, reason="v1")
    receiver.accept_view_change(vc1)

    # Vue 2 : nécessite from_view=1, mais sender est à view=0 localement
    # On forge manuellement un VC pour vue=2 avec un autre sender
    (tmp_path / "n2").mkdir()
    chain2, _ = _make_chain(tmp_path / "n2", replica_id="aws-node-3")
    _install_registry_for((chain, "ovh-node-2"), (chain2, "aws-node-3"))
    sender2 = PbftViewStore(tmp_path / "n2", replica_id="aws-node-3")
    vc2 = sender2.emit_view_change(chain2, view=2, height=5, last_hash="b" * 64, reason="v2")
    receiver.accept_view_change(vc2)

    rows_v1 = receiver.view_changes(1)
    rows_v2 = receiver.view_changes(2)

    assert len(rows_v1) == 1, f"1 VC pour vue 1 attendu, {len(rows_v1)} obtenus"
    assert len(rows_v2) == 1, f"1 VC pour vue 2 attendu, {len(rows_v2)} obtenus"
    assert rows_v1[0]["view"] == 1
    assert rows_v2[0]["view"] == 2


# ---------------------------------------------------------------------------
# V20 — Liveness N=3 (1 nœud absent)
# ---------------------------------------------------------------------------

def test_v20_liveness_n3_quorum_maintained():
    """N=3 (1 nœud absent, pas de panne) : quorum maintenu pour 3 replicas."""
    report = assess_liveness(
        self_reachable=True,
        peer_reachable=[
            ("ovh-node-2", True, int(500_000)),
            ("aws-node-3", True, int(800_000)),
        ],
        include_self=True,
    )
    assert report.reachable == 3
    assert not report.below_quorum


# ---------------------------------------------------------------------------
# V21 — Liveness N=2 below_quorum
# ---------------------------------------------------------------------------

def test_v21_liveness_n2_below_quorum():
    """2 nœuds joignables sur 4 → below_quorum=True."""
    report = assess_liveness(
        self_reachable=True,
        peer_reachable=[
            ("ovh-node-2", False, None),
            ("aws-node-3", False, None),
            ("ovh-node-4", True, int(1e6)),
        ],
        include_self=True,
    )
    assert report.reachable == 2
    assert report.below_quorum


# ---------------------------------------------------------------------------
# V22 — snapshot processes_stay_up
# ---------------------------------------------------------------------------

def test_v22_snapshot_processes_stay_up(tmp_path):
    """snapshot() doit exposer processes_stay_up=True et not_block_append_bft=True."""
    _, store = _make_chain(tmp_path, replica_id="ovh-node-2")
    snap = store.snapshot()
    assert snap["processes_stay_up"] is True, "processes_stay_up doit être True"
    assert snap["not_block_append_bft"] is True, "not_block_append_bft doit être True"
    assert snap["scope"] == "pbft_view_change_settlement"
    assert "replicas" in snap
    assert "n" in snap and "f" in snap and "q" in snap


# ---------------------------------------------------------------------------
# V23 — VIEW-CHANGE signature corrompue → rejet
# ---------------------------------------------------------------------------

def test_v23_view_change_corrupted_signature(tmp_path):
    """VC avec signature corrompue doit être rejetée par verify_view_change."""
    chain, store = _make_chain(tmp_path, replica_id="ovh-node-2")
    _install_registry_for((chain, "ovh-node-2"))

    row = store.emit_view_change(chain, view=1, height=10, last_hash="c" * 64, reason="test")
    tampered = dict(row)
    tampered["signature"] = base64.b64encode(b"\x00" * 64).decode()

    assert not verify_view_change(tampered), "signature corrompue doit être rejetée"


# ---------------------------------------------------------------------------
# V24 — NEW-VIEW clé PQC absente tolérée (D-032 fenêtre Ed25519)
# ---------------------------------------------------------------------------

def test_v24_new_view_no_pqc_tolerated(tmp_path):
    """require_pqc=False dans le registry → NEW-VIEW accepté même si pqc_b64 vide ou présent.

    D-032 : fenêtre Ed25519 jusqu'au 2026-12-31. Le registry ne doit PAS exiger PQC
    (require_pqc=False). Le NEW-VIEW doit passer que liboqs soit disponible ou non.
    """
    replica_ids = ["ovh-node-2", "aws-node-3", "ovh-node-4"]
    chains_and_ids = []
    for i, rid in enumerate(replica_ids):
        d = tmp_path / f"n{i}"
        d.mkdir()
        c, _ = _make_chain(d, replica_id=rid)
        chains_and_ids.append((c, rid))

    # Registry avec require_pqc=False (D-032 fenêtre Ed25519)
    _install_registry_for(*chains_and_ids)

    primary_chain, _ = chains_and_ids[0]
    primary_store = PbftViewStore(tmp_path / "n0", replica_id="ovh-node-2")

    for i, (c, rid) in enumerate(chains_and_ids):
        s = PbftViewStore(tmp_path / f"n{i}", replica_id=rid)
        row = s.emit_view_change(c, view=1, height=5, last_hash="d" * 64, reason="no_pqc")
        primary_store.accept_view_change(row)

    result = primary_store.emit_new_view(primary_chain, view=1)
    # D-032 : NEW-VIEW doit être accepté (require_pqc=False dans le registry)
    assert result["ok"], f"NEW-VIEW doit passer avec require_pqc=False (D-032): {result}"
    nv = result["new_view"]
    # Le registry ne requiert pas PQC → verify_new_view retourne True
    assert verify_new_view(nv, result["view_changes"]), "verify_new_view doit passer (D-032)"
    # Le nœud local peut avoir liboqs → pqc peut être présent ou absent — les deux sont valides
    assert isinstance(nv.get("producer_pqc_b64"), str), "producer_pqc_b64 doit être une chaîne"


# ---------------------------------------------------------------------------
# V25 — view_changes() filtre les lignes invalides
# ---------------------------------------------------------------------------

def test_v25_view_changes_filters_bad_lines(tmp_path):
    """view_changes() doit ignorer les lignes JSON invalides ou mal formées."""
    chain, store = _make_chain(tmp_path, replica_id="ovh-node-2")
    _install_registry_for((chain, "ovh-node-2"))

    # Injecter des lignes invalides dans le fichier VC
    store.vc_path.parent.mkdir(parents=True, exist_ok=True)
    with store.vc_path.open("w") as f:
        f.write("not_json\n")
        f.write("{bad json}\n")
        f.write("\n")
        f.write('{"view":1,"kind":"view-change"}\n')  # valide JSON mais sans signature valide

    # Émettre un vrai VC pour vue=1
    row = store.emit_view_change(chain, view=1, height=0, last_hash="0" * 64, reason="test")

    rows = store.view_changes(1)
    # Seul le VC avec signature valide doit passer verify_view_change
    assert len(rows) == 1, f"1 VC valide attendu, {len(rows)} obtenus"
    assert rows[0]["replica_id"] == "ovh-node-2"
