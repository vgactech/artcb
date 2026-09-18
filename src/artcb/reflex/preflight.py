"""PreflightEngine ARTCB — Vérifications préalables obligatoires (R368, 2026-09-18).

## Rôle

Le PreflightEngine est la couche qui s'exécute AVANT ReflexEngine à chaque cycle.
Il vérifie l'état de l'environnement (ledger, Git, live, tâche) et produit un
PreflightResult structuré qui devient le contexte d'entrée du ReflexEngine.

## Architecture

    PROMPT
      ↓
    UserPromptHook
      ↓
    PreflightEngine           ← CE MODULE
      ├── load_task_ledger()
      ├── get_git_state()
      ├── get_live_state()
      ├── run_checks()
      └── build_context_snapshot()
      ↓
    ReflexEngine
      ↓
    ReasoningRecord

## Policy matrix (rapport 368-370)

| Situation                         | Action         |
|-----------------------------------|----------------|
| Git requis + Git disponible       | PASS           |
| Git requis + Git inaccessible     | BLOCKED        |
| live requis + live inaccessible   | NOT_PROVEN     |
| ledger inaccessible               | DEGRADED       |
| modification de code              | preflight full |
| simple explication                | preflight lite |

## Honnêteté

CERTIFIED_100=false — ce module est fonctionnel mais non certifié en
conditions adversariales réelles. La prochaine étape est le test de bypass
(test_r355_enforcement_e2e.py).
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import time
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


# ─── Status de check individuel ──────────────────────────────────────────────

class CheckStatus(str, Enum):
    PASS       = "PASS"       # vérification réussie
    FAIL       = "FAIL"       # vérification échouée
    BLOCKED    = "BLOCKED"    # bloqué — ne peut pas continuer
    DEGRADED   = "DEGRADED"   # dégradé — peut continuer avec avertissement
    NOT_PROVEN = "NOT_PROVEN" # non prouvé (live inaccessible, etc.)
    SKIPPED    = "SKIPPED"    # non requis pour cette tâche


class PreflightMode(str, Enum):
    LITE  = "lite"   # simple explication : git + ledger seulement
    FULL  = "full"   # modification de code : git + ledger + live + tâche
    NONE  = "none"   # aucune vérification (jamais utilisé si règle respectée)


# ─── Résultats élémentaires ───────────────────────────────────────────────────

@dataclass
class CheckResult:
    """Résultat d'une vérification individuelle."""
    check_id: str
    status: CheckStatus
    evidence: str = ""          # SHA, hauteur, timestamp, etc.
    detail: str = ""            # message humain
    duration_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "check_id": self.check_id,
            "status": self.status.value,
            "evidence": self.evidence,
            "detail": self.detail,
            "duration_ms": round(self.duration_ms, 2),
        }


@dataclass
class GitState:
    """État Git du dépôt au moment du preflight."""
    sha_short: str = ""
    sha_full: str = ""
    branch: str = ""
    dirty: bool = False
    available: bool = False

    @property
    def evidence(self) -> str:
        dirty_marker = "+dirty" if self.dirty else ""
        return f"git:{self.sha_short}{dirty_marker}@{self.branch}" if self.available else "git:unavailable"


@dataclass
class LiveState:
    """État du nœud live ARTCB au moment du preflight."""
    height: int = 0
    last_hash: str = ""
    git_sha: str = ""
    available: bool = False
    url: str = ""

    @property
    def evidence(self) -> str:
        return f"live:height={self.height},sha={self.git_sha[:7]}" if self.available else "live:unavailable"


@dataclass
class LedgerState:
    """État du task ledger au moment du preflight."""
    git_head: str = ""
    chain_height: int = 0
    global_pct: int = 0
    open_count: int = 0
    sha256: str = ""            # hash du fichier ledger (détection de race condition)
    available: bool = False

    @property
    def evidence(self) -> str:
        return f"ledger:sha256={self.sha256[:12]},head={self.git_head}" if self.available else "ledger:unavailable"


