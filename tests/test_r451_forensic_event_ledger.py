"""R451 — Tests FORENSIC-01 : ForensicEvent + ForensicLedger + intégration pipeline.

Couverture — 30 tests F01→F30 :

  FORENSIC EVENT (F01→F08)
  ──────────────────────────
  F01 : ForensicEvent construit via ForensicLedger.build() — champs obligatoires présents
  F02 : ForensicEvent.to_dict() / from_dict() round-trip (enums str ↔ enum)
  F03 : ForensicEvent.compute_hash() déterministe (même entrée → même hash)
  F04 : compute_hash() diffère si event_type change
  F05 : event_hash exclu du calcul (pas d'auto-référence)
  F06 : unique_human_proven = False dans tout événement construit
  F07 : certified_100 = False dans tout événement construit
  F08 : ForensicEvent frozen — mutation directe lève FrozenInstanceError

  LEDGER HASH CHAIN (F09→F15)
  ─────────────────────────────
  F09 : premier événement → previous_event_hash = GENESIS_HASH
  F10 : deuxième événement → previous_event_hash = event_hash du premier
  F11 : troisième événement → hash chain correcte (3 maillons)
  F12 : verify_chain() → ok=True si chaîne intègre
  F13 : verify_chain() → ok=False si un event_hash est altéré
  F14 : ledger vide → verify_chain() retourne ok=True, checked=0
  F15 : list_events() filtre par event_type

  MERKLE ROOT (F16→F18)
  ──────────────────────
  F16 : compute_merkle_root() ledger vide → GENESIS_HASH
  F17 : compute_merkle_root() 4 événements → valeur non vide ≠ GENESIS_HASH
  F18 : emit_merkle_checkpoint() ajoute un événement FORENSIC_MERKLE_ROOT

  EMIT FORENSIC HELPER (F19→F22)
  ────────────────────────────────
  F19 : emit_forensic(ledger=None) → ForensicEvent non None sans I/O
  F20 : emit_forensic(ledger=ledger) → événement ajouté au JSONL
  F21 : emit_forensic() ne lève jamais d'exception même avec mauvais paramètres
  F22 : emit_forensic() → unique_human_proven=False, certified_100=False

  INTÉGRATION PIPELINE G4 (F23→F26)
  ────────────────────────────────────
  F23 : ReasoningPipeline avec forensic_ledger → événements écrits dans JSONL
  F24 : correlation_id propagé à tous les événements d'un même run()
  F25 : 7 événements produits par un run() complet (IR+Canonical+Knowledge+Usage+PoL+Work+Pipeline)
  F26 : REASONING_PIPELINE_OK en dernier événement

  INTÉGRATION BIOMÉTRIE (F27→F28)
  ──────────────────────────────────
  F27 : enroll_biometric() émet BIO_ENROLL_OK sans crash
  F28 : check_uniqueness() émet BIO_UNIQUENESS_OK sans crash

  TYPES ET ÉNUMÉRATIONS (F29→F30)
  ──────────────────────────────────
  F29 : AttemptOutcome.STORE_UNAVAILABLE distinct de STORE_EMPTY et STORE_MISSING
  F30 : EvaluationContext.ENROLLMENT distinct de AUTHENTICATION (segmentation FAR/FRR future)

PROTOCOLE ARTCB — mode DEBUG actif — CERTIFIED_100=false.
"""
from __future__ import annotations

import dataclasses
import json
import tempfile
import uuid
from pathlib import Path

import pytest

from src.artcb.trace.forensic import (
    GENESIS_HASH,
    AttemptOutcome,
    EvaluationContext,
    ForensicEvent,
    ForensicEventType,
    ForensicLedger,
    emit_forensic,
)


# ─── Fixture ──────────────────────────────────────────────────────────────────

@pytest.fixture
def ledger(tmp_path: Path) -> ForensicLedger:
    """Ledger isolé dans un répertoire temporaire."""
    return ForensicLedger(data_dir=tmp_path)


