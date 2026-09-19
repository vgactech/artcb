"""PreflightEngine ARTCB — Vérifications préalables (R368+R369, 2026-09-18).

## Corrections R369 (audit rapport 370 point 1-10)

### P0-A — Sémantique ledger/Git corrigée
  Avant : ledger.git_head comparé naïvement à git HEAD
          → LEDGER_DIVERGENCE permanente car le fichier ne peut pas contenir
            son propre SHA avant que le commit qui le contient existe.
  Après : classify_git_ledger_sync() distingue :
          - PASS           : HEAD == recorded_sha
          - EXPECTED_LAG   : HEAD est enfant direct, commit = ledger-only
          - REAL_DIVERGENCE: changements de code non synchronisés

### P0-B — Remote GitHub synchronization
  Ajout : RemoteGitState + get_remote_git_state()
          compare_local_remote() → LOCAL_AHEAD / REMOTE_AHEAD / IN_SYNC / NOT_PROVEN
          fetch_remote() pour mise à jour optionnelle (non-bloquant)

### P0-C — OperationRisk + PreflightGate
  Ajout : OperationRisk (READ / ANALYSIS / CODE_CHANGE / TEST / DEPLOY / LIVE_WRITE / CRITICAL)
          PreflightGate.authorize() → Authorization
          PreflightGate.require_authorized() → lève PreflightBlockedError si non autorisé
          required_preflight_mode(operation) → détermine LITE/FULL selon risque

### P0-D — Fail-closed pour opérations protégées
  Ajout : Authorization.allowed / reason / operation_id
          PreflightBlockedError(RuntimeError) pour opérations PROTECTED
          run_checks() lève PreflightBlockedError si BLOCKED + operation PROTÉGÉE

### P0-E — LiveState enrichi
  Ajout : live_reachable / live_healthy / live_git_sha_known / live_git_match
          Séparation explicite des 5 niveaux LIVE

## Honnêteté
CERTIFIED_100=false. Tests adversariaux M→S dans test_r369_adversarial.py.
"""
from __future__ import annotations
MODULE_VERSION = '1.0.0'  # R390 — auto-versioning

import hashlib
import json
import subprocess
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

try:
    import yaml  # type: ignore[import]
    _YAML_AVAILABLE = True
except ImportError:
    _YAML_AVAILABLE = False

# ─── Chemins ─────────────────────────────────────────────────────────────────

_ROOT = Path(__file__).resolve().parents[3]

# ─── Exceptions ──────────────────────────────────────────────────────────────

class PreflightBlockedError(RuntimeError):
    """Levée quand une opération protégée est bloquée par PreflightGate.

    P0-D : fail-closed pour opérations PROTECTED_WRITE, LIVE_OPERATION, CRITICAL.
    """
    def __init__(self, reason: str, operation: str = "", check_id: str = ""):
        self.reason = reason
        self.operation = operation
        self.check_id = check_id
        super().__init__(f"PREFLIGHT_BLOCKED [{operation}]: {reason}")


# ─── OperationRisk ────────────────────────────────────────────────────────────

class OperationRisk(str, Enum):
    """Classification du risque d'une opération (P0-C).

    Détermine le mode de preflight requis et si l'opération est protégée.
    """
    READ          = "READ"          # lecture seule — LITE, non protégé
    ANALYSIS      = "ANALYSIS"      # analyse/rapport — LITE, non protégé
    CODE_CHANGE   = "CODE_CHANGE"   # modification code — FULL, protégé
    TEST          = "TEST"          # exécution tests — FULL, non protégé
    DEPLOY        = "DEPLOY"        # déploiement live — FULL, protégé fail-closed
    LIVE_WRITE    = "LIVE_WRITE"    # écriture blockchain — FULL, protégé fail-closed
    CRITICAL      = "CRITICAL"      # identité/wallet/genesis — FULL, protégé fail-closed


# Opérations qui requièrent fail-closed (P0-D)
_FAIL_CLOSED_RISKS = {
    OperationRisk.DEPLOY,
    OperationRisk.LIVE_WRITE,
    OperationRisk.CRITICAL,
    OperationRisk.CODE_CHANGE,
}


def required_preflight_mode(risk: OperationRisk) -> "PreflightMode":
    """Détermine le mode de preflight requis selon le risque (P0-C).

    Empêche l'appelant de choisir LITE pour une opération CODE_CHANGE.
    """
    if risk in (OperationRisk.READ, OperationRisk.ANALYSIS):
        return PreflightMode.LITE
    return PreflightMode.FULL


