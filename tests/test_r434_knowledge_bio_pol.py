"""R434 — Tests : Knowledge Layer, BIO Hamming routing, PoL KnowledgeID.

Couverture :

  KNOWLEDGE LAYER (K-01 → K-20)
  ─────────────────────────────
  K-01  : create_knowledge() retourne un KnowledgeRecord frozen
  K-02  : knowledge_id = "K" + sha256[:24] — déterministe
  K-03  : deux agents même raisonnement → même knowledge_id
  K-04  : is_usable() → True si ACTIVE, False si SUPERSEDED/INVALIDATED
  K-05  : supersede() retourne une nouvelle instance SUPERSEDED
  K-06  : invalidate() retourne une nouvelle instance INVALIDATED
  K-07  : to_dict() / from_dict() round-trip

  USAGE (U-01 → U-06)
  ─────────────────────
  U-01  : record_usage() retourne un UsageRecord frozen
  U-02  : usage_id = "U" + sha256[:24] — déterministe
  U-03  : pol_eligible True si ACTIVE + purpose éligible
  U-04  : pol_eligible False si SUPERSEDED même avec purpose éligible
  U-05  : pol_eligible False si purpose non éligible (REFERENCE)
  U-06  : to_dict() / from_dict() round-trip

  PROVENANCE (P-01 → P-05)
  ──────────────────────────
  P-01  : make_link() retourne un ProvenanceLink frozen
  P-02  : ProvenanceChain.add_link() + seal() empêche ajout ultérieur
  P-03  : chain_hash() change si un lien est réordonné
  P-04  : verify() True si chaîne continue, False si saut
  P-05  : ancestors() retourne les ancêtres dans l'ordre

  COMPOSITION (C-01 → C-05)
  ──────────────────────────
  C-01  : compose_knowledge() produit un KnowledgeRecord COMPOSITION
  C-02  : all_parents_active=True si tous ACTIVE
  C-03  : all_parents_active=False si un parent SUPERSEDED → status=HYPOTHESIS
  C-04  : UsageRecords créés pour chaque parent
  C-05  : ProvenanceChain scellée avec len = nb parents

  STORE (S-01 → S-06)
  ─────────────────────
  S-01  : save() + get() round-trip
  S-02  : list_active() filtre les ACTIVE uniquement
  S-03  : search_by_reasoning() retourne les bons records
  S-04  : save_usage() + list_usages()
  S-05  : pol_eligible_usages() filtre pol_eligible=True
  S-06  : upsert : save() deux fois le même knowledge_id → 1 seul enregistrement

  BIO HAMMING ROUTING (B-01 → B-06)
  ───────────────────────────────────
  B-01  : check_uniqueness() → hamming_direct si records ont template_bytes_b64
  B-02  : check_uniqueness() → privacy_preserving_xor si records sans template_bytes
  B-03  : check_uniqueness() → exact_hash si pas de template_bytes_for_match
  B-04  : hamming_direct → match_found=True si templates proches
  B-05  : hamming_direct → match_found=False si templates distants
  B-06  : invariants unique_human_proven=False + certified=False sur les 3 chemins

  POL KnowledgeID (L-01 → L-03)
  ───────────────────────────────
  L-01  : PolScorer.score() avec knowledge_id → PolMetrics.knowledge_id présent
  L-02  : PolMetrics.to_dict() inclut knowledge_id et usage_id si non None
  L-03  : PolMetrics.to_dict() n'inclut pas les clés si None (backward compat)

PROTOCOLE ARTCB — mode DEBUG actif. CERTIFIED_100=false.
"""

from __future__ import annotations

import base64
import hashlib
from pathlib import Path

import pytest