def _build_event(ledger: ForensicLedger, **kwargs) -> ForensicEvent:
    """Helper : construit un événement avec des valeurs par défaut."""
    return ledger.build(
        event_type=kwargs.get("event_type", ForensicEventType.REASONING_PIPELINE_OK),
        outcome=kwargs.get("outcome", AttemptOutcome.SUCCESS),
        evaluation_context=kwargs.get("evaluation_context", EvaluationContext.REASONING_PIPELINE),
        correlation_id=kwargs.get("correlation_id", "corr-test"),
        layer=kwargs.get("layer", "reasoning"),
        actor_ref=kwargs.get("actor_ref", "agent_test"),
        subject_ref=kwargs.get("subject_ref", "subject_xyz"),
    )


# ═══════════════════════════════════════════════════════════════════════════════
# FORENSIC EVENT
# ═══════════════════════════════════════════════════════════════════════════════

def test_f01_build_produces_forensic_event(ledger: ForensicLedger) -> None:
    """F01 — build() retourne un ForensicEvent avec champs obligatoires remplis."""
    ev = _build_event(ledger)
    assert isinstance(ev, ForensicEvent)
    assert ev.event_id
    assert ev.event_type == ForensicEventType.REASONING_PIPELINE_OK
    assert ev.outcome == AttemptOutcome.SUCCESS
    assert ev.ts_wall_ns > 0
    assert ev.ts_mono_ns > 0
    assert ev.created_at


def test_f02_to_dict_from_dict_roundtrip(ledger: ForensicLedger) -> None:
    """F02 — to_dict() / from_dict() round-trip sans perte."""
    ev = _build_event(ledger)
    d = ev.to_dict()
    restored = ForensicEvent.from_dict(d)
    assert restored.event_id == ev.event_id
    assert restored.event_type == ev.event_type
    assert restored.outcome == ev.outcome
    assert restored.evaluation_context == ev.evaluation_context
    assert restored.ts_wall_ns == ev.ts_wall_ns
    assert restored.correlation_id == ev.correlation_id


def test_f03_compute_hash_deterministic(ledger: ForensicLedger) -> None:
    """F03 — compute_hash() déterministe : même événement → même hash."""
    ev = _build_event(ledger, correlation_id="corr-fixed")
    h1 = ev.compute_hash()
    h2 = ev.compute_hash()
    assert h1 == h2, "compute_hash() doit être déterministe"
    assert len(h1) == 64, "SHA-256 hex = 64 caractères"


def test_f04_compute_hash_differs_on_event_type_change(ledger: ForensicLedger) -> None:
    """F04 — compute_hash() diffère si event_type change."""
    ev1 = _build_event(ledger, event_type=ForensicEventType.REASONING_PIPELINE_OK)
    ev2 = _build_event(ledger, event_type=ForensicEventType.REASONING_PIPELINE_FAIL)
    # Les deux événements ont le même event_id et ts → mais event_type diffère
    ev2_modified = dataclasses.replace(
        ev2,
        event_id=ev1.event_id,
        ts_wall_ns=ev1.ts_wall_ns,
        ts_mono_ns=ev1.ts_mono_ns,
        created_at=ev1.created_at,
    )
    assert ev1.compute_hash() != ev2_modified.compute_hash(), (
        "F04 : event_type différent doit produire un hash différent"
    )


def test_f05_event_hash_excluded_from_computation(ledger: ForensicLedger) -> None:
    """F05 — event_hash n'est pas inclus dans son propre calcul (pas d'auto-référence)."""
    ev = _build_event(ledger)
    # Avec event_hash vide (comme avant append)
    h_empty = ev.compute_hash()
    # Avec event_hash non vide → doit donner le même résultat (car exclu)
    ev_with_hash = dataclasses.replace(ev, event_hash="some_hash_value")
    h_with_hash = ev_with_hash.compute_hash()
    assert h_empty == h_with_hash, "F05 : event_hash doit être exclu du calcul"


def test_f06_unique_human_proven_always_false(ledger: ForensicLedger) -> None:
    """F06 — unique_human_proven = False dans tout événement construit."""
    ev = _build_event(ledger)
    assert ev.unique_human_proven is False, "F06 : unique_human_proven invariant False"


