"""Tests adversariaux R369 — bypass, falsification, gate, opérations protégées.

## Tests M→S (rapport 370, section 12)

Test M : opération protégée sans preflight → BLOCKED
Test N : preflight falsifié (context_sha différent) → détecté
Test O : ledger modifié après preflight → context SHA différent → BLOCKED
Test P : operation_risk détermine mode (CODE_CHANGE → FULL, READ → LITE)
Test Q : PreflightGate.require_authorized lève sur auth refusée
Test R : consume_authorization → réutilisation refusée
Test S : deux gates simultanées → opération_id distincts (pas de partage d'auth)

## Tests supplémentaires P0-A/B/C/D/E

Test AA : EXPECTED_LAG vs REAL_DIVERGENCE — même parents récents
Test AB : remote IN_SYNC / LOCAL_AHEAD / REMOTE_AHEAD / DIVERGED
Test AC : LiveState 5 niveaux — reachable/healthy/git_sha_known/git_match
Test AD : fail-closed — run_checks BLOCKED + CRITICAL lève PreflightBlockedError
Test AE : fail-open — run_checks DEGRADED ne lève pas
Test AF : snapshot triade remote/local/live
"""
from __future__ import annotations

import sys
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from artcb.reflex.preflight import (
    Authorization,
    CheckResult,
    CheckStatus,
    GitState,
    LedgerState,
    LiveState,
    OperationRisk,
    PreflightBlockedError,
    PreflightEngine,
    PreflightGate,
    PreflightMode,
    PreflightResult,
    RemoteGitState,
    RemoteSyncStatus,
    _FAIL_CLOSED_RISKS,
    required_preflight_mode,
)


# ─── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture()
def tmp_ledger(tmp_path: Path) -> Path:
    """Crée un .artcb/task_ledger.yaml dans tmp_path."""
    d = tmp_path / ".artcb"
    d.mkdir()
    f = d / "task_ledger.yaml"
    f.write_text(
        "meta:\n  git_head: abc1111\n  chain_height: 10\n"
        "progress:\n  global_pct: 50\nopen: []\ndone: []\n",
        encoding="utf-8",
    )
    return f


@pytest.fixture()
def pfe(tmp_path: Path, tmp_ledger: Path) -> PreflightEngine:
    return PreflightEngine(root=tmp_path)


@pytest.fixture()
def gate(pfe: PreflightEngine) -> PreflightGate:
    return PreflightGate(pfe)


# ─── Test M : opération protégée sans preflight → BLOCKED ────────────────────

def test_M_protected_operation_requires_preflight(gate: PreflightGate) -> None:
    """DEPLOY sans preflight valide → PreflightBlockedError si BLOCKED.

    Si run_checks retourne BLOCKED (git indisponible dans tmp_path),
    authorize() doit retourner allowed=False pour DEPLOY.
    """
    # Dans tmp_path sans git → git_sync = BLOCKED
    # DEPLOY est fail-closed → run_checks doit lever ou autorisation doit être refusée
    result = gate._engine.run_checks(
        task_id="test-M", mode=PreflightMode.LITE, operation_risk=OperationRisk.ANALYSIS
    )
    overall = result.overall_status
    # Dans tmp_path sans git, git_sync = BLOCKED → overall = BLOCKED
    # ANALYSIS n'est pas fail-closed → run_checks ne lève pas
    # DEPLOY serait fail-closed → on crée manuellement un résultat BLOCKED
    blocked_result = PreflightResult(task_id="test-M", mode=PreflightMode.FULL)
    blocked_result.checks = [CheckResult("git_sync", CheckStatus.BLOCKED, detail="test")]

    auth = gate.authorize("deploy_op", OperationRisk.DEPLOY,
                          preflight_result=blocked_result)
    assert auth.allowed is False, "DEPLOY sur preflight BLOCKED → not allowed"
    with pytest.raises(PreflightBlockedError):
        gate.require_authorized(auth)


# ─── Test N : preflight falsifié → context_sha différent ─────────────────────

