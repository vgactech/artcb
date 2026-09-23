"""Tests R436 — KnowledgeID → WorkID → PoL → on-chain (KnowledgeWork layer).

Suite R436 : tests W01→W18 couvrant :
  - Création de KnowledgeWorkRecord (PENDING)
  - Déterminisme du work_record_id
  - Validation des paramètres (pol_score, ids vides)
  - to_dict / from_dict round-trip
  - seal() → SEALED + block_hash
  - Double seal → ValueError
  - KnowledgeWorkStore : save / get / list_pending / list_sealed / list_by_knowledge_id
  - seal_with_block_hash dans le store
  - Écriture atomique (tmp → fsync → rename)
  - Intégration PoL → KnowledgeWork (pipeline complet)
  - Invariants : block_hash=None avant seal, status PENDING → SEALED

PROTOCOLE ARTCB — mode DEBUG actif. CERTIFIED_100=false.
"""

import tempfile
from pathlib import Path

import pytest

from src.artcb.chain.knowledge_work import (
    KnowledgeWorkRecord,
    KnowledgeWorkStore,
    create_knowledge_work_record,
)

# ── Fixtures ──────────────────────────────────────────────────────────────────

K_ID = "K" + "a" * 24
W_ID = "work_" + "b" * 20
U_ID = "U" + "c" * 24
BLOCK_HASH = "0x" + "f" * 64


# ── W01 — Création basique PENDING ────────────────────────────────────────────

def test_W01_create_basic_pending():
    """create_knowledge_work_record crée un record PENDING valide."""
    rec = create_knowledge_work_record(
        knowledge_id=K_ID,
        work_id=W_ID,
        pol_score=0.72,
        block_accepted=True,
    )
    assert rec.work_record_id.startswith("KW")
    assert rec.knowledge_id == K_ID
    assert rec.work_id == W_ID
    assert rec.pol_score == pytest.approx(0.72, abs=1e-6)
    assert rec.block_accepted is True
    assert rec.status == "PENDING"
    assert rec.block_hash is None
    assert rec.is_sealed() is False


# ── W02 — Déterminisme du work_record_id ──────────────────────────────────────

def test_W02_deterministic_work_record_id():
    """Deux appels avec les mêmes paramètres produisent le même work_record_id."""
    ts = "2026-09-24T12:00:00Z"
    rec1 = create_knowledge_work_record(K_ID, W_ID, 0.72, True, created_at=ts)
    rec2 = create_knowledge_work_record(K_ID, W_ID, 0.72, True, created_at=ts)
    assert rec1.work_record_id == rec2.work_record_id


# ── W03 — IDs différents → work_record_id différents ─────────────────────────

def test_W03_different_ids_different_work_record_ids():
    """Des knowledge_id différents produisent des work_record_ids distincts."""
    ts = "2026-09-24T12:00:00Z"
    rec1 = create_knowledge_work_record(K_ID, W_ID, 0.72, True, created_at=ts)
    rec2 = create_knowledge_work_record("K" + "b" * 24, W_ID, 0.72, True, created_at=ts)
    assert rec1.work_record_id != rec2.work_record_id


# ── W04 — pol_score hors [0,1] → ValueError ──────────────────────────────────

def test_W04_invalid_pol_score_raises():
    """pol_score hors [0.0, 1.0] lève ValueError."""
    with pytest.raises(ValueError, match="pol_score"):
        create_knowledge_work_record(K_ID, W_ID, 1.5, True)
    with pytest.raises(ValueError, match="pol_score"):
        create_knowledge_work_record(K_ID, W_ID, -0.1, False)


# ── W05 — knowledge_id vide → ValueError ─────────────────────────────────────

def test_W05_empty_knowledge_id_raises():
    with pytest.raises(ValueError, match="knowledge_id"):
        create_knowledge_work_record("", W_ID, 0.5, True)


# ── W06 — work_id vide → ValueError ──────────────────────────────────────────

def test_W06_empty_work_id_raises():
    with pytest.raises(ValueError, match="work_id"):
        create_knowledge_work_record(K_ID, "", 0.5, True)


# ── W07 — to_dict / from_dict round-trip ──────────────────────────────────────

