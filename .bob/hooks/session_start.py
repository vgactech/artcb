#!/usr/bin/env python3
"""Bob IDE — SessionStart hook.

Exécute artcb_live_bootstrap.py pour charger la mémoire ARTCB live
et injecte le contexte complet dans chaque nouvelle session Bob IDE.

Priorité nœud :
  1. ARTCB_API_URL env (si déjà défini)
  2. OVH2 http://151.80.107.29:8000  (OVH1 bloqué — D-027)
  3. AWS3 http://13.38.209.25:8000
  4. OVH4 http://91.134.45.8:8000

Clé API :
  1. ARTCB_API_KEY env
  2. Doppler artcb-2/dev → ARTCB_API_KEY
  3. ~/.artcb/cursor_agent.env

Fail-open : exit 0 en toutes circonstances.
Jamais de secrets affichés.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TRACE = ROOT / "data" / "trace"

# OVH1 bloqué (D-027) — fallback dans l'ordre
FALLBACK_NODES = [
    ("artcb-2", "dev", "http://151.80.107.29:8000"),
    ("artcb3",  "dev", "http://13.38.209.25:8000"),
    ("artcb-4", "dev", "http://91.134.45.8:8000"),
]

RULE_FILES = [
    ".cursor/rules/artcb-live-node.mdc",
    ".cursor/rules/artcb-read-all.mdc",
    ".cursor/rules/mac-node-local.mdc",
    "AUTO_PROMPT_ARTCB",
    "PROTOCOLE_ARTCB",
    "LEÇONS_APPRISES_ARTCB",
    "ROADMAP_GENERAL_ARTCB",
    "DECISIONS_UTILISATEUR_ARTCB",
]


def _doppler_key(project: str, config: str) -> str:
    """Lit ARTCB_API_KEY depuis Doppler. Retourne '' si indisponible."""
    try:
        r = subprocess.run(
            ["doppler", "secrets", "get", "ARTCB_API_KEY",
             "--project", project, "--config", config, "--plain"],
            capture_output=True, text=True, timeout=8,
        )
        val = r.stdout.strip()
        return val if val.startswith("artcb_") else ""
    except Exception:
        return ""


def _pick_node() -> tuple[str, str]:
    """Retourne (url, api_key) du premier nœud joignable."""
    import urllib.request
    import urllib.error

    # Clé déjà dans l'env ?
    env_key = os.environ.get("ARTCB_API_KEY", "")
    env_url = os.environ.get("ARTCB_API_URL", "")
    if env_url and env_key.startswith("artcb_"):
        return env_url.rstrip("/"), env_key

    for proj, cfg, url in FALLBACK_NODES:
        try:
            urllib.request.urlopen(url + "/api/v1/health", timeout=5)
        except Exception:
            continue
        # Nœud joignable — chercher la clé
        key = env_key if env_key.startswith("artcb_") else _doppler_key(proj, cfg)
        if key:
            return url, key
        return url, ""  # nœud joignable mais sans clé

    return FALLBACK_NODES[0][2], ""  # fallback sans vérification


def _run_bootstrap(url: str, api_key: str) -> dict:
    """Lance artcb_live_bootstrap.py avec les bonnes variables d'env."""
    script = ROOT / "scripts" / "artcb_live_bootstrap.py"
    if not script.is_file():
        return {"ok": False, "error": "script_not_found"}
    env = {**os.environ, "ARTCB_API_URL": url, "PYTHONPATH": str(ROOT / "src")}
    if api_key:
        env["ARTCB_API_KEY"] = api_key
    # Les nœuds OVH2/AWS3/OVH4 sont en HTTP (pas HTTPS) — Bearer autorisé
    # uniquement pour les IP cloud de confiance, jamais pour un serveur inconnu.
    if url.startswith("http://") and any(
        ip in url for ip in ("151.80.107.29", "13.38.209.25", "91.134.45.8")
    ):
        env["ARTCB_ALLOW_INSECURE_HTTP"] = "1"
    try:
        r = subprocess.run(
            [sys.executable, str(script)],
            capture_output=True, text=True, timeout=30, env=env,
        )
        try:
            return json.loads(r.stdout)
        except json.JSONDecodeError:
            return {"ok": False, "raw": r.stdout[:200], "stderr": r.stderr[:200]}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "bootstrap_timeout"}
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:120]}