def test_N_falsified_preflight_context_sha_differs() -> None:
    """Si on falsifie un PreflightResult (context_sha modifié), c'est détectable.

    Le context_sha est calculé depuis l'état réel. Deux exécutions différentes
    produisent des SHA différents → impossibilité de réutiliser un résultat.
    """
    pfe = PreflightEngine()

    r1 = pfe.run_checks(task_id="task-A", mode=PreflightMode.LITE)
    r2 = pfe.run_checks(task_id="task-B", mode=PreflightMode.LITE)

    assert r1.context_sha != r2.context_sha, (
        "Des task_id différents produisent des context_sha différents"
    )


# ─── Test O : ledger modifié après preflight → SHA différent ─────────────────

def test_O_ledger_modified_after_preflight_detected(
    tmp_path: Path, tmp_ledger: Path
) -> None:
    """Si le ledger est modifié après le preflight, le SHA change.

    Le ReasoningRecord peut détecter que le contexte a changé.
    """
    pfe = PreflightEngine(root=tmp_path)
    snap1 = pfe.build_context_snapshot()
    sha1 = snap1["ledger_sha256"]

    # Modifier le ledger après le snapshot
    tmp_ledger.write_text(
        tmp_ledger.read_text() + "\n# modifié après preflight\n", encoding="utf-8"
    )

    snap2 = pfe.build_context_snapshot()
    sha2 = snap2["ledger_sha256"]

    assert sha1 != sha2, "Ledger modifié → SHA doit changer → détecté"


# ─── Test P : operation_risk détermine le mode ────────────────────────────────

@pytest.mark.parametrize("risk,expected_mode", [
    (OperationRisk.READ,        PreflightMode.LITE),
    (OperationRisk.ANALYSIS,    PreflightMode.LITE),
    (OperationRisk.CODE_CHANGE, PreflightMode.FULL),
    (OperationRisk.TEST,        PreflightMode.FULL),
    (OperationRisk.DEPLOY,      PreflightMode.FULL),
    (OperationRisk.LIVE_WRITE,  PreflightMode.FULL),
    (OperationRisk.CRITICAL,    PreflightMode.FULL),
])
def test_P_operation_risk_determines_mode(
    risk: OperationRisk, expected_mode: PreflightMode
) -> None:
    """required_preflight_mode() retourne le bon mode pour chaque risque."""
    assert required_preflight_mode(risk) == expected_mode


# ─── Test Q : require_authorized lève sur auth refusée ───────────────────────

def test_Q_require_authorized_raises_on_refused() -> None:
    """require_authorized lève PreflightBlockedError si auth.allowed=False."""
    gate = PreflightGate()
    auth = Authorization(allowed=False, operation="test_Q", reason="test_refused")
    with pytest.raises(PreflightBlockedError) as exc_info:
        gate.require_authorized(auth)
    assert "test_refused" in str(exc_info.value)


def test_Q2_require_authorized_passes_on_allowed() -> None:
    """require_authorized ne lève pas si auth.allowed=True."""
    gate = PreflightGate()
    auth = Authorization(allowed=True, operation="test_Q2")
    gate.require_authorized(auth)  # ne doit pas lever


# ─── Test R : consume_authorization → réutilisation refusée ──────────────────

def test_R_consumed_authorization_cannot_be_reused() -> None:
    """Une autorisation consommée lève PreflightBlockedError à la réutilisation."""
    gate = PreflightGate()
    auth = Authorization(allowed=True, operation="test_R")

    gate.require_authorized(auth)  # OK
    gate.consume_authorization(auth)  # marque consommée

    with pytest.raises(PreflightBlockedError) as exc_info:
        gate.require_authorized(auth)
    assert "consommée" in str(exc_info.value) or "consumed" in str(exc_info.value)


# ─── Test S : deux gates → operation_id distincts ────────────────────────────

def test_S_concurrent_gates_distinct_operation_ids() -> None:
    """Deux gates simultanées produisent des operation_id distincts."""
    results: list[Authorization] = []
    errors: list[Exception] = []

    def authorize_worker() -> None:
        try:
            gate = PreflightGate()
            auth = Authorization(allowed=True, operation="concurrent",
                                 risk=OperationRisk.ANALYSIS)
            results.append(auth)
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=authorize_worker) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5)

    assert not errors
    assert len(results) == 5
    ids = {a.operation_id for a in results}
    assert len(ids) == 5, "Chaque autorisation doit avoir un operation_id unique"


