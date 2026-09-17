#!/usr/bin/env python3
"""Bob IDE — UserPromptSubmit hook.

Capture le prompt entrant + injecte le contexte ARTCB dans chaque tour.
Archive dans data/trace/bob_prompts.jsonl (append-only, gitignored).
Injecte aussi l'état git HEAD courant pour que le modèle sache toujours où il en est.

R350–R354 (2026-09-17) : Ce hook active automatiquement le réflexe ARTCB.
Toute modification liée à la mémoire/thinking/réflexe = priorité absolue.

R366/AUTO_PREFLIGHT (2026-09-17) :
  - Charge .artcb/task_ledger.yaml à chaque prompt
  - Détecte divergence ledger.git_head ↔ git HEAD réel
  - Injecte résumé OPEN/IN_PROGRESS dans le contexte

Fail-open : exit 0 en cas d'erreur.
Jamais de secrets affichés.
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TRACE = ROOT / "data" / "trace"

# Fichiers de règles à rappeler dans chaque prompt (résumé court)
RULE_REMINDERS = [
    "PROTOCOLE_ARTCB",
    "DECISIONS_UTILISATEUR_ARTCB",
    ".cursor/rules/artcb-live-node.mdc",
    ".cursor/rules/artcb-reflex-priority.mdc",  # R350 nouveau
]

# R350 — Mots-clés qui déclenchent la priorité réflexe absolue
REFLEX_PRIORITY_KEYWORDS = [
    "réflexe", "reflexe", "reflex", "reflect",
    "mémoire", "memoire", "memory", "memo",
    "thinking", "raisonnement", "reasoning",
    "ai_memory", "améliorer", "ameliorer", "autonome",
    "priorité", "priorite", "priority",
    "hook", "cursor", "bob ide", "bobide",
]

SECURITY_KEYWORDS = [
    "biométrie", "biometrie", "biometric", "webauthn",
    "empreinte", "fingerprint", "human_identity",
    "add_device", "multi_device", "wallet_device",
    "face_camera", "pin", "unique_human",
]

PQC_KEYWORDS = [
    "pqc", "ml-dsa", "ml_dsa", "ML-DSA", "post.quantique",
    "vpqc", "dilithium", "kyber", "falcon",
]


# ─── AUTO_PREFLIGHT : chargement du ledger + détection divergence ────────────

LEDGER_PATH = ROOT / ".artcb" / "task_ledger.yaml"


def load_ledger() -> dict:
    """Charge .artcb/task_ledger.yaml. Retourne {} si absent ou invalide."""
    try:
        import yaml  # type: ignore[import]
        if LEDGER_PATH.exists():
            return yaml.safe_load(LEDGER_PATH.read_text(encoding="utf-8")) or {}
    except Exception:
        pass
    return {}


def preflight_summary(real_head: str) -> list[str]:
    """Génère un résumé AUTO_PREFLIGHT depuis le ledger.

    Détecte divergence ledger.git_head ↔ git HEAD réel.
    Retourne des lignes à injecter dans le contexte.
    """
    lines: list[str] = []
    ledger = load_ledger()
    if not ledger:
        lines.append("⚠ .artcb/task_ledger.yaml absent ou invalide — ledger non chargé")
        return lines

    meta = ledger.get("meta", {})
    ledger_head = str(meta.get("git_head", "?"))
    # Extraire le SHA court depuis real_head ("275f746 (main)" → "275f746")
    real_sha = real_head.split()[0] if real_head else real_head
    # Détecter divergence (comparer les SHA sans branche)
    if ledger_head != "?" and not real_sha.startswith(ledger_head) and not ledger_head.startswith(real_sha):
        lines.append(f"⚠ LEDGER_DIVERGENCE: ledger.git_head={ledger_head} ↔ git HEAD={real_sha} — synchronisation requise")
    else:
        lines.append(f"✅ Ledger synchronisé: git_head={ledger_head} ({real_sha})")

    # Tâches IN PROGRESS
    in_progress = ledger.get("in_progress") or []
    if in_progress:
        ids = [t.get("id", "?") for t in in_progress if isinstance(t, dict)]
        lines.append(f"🔄 IN_PROGRESS: {', '.join(ids)}")

    # Tâches OPEN (top 5 par priorité)
    open_tasks = ledger.get("open") or []
    if open_tasks:
        high = [t for t in open_tasks if isinstance(t, dict) and t.get("priority") in ("HIGH", "CRITICAL")]
        med  = [t for t in open_tasks if isinstance(t, dict) and t.get("priority") == "MEDIUM"]
        low  = [t for t in open_tasks if isinstance(t, dict) and t.get("priority") == "LOW"]
        parts = []
        for t in (high + med + low)[:5]:
            tid = t.get("id", "?")
            blocker = " 🚨BLOCKER" if t.get("blocker") else ""
            parts.append(f"{tid}{blocker}")
        lines.append(f"📋 OPEN ({len(open_tasks)} tâches): {', '.join(parts)}" + (" …" if len(open_tasks) > 5 else ""))

    # Avancement global
    progress = ledger.get("progress", {})
    global_pct = progress.get("global_pct")
    if global_pct is not None:
        lines.append(f"📊 Global: {global_pct}% | PBFT: {meta.get('pbft_status', '?')}")

    return lines


def get_git_head() -> str:
    try:
        sha = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], cwd=str(ROOT), text=True
        ).strip()
        branch = subprocess.check_output(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=str(ROOT), text=True
        ).strip()
        return f"{sha} ({branch})"
    except Exception:
        return "inconnu"


def detect_reflex_priority(prompt: str) -> str:
    """Détecte la priorité du réflexe depuis le prompt.

    Returns:
        "REFLEX_MEMORY" | "SECURITY" | "PQC" | "STANDARD"
    """
    p = prompt.lower()
    if any(kw.lower() in p for kw in REFLEX_PRIORITY_KEYWORDS):
        return "REFLEX_MEMORY"
    if any(kw.lower() in p for kw in SECURITY_KEYWORDS):
        return "SECURITY"
    if any(kw.lower() in p for kw in PQC_KEYWORDS):
        return "PQC"
    return "STANDARD"


def main() -> int:
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
    except Exception:
        payload = {}

    prompt = payload.get("prompt", "")
    session_id = payload.get("session_id", "")
    ts_ns = time.time_ns()

    # Détecter la priorité du réflexe
    reflex_priority = detect_reflex_priority(prompt)

    # Archive le prompt (jamais les secrets)
    try:
        TRACE.mkdir(parents=True, exist_ok=True)
        row = {
            "ts_ns": ts_ns,
            "kind": "bob_prompt_submit",
            "session_id": session_id,
            "prompt_len": len(prompt),
            "prompt_preview": prompt[:80].replace("\n", " "),
            "git_head": get_git_head(),
            "reflex_priority": reflex_priority,  # R350
        }
        with (TRACE / "bob_prompts.jsonl").open("a") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    except Exception:
        pass

    # Injecter contexte ARTCB dans stdout → ajouté au contexte du modèle
    git_head = get_git_head()

    # Ligne de priorité réflexe (R350–R354)
    reflex_line = ""
    if reflex_priority == "REFLEX_MEMORY":
        reflex_line = "⚡ RÉFLEXE PRIORITÉ 0 : Mémoire/thinking/réflexe détecté → CHANTIER PRIORITAIRE ABSOLU"
    elif reflex_priority == "SECURITY":
        reflex_line = "🔒 RÉFLEXE PRIORITÉ 1 : Sécurité biométrique/identité détectée → priorité élevée"
    elif reflex_priority == "PQC":
        reflex_line = "🔐 RÉFLEXE PRIORITÉ 2 : Cryptographie PQC détectée → priorité élevée"

    lines = [
        "## ARTCB — Rappel automatique (Bob IDE UserPromptSubmit)",
        f"git HEAD = {git_head}",
        "CERTIFIED_100=false | Jamais wipe | Jamais inventer SHA/hauteur/tip",
        "Mode DEBUG actif | Répondre en français | Python+C uniquement",
        "Nœud live OVH1 = ❌ BLOQUÉ — désactivé par l'utilisateur (ne pas tenter de connexion)",
        "V-PQC-1 PASS ✅ (recompute artcb2 validé) | V-PQC-2 C5 ✅ PASS (3/3 nœuds N4/N3/N2)",
        "WebAuthn ARTCB ✅ (19 tests PASS) | ADD_DEVICE ✅ | face_camera = FALLBACK_ACCESSIBILITY_ONLY",
        f"Réflexe ARTCB R350–R354 ✅ ACTIF | Priorité courante: {reflex_priority}",
        "Hooks Bob IDE: SessionStart ✅ | Stop ✅ | PostToolUse ✅ | UserPromptSubmit ✅ (ce hook)",
    ]

    if reflex_line:
        lines.insert(3, reflex_line)

    # AUTO_PREFLIGHT — ledger + divergence (R366)
    try:
        pf = preflight_summary(git_head)
        if pf:
            lines.append("")
            lines.append("## AUTO_PREFLIGHT ARTCB")
            lines.extend(pf)
    except Exception:
        pass

    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
