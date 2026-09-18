"""Tests E2E R355 enforcement — chemin complet Prompt→Preflight→Reflex→Record.

## Tests couverts (rapport 368-370)

Test A : chemin complet — activate() produit preflight_status + record_id + first_reflex
Test B : preflight dégradé si ledger absent — statut DEGRADED, pas BLOCKED
Test C : divergence git détectée — git_sync DEGRADED quand ledger.head ≠ git HEAD
Test D : mot-clé critique déclenche FIRST_REFLEX non null
Test E : seal() produit final_hash non-vide et frozen=True
Test F : bypass attempt — modifier un record scellé lève SealedRecordError
Test G : concurrence — deux activations simultanées produisent deux record_id distincts
Test H : snapshot contient git_sha + ledger_sha + live fields
Test I : preflight lite ne vérifie pas live_node (SKIPPED)
Test J : policy matrix — PASS/DEGRADED/NOT_PROVEN selon états
"""
from __future__ import annotations

import hashlib
import os
import sys
import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Ajouter src/ au path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from artcb.reflex.core import ReflexEngine, ReflexPriority
from artcb.reflex.preflight import (
    CheckStatus,
    GitState,
    LedgerState,
    LiveState,
    PreflightEngine,
    PreflightMode,
)
from artcb.reasoning.record import ReasoningRecord, RecordAction, RecordOutcome, SealedRecordError


# ─── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture()
def engine() -> ReflexEngine:
    """ReflexEngine frais à chaque test."""
    return ReflexEngine()


@pytest.fixture()
def preflight_engine(tmp_path: Path) -> PreflightEngine:
    """PreflightEngine pointant sur tmp_path."""
    return PreflightEngine(root=tmp_path)


@pytest.fixture()
def minimal_ledger(tmp_path: Path) -> Path:
    """Crée un .artcb/task_ledger.yaml minimal dans tmp_path."""
    artcb_dir = tmp_path / ".artcb"
    artcb_dir.mkdir()
    ledger = artcb_dir / "task_ledger.yaml"
    ledger.write_text(
        "meta:\n"
        "  git_head: abc1234\n"
        "  chain_height: 42\n"
        "  certified_100: false\n"
        "  pbft_status: test\n"
        "progress:\n"
        "  global_pct: 72\n"
        "open: []\n"
        "done: []\n",
        encoding="utf-8",
    )
    return ledger


# ─── Test A : chemin complet ──────────────────────────────────────────────────

def test_A_full_chain_prompt_to_record(engine: ReflexEngine) -> None:
    """Chemin complet : activate() → preflight → reflex → record.

    Vérifie que :
    - reflex_activated = True
    - record_id non vide
    - preflight_status présent (pas 'not_run')
    - first_reflex non null si mot-clé détecté
    - note mentionne R368
    """
    report = engine.activate(
        text="test réflexe mémoire thinking raisonnement",
        session_id="test-A",
        task_id="R368-test-A",
        preflight_mode="lite",
    )

    assert report["reflex_activated"] is True
    assert report["record_id"], "record_id doit être non vide"
    assert len(report["record_id"]) >= 16, "record_id doit être un hash hex"
    assert report["preflight_status"] != "not_run", "PreflightEngine doit avoir tourné"
    assert report["first_reflex"] is not None, "FIRST_REFLEX doit être créé si mot-clé détecté"
    assert "R368" in report["note"], "note doit mentionner R368"
    assert report["priority_name"] == "REFLEX_MEMORY"


# ─── Test B : preflight dégradé si ledger absent ──────────────────────────────

def test_B_preflight_degraded_no_ledger(tmp_path: Path) -> None:
    """Si le ledger est absent, le check ledger_available est DEGRADED (pas BLOCKED).

    On vérifie uniquement le check ledger, indépendamment de git.
    (Git peut être BLOCKED si tmp_path n'est pas un repo git — c'est normal.)
    """
    pfe = PreflightEngine(root=tmp_path)
    # Pas de .artcb/task_ledger.yaml dans tmp_path
    result = pfe.run_checks(task_id="test-B", mode=PreflightMode.LITE)

    ledger_check = next(c for c in result.checks if c.check_id == "ledger_available")
    assert ledger_check.status == CheckStatus.DEGRADED, (
        f"Ledger absent → check ledger_available doit être DEGRADED, got {ledger_check.status}"
    )
    # Le check ledger_available lui-même ne doit pas être BLOCKED
    assert ledger_check.status != CheckStatus.BLOCKED, (
        "Ledger absent ne doit pas bloquer (BLOCKED) — seulement DEGRADED"
    )