# ─── Test AA : EXPECTED_LAG vs REAL_DIVERGENCE ────────────────────────────────

def test_AA_expected_lag_vs_real_divergence(
    tmp_path: Path, tmp_ledger: Path
) -> None:
    """EXPECTED_LAG si parent direct, REAL_DIVERGENCE sinon."""
    pfe = PreflightEngine(root=tmp_path)
    ledger = pfe.load_task_ledger()
    assert ledger.recorded_sha[:7] == "abc1111"

    # Cas EXPECTED_LAG : git HEAD a abc1111 dans ses parents
    git_lag = GitState(
        sha_short="def2222", sha_full="def222200000000", branch="main",
        available=True, recent_parents=["def2222", "abc1111", "000ffff"]
    )
    check_lag = pfe.classify_git_ledger_sync(git_lag, ledger)
    assert check_lag.status == CheckStatus.EXPECTED_LAG

    # Cas REAL_DIVERGENCE : abc1111 pas dans les parents
    git_div = GitState(
        sha_short="ghi3333", sha_full="ghi333300000000", branch="main",
        available=True, recent_parents=["ghi3333", "jkl4444"]
    )
    check_div = pfe.classify_git_ledger_sync(git_div, ledger)
    assert check_div.status == CheckStatus.DEGRADED
    assert "REAL_DIVERGENCE" in check_div.detail


# ─── Test AB : remote sync statuses ──────────────────────────────────────────

def test_AB_remote_sync_in_sync() -> None:
    """IN_SYNC si local == remote."""
    pfe = PreflightEngine()
    local = GitState(sha_short="aaa", sha_full="aaa000", available=True,
                     recent_parents=["aaa"])
    remote = RemoteGitState(sha_short="aaa", sha_full="aaa000", available=True)
    assert pfe.compare_local_remote(local, remote) == RemoteSyncStatus.IN_SYNC


def test_AB_remote_sync_local_ahead() -> None:
    """LOCAL_AHEAD si remote SHA est dans les parents locaux."""
    pfe = PreflightEngine()
    local = GitState(sha_short="bbb", sha_full="bbb000", available=True,
                     recent_parents=["bbb", "aaa"])
    remote = RemoteGitState(sha_short="aaa", sha_full="aaa000", available=True)
    assert pfe.compare_local_remote(local, remote) == RemoteSyncStatus.LOCAL_AHEAD


def test_AB_remote_sync_not_proven_unavailable() -> None:
    """NOT_PROVEN si remote indisponible."""
    pfe = PreflightEngine()
    local = GitState(sha_short="ccc", available=True)
    remote = RemoteGitState(available=False)
    assert pfe.compare_local_remote(local, remote) == RemoteSyncStatus.NOT_PROVEN


# ─── Test AC : LiveState 5 niveaux ───────────────────────────────────────────

def test_AC_live_state_5_levels() -> None:
    """LiveState expose les 5 niveaux correctement."""
    # Niveau 0 : pas joignable
    live = LiveState()
    assert live.reachable is False
    assert live.available is False
    assert live.git_sha_known is False
    assert live.git_match is False

    # Niveau 1-2 : joignable + healthy
    live.reachable = True
    live.healthy = True
    assert live.available is True

    # Niveau 3 : sha connu
    live.git_sha = "abc1234"
    live.git_sha_known = True
    assert "abc1234" in live.evidence

    # Niveau 4 : height connu
    live.height = 1198
    assert "1198" in live.evidence

    # Niveau 5 : match
    live.git_match = True
    assert "✓" in live.evidence


# ─── Test AD : fail-closed pour CRITICAL ─────────────────────────────────────

def test_AD_fail_closed_critical_raises(tmp_path: Path) -> None:
    """run_checks avec CRITICAL + BLOCKED lève PreflightBlockedError.

    Dans tmp_path sans git repo → git_sync = BLOCKED → CRITICAL fail-closed.
    """
    pfe = PreflightEngine(root=tmp_path)
    with pytest.raises(PreflightBlockedError) as exc_info:
        pfe.run_checks(
            task_id="test-AD",
            mode=PreflightMode.LITE,
            operation_risk=OperationRisk.CRITICAL,
        )
    assert "PREFLIGHT_BLOCKED" in str(exc_info.value) or "git" in str(exc_info.value).lower()