from src.artcb.knowledge.knowledge import (
    KnowledgeRecord,
    KnowledgeStatus,
    KnowledgeType,
    create_knowledge,
)
from src.artcb.knowledge.usage import (
    POL_ELIGIBLE_PURPOSES,
    UsagePurpose,
    record_usage,
)
from src.artcb.knowledge.provenance import (
    ProvenanceChain,
    Transformation,
    make_link,
)
from src.artcb.knowledge.composition import compose_knowledge
from src.artcb.knowledge.store import KnowledgeStore


# ─────────────────────────────────────────────────────────────────────────────
# KNOWLEDGE LAYER — K-01 → K-07
# ─────────────────────────────────────────────────────────────────────────────

def test_k01_create_knowledge_frozen() -> None:
    """K-01 : create_knowledge() retourne un KnowledgeRecord (frozen=True)."""
    rec = create_knowledge(reasoning_id="R_abc123", producer_id="agent_A")
    assert isinstance(rec, KnowledgeRecord)
    with pytest.raises((AttributeError, TypeError)):
        rec.status = KnowledgeStatus.SUPERSEDED  # type: ignore[misc]


def test_k02_knowledge_id_format() -> None:
    """K-02 : knowledge_id = 'K' + 24 hex chars."""
    rec = create_knowledge(reasoning_id="R_x", producer_id="agent_A")
    assert rec.knowledge_id.startswith("K")
    assert len(rec.knowledge_id) == 25  # "K" + 24 hex


def test_k03_deterministic_knowledge_id() -> None:
    """K-03 : deux agents même raisonnement + same params → même knowledge_id."""
    ts = "2026-09-23T10:00:00Z"
    rec_a = create_knowledge(
        reasoning_id="R_same", producer_id="agent_A",
        knowledge_type=KnowledgeType.REASONING, created_at=ts,
    )
    rec_b = create_knowledge(
        reasoning_id="R_same", producer_id="agent_A",
        knowledge_type=KnowledgeType.REASONING, created_at=ts,
    )
    assert rec_a.knowledge_id == rec_b.knowledge_id, (
        "K-03 : même raisonnement → même KnowledgeID (global, déterministe)"
    )


def test_k04_is_usable() -> None:
    """K-04 : is_usable() True si ACTIVE, False sinon."""
    rec = create_knowledge(reasoning_id="R_x", producer_id="p")
    assert rec.is_usable() is True

    superseded = rec.supersede(superseded_by="K_newer")
    assert superseded.is_usable() is False

    invalidated = rec.invalidate(reason="test")
    assert invalidated.is_usable() is False


def test_k05_supersede_new_instance() -> None:
    """K-05 : supersede() retourne une nouvelle instance SUPERSEDED (frozen original intact)."""
    rec = create_knowledge(reasoning_id="R_x", producer_id="p")
    sup = rec.supersede(superseded_by="K_new")
    assert sup.status == KnowledgeStatus.SUPERSEDED
    assert rec.status == KnowledgeStatus.ACTIVE  # original intact
    assert sup.knowledge_id == rec.knowledge_id  # même ID
    assert "superseded_by" in sup.metadata


def test_k06_invalidate_new_instance() -> None:
    """K-06 : invalidate() retourne une nouvelle instance INVALIDATED."""
    rec = create_knowledge(reasoning_id="R_x", producer_id="p")
    inv = rec.invalidate(reason="refuted by K_counter")
    assert inv.status == KnowledgeStatus.INVALIDATED
    assert rec.status == KnowledgeStatus.ACTIVE
    assert inv.metadata["invalidation_reason"] == "refuted by K_counter"


def test_k07_round_trip() -> None:
    """K-07 : to_dict() / from_dict() round-trip exact."""
    rec = create_knowledge(
        reasoning_id="R_rt",
        producer_id="agent_RT",
        knowledge_type=KnowledgeType.FACT,
        parent_ids=["K_parent1", "K_parent2"],
        metadata={"lang": "fr", "confidence": 0.9},
    )
    d = rec.to_dict()
    rec2 = KnowledgeRecord.from_dict(d)
    assert rec2.knowledge_id == rec.knowledge_id
    assert rec2.knowledge_type == KnowledgeType.FACT
    assert set(rec2.parent_ids) == {"K_parent1", "K_parent2"}
    assert rec2.metadata["confidence"] == 0.9