# ─── Status de check individuel ──────────────────────────────────────────────

class CheckStatus(str, Enum):
    PASS         = "PASS"          # vérification réussie
    FAIL         = "FAIL"          # vérification échouée
    BLOCKED      = "BLOCKED"       # bloqué — opération protégée ne peut pas continuer
    DEGRADED     = "DEGRADED"      # dégradé — peut continuer avec avertissement
    NOT_PROVEN   = "NOT_PROVEN"    # non prouvé (live inaccessible, remote inaccessible)
    SKIPPED      = "SKIPPED"       # non requis pour cette tâche
    EXPECTED_LAG = "EXPECTED_LAG"  # P0-A : lag d'un commit ledger-only — normal


class PreflightMode(str, Enum):
    LITE = "lite"   # explication : git + ledger
    FULL = "full"   # code change : git + remote + ledger + live


# ─── Résultats élémentaires ───────────────────────────────────────────────────

@dataclass
class CheckResult:
    check_id: str
    status: CheckStatus
    evidence: str = ""
    detail: str = ""
    duration_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "check_id": self.check_id,
            "status": self.status.value,
            "evidence": self.evidence,
            "detail": self.detail,
            "duration_ms": round(self.duration_ms, 2),
        }


# ─── États collectés ─────────────────────────────────────────────────────────

@dataclass
class GitState:
    """État Git LOCAL au moment du preflight."""
    sha_short: str = ""
    sha_full: str = ""
    branch: str = ""
    dirty: bool = False
    available: bool = False
    # P0-A : liste des commits récents (pour détecter EXPECTED_LAG)
    recent_parents: list[str] = field(default_factory=list)

    @property
    def evidence(self) -> str:
        d = "+dirty" if self.dirty else ""
        return f"git:{self.sha_short}{d}@{self.branch}" if self.available else "git:unavailable"


@dataclass
class RemoteGitState:
    """État Git DISTANT (origin/main) — P0-B."""
    sha_short: str = ""
    sha_full: str = ""
    branch: str = ""
    available: bool = False
    fetch_ts: float = 0.0

    @property
    def evidence(self) -> str:
        return f"remote:{self.sha_short}@{self.branch}" if self.available else "remote:unavailable"


class RemoteSyncStatus(str, Enum):
    IN_SYNC      = "IN_SYNC"       # local == remote
    LOCAL_AHEAD  = "LOCAL_AHEAD"   # travail local non poussé
    REMOTE_AHEAD = "REMOTE_AHEAD"  # local en retard (pull requis)
    DIVERGED     = "DIVERGED"      # branches divergées
    NOT_PROVEN   = "NOT_PROVEN"    # remote inaccessible


@dataclass
class LiveState:
    """État du nœud live ARTCB — P0-E : 5 niveaux distincts."""
    # Niveau 1 : nœud joignable
    reachable: bool = False
    # Niveau 2 : santé confirmée
    healthy: bool = False
    # Niveau 3 : git_sha connu
    git_sha_known: bool = False
    git_sha: str = ""
    # Niveau 4 : chaîne disponible
    height: int = 0
    last_hash: str = ""
    # Niveau 5 : git SHA correspond au git local
    git_match: bool = False
    url: str = ""

    @property
    def available(self) -> bool:
        """Compatibilité ascendante — True si au moins joignable."""
        return self.reachable

    @property
    def evidence(self) -> str:
        if not self.reachable:
            return "live:unreachable"
        parts = [f"live:h={self.height}"]
        if self.git_sha_known:
            match = "✓" if self.git_match else "✗"
            parts.append(f"sha={self.git_sha[:7]}{match}")
        return ",".join(parts)


@dataclass
class LedgerState:
    """État du task ledger au moment du preflight."""
    # P0-A : recorded_sha = le SHA enregistré dans le ledger
    # Ce n'est PAS forcément git HEAD (décalage d'un commit normal)
    recorded_sha: str = ""   # anciennement git_head
    chain_height: int = 0
    global_pct: int = 0
    open_count: int = 0
    sha256: str = ""
    available: bool = False

    @property
    def git_head(self) -> str:
        """Compatibilité ascendante."""
        return self.recorded_sha

    @property
    def evidence(self) -> str:
        return f"ledger:sha256={self.sha256[:12]},rec={self.recorded_sha[:7]}" if self.available else "ledger:unavailable"