@dataclass
class PreflightResult:
    """Résultat complet du preflight — entrée de ReflexEngine."""
    task_id: str
    mode: PreflightMode
    ts: float = field(default_factory=time.time)
    checks: list[CheckResult] = field(default_factory=list)
    git: GitState = field(default_factory=GitState)
    live: LiveState = field(default_factory=LiveState)
    ledger: LedgerState = field(default_factory=LedgerState)
    # SHA du contexte complet — permet de détecter les changements entre sessions
    context_sha: str = ""
    # Résumé pour injection dans le prompt
    summary_lines: list[str] = field(default_factory=list)

    @property
    def overall_status(self) -> CheckStatus:
        """Status global : le pire parmi tous les checks."""
        if not self.checks:
            return CheckStatus.DEGRADED
        # Ordre de sévérité
        order = [
            CheckStatus.BLOCKED,
            CheckStatus.FAIL,
            CheckStatus.NOT_PROVEN,
            CheckStatus.DEGRADED,
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
            "checks": [c.to_dict() for c in self.checks],
            "git": {
                "sha_short": self.git.sha_short,
                "branch": self.git.branch,
                "dirty": self.git.dirty,
                "available": self.git.available,
                "evidence": self.git.evidence,
            },
            "live": {
                "height": self.live.height,
                "last_hash": self.live.last_hash,
                "git_sha": self.live.git_sha,
                "available": self.live.available,
                "evidence": self.live.evidence,
            },
            "ledger": {
                "git_head": self.ledger.git_head,
                "chain_height": self.ledger.chain_height,
                "global_pct": self.ledger.global_pct,
                "sha256": self.ledger.sha256,
                "available": self.ledger.available,
                "evidence": self.ledger.evidence,
            },
        }


# ─── PreflightEngine ──────────────────────────────────────────────────────────