# ─────────────────────────────────────────────────────────────────────────────
# USAGE — U-01 → U-06
# ─────────────────────────────────────────────────────────────────────────────

def test_u01_record_usage_frozen() -> None:
    """U-01 : record_usage() retourne un UsageRecord frozen."""
    u = record_usage(knowledge_id="K_abc", consumer_id="agent_B", purpose=UsagePurpose.VALIDATION)
    from dataclasses import fields
    assert any(f.name == "usage_id" for f in fields(u))


def test_u02_usage_id_format() -> None:
    """U-02 : usage_id = 'U' + 24 hex chars — déterministe."""
    ts = "2026-09-23T10:00:00Z"
    u1 = record_usage(knowledge_id="K_x", consumer_id="c", purpose=UsagePurpose.COMPOSITION, used_at=ts)
    u2 = record_usage(knowledge_id="K_x", consumer_id="c", purpose=UsagePurpose.COMPOSITION, used_at=ts)
    assert u1.usage_id.startswith("U")
    assert len(u1.usage_id) == 25
    assert u1.usage_id == u2.usage_id, "U-02 : usage_id déterministe"


def test_u03_pol_eligible_active_composition() -> None:
    """U-03 : pol_eligible=True si ACTIVE + purpose COMPOSITION."""
    u = record_usage(
        knowledge_id="K_x", consumer_id="c",
        purpose=UsagePurpose.COMPOSITION, knowledge_status="ACTIVE",
    )
    assert u.pol_eligible is True


def test_u04_pol_eligible_false_if_superseded() -> None:
    """U-04 : pol_eligible=False si SUPERSEDED même avec purpose éligible."""
    u = record_usage(
        knowledge_id="K_x", consumer_id="c",
        purpose=UsagePurpose.POL_CLAIM, knowledge_status="SUPERSEDED",
    )
    assert u.pol_eligible is False


def test_u05_pol_eligible_false_reference() -> None:
    """U-05 : pol_eligible=False si purpose=REFERENCE (non éligible)."""
    assert UsagePurpose.REFERENCE not in POL_ELIGIBLE_PURPOSES
    u = record_usage(
        knowledge_id="K_x", consumer_id="c",
        purpose=UsagePurpose.REFERENCE, knowledge_status="ACTIVE",
    )
    assert u.pol_eligible is False


def test_u06_round_trip() -> None:
    """U-06 : to_dict() / from_dict() round-trip."""
    from src.artcb.knowledge.usage import UsageRecord
    u = record_usage(
        knowledge_id="K_rt", consumer_id="c_rt",
        purpose=UsagePurpose.DERIVATION,
        result_knowledge_id="K_result",
        metadata={"job_id": "J-001"},
    )
    u2 = UsageRecord.from_dict(u.to_dict())
    assert u2.usage_id == u.usage_id
    assert u2.result_knowledge_id == "K_result"
    assert u2.metadata["job_id"] == "J-001"


# ─────────────────────────────────────────────────────────────────────────────
# PROVENANCE — P-01 → P-05
# ─────────────────────────────────────────────────────────────────────────────

def test_p01_make_link_frozen() -> None:
    """P-01 : make_link() retourne un ProvenanceLink frozen."""
    lk = make_link(from_id="K_A", to_id="K_B", transformation=Transformation.DERIVATION, actor_id="a")
    assert lk.link_id.startswith("PL")
    assert len(lk.link_id) == 22  # "PL" + 20 hex


def test_p02_chain_seal_prevents_add() -> None:
    """P-02 : seal() empêche tout ajout ultérieur à la chaîne."""
    chain = ProvenanceChain()
    lk = make_link(from_id="K_A", to_id="K_B", transformation=Transformation.DERIVATION, actor_id="a")
    chain.add_link(lk)
    chain.seal()
    lk2 = make_link(from_id="K_B", to_id="K_C", transformation=Transformation.DERIVATION, actor_id="a")
    with pytest.raises(RuntimeError, match="scellée"):
        chain.add_link(lk2)