def main() -> int:
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
    except Exception:
        payload = {}

    session_id = payload.get("session_id")
    source = payload.get("source", "?")

    # ── 1. Choisir le nœud et lancer le bootstrap ──────────────────────────
    url, api_key = _pick_node()
    bootstrap = _run_bootstrap(url, api_key)

    # ── 2. Archive locale ──────────────────────────────────────────────────
    try:
        TRACE.mkdir(parents=True, exist_ok=True)
        row = {
            "ts_ns": time.time_ns(),
            "kind": "bob_session_start",
            "source": source,
            "session_id": session_id,
            "artcb_url": url,
            "artcb_bound": bootstrap.get("ok", False),
            "chain_height": bootstrap.get("chain_height"),
            "last_hash": bootstrap.get("last_hash"),
            "ai_memory_count": bootstrap.get("ai_memory_count"),
            "git_sha": bootstrap.get("git_sha"),
            "note": "bob_ide_hook_v2_bootstrap",
        }
        with (TRACE / "bob_sessions.jsonl").open("a") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    except Exception:
        pass

    # ── 3. Construire le contexte injecté dans Bob ─────────────────────────
    lines: list[str] = ["## ARTCB — Contexte automatique (Bob IDE SessionStart)\n"]

    # Git HEAD
    try:
        sha = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=str(ROOT), text=True
        ).strip()[:12]
        branch = subprocess.check_output(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=str(ROOT), text=True
        ).strip()
        lines.append(f"git HEAD = {sha} ({branch})")
    except Exception:
        lines.append("git HEAD = inconnu")

    # État bootstrap ARTCB
    if bootstrap.get("ok"):
        h = bootstrap.get("chain_height", "?")
        tip = str(bootstrap.get("last_hash") or "?")[:16]
        mem = bootstrap.get("ai_memory_count", "?")
        kcg = bootstrap.get("kcg_knowledge_count", "?")
        node_sha = str(bootstrap.get("git_sha") or "?")[:10]
        ctx_head = str(bootstrap.get("ai_context_prompt_head") or "")[:120]
        lines.append(f"\n### ARTCB Mémoire live — {url}")
        lines.append(f"  chain_height={h}  last_hash={tip}…")
        lines.append(f"  ai_memory_count={mem}  kcg_knowledge={kcg}")
        lines.append(f"  node_sha={node_sha}  key={'✅' if api_key else '❌ absente'}")
        if ctx_head:
            lines.append(f"  contexte_IA: {ctx_head}")
        # Dernier mémo
        last_memo_sha = bootstrap.get("last_memo_content_sha256")
        last_memo_chars = bootstrap.get("last_memo_content_chars")
        if last_memo_sha:
            lines.append(f"  last_memo: {last_memo_chars} chars sha256={last_memo_sha[:16]}…")
    else:
        err = bootstrap.get("error") or bootstrap.get("raw") or "nœuds indisponibles"
        lines.append(f"\n⚠️  Bootstrap ARTCB: échec — {str(err)[:80]}")
        lines.append(f"   URL tentée: {url}  clé: {'présente' if api_key else 'absente'}")

    # Fichiers de règles
    lines.append("\nFichiers de règles ARTCB à relire (première→dernière ligne) :")
    for f in RULE_FILES:
        p = ROOT / f
        exists = "✅" if p.exists() else "❌"
        lines.append(f"  {exists} {f}")

    # Rappels protocole
    lines.append("\n⚠️  CERTIFIED_100=false — Jamais wipe — Jamais inventer SHA/hauteur/tip")
    lines.append("⚠️  Relire artcb-live-node.mdc + artcb-read-all.mdc avant tout travail")
    lines.append("🚫  OVH1 = BLOQUÉ par l'utilisateur — aucune tentative de connexion jusqu'à réactivation explicite")

    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