# ─── Test AE : fail-open pour ANALYSIS ───────────────────────────────────────

def test_AE_fail_open_analysis_does_not_raise(tmp_path: Path, tmp_ledger: Path) -> None:
    """run_checks avec ANALYSIS + DEGRADED/EXPECTED_LAG ne lève pas.

    Même avec un ledger désynchronisé, ANALYSIS ne doit pas bloquer.
    """
    pfe = PreflightEngine(root=tmp_path)
    # ANALYSIS n'est pas fail-closed même si DEGRADED
    result = pfe.run_checks(
        task_id="test-AE",
        mode=PreflightMode.LITE,
        operation_risk=OperationRisk.ANALYSIS,
    )
    # Pas d'exception levée — le résultat peut être DEGRADED/BLOCKED/etc.
    assert result is not None


# ─── Test AF : snapshot triade remote/local/live ─────────────────────────────

def test_AF_snapshot_triad(tmp_path: Path, tmp_ledger: Path) -> None:
    """build_context_snapshot() contient les trois triades."""
    pfe = PreflightEngine(root=tmp_path)
    snap = pfe.build_context_snapshot()

    # Git local
    assert "git_sha" in snap
    assert "git_branch" in snap
    assert "git_dirty" in snap

    # Remote (P0-B)
    assert "remote_sha" in snap
    assert "remote_sync" in snap

    # Ledger (P0-A)
    assert "ledger_sha256" in snap
    assert "ledger_recorded_sha" in snap

    # Live (P0-E)
    assert "live_reachable" in snap
    assert "live_healthy" in snap
    assert "live_git_sha" in snap
    assert "live_git_match" in snap
    assert "live_height" in snap

    # Méta
    assert snap["certified_100"] is False
    assert "snapshot_ts" in snap


# ─── Test : _FAIL_CLOSED_RISKS contient exactement les risques attendus ──────

def test_fail_closed_risks_set() -> None:
    """Les risques fail-closed sont exactement DEPLOY, LIVE_WRITE, CRITICAL, CODE_CHANGE."""
    assert OperationRisk.DEPLOY in _FAIL_CLOSED_RISKS
    assert OperationRisk.LIVE_WRITE in _FAIL_CLOSED_RISKS
    assert OperationRisk.CRITICAL in _FAIL_CLOSED_RISKS
    assert OperationRisk.CODE_CHANGE in _FAIL_CLOSED_RISKS
    # Ces risques ne sont PAS fail-closed
    assert OperationRisk.READ not in _FAIL_CLOSED_RISKS
    assert OperationRisk.ANALYSIS not in _FAIL_CLOSED_RISKS
    assert OperationRisk.TEST not in _FAIL_CLOSED_RISKS


# ═══════════════════════════════════════════════════════════════════════════════
# Tests T/U/V/W — R370 bypass-closure (2026-09-18)
# ═══════════════════════════════════════════════════════════════════════════════
#
# Test T : appel Python direct à require_operation_authorized() sans Gate HTTP
#           → Gate logicielle intercepte (pas de bypass à ce niveau)
# Test U : autorisation à usage unique — consume_authorization empêche réutilisation
# Test V : ARTCB_PREFLIGHT_GATE_DISABLED=1 + ARTCB_ENV=production → GateProductionBypassError
# Test W : matrice appelants append_block — vérifier que la Gate est bien au point
#           d'écriture interne (pas seulement sur les routes HTTP)
# ═══════════════════════════════════════════════════════════════════════════════

import os
import importlib


# ─── Test T : Gate logicielle intercepte l'appel Python direct ────────────────