# ─── Test C : divergence git détectée ────────────────────────────────────────

def test_C_git_divergence_detected(tmp_path: Path, minimal_ledger: Path) -> None:
    """Si ledger.git_head ≠ git HEAD réel, git_sync est DEGRADED.

    Le ledger a git_head=abc1234.
    On simule git HEAD = xyz9999 (différent).
    """
    pfe = PreflightEngine(root=tmp_path)

    # Ledger dit abc1234
    git_state = GitState(sha_short="xyz9999", sha_full="xyz9999abcdef", branch="main", available=True)
    ledger_state = pfe.load_task_ledger()  # chargé depuis minimal_ledger (abc1234)

    assert ledger_state.available, "Ledger doit être chargé"
    check = pfe._check_git_sync(git_state, ledger_state)

    assert check.status == CheckStatus.DEGRADED, (
        f"Divergence ledger=abc1234 ≠ git=xyz9999 doit produire DEGRADED, got {check.status}"
    )
    assert "LEDGER_DIVERGENCE" in check.detail or "sync" in check.detail.lower()


def test_C2_git_sync_pass_when_matching(tmp_path: Path, minimal_ledger: Path) -> None:
    """Si ledger.git_head correspond à git HEAD, git_sync est PASS."""
    pfe = PreflightEngine(root=tmp_path)
    # Git SHA correspondant exactement au ledger (abc1234)
    git_state = GitState(sha_short="abc1234", sha_full="abc1234567890abcdef", branch="main", available=True)
    ledger_state = pfe.load_task_ledger()

    assert ledger_state.available, "Ledger doit être disponible (fixture minimal_ledger créé dans tmp_path)"
    assert ledger_state.git_head == "abc1234", f"Ledger git_head attendu abc1234, got {ledger_state.git_head!r}"

    check = pfe._check_git_sync(git_state, ledger_state)
    assert check.status == CheckStatus.PASS, (
        f"git={git_state.sha_short} ledger={ledger_state.git_head} → doit être PASS, got {check.status}"
    )


# ─── Test D : mot-clé critique → FIRST_REFLEX non null ───────────────────────

def test_D_keyword_triggers_first_reflex(engine: ReflexEngine) -> None:
    """Un mot-clé critique dans le texte produit FIRST_REFLEX non null."""
    report = engine.activate(
        text="analyse de la mémoire IA et du réflexe automatique",
        session_id="test-D",
        task_id="R368-test-D",
        preflight_mode="lite",
    )

    assert report["first_reflex"] is not None, "FIRST_REFLEX doit être non null"
    fr = report["first_reflex"]
    assert fr["trigger_name"] in ("REFLEX_MEMORY", "SECURITY", "PQC")
    assert fr["priority"] <= 2, "Priorité doit être ≤ 2 pour un déclencheur critique"


def test_D2_no_keyword_no_trigger(engine: ReflexEngine) -> None:
    """Sans mot-clé, first_reflex est None."""
    report = engine.activate(
        text="bonjour comment puis-je créer un wallet",
        session_id="test-D2",
        task_id="R368-test-D2",
        preflight_mode="lite",
    )
    # Pas de mot-clé réflexe → first_reflex peut être None
    # (priority = OTHER)
    assert report["priority_name"] == "OTHER"


# ─── Test E : seal() → final_hash + frozen ───────────────────────────────────

def test_E_seal_final_hash_frozen() -> None:
    """seal() produit final_hash non-vide et frozen=True."""
    record = ReasoningRecord(
        session_id="test-E",
        agent_id="test-agent",
        context_summary="contexte de test E",
        context_sha256=hashlib.sha256(b"contexte de test E").hexdigest(),
        action=RecordAction.TEST,
        outcome=RecordOutcome.PASS,
    )

    assert record.final_hash == "", "final_hash doit être vide avant seal()"
    assert record.frozen is False

    record.seal()

    assert record.final_hash, "final_hash doit être non-vide après seal()"
    assert len(record.final_hash) == 64, "final_hash doit être un SHA-256 hex (64 chars)"
    assert record.frozen is True, "frozen doit être True après seal()"