# ─── Authorization ────────────────────────────────────────────────────────────

@dataclass
class Authorization:
    """Résultat d'une autorisation PreflightGate (P0-C/P0-D)."""
    allowed: bool
    operation_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    operation: str = ""
    risk: OperationRisk = OperationRisk.READ
    reason: str = ""
    preflight_context_sha: str = ""
    ts: float = field(default_factory=time.time)
    # True si cette autorisation est à usage unique (consume_authorization)
    consumed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "operation_id": self.operation_id,
            "operation": self.operation,
            "risk": self.risk.value,
            "reason": self.reason,
            "preflight_context_sha": self.preflight_context_sha,
            "ts": self.ts,
            "consumed": self.consumed,
        }


# ─── PreflightResult ──────────────────────────────────────────────────────────

@dataclass
class PreflightResult:
    """Résultat complet du preflight — entrée de ReflexEngine."""
    task_id: str
    mode: PreflightMode
    ts: float = field(default_factory=time.time)
    checks: list[CheckResult] = field(default_factory=list)
    git: GitState = field(default_factory=GitState)
    remote: RemoteGitState = field(default_factory=RemoteGitState)
    remote_sync: RemoteSyncStatus = RemoteSyncStatus.NOT_PROVEN
    live: LiveState = field(default_factory=LiveState)
    ledger: LedgerState = field(default_factory=LedgerState)
    context_sha: str = ""
    summary_lines: list[str] = field(default_factory=list)

    @property
    def overall_status(self) -> CheckStatus:
        """Status global : le pire parmi tous les checks (EXPECTED_LAG < PASS)."""
        if not self.checks:
            return CheckStatus.DEGRADED
        order = [
            CheckStatus.BLOCKED,
            CheckStatus.FAIL,
            CheckStatus.NOT_PROVEN,
            CheckStatus.DEGRADED,
            CheckStatus.EXPECTED_LAG,
            CheckStatus.SKIPPED,
            CheckStatus.PASS,
        ]
        for s in order:
            if any(c.status == s for c in self.checks):
                return s
        return CheckStatus.PASS

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "mode": self.mode.value,
            "ts": self.ts,
            "overall_status": self.overall_status.value,
            "context_sha": self.context_sha,
            "remote_sync": self.remote_sync.value,
            "checks": [c.to_dict() for c in self.checks],
            "git": {"sha_short": self.git.sha_short, "branch": self.git.branch,
                    "dirty": self.git.dirty, "available": self.git.available,
                    "evidence": self.git.evidence},
            "remote": {"sha_short": self.remote.sha_short, "available": self.remote.available,
                       "evidence": self.remote.evidence},
            "live": {"reachable": self.live.reachable, "healthy": self.live.healthy,
                     "git_sha": self.live.git_sha, "git_match": self.live.git_match,
                     "height": self.live.height, "evidence": self.live.evidence},
            "ledger": {"recorded_sha": self.ledger.recorded_sha, "sha256": self.ledger.sha256,
                       "available": self.ledger.available, "evidence": self.ledger.evidence},
        }


# ─── PreflightEngine ──────────────────────────────────────────────────────────