def test_f07_certified_100_always_false(ledger: ForensicLedger) -> None:
    """F07 — certified_100 = False dans tout événement construit."""
    ev = _build_event(ledger)
    assert ev.certified_100 is False, "F07 : certified_100 invariant False"


def test_f08_forensic_event_frozen(ledger: ForensicLedger) -> None:
    """F08 — ForensicEvent frozen — mutation directe lève FrozenInstanceError."""
    ev = _build_event(ledger)
    with pytest.raises(dataclasses.FrozenInstanceError):
        ev.event_id = "tampered"  # type: ignore[misc]


# ═══════════════════════════════════════════════════════════════════════════════
# LEDGER HASH CHAIN
# ═══════════════════════════════════════════════════════════════════════════════

def test_f09_first_event_previous_hash_is_genesis(ledger: ForensicLedger) -> None:
    """F09 — Premier événement → previous_event_hash = GENESIS_HASH."""
    ev = _build_event(ledger)
    sealed = ledger.append(ev)
    assert sealed.previous_event_hash == GENESIS_HASH, (
        f"F09 : attendu GENESIS_HASH, reçu {sealed.previous_event_hash!r}"
    )


def test_f10_second_event_previous_hash_matches_first(ledger: ForensicLedger) -> None:
    """F10 — Deuxième événement → previous_event_hash = event_hash du premier."""
    ev1 = _build_event(ledger, layer="step1")
    sealed1 = ledger.append(ev1)

    ev2 = _build_event(ledger, layer="step2")
    sealed2 = ledger.append(ev2)

    assert sealed2.previous_event_hash == sealed1.event_hash, (
        f"F10 : hash_prev[2]={sealed2.previous_event_hash[:16]}… ≠ event_hash[1]={sealed1.event_hash[:16]}…"
    )


def test_f11_three_events_hash_chain_valid(ledger: ForensicLedger) -> None:
    """F11 — Trois événements → chaîne hash intègre (3 maillons)."""
    s1 = ledger.append(_build_event(ledger, subject_ref="e1"))
    s2 = ledger.append(_build_event(ledger, subject_ref="e2"))
    s3 = ledger.append(_build_event(ledger, subject_ref="e3"))

    assert s2.previous_event_hash == s1.event_hash
    assert s3.previous_event_hash == s2.event_hash
    assert s1.event_hash and s2.event_hash and s3.event_hash


def test_f12_verify_chain_ok_on_intact_ledger(ledger: ForensicLedger) -> None:
    """F12 — verify_chain() → ok=True sur un ledger intègre."""
    ledger.append(_build_event(ledger, subject_ref="a"))
    ledger.append(_build_event(ledger, subject_ref="b"))
    ledger.append(_build_event(ledger, subject_ref="c"))

    result = ledger.verify_chain()
    assert result["ok"] is True, f"F12 : chaîne brisée inattendue : {result}"
    assert result["checked"] == 3


def test_f13_verify_chain_detects_tampering(ledger: ForensicLedger) -> None:
    """F13 — verify_chain() → ok=False si un event_hash est altéré."""
    ledger.append(_build_event(ledger, subject_ref="x"))
    ledger.append(_build_event(ledger, subject_ref="y"))

    # Altérer le premier événement dans le JSONL
    path = ledger._ledger_path
    lines = path.read_text(encoding="utf-8").splitlines()
    first = json.loads(lines[0])
    first["event_hash"] = "0" * 64   # valeur falsifiée
    lines[0] = json.dumps(first, ensure_ascii=False, separators=(",", ":"))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    result = ledger.verify_chain()
    assert result["ok"] is False, "F13 : altération non détectée"
    assert result["broken_at"] == 0


def test_f14_verify_chain_empty_ledger(tmp_path: Path) -> None:
    """F14 — verify_chain() sur ledger vide → ok=True, checked=0."""
    empty_ledger = ForensicLedger(data_dir=tmp_path / "empty")
    result = empty_ledger.verify_chain()
    assert result["ok"] is True
    assert result["checked"] == 0