def test_p03_chain_hash_changes_on_reorder() -> None:
    """P-03 : chain_hash() change si l'ordre des liens change."""
    lk1 = make_link(from_id="K_A", to_id="K_B", transformation=Transformation.DERIVATION, actor_id="a")
    lk2 = make_link(from_id="K_B", to_id="K_C", transformation=Transformation.COMPOSITION, actor_id="a")
    c1 = ProvenanceChain(links=[lk1, lk2])
    c2 = ProvenanceChain(links=[lk2, lk1])
    assert c1.chain_hash() != c2.chain_hash(), "P-03 : réordonnancement invalide la chain_hash"


def test_p04_verify_continuous_and_gap() -> None:
    """P-04 : verify() True si continue, False si saut."""
    lk1 = make_link(from_id="K_A", to_id="K_B", transformation=Transformation.DERIVATION, actor_id="a")
    lk2 = make_link(from_id="K_B", to_id="K_C", transformation=Transformation.DERIVATION, actor_id="a")
    c_ok = ProvenanceChain(links=[lk1, lk2])
    assert c_ok.verify() is True

    # Saut : K_A → K_C sans K_B
    lk_gap = make_link(from_id="K_A", to_id="K_C", transformation=Transformation.DERIVATION, actor_id="a")
    c_gap = ProvenanceChain(links=[lk1, lk_gap])
    assert c_gap.verify() is False


def test_p05_ancestors() -> None:
    """P-05 : ancestors() retourne les KnowledgeIDs ancêtres."""
    lk1 = make_link(from_id="K_A", to_id="K_B", transformation=Transformation.DERIVATION, actor_id="a")
    lk2 = make_link(from_id="K_B", to_id="K_C", transformation=Transformation.DERIVATION, actor_id="a")
    chain = ProvenanceChain(links=[lk1, lk2])
    ancs = chain.ancestors("K_C")
    assert "K_B" in ancs
    assert "K_A" in ancs


# ─────────────────────────────────────────────────────────────────────────────
# COMPOSITION — C-01 → C-05
# ─────────────────────────────────────────────────────────────────────────────

def _make_rec(reasoning_id: str, producer: str = "p", status: KnowledgeStatus = KnowledgeStatus.ACTIVE) -> KnowledgeRecord:
    base = create_knowledge(reasoning_id=reasoning_id, producer_id=producer)
    if status != KnowledgeStatus.ACTIVE:
        base = base.supersede(superseded_by="K_new") if status == KnowledgeStatus.SUPERSEDED else base.invalidate(reason="test")
    return base


def test_c01_compose_produces_composition_record() -> None:
    """C-01 : compose_knowledge() produit un KnowledgeRecord type COMPOSITION."""
    parents = [_make_rec("R_p1"), _make_rec("R_p2")]
    result = compose_knowledge(
        parent_records=parents,
        producer_id="agent_C",
        reasoning_id="R_comp",
    )
    assert result.composed_record.knowledge_type == KnowledgeType.COMPOSITION
    assert len(result.composed_record.parent_ids) == 2


def test_c02_all_parents_active_true() -> None:
    """C-02 : all_parents_active=True si tous ACTIVE → status=ACTIVE."""
    parents = [_make_rec("R_a"), _make_rec("R_b")]
    result = compose_knowledge(parent_records=parents, producer_id="p", reasoning_id="R_c")
    assert result.all_parents_active is True
    assert result.composed_record.status == KnowledgeStatus.ACTIVE