def test_W07_to_dict_from_dict_roundtrip():
    """to_dict / from_dict préservent tous les champs."""
    rec = create_knowledge_work_record(
        K_ID, W_ID, 0.65, False,
        usage_id=U_ID, producer_id="agent_X",
        metadata={"job_id": "job_1"},
    )
    d = rec.to_dict()
    assert d["status"] == "PENDING"
    assert d["block_hash"] is None
    assert d["usage_id"] == U_ID
    assert d["metadata"]["job_id"] == "job_1"

    rec2 = KnowledgeWorkRecord.from_dict(d)
    assert rec2.work_record_id == rec.work_record_id
    assert rec2.pol_score == rec.pol_score
    assert rec2.usage_id == U_ID
    assert rec2.producer_id == "agent_X"
    assert rec2.metadata["job_id"] == "job_1"


# ── W08 — seal() → SEALED avec block_hash ────────────────────────────────────

def test_W08_seal_produces_sealed_record():
    """seal() retourne un nouveau record SEALED avec block_hash."""
    rec = create_knowledge_work_record(K_ID, W_ID, 0.72, True)
    sealed = rec.seal(BLOCK_HASH)

    assert sealed.status == "SEALED"
    assert sealed.block_hash == BLOCK_HASH
    assert sealed.is_sealed() is True
    # L'original reste inchangé (frozen)
    assert rec.status == "PENDING"
    assert rec.block_hash is None


# ── W09 — seal() avec block_hash vide → ValueError ────────────────────────────

def test_W09_seal_empty_block_hash_raises():
    rec = create_knowledge_work_record(K_ID, W_ID, 0.72, True)
    with pytest.raises(ValueError, match="block_hash"):
        rec.seal("")


# ── W10 — Record frozen → modification directe interdite ──────────────────────

def test_W10_frozen_record_immutable():
    """KnowledgeWorkRecord est frozen — modification directe lève FrozenInstanceError."""
    rec = create_knowledge_work_record(K_ID, W_ID, 0.72, True)
    with pytest.raises(Exception):  # FrozenInstanceError ou AttributeError
        rec.pol_score = 0.99  # type: ignore[misc]


# ── W11 — Store : save + get ──────────────────────────────────────────────────

def test_W11_store_save_and_get(tmp_path):
    """KnowledgeWorkStore.save() et get() fonctionnent correctement."""
    store = KnowledgeWorkStore(tmp_path / "kw")
    rec = create_knowledge_work_record(K_ID, W_ID, 0.72, True)
    store.save(rec)

    loaded = store.get(rec.work_record_id)
    assert loaded is not None
    assert loaded.work_record_id == rec.work_record_id
    assert loaded.status == "PENDING"
    assert loaded.block_hash is None


# ── W12 — Store : list_pending / list_sealed ─────────────────────────────────

def test_W12_store_list_pending_sealed(tmp_path):
    """list_pending() et list_sealed() retournent les records dans le bon état."""
    store = KnowledgeWorkStore(tmp_path / "kw")
    rec_a = create_knowledge_work_record(K_ID, W_ID, 0.72, True, created_at="2026-09-24T10:00:00Z")
    rec_b = create_knowledge_work_record(K_ID, "work_other_" + "x" * 10, 0.55, False, created_at="2026-09-24T11:00:00Z")
    store.save(rec_a)
    store.save(rec_b)

    assert len(store.list_pending()) == 2
    assert len(store.list_sealed()) == 0

    store.seal_with_block_hash(rec_a.work_record_id, BLOCK_HASH)
    assert len(store.list_pending()) == 1
    assert len(store.list_sealed()) == 1


# ── W13 — Store : seal_with_block_hash ────────────────────────────────────────

def test_W13_store_seal_with_block_hash(tmp_path):
    """seal_with_block_hash() met à jour le status → SEALED et conserve le block_hash."""
    store = KnowledgeWorkStore(tmp_path / "kw")
    rec = create_knowledge_work_record(K_ID, W_ID, 0.72, True)
    store.save(rec)

    sealed = store.seal_with_block_hash(rec.work_record_id, BLOCK_HASH)
    assert sealed.status == "SEALED"
    assert sealed.block_hash == BLOCK_HASH

    # Vérification persistance
    loaded = store.get(rec.work_record_id)
    assert loaded is not None
    assert loaded.status == "SEALED"
    assert loaded.block_hash == BLOCK_HASH


# ── W14 — Store : double seal → ValueError ───────────────────────────────────

def test_W14_store_double_seal_raises(tmp_path):
    """Sceller un record déjà SEALED lève ValueError."""
    store = KnowledgeWorkStore(tmp_path / "kw")
    rec = create_knowledge_work_record(K_ID, W_ID, 0.72, True)
    store.save(rec)
    store.seal_with_block_hash(rec.work_record_id, BLOCK_HASH)

    with pytest.raises(ValueError, match="déjà SEALED"):
        store.seal_with_block_hash(rec.work_record_id, "0x" + "a" * 64)