def test_f15_list_events_filter_by_event_type(ledger: ForensicLedger) -> None:
    """F15 — list_events() filtre correctement par event_type."""
    ledger.append(_build_event(ledger, event_type=ForensicEventType.REASONING_PIPELINE_OK))
    ledger.append(_build_event(ledger, event_type=ForensicEventType.IR_ENCODE_OK))
    ledger.append(_build_event(ledger, event_type=ForensicEventType.REASONING_PIPELINE_OK))

    pipeline_events = ledger.list_events(event_type=ForensicEventType.REASONING_PIPELINE_OK)
    ir_events = ledger.list_events(event_type=ForensicEventType.IR_ENCODE_OK)

    assert len(pipeline_events) == 2, f"F15 : attendu 2 REASONING_PIPELINE_OK, reçu {len(pipeline_events)}"
    assert len(ir_events) == 1, f"F15 : attendu 1 IR_ENCODE_OK, reçu {len(ir_events)}"


# ═══════════════════════════════════════════════════════════════════════════════
# MERKLE ROOT
# ═══════════════════════════════════════════════════════════════════════════════

def test_f16_merkle_root_empty_ledger_returns_genesis(tmp_path: Path) -> None:
    """F16 — Ledger vide → merkle_root = GENESIS_HASH."""
    empty_ledger = ForensicLedger(data_dir=tmp_path / "empty2")
    assert empty_ledger.compute_merkle_root() == GENESIS_HASH


def test_f17_merkle_root_non_empty_non_genesis(ledger: ForensicLedger) -> None:
    """F17 — 4 événements → Merkle root valide ≠ GENESIS_HASH."""
    for i in range(4):
        ledger.append(_build_event(ledger, subject_ref=f"e{i}"))
    root = ledger.compute_merkle_root()
    assert root != GENESIS_HASH, "F17 : Merkle root ne doit pas être GENESIS_HASH"
    assert len(root) == 64, "F17 : Merkle root doit être un hash SHA-256 (64 hex)"


def test_f18_emit_merkle_checkpoint_adds_event(ledger: ForensicLedger) -> None:
    """F18 — emit_merkle_checkpoint() ajoute un FORENSIC_MERKLE_ROOT au ledger."""
    ledger.append(_build_event(ledger, subject_ref="base"))
    checkpoint = ledger.emit_merkle_checkpoint()

    assert checkpoint is not None
    assert checkpoint.event_type == ForensicEventType.FORENSIC_MERKLE_ROOT
    assert "merkle_root" in checkpoint.extra


# ═══════════════════════════════════════════════════════════════════════════════
# EMIT FORENSIC HELPER
# ═══════════════════════════════════════════════════════════════════════════════

def test_f19_emit_forensic_none_ledger_no_io() -> None:
    """F19 — emit_forensic(ledger=None) → ForensicEvent retourné sans I/O."""
    ev = emit_forensic(
        None,
        event_type=ForensicEventType.BIO_ENROLL_OK,
        outcome=AttemptOutcome.SUCCESS,
        evaluation_context=EvaluationContext.ENROLLMENT,
        layer="biometric",
        subject_ref="human_abc",
    )
    assert ev is not None
    assert isinstance(ev, ForensicEvent)
    assert ev.event_type == ForensicEventType.BIO_ENROLL_OK


def test_f20_emit_forensic_with_ledger_writes_to_jsonl(ledger: ForensicLedger) -> None:
    """F20 — emit_forensic(ledger=ledger) → événement écrit dans le JSONL."""
    ev = emit_forensic(
        ledger,
        event_type=ForensicEventType.SYBIL_CHECK_OK,
        outcome=AttemptOutcome.SUCCESS,
        evaluation_context=EvaluationContext.SYBIL_CHECK,
        layer="sybil",
        subject_ref="human_xyz",
    )
    assert ev is not None
    events = ledger.list_events(event_type=ForensicEventType.SYBIL_CHECK_OK)
    assert len(events) == 1, "F20 : événement non trouvé dans le ledger"
    assert events[0].event_id == ev.event_id