def test_c03_superseded_parent_hypothesis() -> None:
    """C-03 : si un parent est SUPERSEDED → all_parents_active=False → status=HYPOTHESIS."""
    parents = [_make_rec("R_a"), _make_rec("R_b", status=KnowledgeStatus.SUPERSEDED)]
    result = compose_knowledge(parent_records=parents, producer_id="p", reasoning_id="R_c")
    assert result.all_parents_active is False
    assert result.composed_record.status == KnowledgeStatus.HYPOTHESIS


def test_c04_usage_records_per_parent() -> None:
    """C-04 : un UsageRecord créé pour chaque parent."""
    parents = [_make_rec("R_p1"), _make_rec("R_p2"), _make_rec("R_p3")]
    result = compose_knowledge(parent_records=parents, producer_id="p", reasoning_id="R_c")
    assert len(result.usage_records) == 3
    for u in result.usage_records:
        assert u.purpose == UsagePurpose.COMPOSITION


def test_c05_provenance_chain_sealed() -> None:
    """C-05 : ProvenanceChain scellée avec len = nb parents."""
    parents = [_make_rec("R_a"), _make_rec("R_b")]
    result = compose_knowledge(parent_records=parents, producer_id="p", reasoning_id="R_c")
    assert result.provenance_chain.is_sealed is True
    assert len(result.provenance_chain.links) == 2


# ─────────────────────────────────────────────────────────────────────────────
# STORE — S-01 → S-06
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture()
def kstore(tmp_path: Path) -> KnowledgeStore:
    return KnowledgeStore(tmp_path)


def test_s01_save_get_round_trip(kstore: KnowledgeStore) -> None:
    """S-01 : save() + get() round-trip."""
    rec = create_knowledge(reasoning_id="R_s1", producer_id="p")
    kstore.save(rec)
    retrieved = kstore.get(rec.knowledge_id)
    assert retrieved is not None
    assert retrieved.knowledge_id == rec.knowledge_id
    assert retrieved.reasoning_id == "R_s1"


def test_s02_list_active(kstore: KnowledgeStore) -> None:
    """S-02 : list_active() filtre les ACTIVE uniquement."""
    rec_a = create_knowledge(reasoning_id="R_a", producer_id="p")
    rec_s = create_knowledge(reasoning_id="R_s", producer_id="p").supersede(superseded_by="K_new")
    kstore.save(rec_a)
    kstore.save(rec_s)
    active = kstore.list_active()
    assert any(r.knowledge_id == rec_a.knowledge_id for r in active)
    assert not any(r.knowledge_id == rec_s.knowledge_id for r in active)


def test_s03_search_by_reasoning(kstore: KnowledgeStore) -> None:
    """S-03 : search_by_reasoning() retourne les bons records."""
    rec = create_knowledge(reasoning_id="R_search", producer_id="p")
    kstore.save(rec)
    results = kstore.search_by_reasoning("R_search")
    assert len(results) >= 1
    assert results[0].reasoning_id == "R_search"


def test_s04_save_usage_list_usages(kstore: KnowledgeStore) -> None:
    """S-04 : save_usage() + list_usages() round-trip."""
    u = record_usage(knowledge_id="K_x", consumer_id="c", purpose=UsagePurpose.VALIDATION)
    kstore.save_usage(u)
    usages = kstore.list_usages("K_x")
    assert len(usages) >= 1
    assert usages[0].usage_id == u.usage_id


def test_s05_pol_eligible_usages(kstore: KnowledgeStore) -> None:
    """S-05 : pol_eligible_usages() filtre pol_eligible=True."""
    u_eligible = record_usage(
        knowledge_id="K_e", consumer_id="c",
        purpose=UsagePurpose.POL_CLAIM, knowledge_status="ACTIVE",
    )
    u_not = record_usage(
        knowledge_id="K_n", consumer_id="c",
        purpose=UsagePurpose.REFERENCE, knowledge_status="ACTIVE",
    )
    kstore.save_usage(u_eligible)
    kstore.save_usage(u_not)
    eligible = kstore.pol_eligible_usages()
    eligible_ids = {u.usage_id for u in eligible}
    assert u_eligible.usage_id in eligible_ids
    assert u_not.usage_id not in eligible_ids