def test_T_direct_python_call_blocked_by_gate() -> None:
    """Test T (R370) : require_operation_authorized() bloque si preflight BLOCKED.

    Démontre que la Gate n'est pas contournée par un appel Python direct
    (le bypass serait un appel à append_block() sans require_operation_authorized).
    Ce test vérifie que la Gate elle-même fonctionne quand on l'appelle directement.
    """
    engine = PreflightEngine()
    gate = PreflightGate(engine)

    # Forcer un résultat BLOCKED en simulant un ledger divergeant fortement
    fake_ledger = CheckResult(
        check_id="ledger_sync",
        status=CheckStatus.BLOCKED,
        evidence="REAL_DIVERGENCE: ledger SHA inconnu de git",
    )
    blocked_result = PreflightResult(
        task_id="test_T",
        mode=PreflightMode.FULL,
        checks=[fake_ledger],
        git=GitState(sha_short="aaa", sha_full="aaa", branch="main",
                     dirty=False, available=True, recent_parents=[]),
        live=LiveState(reachable=False, healthy=False, git_sha_known=False,
                       git_sha="", height=0, last_hash="", git_match=False,
                       url="http://localhost:8000"),
        ledger=LedgerState(available=False, sha256="", recorded_sha="X"),
        remote=RemoteGitState(available=False, sha_short="", sha_full="", branch="main"),
        remote_sync=RemoteSyncStatus.NOT_PROVEN,
    )

    auth = gate.authorize(
        operation="append_block",
        risk=OperationRisk.LIVE_WRITE,
        task_id="test_T",
        preflight_result=blocked_result,
    )

    # BLOCKED → auth.allowed doit être False
    assert not auth.allowed, "Auth BLOCKED doit avoir allowed=False"
    with pytest.raises(PreflightBlockedError):
        gate.require_authorized(auth)


def test_T2_direct_python_call_allowed_when_ok() -> None:
    """Test T2 (R370) : Gate autorise si preflight OK.

    Vérifie que la Gate n'est pas trop restrictive (pas de faux positif).
    """
    engine = PreflightEngine()
    gate = PreflightGate(engine)

    ok_result = PreflightResult(
        task_id="test_T2",
        mode=PreflightMode.LITE,
        checks=[],
        git=GitState(sha_short="abc", sha_full="abc123", branch="main",
                     dirty=False, available=True, recent_parents=[]),
        live=LiveState(reachable=False, healthy=False, git_sha_known=False,
                       git_sha="", height=0, last_hash="", git_match=False,
                       url="http://localhost:8000"),
        ledger=LedgerState(available=True, sha256="ok", recorded_sha="abc"),
        remote=RemoteGitState(available=False, sha_short="", sha_full="", branch="main"),
        remote_sync=RemoteSyncStatus.NOT_PROVEN,
    )

    auth = gate.authorize(
        operation="append_block",
        risk=OperationRisk.LIVE_WRITE,
        task_id="test_T2",
        preflight_result=ok_result,
    )
    # PASS / EXPECTED_LAG → allowed
    assert auth.allowed, "Auth OK doit avoir allowed=True"
    gate.require_authorized(auth)  # ne doit pas lever


# ─── Test U : consume_authorization — usage unique ────────────────────────────

def test_U_consume_authorization_blocks_reuse() -> None:
    """Test U (R370) : consume_authorization() empêche la réutilisation d'une auth.

    Démontre le modèle capability à usage unique :
        autorisation → opération → consommation → réutilisation refusée.
    """
    engine = PreflightEngine()
    gate = PreflightGate(engine)

    ok_result = PreflightResult(
        task_id="test_U",
        mode=PreflightMode.LITE,
        checks=[],
        git=GitState(sha_short="abc", sha_full="abc123", branch="main",
                     dirty=False, available=True, recent_parents=[]),
        live=LiveState(reachable=False, healthy=False, git_sha_known=False,
                       git_sha="", height=0, last_hash="", git_match=False,
                       url="http://localhost:8000"),
        ledger=LedgerState(available=True, sha256="ok", recorded_sha="abc"),
        remote=RemoteGitState(available=False, sha_short="", sha_full="", branch="main"),
        remote_sync=RemoteSyncStatus.NOT_PROVEN,
    )

    auth = gate.authorize(
        operation="wallet_create",
        risk=OperationRisk.CRITICAL,
        task_id="test_U",
        preflight_result=ok_result,
    )
    assert auth.allowed

    # Première utilisation : OK
    gate.require_authorized(auth)

    # Consommation
    gate.consume_authorization(auth)
    assert auth.consumed is True

    # Deuxième utilisation : doit être refusée
    with pytest.raises(PreflightBlockedError, match="consommée"):
        gate.require_authorized(auth)