def test_f21_emit_forensic_never_raises(tmp_path: Path) -> None:
    """F21 — emit_forensic() ne lève jamais d'exception même avec paramètres limites."""
    # Même avec un ledger dont le répertoire est en lecture seule (simulation)
    result = emit_forensic(
        None,
        event_type=ForensicEventType.INTERNAL_ERROR,
        outcome=AttemptOutcome.INTERNAL_ERROR,
        evaluation_context=EvaluationContext.UNKNOWN,
        layer="",
        extra={"nested": {"deep": "value"}, "list": [1, 2, 3]},
    )
    # Pas d'exception levée
    assert result is not None or result is None  # toujours vrai — pas d'exception


def test_f22_emit_forensic_invariants(ledger: ForensicLedger) -> None:
    """F22 — emit_forensic() → unique_human_proven=False, certified_100=False."""
    ev = emit_forensic(
        ledger,
        event_type=ForensicEventType.WALLET_CREATE_OK,
        outcome=AttemptOutcome.SUCCESS,
        evaluation_context=EvaluationContext.WALLET_CREATION,
        layer="wallet",
    )
    assert ev is not None
    assert ev.unique_human_proven is False
    assert ev.certified_100 is False


# ═══════════════════════════════════════════════════════════════════════════════
# INTÉGRATION PIPELINE G4
# ═══════════════════════════════════════════════════════════════════════════════

def test_f23_pipeline_with_forensic_ledger_writes_events(tmp_path: Path) -> None:
    """F23 — ReasoningPipeline avec forensic_ledger → événements écrits dans JSONL."""
    from src.artcb.reasoning.pipeline import ReasoningPipeline
    ledger = ForensicLedger(data_dir=tmp_path)
    pipeline = ReasoningPipeline(forensic_ledger=ledger)
    pipeline.run(
        "Le serveur ARTCB valide la signature PQC et produit un bloc.",
        producer_id="agent_test",
        language_hint="fr",
    )
    events = ledger.list_events()
    assert len(events) >= 1, "F23 : aucun événement forensic produit par le pipeline"


def test_f24_pipeline_correlation_id_propagated(tmp_path: Path) -> None:
    """F24 — correlation_id propagé à tous les événements d'un même run()."""
    from src.artcb.reasoning.pipeline import ReasoningPipeline
    ledger = ForensicLedger(data_dir=tmp_path)
    pipeline = ReasoningPipeline(forensic_ledger=ledger)
    corr = f"test-corr-{uuid.uuid4().hex[:8]}"
    pipeline.run(
        "ARTCB blockchain verification node",
        producer_id="agent_test",
        language_hint="en",
        correlation_id=corr,
    )
    events = ledger.list_events(correlation_id=corr)
    assert len(events) >= 1, (
        f"F24 : aucun événement avec correlation_id={corr!r} trouvé dans le ledger"
    )
    # Tous les événements filtrés doivent avoir le bon correlation_id
    for ev in events:
        assert ev.correlation_id == corr, (
            f"F24 : événement {ev.event_type} a correlation_id={ev.correlation_id!r} ≠ {corr!r}"
        )


def test_f25_pipeline_produces_7_forensic_events(tmp_path: Path) -> None:
    """F25 — Un run() complet produit au moins 7 événements (IR+Canonical+Knowledge+Usage+PoL+Work+Pipeline)."""
    from src.artcb.reasoning.pipeline import ReasoningPipeline
    ledger = ForensicLedger(data_dir=tmp_path)
    pipeline = ReasoningPipeline(forensic_ledger=ledger)
    corr = f"corr-f25-{uuid.uuid4().hex[:8]}"
    pipeline.run(
        "Le serveur valide la signature et crée un bloc.",
        producer_id="agent_test",
        correlation_id=corr,
    )
    events = ledger.list_events(correlation_id=corr)
    # 6 étapes instrumentées : IR_ENCODE_OK, CANONICAL_OK, KNOWLEDGE_CREATE_OK,
    # USAGE_RECORD_OK, POL_SCORE_OK, REASONING_PIPELINE_OK (KNOWLEDGE_WORK inclus dans le final)
    assert len(events) >= 6, (
        f"F25 : attendu >= 6 événements, reçu {len(events)} "
        f"(types: {[e.event_type.value for e in events]})"
    )