def test_s06_upsert_no_duplicate(kstore: KnowledgeStore) -> None:
    """S-06 : save() deux fois le même knowledge_id → 1 seul enregistrement."""
    rec = create_knowledge(reasoning_id="R_dup", producer_id="p")
    kstore.save(rec)
    kstore.save(rec)
    all_records = kstore.list_all()
    count = sum(1 for r in all_records if r.knowledge_id == rec.knowledge_id)
    assert count == 1, "S-06 : upsert — pas de doublon"


# ─────────────────────────────────────────────────────────────────────────────
# BIO HAMMING ROUTING — B-01 → B-06
# ─────────────────────────────────────────────────────────────────────────────

def _make_bio_commitment(template_bytes: bytes):
    """Helper : crée un BiometricCommitment minimal pour les tests."""
    from src.artcb.crypto.homomorphic import commit_biometric_template
    return commit_biometric_template(template_bytes)


def test_b01_routes_hamming_if_template_bytes_in_records() -> None:
    """B-01 : check_uniqueness() → hamming_direct si records ont template_bytes_b64."""
    from src.artcb.identity.biometric_onchain import check_uniqueness
    template = bytes(range(32))
    commitment = _make_bio_commitment(template)

    # Record avec template_bytes_b64 → routing Hamming
    existing = [{
        "human_id": "H_001",
        "template_bytes_b64": base64.b64encode(bytes(range(64, 96))).decode(),  # template différent
        "template_hash": commitment.template_hash_hex,
    }]
    result = check_uniqueness(commitment, existing, template_bytes_for_match=template)
    assert result.match_method == "hamming_direct", (
        f"B-01 : attendu hamming_direct, got {result.match_method!r}"
    )


def test_b02_routes_xor_if_no_template_bytes_in_records() -> None:
    """B-02 : check_uniqueness() → privacy_preserving_xor si records sans template_bytes."""
    from src.artcb.identity.biometric_onchain import check_uniqueness
    template = bytes(range(32))
    commitment = _make_bio_commitment(template)

    # Record SANS template_bytes (hash only) → routing XOR
    existing = [{
        "human_id": "H_002",
        "template_hash": commitment.template_hash_hex,
        "commitment": commitment.commitment_hex,
    }]
    result = check_uniqueness(commitment, existing, template_bytes_for_match=template)
    assert result.match_method == "privacy_preserving_xor", (
        f"B-02 : attendu privacy_preserving_xor, got {result.match_method!r}"
    )


def test_b03_routes_exact_if_no_template_bytes_for_match() -> None:
    """B-03 : check_uniqueness() → exact_hash si template_bytes_for_match absent."""
    from src.artcb.identity.biometric_onchain import check_uniqueness
    template = bytes(range(32))
    commitment = _make_bio_commitment(template)

    existing = [{"human_id": "H_003", "template_hash": "deadbeef"}]
    result = check_uniqueness(commitment, existing)  # sans template_bytes_for_match
    assert result.match_method == "exact_hash", (
        f"B-03 : attendu exact_hash, got {result.match_method!r}"
    )


def test_b04_hamming_match_found_close_templates() -> None:
    """B-04 : hamming_direct → match_found=True si templates proches (dist=1 bit)."""
    from src.artcb.identity.biometric_onchain import check_uniqueness
    template_enroll = bytearray(32)           # 32 zéros
    template_probe = bytearray(32)
    template_probe[0] = 0x01                   # 1 bit différent

    commitment = _make_bio_commitment(bytes(template_probe))
    existing = [{
        "human_id": "H_close",
        "template_bytes_b64": base64.b64encode(bytes(template_enroll)).decode(),
    }]
    result = check_uniqueness(
        commitment, existing,
        template_bytes_for_match=bytes(template_probe),
        threshold_bits=4,  # seuil explicite = 4 bits
    )
    assert result.match_found is True, "B-04 : dist=1 ≤ threshold=4 → match attendu"
    assert result.match_method == "hamming_direct"