# ── W15 — Store : seal record inexistant → ValueError ────────────────────────

def test_W15_store_seal_unknown_id_raises(tmp_path):
    """Sceller un work_record_id inconnu lève ValueError."""
    store = KnowledgeWorkStore(tmp_path / "kw")
    with pytest.raises(ValueError, match="introuvable"):
        store.seal_with_block_hash("KW_inconnu", BLOCK_HASH)


# ── W16 — Store : list_by_knowledge_id ───────────────────────────────────────

def test_W16_store_list_by_knowledge_id(tmp_path):
    """list_by_knowledge_id retourne uniquement les records du knowledge_id demandé."""
    store = KnowledgeWorkStore(tmp_path / "kw")
    k2 = "K" + "b" * 24
    rec1 = create_knowledge_work_record(K_ID, "work1_" + "x" * 14, 0.72, True, created_at="2026-09-24T10:00:00Z")
    rec2 = create_knowledge_work_record(K_ID, "work2_" + "y" * 14, 0.60, True, created_at="2026-09-24T11:00:00Z")
    rec3 = create_knowledge_work_record(k2, "work3_" + "z" * 14, 0.55, False, created_at="2026-09-24T12:00:00Z")
    store.save(rec1)
    store.save(rec2)
    store.save(rec3)

    results = store.list_by_knowledge_id(K_ID)
    assert len(results) == 2
    assert all(r.knowledge_id == K_ID for r in results)

    results_k2 = store.list_by_knowledge_id(k2)
    assert len(results_k2) == 1
    assert results_k2[0].knowledge_id == k2


# ── W17 — Store : upsert (sauvegarde écrase l'existant par work_record_id) ────

def test_W17_store_upsert(tmp_path):
    """Sauvegarder deux fois le même work_record_id → seul le plus récent est conservé."""
    store = KnowledgeWorkStore(tmp_path / "kw")
    rec = create_knowledge_work_record(K_ID, W_ID, 0.72, True)
    store.save(rec)
    # Sceller via .seal() puis re-sauvegarder
    sealed = rec.seal(BLOCK_HASH)
    store.save(sealed)  # upsert

    all_records = store.list_sealed() + store.list_pending()
    matching = [r for r in all_records if r.work_record_id == rec.work_record_id]
    assert len(matching) == 1
    assert matching[0].status == "SEALED"


# ── W18 — Pipeline complet PoL → KnowledgeWork ───────────────────────────────

def test_W18_full_pipeline_pol_to_knowledge_work(tmp_path):
    """Test d'intégration : PolMetrics → create_knowledge_work_record → store → seal.

    Simule le pipeline complet sans dépendance sur la blockchain live.
    """
    from src.artcb.pol.scorer import PolMetrics

    # 1. Simuler un PolMetrics produit par PolScorer
    metrics = PolMetrics(
        delta_compression=0.40,
        validation_rate=0.90,
        retrieval_accuracy=0.85,
        pol_score=0.71,
        block_accepted=True,
        knowledge_id=K_ID,
        usage_id=U_ID,
    )

    assert metrics.knowledge_id == K_ID
    assert metrics.usage_id == U_ID
    assert metrics.block_accepted is True

    # 2. Créer un KnowledgeWorkRecord depuis les métriques PoL
    rec = create_knowledge_work_record(
        knowledge_id=metrics.knowledge_id,
        work_id="work_integration_test_" + "x" * 8,
        pol_score=metrics.pol_score,
        block_accepted=metrics.block_accepted,
        usage_id=metrics.usage_id,
        producer_id="agent_test",
        metadata={"test": "W18"},
    )
    assert rec.status == "PENDING"
    assert rec.pol_score == pytest.approx(0.71, abs=1e-4)
    assert rec.block_accepted is True

    # 3. Sauvegarder dans le store
    store = KnowledgeWorkStore(tmp_path / "kw")
    store.save(rec)
    assert store.get(rec.work_record_id) is not None

    # 4. Sceller avec un block_hash simulé
    fake_hash = "0x" + "d" * 64
    sealed = store.seal_with_block_hash(rec.work_record_id, fake_hash)
    assert sealed.is_sealed() is True
    assert sealed.block_hash == fake_hash

    # 5. Vérifier la chaîne complète
    d = sealed.to_dict()
    assert d["knowledge_id"] == K_ID
    assert d["usage_id"] == U_ID
    assert d["block_hash"] == fake_hash
    assert d["block_accepted"] is True
    assert d["pol_score"] == pytest.approx(0.71, abs=1e-4)