class PreflightEngine:
    """Moteur de vérifications préalables ARTCB (R368).

    Usage:
        engine = PreflightEngine()
        result = engine.run_checks(task_id="R368-R370", mode=PreflightMode.FULL)
        if result.overall_status == CheckStatus.BLOCKED:
            # Ne pas continuer
        else:
            # Passer à ReflexEngine
    """

    # URL du nœud live (jamais OVH1 — bloqué)
    LIVE_URL = "http://151.80.107.29:8000"
    # Timeout réseau court pour ne pas bloquer le prompt
    NETWORK_TIMEOUT_S = 2.0

    def __init__(self, root: Path | None = None):
        self._root = root or _ROOT

    # ─── Collecteurs d'état ──────────────────────────────────────────────────

    def get_git_state(self) -> GitState:
        """Lit l'état Git local."""
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
            # Détecte si le dépôt est dirty (fichiers modifiés non commités)
            dirty_out = subprocess.check_output(
                ["git", "status", "--porcelain"],
                cwd=str(self._root), text=True, timeout=3,
            ).strip()
            return GitState(
                sha_short=sha_short,
                sha_full=sha_full,
                branch=branch,
                dirty=bool(dirty_out),
                available=True,
            )
        except Exception:
            return GitState(available=False)

    def get_live_state(self) -> LiveState:
        """Interroge le nœud live OVH2 (timeout court)."""
        try:
            import urllib.request
            url = f"{self.LIVE_URL}/health"
            req = urllib.request.urlopen(url, timeout=self.NETWORK_TIMEOUT_S)
            data = json.loads(req.read().decode())
            return LiveState(
                git_sha=str(data.get("git_sha", ""))[:7],
                available=True,
                url=self.LIVE_URL,
            )
        except Exception:
            pass

        try:
            url = f"{self.LIVE_URL}/api/v1/ai/status"
            req = urllib.request.urlopen(url, timeout=self.NETWORK_TIMEOUT_S)  # type: ignore[name-defined]
            data = json.loads(req.read().decode())
            chain = data.get("chain", {})
            lb = chain.get("last_block") or {}
            return LiveState(
                height=int(chain.get("height") or 0),
                last_hash=str(lb.get("hash", ""))[:16],
                available=True,
                url=self.LIVE_URL,
            )
        except Exception:
            return LiveState(available=False, url=self.LIVE_URL)

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
            return LedgerState(
                git_head=str(meta.get("git_head", "")),
                chain_height=int(meta.get("chain_height") or 0),
                global_pct=int(progress.get("global_pct") or 0),
                open_count=len(open_tasks),
                sha256=sha,
                available=True,
            )
        except Exception:
            return LedgerState(available=False)

    # ─── Checks individuels ───────────────────────────────────────────────────

    def _check_git_sync(self, git: GitState, ledger: LedgerState) -> CheckResult:
        """Vérifie que ledger.git_head est synchronisé avec git HEAD."""
        t0 = time.time()
        if not git.available:
            return CheckResult(
                "git_sync", CheckStatus.BLOCKED,
                detail="Git non disponible",
                duration_ms=(time.time() - t0) * 1000,
            )
        if not ledger.available:
            return CheckResult(
                "git_sync", CheckStatus.DEGRADED,
                evidence=git.evidence,
                detail="Ledger absent — divergence non vérifiable",
                duration_ms=(time.time() - t0) * 1000,
            )
        # Comparer SHA courts
        l_head = ledger.git_head[:7]
        g_head = git.sha_short[:7]
        if l_head == g_head or git.sha_full.startswith(l_head):
            return CheckResult(
                "git_sync", CheckStatus.PASS,
                evidence=f"ledger={l_head} git={g_head}",
                duration_ms=(time.time() - t0) * 1000,
            )
        return CheckResult(
            "git_sync", CheckStatus.DEGRADED,
            evidence=f"ledger={l_head} git={g_head}",
            detail=f"LEDGER_DIVERGENCE: ledger.git_head={l_head} ↔ git={g_head} — sync requise",
            duration_ms=(time.time() - t0) * 1000,
        )

    def _check_ledger_available(self, ledger: LedgerState) -> CheckResult:
        """Vérifie que le ledger est lisible."""
        t0 = time.time()
        if ledger.available:
            return CheckResult(
                "ledger_available", CheckStatus.PASS,
                evidence=ledger.evidence,
                duration_ms=(time.time() - t0) * 1000,
            )
        return CheckResult(
            "ledger_available", CheckStatus.DEGRADED,
            detail=".artcb/task_ledger.yaml absent ou illisible",
            duration_ms=(time.time() - t0) * 1000,
        )

    def _check_live_node(self, live: LiveState, mode: PreflightMode) -> CheckResult:
        """Vérifie la disponibilité du nœud live (seulement en mode FULL)."""
        t0 = time.time()
        if mode == PreflightMode.LITE:
            return CheckResult(
                "live_node", CheckStatus.SKIPPED,
                detail="Mode lite — live non requis",
                duration_ms=(time.time() - t0) * 1000,
            )
        if live.available:
            return CheckResult(
                "live_node", CheckStatus.PASS,
                evidence=live.evidence,
                duration_ms=(time.time() - t0) * 1000,
            )
        return CheckResult(
            "live_node", CheckStatus.NOT_PROVEN,
            detail=f"Nœud live {live.url} inaccessible — résultat non prouvé en conditions réelles",
            duration_ms=(time.time() - t0) * 1000,
        )

    def _check_git_code_deployed(self, git: GitState, live: LiveState, mode: PreflightMode) -> CheckResult:
        """Vérifie que le code déployé sur live correspond au git HEAD."""
        t0 = time.time()
        if mode == PreflightMode.LITE:
            return CheckResult(
                "code_deployed", CheckStatus.SKIPPED,
                detail="Mode lite — déploiement non vérifié",
                duration_ms=(time.time() - t0) * 1000,
            )
        if not live.available:
            return CheckResult(
                "code_deployed", CheckStatus.NOT_PROVEN,
                detail="Live inaccessible — impossible de vérifier le déploiement",
                duration_ms=(time.time() - t0) * 1000,
            )
        if not git.available:
            return CheckResult(
                "code_deployed", CheckStatus.DEGRADED,
                evidence=live.evidence,
                detail="Git non disponible localement",
                duration_ms=(time.time() - t0) * 1000,
            )
        if live.git_sha and git.sha_full.startswith(live.git_sha):
            return CheckResult(
                "code_deployed", CheckStatus.PASS,
                evidence=f"git={git.sha_short} live={live.git_sha}",
                duration_ms=(time.time() - t0) * 1000,
            )
        detail = f"Code non déployé : git={git.sha_short} ≠ live={live.git_sha or 'inconnu'}"
        return CheckResult(
            "code_deployed", CheckStatus.NOT_PROVEN,
            evidence=f"git={git.sha_short} live={live.git_sha}",
            detail=detail,
            duration_ms=(time.time() - t0) * 1000,
        )

    # ─── Point d'entrée principal ─────────────────────────────────────────────

    def run_checks(
        self,
        task_id: str = "unknown",
        mode: PreflightMode = PreflightMode.FULL,
    ) -> PreflightResult:
        """Exécute tous les checks et retourne un PreflightResult complet.

        Args:
            task_id: identifiant de la tâche en cours (ex: "R368-R370")
            mode: FULL (code change) ou LITE (explication)

        Returns:
            PreflightResult avec checks, états et résumé injectables dans le prompt.
        """
        # Collecter les états
        git = self.get_git_state()
        ledger = self.load_task_ledger()
        live = self.get_live_state() if mode == PreflightMode.FULL else LiveState(available=False)

        # Exécuter les checks
        checks = [
            self._check_ledger_available(ledger),
            self._check_git_sync(git, ledger),
            self._check_live_node(live, mode),
            self._check_git_code_deployed(git, live, mode),
        ]

        # Calculer le SHA du contexte complet (détection de race condition)
        context_raw = json.dumps({
            "git": git.evidence,
            "ledger": ledger.evidence,
            "live": live.evidence,
            "task_id": task_id,
        }, sort_keys=True).encode()
        context_sha = hashlib.sha256(context_raw).hexdigest()[:16]

        # Construire les lignes de résumé pour injection dans le prompt
        result = PreflightResult(
            task_id=task_id,
            mode=mode,
            checks=checks,
            git=git,
            live=live,
            ledger=ledger,
            context_sha=context_sha,
        )
        result.summary_lines = self._build_summary(result)
        return result

    def _build_summary(self, r: PreflightResult) -> list[str]:
        """Produit des lignes résumé pour injection dans le contexte du prompt."""
        lines = []
        overall = r.overall_status

        icon = {"PASS": "✅", "FAIL": "❌", "BLOCKED": "🚫", "DEGRADED": "⚠",
                "NOT_PROVEN": "🔵", "SKIPPED": "⏭"}.get(overall.value, "?")
        lines.append(f"## PREFLIGHT [{overall.value}] {icon} task={r.task_id} ctx={r.context_sha}")

        for c in r.checks:
            if c.status == CheckStatus.SKIPPED:
                continue
            ci = {"PASS": "✅", "FAIL": "❌", "BLOCKED": "🚫", "DEGRADED": "⚠",
                  "NOT_PROVEN": "🔵"}.get(c.status.value, "?")
            ev = f" [{c.evidence}]" if c.evidence else ""
            dt = f" — {c.detail}" if c.detail else ""
            lines.append(f"  {ci} {c.check_id}{ev}{dt}")

        # Divergence ledger détaillée
        if not r.ledger.available:
            lines.append("  ⚠ Ledger absent → synchroniser .artcb/task_ledger.yaml")
        elif r.git.available and r.ledger.git_head and not r.git.sha_full.startswith(r.ledger.git_head[:7]):
            lines.append(f"  ⚠ Ledger désynchronisé : faire git add .artcb/ && git commit && git push")

        return lines

    def build_context_snapshot(self) -> dict[str, Any]:
        """Construit un snapshot complet du contexte pour ReasoningRecord.

        Retourne un dict avec git_sha, live_sha, live_height, ledger_sha,
        ledger_git_head — suffisant pour ancrer un ReasoningRecord.
        """
        git = self.get_git_state()
        ledger = self.load_task_ledger()
        live = self.get_live_state()
        return {
            "git_sha": git.sha_full if git.available else None,
            "git_branch": git.branch if git.available else None,
            "git_dirty": git.dirty if git.available else None,
            "ledger_sha256": ledger.sha256 if ledger.available else None,
            "ledger_git_head": ledger.git_head if ledger.available else None,
            "ledger_chain_height": ledger.chain_height if ledger.available else None,
            "live_height": live.height if live.available else None,
            "live_last_hash": live.last_hash if live.available else None,
            "live_git_sha": live.git_sha if live.available else None,
            "live_available": live.available,
            "snapshot_ts": time.time(),
            "certified_100": False,  # jamais True
        }