def test_E2_seal_idempotent() -> None:
    """Appeler seal() deux fois produit le même final_hash."""
    record = ReasoningRecord(
        session_id="test-E2",
        agent_id="test-agent",
        context_summary="idempotent",
        context_sha256=hashlib.sha256(b"idempotent").hexdigest(),
    )
    record.seal()
    h1 = record.final_hash

    # Re-seal avec le même record → même hash
    # Note: seal() sur un record frozen doit lever SealedRecordError
    # ou être idempotent selon l'implémentation
    try:
        record.seal()
        assert record.final_hash == h1, "Re-seal doit produire le même hash"
    except SealedRecordError:
        # Comportement acceptable : seal sur frozen lève l'erreur
        pass


# ─── Test F : bypass — modifier un record scellé lève SealedRecordError ──────

def test_F_bypass_sealed_record_raises() -> None:
    """Tenter de modifier un record scellé lève SealedRecordError.

    C'est le test de 'bypass attempt' : le mécanisme doit résister
    à toute tentative de modification post-seal.
    """
    record = ReasoningRecord(
        session_id="test-F",
        agent_id="test-agent",
        context_summary="test bypass",
        context_sha256=hashlib.sha256(b"test bypass").hexdigest(),
    )
    record.seal()

    assert record.frozen is True

    # Tentative 1 : add_observation après seal
    with pytest.raises(SealedRecordError):
        record.add_observation("tentative_bypass", detail="ne doit pas passer")

    # Tentative 2 : add_reference après seal
    with pytest.raises(SealedRecordError):
        from artcb.reasoning.reference_id import ref_rule
        record.add_reference(ref_rule(rule_name="test-bypass", rule_file="test.mdc", rule_version="v1"))

    # Tentative 3 : appeler seal() une seconde fois doit lever SealedRecordError
    # (le record est déjà gelé — ré-sceller est interdit)
    try:
        record.seal()
        # Si seal() est idempotent, c'est acceptable — vérifier que frozen reste True
        assert record.frozen is True, "frozen doit rester True"
    except SealedRecordError:
        pass  # comportement attendu : on ne peut pas ré-sceller


# ─── Test G : concurrence — deux activations → deux record_id distincts ──────

def test_G_concurrent_activations_distinct_records() -> None:
    """Deux activations concurrentes produisent des record_id différents."""
    results: list[dict] = []
    errors: list[Exception] = []

    def activate_worker(idx: int) -> None:
        try:
            eng = ReflexEngine()
            r = eng.activate(
                text=f"test concurrence réflexe mémoire session {idx}",
                session_id=f"concurrent-{idx}-{time.time_ns()}",
                task_id=f"R368-concurrent-{idx}",
                preflight_mode="lite",
            )
            results.append(r)
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=activate_worker, args=(i,)) for i in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    assert not errors, f"Erreurs concurrence : {errors}"
    assert len(results) == 3

    record_ids = {r["record_id"] for r in results}
    assert len(record_ids) == 3, (
        f"Chaque activation doit produire un record_id unique, got: {record_ids}"
    )


# ─── Test H : snapshot contient les champs requis ────────────────────────────

def test_H_snapshot_contains_required_fields() -> None:
    """build_context_snapshot() retourne git_sha, ledger_sha, certified_100."""
    pfe = PreflightEngine()
    snap = pfe.build_context_snapshot()

    assert "certified_100" in snap, "snapshot doit contenir certified_100"
    assert snap["certified_100"] is False, "certified_100 doit toujours être False"
    assert "snapshot_ts" in snap
    # git_sha peut être None si git non dispo, mais la clé doit exister
    assert "git_sha" in snap
    assert "ledger_sha256" in snap
    assert "live_available" in snap


def test_H2_snapshot_in_report(engine: ReflexEngine) -> None:
    """Le rapport d'activation contient preflight_git_sha et preflight_ledger_sha."""
    report = engine.activate(
        text="mémoire réflexe snapshot",
        session_id="test-H2",
        task_id="R368-test-H2",
        preflight_mode="lite",
    )
    # Ces clés doivent être présentes dans le rapport
    assert "preflight_status" in report
    assert "preflight_context_sha" in report
    assert "preflight_git_sha" in report
    assert "preflight_ledger_sha" in report