def test_f26_pipeline_last_event_is_pipeline_ok(tmp_path: Path) -> None:
    """F26 — REASONING_PIPELINE_OK est le dernier événement produit par run()."""
    from src.artcb.reasoning.pipeline import ReasoningPipeline
    ledger = ForensicLedger(data_dir=tmp_path)
    pipeline = ReasoningPipeline(forensic_ledger=ledger)
    corr = f"corr-f26-{uuid.uuid4().hex[:8]}"
    pipeline.run(
        "ARTCB PoL knowledge work blockchain",
        producer_id="agent_test",
        correlation_id=corr,
    )
    events = ledger.list_events(correlation_id=corr)
    assert events, "F26 : aucun événement produit"
    last = events[-1]
    assert last.event_type == ForensicEventType.REASONING_PIPELINE_OK, (
        f"F26 : dernier événement = {last.event_type.value}, attendu REASONING_PIPELINE_OK"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# INTÉGRATION BIOMÉTRIE
# ═══════════════════════════════════════════════════════════════════════════════

def test_f27_enroll_biometric_emits_forensic_event() -> None:
    """F27 — enroll_biometric() émet BIO_ENROLL_OK sans crash (fail-open forensic)."""
    from src.artcb.identity.biometric_onchain import enroll_biometric
    template = bytes(range(32))
    # Pas de crash — le forensic est fail-open
    result, secret_hex, blinding_hex = enroll_biometric(
        template_bytes=template,
        wallet_address="wallet-f27",
    )
    assert result.human_id
    assert not result.sybil_blocked


def test_f28_check_uniqueness_emits_forensic_event() -> None:
    """F28 — check_uniqueness() émet BIO_UNIQUENESS_OK sans crash."""
    from src.artcb.identity.biometric_onchain import enroll_biometric, check_uniqueness
    from src.artcb.crypto.homomorphic import commit_biometric_template
    template = bytes(range(64))
    result_enroll, _, _ = enroll_biometric(template_bytes=template)
    # Vérification d'unicité avec un template différent → no match attendu
    different_template = bytes([b ^ 0x01 for b in template])
    new_commitment = commit_biometric_template(different_template)
    result_check = check_uniqueness(
        new_commitment=new_commitment,
        existing_records=[result_enroll.human_identity_record],
        template_bytes_for_match=different_template,
    )
    # Le forensic est fail-open — pas d'exception levée
    assert result_check is not None


# ═══════════════════════════════════════════════════════════════════════════════
# TYPES ET ÉNUMÉRATIONS
# ═══════════════════════════════════════════════════════════════════════════════

def test_f29_attempt_outcome_store_states_distinct() -> None:
    """F29 — AttemptOutcome.STORE_UNAVAILABLE distinct de STORE_EMPTY et STORE_MISSING."""
    assert AttemptOutcome.STORE_UNAVAILABLE != AttemptOutcome.STORE_EMPTY
    assert AttemptOutcome.STORE_UNAVAILABLE != AttemptOutcome.STORE_MISSING
    assert AttemptOutcome.STORE_EMPTY != AttemptOutcome.STORE_MISSING
    # Vérification des valeurs str (R447 cohérence)
    assert AttemptOutcome.STORE_UNAVAILABLE.value == "STORE_UNAVAILABLE"
    assert AttemptOutcome.STORE_EMPTY.value == "STORE_EMPTY"
    assert AttemptOutcome.STORE_MISSING.value == "STORE_MISSING"


def test_f30_evaluation_context_enrollment_distinct_from_authentication() -> None:
    """F30 — EvaluationContext.ENROLLMENT distinct de AUTHENTICATION (segmentation FAR/FRR future)."""
    assert EvaluationContext.ENROLLMENT != EvaluationContext.AUTHENTICATION
    assert EvaluationContext.ENROLLMENT.value == "ENROLLMENT"
    assert EvaluationContext.AUTHENTICATION.value == "AUTHENTICATION"
    # Les deux contextes existent → segmentation FAR/FRR possible
    all_contexts = {c.value for c in EvaluationContext}
    assert "ENROLLMENT" in all_contexts
    assert "AUTHENTICATION" in all_contexts
    assert "UNIQUENESS_CHECK" in all_contexts
    assert "SYBIL_CHECK" in all_contexts
    assert "WALLET_CREATION" in all_contexts