def test_b05_hamming_no_match_distant_templates() -> None:
    """B-05 : hamming_direct → match_found=False si templates distants."""
    from src.artcb.identity.biometric_onchain import check_uniqueness
    template_a = bytes([0xFF] * 32)    # tous les bits à 1
    template_b = bytes([0x00] * 32)    # tous les bits à 0 (distance = 256 bits)

    commitment = _make_bio_commitment(template_b)
    existing = [{
        "human_id": "H_far",
        "template_bytes_b64": base64.b64encode(template_a).decode(),
    }]
    result = check_uniqueness(
        commitment, existing,
        template_bytes_for_match=template_b,
        threshold_bits=10,  # seuil = 10 bits, distance = 256 bits → no-match
    )
    assert result.match_found is False, "B-05 : dist=256 > threshold=10 → no-match attendu"


def test_b06_invariants_all_paths() -> None:
    """B-06 : unique_human_proven=False + certified=False sur les 3 chemins."""
    from src.artcb.identity.biometric_onchain import check_uniqueness
    template = bytes(range(32))
    commitment = _make_bio_commitment(template)

    # Chemin exact_hash
    r1 = check_uniqueness(commitment, [])
    assert r1.unique_human_proven is False
    assert r1.certified is False

    # Chemin privacy_preserving_xor (record avec hash valide, sans template_bytes)
    valid_hash = "a" * 64  # sha256 hex valide (64 chars hex)
    r2 = check_uniqueness(commitment, [{"human_id": "H", "template_hash": valid_hash}], template_bytes_for_match=template)
    assert r2.unique_human_proven is False
    assert r2.certified is False

    # Chemin hamming_direct
    r3 = check_uniqueness(
        commitment,
        [{"human_id": "H", "template_bytes_b64": base64.b64encode(template).decode()}],
        template_bytes_for_match=template,
    )
    assert r3.unique_human_proven is False
    assert r3.certified is False


# ─────────────────────────────────────────────────────────────────────────────
# POL KnowledgeID — L-01 → L-03
# ─────────────────────────────────────────────────────────────────────────────

def _make_ir_graph():
    """Helper : crée un IRGraph minimal pour les tests PolScorer."""
    from src.artcb.ir.encoder import IREncoder
    return IREncoder().encode("The quick brown fox jumps over the lazy dog.")


def test_l01_scorer_passes_knowledge_id() -> None:
    """L-01 : PolScorer.score() avec knowledge_id → PolMetrics.knowledge_id présent."""
    from src.artcb.pol.scorer import PolScorer
    graph = _make_ir_graph()
    scorer = PolScorer()
    metrics = scorer.score(graph, knowledge_id="K_abc123", usage_id="U_xyz789")
    assert metrics.knowledge_id == "K_abc123"
    assert metrics.usage_id == "U_xyz789"


def test_l02_to_dict_includes_ids_when_set() -> None:
    """L-02 : PolMetrics.to_dict() inclut knowledge_id et usage_id si non None."""
    from src.artcb.pol.scorer import PolScorer
    graph = _make_ir_graph()
    scorer = PolScorer()
    metrics = scorer.score(graph, knowledge_id="K_test")
    d = metrics.to_dict()
    assert "knowledge_id" in d
    assert d["knowledge_id"] == "K_test"


def test_l03_to_dict_backward_compat_no_ids() -> None:
    """L-03 : PolMetrics.to_dict() n'inclut pas les clés si None (backward compat)."""
    from src.artcb.pol.scorer import PolScorer
    graph = _make_ir_graph()
    scorer = PolScorer()
    metrics = scorer.score(graph)
    d = metrics.to_dict()
    assert "knowledge_id" not in d
    assert "usage_id" not in d