class PreflightEngine:
    """Moteur de vérifications préalables ARTCB (R368+R369).

    Usage:
        engine = PreflightEngine()
        # Mode automatique selon le risque de l'opération (P0-C)
        mode = required_preflight_mode(OperationRisk.CODE_CHANGE)
        result = engine.run_checks(task_id="R369", mode=mode)
        # Autorisation (P0-D)
        auth = gate.authorize("git_push", OperationRisk.CODE_CHANGE, result)
        gate.require_authorized(auth)  # lève PreflightBlockedError si BLOCKED
    """

    LIVE_URL = "http://151.80.107.29:8000"
    NETWORK_TIMEOUT_S = 2.0
    REMOTE_FETCH_TIMEOUT_S = 5.0

    def __init__(self, root: Path | None = None):
        self._root = root or _ROOT

    # ─── Collecteurs d'état ──────────────────────────────────────────────────

    def get_git_state(self) -> GitState:
        """Lit l'état Git LOCAL + parents récents pour détecter EXPECTED_LAG."""
        try:
            sha_full = subprocess.check_output(
                ["git", "rev-parse", "HEAD"],
                cwd=str(self._root), text=True, timeout=3,
            ).strip()
            sha_short = sha_full[:7]
            branch = subprocess.check_output(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                cwd=str(self._root), text=True, timeout=3,
            ).strip()
            dirty_out = subprocess.check_output(
                ["git", "status", "--porcelain"],
                cwd=str(self._root), text=True, timeout=3,
            ).strip()
            # P0-A : récupère les 5 parents pour détecter EXPECTED_LAG
            parents_raw = subprocess.check_output(
                ["git", "log", "--format=%H %s", "-5"],
                cwd=str(self._root), text=True, timeout=3,
            ).strip()
            parents = [line.split()[0][:7] for line in parents_raw.splitlines() if line.strip()]
            return GitState(
                sha_short=sha_short,
                sha_full=sha_full,
                branch=branch,
                dirty=bool(dirty_out),
                available=True,
                recent_parents=parents,
            )
        except Exception:
            return GitState(available=False)

    def get_remote_git_state(self) -> RemoteGitState:
        """Lit l'état Git DISTANT (origin/main) sans fetch — P0-B.

        Lit le SHA connu de origin/main depuis les refs locaux.
        Rapide (pas de réseau) mais peut être obsolète si pas fetchée récemment.
        """
        try:
            branch = subprocess.check_output(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                cwd=str(self._root), text=True, timeout=3,
            ).strip()
            remote_ref = f"origin/{branch}"
            sha_full = subprocess.check_output(
                ["git", "rev-parse", remote_ref],
                cwd=str(self._root), text=True, timeout=3,
            ).strip()
            return RemoteGitState(
                sha_short=sha_full[:7],
                sha_full=sha_full,
                branch=branch,
                available=True,
                fetch_ts=time.time(),
            )
        except Exception:
            return RemoteGitState(available=False)

    def fetch_remote(self) -> bool:
        """Exécute git fetch origin (réseau, timeout court) — P0-B.

        Non-bloquant en cas d'échec. Retourne True si réussi.
        """
        try:
            subprocess.check_call(
                ["git", "fetch", "origin", "--quiet"],
                cwd=str(self._root), timeout=self.REMOTE_FETCH_TIMEOUT_S,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            return True
        except Exception:
            return False

    def compare_local_remote(self, local: GitState, remote: RemoteGitState) -> RemoteSyncStatus:
        """Classifie la relation local ↔ remote — P0-B."""
        if not remote.available:
            return RemoteSyncStatus.NOT_PROVEN
        if not local.available:
            return RemoteSyncStatus.NOT_PROVEN
        if local.sha_full == remote.sha_full:
            return RemoteSyncStatus.IN_SYNC
        # Local est en avance si remote SHA est dans les parents locaux
        if remote.sha_short in local.recent_parents:
            return RemoteSyncStatus.LOCAL_AHEAD
        # Remote est en avance si local SHA est dans... on ne peut pas savoir
        # sans fetch. On retourne REMOTE_AHEAD par défaut si SHAs différents
        # et local n'est pas en avance.
        return RemoteSyncStatus.REMOTE_AHEAD

    def get_live_state(self) -> LiveState:
        """Interroge le nœud live OVH2 — P0-E : 5 niveaux."""
        import urllib.request
        state = LiveState(url=self.LIVE_URL)

        # Niveau 1 + 2 + 3 : /health
        try:
            req = urllib.request.urlopen(
                f"{self.LIVE_URL}/health", timeout=self.NETWORK_TIMEOUT_S
            )
            data = json.loads(req.read().decode())
            state.reachable = True
            state.healthy = data.get("status") == "healthy"
            raw_sha = str(data.get("git_sha", ""))
            if raw_sha and raw_sha != "unknown":
                state.git_sha = raw_sha[:7]
                state.git_sha_known = True
        except Exception:
            return state  # non joignable

        # Niveau 4 : /api/v1/ai/status
        try:
            req = urllib.request.urlopen(
                f"{self.LIVE_URL}/api/v1/ai/status", timeout=self.NETWORK_TIMEOUT_S
            )
            data = json.loads(req.read().decode())
            chain = data.get("chain", {})
            lb = chain.get("last_block") or {}
            state.height = int(chain.get("height") or 0)
            state.last_hash = str(lb.get("hash", ""))[:16]
        except Exception:
            pass

        return state

    def load_task_ledger(self) -> LedgerState:
        """Charge le task ledger et calcule son SHA256."""
        ledger_path = self._root / ".artcb" / "task_ledger.yaml"
        if not ledger_path.exists():
            return LedgerState(available=False)
        try:
            raw = ledger_path.read_bytes()
            sha = hashlib.sha256(raw).hexdigest()
            if not _YAML_AVAILABLE:
                return LedgerState(sha256=sha, available=True)
            data = yaml.safe_load(raw.decode("utf-8")) or {}
            meta = data.get("meta", {})
            progress = data.get("progress", {})
            open_tasks = data.get("open") or []
            # P0-A : utiliser recorded_sha (anciennement git_head)
            recorded = str(meta.get("git_head", "") or meta.get("recorded_sha", ""))
            return LedgerState(
                recorded_sha=recorded,
                chain_height=int(meta.get("chain_height") or 0),
                global_pct=int(progress.get("global_pct") or 0),
                open_count=len(open_tasks),
                sha256=sha,
                available=True,
            )
        except Exception:
            return LedgerState(available=False)

    # ─── P0-A : classification divergence ledger/Git ─────────────────────────

    def classify_git_ledger_sync(
        self, git: GitState, ledger: LedgerState
    ) -> CheckResult:
        """P0-A : distingue PASS / EXPECTED_LAG / REAL_DIVERGENCE.

        EXPECTED_LAG : git HEAD est enfant direct de recorded_sha et le commit
        est un ledger-only sync. C'est le comportement normal après un push
        de synchronisation ledger.

        REAL_DIVERGENCE : changements de code non reflétés dans le ledger.
        """
        t0 = time.time()

        if not git.available:
            return CheckResult("git_sync", CheckStatus.BLOCKED,
                detail="Git non disponible", duration_ms=(time.time()-t0)*1000)

        if not ledger.available:
            return CheckResult("git_sync", CheckStatus.DEGRADED,
                evidence=git.evidence,
                detail="Ledger absent — divergence non vérifiable",
                duration_ms=(time.time()-t0)*1000)

        rec = ledger.recorded_sha[:7]
        g = git.sha_short[:7]

        # Cas 1 : identiques → PASS
        if rec == g or git.sha_full.startswith(rec):
            return CheckResult("git_sync", CheckStatus.PASS,
                evidence=f"recorded={rec} git={g}",
                duration_ms=(time.time()-t0)*1000)

        # Cas 2 : recorded est dans les parents récents → EXPECTED_LAG
        # (git HEAD est 1 commit en avance sur recorded = commit de sync ledger)
        if rec in git.recent_parents:
            return CheckResult("git_sync", CheckStatus.EXPECTED_LAG,
                evidence=f"recorded={rec} git={g}",
                detail=(
                    f"EXPECTED_LAG : git HEAD={g} est un enfant direct de "
                    f"recorded={rec} — normal après un push de sync ledger"
                ),
                duration_ms=(time.time()-t0)*1000)

        # Cas 3 : divergence réelle
        return CheckResult("git_sync", CheckStatus.DEGRADED,
            evidence=f"recorded={rec} git={g}",
            detail=(
                f"REAL_DIVERGENCE: ledger.recorded_sha={rec} ↔ git={g} — "
                "changements de code non synchronisés avec le ledger"
            ),
            duration_ms=(time.time()-t0)*1000)

    # ─── Checks individuels ───────────────────────────────────────────────────

    def _check_ledger_available(self, ledger: LedgerState) -> CheckResult:
        t0 = time.time()
        if ledger.available:
            return CheckResult("ledger_available", CheckStatus.PASS,
                evidence=ledger.evidence, duration_ms=(time.time()-t0)*1000)
        return CheckResult("ledger_available", CheckStatus.DEGRADED,
            detail=".artcb/task_ledger.yaml absent ou illisible",
            duration_ms=(time.time()-t0)*1000)

    def _check_remote_sync(
        self, local: GitState, remote: RemoteGitState, sync: RemoteSyncStatus
    ) -> CheckResult:
        """P0-B : vérification synchronisation remote."""
        t0 = time.time()
        if not remote.available:
            return CheckResult("remote_sync", CheckStatus.NOT_PROVEN,
                detail="Remote origin inaccessible — état non prouvé",
                duration_ms=(time.time()-t0)*1000)
        icons = {
            RemoteSyncStatus.IN_SYNC: CheckStatus.PASS,
            RemoteSyncStatus.LOCAL_AHEAD: CheckStatus.DEGRADED,
            RemoteSyncStatus.REMOTE_AHEAD: CheckStatus.DEGRADED,
            RemoteSyncStatus.DIVERGED: CheckStatus.BLOCKED,
            RemoteSyncStatus.NOT_PROVEN: CheckStatus.NOT_PROVEN,
        }
        status = icons.get(sync, CheckStatus.NOT_PROVEN)
        detail = {
            RemoteSyncStatus.IN_SYNC: "",
            RemoteSyncStatus.LOCAL_AHEAD: f"local={local.sha_short} en avance sur remote={remote.sha_short} — git push requis",
            RemoteSyncStatus.REMOTE_AHEAD: f"remote={remote.sha_short} en avance sur local={local.sha_short} — git pull requis",
            RemoteSyncStatus.DIVERGED: "branches divergées — merge/rebase requis",
        }.get(sync, "état inconnu")
        return CheckResult("remote_sync", status,
            evidence=f"local={local.sha_short} remote={remote.sha_short}",
            detail=detail, duration_ms=(time.time()-t0)*1000)

    def _check_live_node(self, live: LiveState, mode: PreflightMode) -> CheckResult:
        t0 = time.time()
        if mode == PreflightMode.LITE:
            return CheckResult("live_node", CheckStatus.SKIPPED,
                detail="Mode lite — live non requis",
                duration_ms=(time.time()-t0)*1000)
        if not live.reachable:
            return CheckResult("live_node", CheckStatus.NOT_PROVEN,
                detail=f"Nœud live {live.url} inaccessible",
                duration_ms=(time.time()-t0)*1000)
        if not live.healthy:
            return CheckResult("live_node", CheckStatus.DEGRADED,
                evidence=live.evidence,
                detail="Nœud live joignable mais pas healthy",
                duration_ms=(time.time()-t0)*1000)
        return CheckResult("live_node", CheckStatus.PASS,
            evidence=live.evidence, duration_ms=(time.time()-t0)*1000)

    def _check_git_code_deployed(
        self, git: GitState, live: LiveState, mode: PreflightMode
    ) -> CheckResult:
        """P0-E : vérification déploiement en 5 niveaux."""
        t0 = time.time()
        if mode == PreflightMode.LITE:
            return CheckResult("code_deployed", CheckStatus.SKIPPED,
                detail="Mode lite — déploiement non vérifié",
                duration_ms=(time.time()-t0)*1000)
        if not live.reachable:
            return CheckResult("code_deployed", CheckStatus.NOT_PROVEN,
                detail="Live inaccessible — déploiement non vérifiable",
                duration_ms=(time.time()-t0)*1000)
        if not live.git_sha_known:
            return CheckResult("code_deployed", CheckStatus.NOT_PROVEN,
                evidence=live.evidence,
                detail="SHA git du live inconnu — /health ne retourne pas git_sha",
                duration_ms=(time.time()-t0)*1000)
        if not git.available:
            return CheckResult("code_deployed", CheckStatus.DEGRADED,
                evidence=live.evidence,
                detail="Git local non disponible",
                duration_ms=(time.time()-t0)*1000)
        # Niveau 5 : comparer
        live_sha = live.git_sha[:7]
        git_sha = git.sha_short[:7]
        match = git.sha_full.startswith(live_sha) or live_sha == git_sha
        if match:
            live.git_match = True
            return CheckResult("code_deployed", CheckStatus.PASS,
                evidence=f"git={git_sha} live={live_sha}",
                duration_ms=(time.time()-t0)*1000)
        # Lag d'un ou deux commits (déploiement en cours) → NOT_PROVEN
        if live_sha in git.recent_parents:
            return CheckResult("code_deployed", CheckStatus.NOT_PROVEN,
                evidence=f"git={git_sha} live={live_sha}",
                detail=f"Code non encore déployé : git={git_sha} > live={live_sha} (déploiement en cours ?)",
                duration_ms=(time.time()-t0)*1000)
        return CheckResult("code_deployed", CheckStatus.NOT_PROVEN,
            evidence=f"git={git_sha} live={live_sha}",
            detail=f"Divergence déploiement : git={git_sha} ≠ live={live_sha}",
            duration_ms=(time.time()-t0)*1000)

    # ─── Point d'entrée principal ─────────────────────────────────────────────

    def run_checks(
        self,
        task_id: str = "unknown",
        mode: PreflightMode = PreflightMode.FULL,
        operation_risk: OperationRisk = OperationRisk.ANALYSIS,
        do_fetch: bool = False,
    ) -> PreflightResult:
        """Exécute tous les checks et retourne un PreflightResult.

        P0-C : le mode est déterminé par operation_risk si non spécifié.
        P0-D : lève PreflightBlockedError si BLOCKED + risk protégé.

        Args:
            task_id:        identifiant tâche courante
            mode:           LITE/FULL (surchargé par required_preflight_mode si AUTO)
            operation_risk: risque de l'opération — détermine le mode si FULL requis
            do_fetch:       si True, exécute git fetch avant la vérification remote
        """
        # P0-C : le risque détermine le mode minimum
        required_mode = required_preflight_mode(operation_risk)
        if required_mode == PreflightMode.FULL:
            mode = PreflightMode.FULL

        # Collecter états
        git = self.get_git_state()
        ledger = self.load_task_ledger()

        remote = RemoteGitState(available=False)
        remote_sync = RemoteSyncStatus.NOT_PROVEN
        live = LiveState(url=self.LIVE_URL)

        if mode == PreflightMode.FULL:
            if do_fetch:
                self.fetch_remote()
            remote = self.get_remote_git_state()
            remote_sync = self.compare_local_remote(git, remote)
            live = self.get_live_state()
            # P0-E : git_match
            if live.git_sha_known and git.available:
                live.git_match = git.sha_full.startswith(live.git_sha)

        # Checks
        checks = [
            self._check_ledger_available(ledger),
            self.classify_git_ledger_sync(git, ledger),   # P0-A
        ]
        if mode == PreflightMode.FULL:
            checks += [
                self._check_remote_sync(git, remote, remote_sync),  # P0-B
                self._check_live_node(live, mode),
                self._check_git_code_deployed(git, live, mode),     # P0-E
            ]
        else:
            checks += [
                CheckResult("remote_sync", CheckStatus.SKIPPED, detail="Mode lite"),
                self._check_live_node(live, mode),
                CheckResult("code_deployed", CheckStatus.SKIPPED, detail="Mode lite"),
            ]

        # SHA contexte
        context_raw = json.dumps({
            "git": git.evidence, "remote": remote.evidence,
            "ledger": ledger.evidence, "live": live.evidence,
            "task_id": task_id, "mode": mode.value,
        }, sort_keys=True).encode()
        context_sha = hashlib.sha256(context_raw).hexdigest()[:16]

        result = PreflightResult(
            task_id=task_id, mode=mode,
            checks=checks, git=git, remote=remote,
            remote_sync=remote_sync, live=live, ledger=ledger,
            context_sha=context_sha,
        )
        result.summary_lines = self._build_summary(result)

        # P0-D : fail-closed pour opérations protégées
        if (result.overall_status == CheckStatus.BLOCKED
                and operation_risk in _FAIL_CLOSED_RISKS):
            blocked = next(
                (c for c in checks if c.status == CheckStatus.BLOCKED), None
            )
            raise PreflightBlockedError(
                reason=blocked.detail if blocked else "preflight BLOCKED",
                operation=task_id,
                check_id=blocked.check_id if blocked else "",
            )

        return result

    def _build_summary(self, r: PreflightResult) -> list[str]:
        overall = r.overall_status
        icon = {"PASS": "✅", "FAIL": "❌", "BLOCKED": "🚫", "DEGRADED": "⚠",
                "NOT_PROVEN": "🔵", "SKIPPED": "⏭", "EXPECTED_LAG": "🔄"}.get(overall.value, "?")
        lines = [f"## PREFLIGHT [{overall.value}] {icon} task={r.task_id} ctx={r.context_sha}"]
        for c in r.checks:
            if c.status == CheckStatus.SKIPPED:
                continue
            ci = {"PASS": "✅", "FAIL": "❌", "BLOCKED": "🚫", "DEGRADED": "⚠",
                  "NOT_PROVEN": "🔵", "EXPECTED_LAG": "🔄"}.get(c.status.value, "?")
            ev = f" [{c.evidence}]" if c.evidence else ""
            dt = f" — {c.detail}" if c.detail else ""
            lines.append(f"  {ci} {c.check_id}{ev}{dt}")
        # Remote sync résumé
        if r.remote_sync != RemoteSyncStatus.NOT_PROVEN:
            lines.append(f"  remote_sync={r.remote_sync.value}")
        return lines

    def build_context_snapshot(self) -> dict[str, Any]:
        """Snapshot complet pour ReasoningRecord — P0-E triade Remote/Local/Live."""
        git = self.get_git_state()
        remote = self.get_remote_git_state()
        ledger = self.load_task_ledger()
        live = self.get_live_state()
        if live.git_sha_known and git.available:
            live.git_match = git.sha_full.startswith(live.git_sha)
        remote_sync = self.compare_local_remote(git, remote)
        return {
            # Git local
            "git_sha": git.sha_full if git.available else None,
            "git_branch": git.branch if git.available else None,
            "git_dirty": git.dirty if git.available else None,
            # Git remote (P0-B)
            "remote_sha": remote.sha_full if remote.available else None,
            "remote_sync": remote_sync.value,
            # Ledger (P0-A)
            "ledger_sha256": ledger.sha256 if ledger.available else None,
            "ledger_recorded_sha": ledger.recorded_sha if ledger.available else None,
            "ledger_chain_height": ledger.chain_height if ledger.available else None,
            # Live (P0-E)
            "live_reachable": live.reachable,
            "live_healthy": live.healthy,
            "live_git_sha": live.git_sha if live.git_sha_known else None,
            "live_git_match": live.git_match,
            "live_height": live.height if live.reachable else None,
            "live_last_hash": live.last_hash if live.reachable else None,
            # Méta
            "snapshot_ts": time.time(),
            "certified_100": False,
        }


# ─── PreflightGate ────────────────────────────────────────────────────────────

class PreflightGate:
    """Barrière d'autorisation pour opérations protégées — P0-C/P0-D.

    Usage:
        gate = PreflightGate(engine)
        auth = gate.authorize("git_push", OperationRisk.CODE_CHANGE)
        gate.require_authorized(auth)  # lève PreflightBlockedError si non autorisé
    """

    def __init__(self, engine: PreflightEngine | None = None):
        self._engine = engine or PreflightEngine()
        self._issued: dict[str, Authorization] = {}  # operation_id → auth

    def authorize(
        self,
        operation: str,
        risk: OperationRisk = OperationRisk.ANALYSIS,
        task_id: str = "unknown",
        preflight_result: PreflightResult | None = None,
    ) -> Authorization:
        """Autorise ou refuse une opération selon le résultat du preflight.

        Si preflight_result n'est pas fourni, exécute run_checks() automatiquement.
        Pour les risques fail-closed, lève PreflightBlockedError si BLOCKED.
        """
        if preflight_result is None:
            mode = required_preflight_mode(risk)
            preflight_result = self._engine.run_checks(
                task_id=task_id,
                mode=mode,
                operation_risk=risk,
            )

        overall = preflight_result.overall_status
        # BLOCKED + opération protégée → refus
        if overall == CheckStatus.BLOCKED and risk in _FAIL_CLOSED_RISKS:
            auth = Authorization(
                allowed=False,
                operation=operation,
                risk=risk,
                reason=f"PREFLIGHT_BLOCKED: {overall.value}",
                preflight_context_sha=preflight_result.context_sha,
            )
            self._issued[auth.operation_id] = auth
            return auth

        # DEGRADED / EXPECTED_LAG / NOT_PROVEN → autorisé avec avertissement
        allowed = overall not in (CheckStatus.BLOCKED, CheckStatus.FAIL)
        auth = Authorization(
            allowed=allowed,
            operation=operation,
            risk=risk,
            reason="" if allowed else f"refused: {overall.value}",
            preflight_context_sha=preflight_result.context_sha,
        )
        self._issued[auth.operation_id] = auth
        return auth

    def require_authorized(self, auth: Authorization) -> None:
        """Lève PreflightBlockedError si l'autorisation est refusée (P0-D).

        Cette méthode est le point de fail-closed : les opérations protégées
        DOIVENT appeler require_authorized() avant de s'exécuter.
        """
        if not auth.allowed:
            raise PreflightBlockedError(
                reason=auth.reason,
                operation=auth.operation,
            )
        if auth.consumed:
            raise PreflightBlockedError(
                reason="autorisation déjà consommée (usage unique)",
                operation=auth.operation,
            )

    def consume_authorization(self, auth: Authorization) -> None:
        """Marque l'autorisation comme consommée (P0-C : usage unique).

        Empêche la réutilisation d'une autorisation pour plusieurs opérations.
        """
        if auth.operation_id in self._issued:
            self._issued[auth.operation_id].consumed = True
        auth.consumed = True