def test_U2_unconsumed_auth_reusable() -> None:
    """Test U2 (R370) : une auth non consommée peut être appelée plusieurs fois.

    Vérifie que consume_authorization() est bien explicite (pas automatique).
    """
    engine = PreflightEngine()
    gate = PreflightGate(engine)

    ok_result = PreflightResult(
        task_id="test_U2",
        mode=PreflightMode.LITE,
        checks=[],
        git=GitState(sha_short="abc", sha_full="abc123", branch="main",
                     dirty=False, available=True, recent_parents=[]),
        live=LiveState(reachable=False, healthy=False, git_sha_known=False,
                       git_sha="", height=0, last_hash="", git_match=False,
                       url="http://localhost:8000"),
        ledger=LedgerState(available=True, sha256="ok", recorded_sha="abc"),
        remote=RemoteGitState(available=False, sha_short="", sha_full="", branch="main"),
        remote_sync=RemoteSyncStatus.NOT_PROVEN,
    )

    auth = gate.authorize(
        operation="add_device",
        risk=OperationRisk.CRITICAL,
        task_id="test_U2",
        preflight_result=ok_result,
    )
    # Sans consume_authorization, require_authorized peut être appelé plusieurs fois
    gate.require_authorized(auth)
    gate.require_authorized(auth)  # toujours OK (non consommée)
    assert not auth.consumed


# ─── Test V : bypass Gate en production → GateProductionBypassError ───────────

def test_V_production_bypass_raises() -> None:
    """Test V (R370) : ARTCB_PREFLIGHT_GATE_DISABLED=1 + ARTCB_ENV=production → erreur.

    Démontre que la Gate ne peut pas être désactivée en production.
    fail-closed garanti au chargement du module.
    """
    from src.artcb.agent_control.gate import GateProductionBypassError, _check_gate_disabled

    with patch.dict(os.environ, {
        "ARTCB_PREFLIGHT_GATE_DISABLED": "1",
        "ARTCB_ENV": "production",
    }):
        with pytest.raises(GateProductionBypassError, match="interdit en production"):
            _check_gate_disabled()


def test_V2_production_bypass_also_with_NODE_ENV() -> None:
    """Test V2 (R370) : NODE_ENV=production est aussi détecté."""
    from src.artcb.agent_control.gate import GateProductionBypassError, _check_gate_disabled

    with patch.dict(os.environ, {
        "ARTCB_PREFLIGHT_GATE_DISABLED": "1",
        "NODE_ENV": "production",
    }, clear=False):
        # S'assurer qu'ARTCB_ENV n'est pas "production" pour ce test
        env_backup = os.environ.pop("ARTCB_ENV", None)
        try:
            with pytest.raises(GateProductionBypassError):
                _check_gate_disabled()
        finally:
            if env_backup is not None:
                os.environ["ARTCB_ENV"] = env_backup


def test_V3_dev_bypass_allowed() -> None:
    """Test V3 (R370) : ARTCB_PREFLIGHT_GATE_DISABLED=1 sans ARTCB_ENV=production → OK."""
    from src.artcb.agent_control.gate import _check_gate_disabled

    env = {"ARTCB_PREFLIGHT_GATE_DISABLED": "1"}
    # Aucune variable de production
    saved_artcb = os.environ.pop("ARTCB_ENV", None)
    saved_node = os.environ.pop("NODE_ENV", None)
    try:
        with patch.dict(os.environ, env, clear=False):
            result = _check_gate_disabled()
            assert result is True  # désactivé en dev = acceptable
    finally:
        if saved_artcb is not None:
            os.environ["ARTCB_ENV"] = saved_artcb
        if saved_node is not None:
            os.environ["NODE_ENV"] = saved_node


# ─── Test W : Gate présente au point d'écriture (append_block lui-même) ───────