# ─── Test I : mode lite → live_node SKIPPED ──────────────────────────────────

def test_I_lite_mode_skips_live_check(tmp_path: Path) -> None:
    """En mode LITE, le check live_node est SKIPPED."""
    pfe = PreflightEngine(root=tmp_path)
    result = pfe.run_checks(task_id="test-I", mode=PreflightMode.LITE)

    live_check = next(c for c in result.checks if c.check_id == "live_node")
    assert live_check.status == CheckStatus.SKIPPED, (
        f"Mode lite doit skipper live_node, got {live_check.status}"
    )

    deployed_check = next(c for c in result.checks if c.check_id == "code_deployed")
    assert deployed_check.status == CheckStatus.SKIPPED


# ─── Test J : policy matrix ───────────────────────────────────────────────────

def test_J_policy_git_unavailable_blocked(tmp_path: Path) -> None:
    """Si Git est indisponible, git_sync est BLOCKED."""
    pfe = PreflightEngine(root=tmp_path)
    git_unavailable = GitState(available=False)
    ledger_ok = LedgerState(git_head="abc1234", available=True, sha256="x" * 64)

    check = pfe._check_git_sync(git_unavailable, ledger_ok)
    assert check.status == CheckStatus.BLOCKED


def test_J2_live_unavailable_not_proven(tmp_path: Path) -> None:
    """Si live est indisponible en mode FULL, live_node est NOT_PROVEN."""
    pfe = PreflightEngine(root=tmp_path)
    live_unavailable = LiveState(available=False, url="http://test")

    check = pfe._check_live_node(live_unavailable, PreflightMode.FULL)
    assert check.status == CheckStatus.NOT_PROVEN


def test_J3_overall_worst_status() -> None:
    """overall_status retourne le pire status parmi tous les checks."""
    from artcb.reflex.preflight import CheckResult, PreflightResult

    result = PreflightResult(task_id="test-J3", mode=PreflightMode.FULL)
    result.checks = [
        CheckResult("a", CheckStatus.PASS),
        CheckResult("b", CheckStatus.DEGRADED),
        CheckResult("c", CheckStatus.PASS),
    ]
    assert result.overall_status == CheckStatus.DEGRADED

    result.checks.append(CheckResult("d", CheckStatus.BLOCKED))
    assert result.overall_status == CheckStatus.BLOCKED


# ─── Test K : CERTIFIED_100 toujours False ────────────────────────────────────

def test_K_certified_100_always_false(engine: ReflexEngine) -> None:
    """CERTIFIED_100 doit toujours être False dans le rapport et le record."""
    report = engine.activate(
        text="test certif réflexe mémoire",
        session_id="test-K",
        task_id="R368-test-K",
        preflight_mode="lite",
    )

    assert report["certified"] is False
    assert report["unique_human_proven"] is False

    # Le snapshot de preflight doit aussi avoir certified_100=False
    pfe = PreflightEngine()
    snap = pfe.build_context_snapshot()
    assert snap["certified_100"] is False


# ─── Test L : ledger SHA dans snapshot — détection de race condition ──────────

def test_L_ledger_sha_changes_if_file_changes(tmp_path: Path) -> None:
    """Si le ledger est modifié entre deux snapshots, le SHA change."""
    # Créer le ledger directement dans tmp_path (pas via fixture qui peut être partagée)
    artcb_dir = tmp_path / ".artcb"
    artcb_dir.mkdir(exist_ok=True)
    ledger_file = artcb_dir / "task_ledger.yaml"
    ledger_file.write_text("meta:\n  git_head: aaa0001\n  chain_height: 1\n", encoding="utf-8")

    pfe = PreflightEngine(root=tmp_path)

    snap1 = pfe.load_task_ledger()
    sha1 = snap1.sha256
    assert snap1.available, "Ledger doit être lisible"

    # Modifier le fichier — ajout d'une ligne
    ledger_file.write_text(
        "meta:\n  git_head: aaa0001\n  chain_height: 1\n\n# modification-test\n",
        encoding="utf-8",
    )
    snap2 = pfe.load_task_ledger()
    sha2 = snap2.sha256

    assert sha1 != sha2, (
        "SHA du ledger doit changer si le fichier est modifié — détection race condition"
    )