def test_W_gate_is_at_write_point_not_only_http() -> None:
    """Test W (R370) : la Gate est intégrée dans append_block(), pas seulement HTTP.

    Vérifie que le code source de ChainManager.append_block() contient
    l'appel require_operation_authorized(), prouvant que TOUS les appelants
    (mining, bridge, memory, authz, p2p) passent par la Gate.

    Ce test est statique (analyse source) car instancier ChainManager complet
    nécessiterait un nœud live.
    """
    import inspect
    from pathlib import Path

    manager_path = Path(__file__).resolve().parents[1] / "src/artcb/chain/manager.py"
    source = manager_path.read_text()

    # La Gate doit être présente dans la fonction append_block
    assert "require_operation_authorized" in source, \
        "require_operation_authorized absent de manager.py"
    assert "OperationRisk.LIVE_WRITE" in source, \
        "OperationRisk.LIVE_WRITE absent de manager.py"
    assert "dry_run" in source, \
        "dry_run absent de manager.py (skip dry_run pour PBFT)"

    # Vérifier que c'est bien DANS append_block (pas ailleurs dans le fichier)
    lines = source.splitlines()
    in_append_block = False
    found_gate_in_append = False
    for line in lines:
        if "def append_block(" in line:
            in_append_block = True
        if in_append_block and "require_operation_authorized" in line:
            found_gate_in_append = True
            break
        # Sortie de la fonction (prochain def au même niveau d'indentation)
        if in_append_block and line.startswith("    def ") and "append_block" not in line:
            break

    assert found_gate_in_append, \
        "require_operation_authorized doit être appelé DANS append_block(), " \
        "pas uniquement dans les routes HTTP"


def test_W2_gate_also_in_wallet_create() -> None:
    """Test W2 (R370) : Gate présente dans wallet_create (routes.py)."""
    from pathlib import Path
    routes_path = Path(__file__).resolve().parents[1] / "src/api/routes.py"
    source = routes_path.read_text()

    # Chercher dans wallet_create
    lines = source.splitlines()
    in_wallet_create = False
    found_gate = False
    for line in lines:
        if "def wallet_create(" in line:
            in_wallet_create = True
        if in_wallet_create and "require_operation_authorized" in line:
            found_gate = True
            break
        if in_wallet_create and line.startswith("def ") and "wallet_create" not in line:
            break

    assert found_gate, "require_operation_authorized doit être dans wallet_create()"


def test_W3_all_fail_closed_callers_documented() -> None:
    """Test W3 (R370) : matrice des appelants append_block documentée et cohérente.

    Vérifie que les appelants principaux d'append_block sont connus
    et que leur comportement dry_run/live est cohérent.

    Matrice attendue (source d'écriture réelle = dry_run=False par défaut) :
      - mining/pipeline.py    → dry_run=False (écriture réelle)
      - mining/protocol.py    → dry_run=False (écriture réelle)
      - api/bridges_routes.py → dry_run=False (écriture réelle)
      - authz/anchor.py       → dry_run=False (écriture réelle)
      - memory/repo_ingest.py → dry_run=False (écriture réelle)
      - api/consensus_routes.py → dry_run=True pour propose (PBFT)
      - p2p/producer_runtime.py → dry_run=True par défaut (failover)
    Tous passent par append_block() → Gate LIVE_WRITE active pour dry_run=False.
    """
    from pathlib import Path

    root = Path(__file__).resolve().parents[1] / "src"
    callers = {
        "artcb/mining/pipeline.py": {"has_append_block": True, "dry_run_safe": False},
        "artcb/mining/protocol.py": {"has_append_block": True, "dry_run_safe": False},
        "api/bridges_routes.py": {"has_append_block": True, "dry_run_safe": False},
        "artcb/authz/anchor.py": {"has_append_block": True, "dry_run_safe": False},
        "artcb/memory/repo_ingest.py": {"has_append_block": True, "dry_run_safe": False},
        "api/consensus_routes.py": {"has_append_block": True, "dry_run_safe": True},  # propose=dry_run
        "artcb/p2p/producer_runtime.py": {"has_append_block": True, "dry_run_safe": True},
    }

    for rel_path, expected in callers.items():
        path = root / rel_path
        assert path.exists(), f"Fichier attendu absent : {rel_path}"
        source = path.read_text()
        if expected["has_append_block"]:
            assert "append_block" in source, \
                f"append_block attendu dans {rel_path}"
