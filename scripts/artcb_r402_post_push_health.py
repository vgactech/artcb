#!/usr/bin/env python3
# ruff: noqa: S501
"""
R402 — Post-push health check automatique pour artcb.me + nœuds live.

Objectif : détecter immédiatement après chaque mise à jour si artcb.me
ou un nœud live est DOWN, et produire un rapport nanoseconde horodaté.

Logique (L-054 — DNS split) :
  1. Vérifie les 3 IPs directes N2/N4/N3 via /api/v1/health
  2. Vérifie artcb.me via DNS (domaine) → détecte DNS split
  3. Vérifie la cohérence SHA git sur chaque nœud vs HEAD local
  4. Vérifie que le frontend / répond (HTML)
  5. Écrit un log forensic nanoseconde dans logs/R402_health_<sha>_<ts_ns>.json
  6. Affiche un résumé clair : ✅ OK / ❌ DOWN / ⚠️ DÉGRADÉ
  7. Retourne exit code 0 si ≥1 nœud UP, 1 si tous DOWN

IPs live ARTCB (INFRA_IPV4 — D-045) :
  N2 = 151.80.107.29  (OVH2)
  N4 = 91.134.45.8    (OVH4)
  N3 = 13.38.209.25   (AWS3)
  OVH1 = 152.228.144.34  ❌ BLOQUÉ — ne jamais tester

Usage :
    python3 scripts/artcb_r402_post_push_health.py
    python3 scripts/artcb_r402_post_push_health.py --expected-sha e5da415
    python3 scripts/artcb_r402_post_push_health.py --timeout 8

CERTIFIED_100=false | DEBUG MODE | Jamais inventer SHA/IP/status
"""
from __future__ import annotations

MODULE_VERSION = '1.0.0'  # R402 — post-push health check artcb.me

import argparse
import json
import ssl
import subprocess
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path
from datetime import datetime, timezone

# ── Configuration des nœuds (INFRA_IPV4 — D-045 / public_url.py) ──────────
NODE_CONFIG: list[dict] = [
    {"id": "N2", "label": "OVH2",  "ip": "151.80.107.29"},
    {"id": "N4", "label": "OVH4",  "ip": "91.134.45.8"},
    {"id": "N3", "label": "AWS3",  "ip": "13.38.209.25"},
    # OVH1 (152.228.144.34) — ❌ BLOQUÉ par décision utilisateur — ne jamais tester
]

DOMAIN = "artcb.me"
HEALTH_PATH = "/api/v1/health"
FRONTEND_PATH = "/"

REPO_ROOT = Path(__file__).parent.parent.resolve()
LOG_DIR = REPO_ROOT / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

# ── Helpers ─────────────────────────────────────────────────────────────────

def _git_sha_short() -> str:
    try:
        r = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=5, cwd=str(REPO_ROOT)
        )
        return r.stdout.strip() or "unknown"
    except Exception:
        return "unknown"


# Contexte SSL souple pour les IPs directes (cert émis pour artcb.me, pas les IPs)
_SSL_NO_VERIFY = ssl.create_default_context()
_SSL_NO_VERIFY.check_hostname = False
_SSL_NO_VERIFY.verify_mode = ssl.CERT_NONE


def _http_get(url: str, timeout: int = 8, verify_ssl: bool = True) -> tuple[int, str]:
    """GET url. Retourne (http_code, body[:512]) ou (-1, error_msg).
    verify_ssl=False : désactive la vérification SSL pour les IPs directes
    (cert artcb.me ne couvre pas les IPs — L-054).
    """
    ctx = None if verify_ssl else _SSL_NO_VERIFY
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "ARTCB-R402-HealthProbe/1.0"},
        )
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            body = resp.read(4096).decode("utf-8", errors="replace")
            return resp.status, body
    except urllib.error.HTTPError as e:
        return e.code, str(e)
    except urllib.error.URLError as e:
        return -1, str(e.reason)
    except Exception as e:
        return -1, str(e)


def _probe_node(ip: str, timeout: int = 8) -> dict:
    """Sonde un nœud via IP directe (https port 443 via nginx)."""
    ts_ns = time.time_ns()
    url_health = f"https://{ip}/api/v1/health"
    url_frontend = f"https://{ip}/"

    t0 = time.monotonic()
    # verify_ssl=False : cert émis pour artcb.me, pas pour l'IP directe (L-054)
    code, body = _http_get(url_health, timeout=timeout, verify_ssl=False)
    latency_ms = round((time.monotonic() - t0) * 1000, 1)

    result = {
        "ts_ns": ts_ns,
        "ip": ip,
        "url": url_health,
        "http_code": code,
        "latency_ms": latency_ms,
        "api_ok": False,
        "git_sha": None,
        "status": None,
        "frontend_ok": False,
        "frontend_code": None,
        "error": None,
    }

    if code == 200:
        try:
            data = json.loads(body)
            result["api_ok"] = data.get("status") == "ok"
            result["git_sha"] = (data.get("git_sha") or "")[:12]
            result["status"] = data.get("status")
        except json.JSONDecodeError:
            result["error"] = "json_parse_error"

        # Vérification frontend (verify_ssl=False aussi pour IP directe)
        fc, fb = _http_get(url_frontend, timeout=timeout, verify_ssl=False)
        result["frontend_ok"] = fc == 200 and "<!doctype html" in fb.lower()
        result["frontend_code"] = fc
    else:
        result["error"] = body[:120]

    return result


def _probe_domain(timeout: int = 8) -> dict:
    """Sonde artcb.me via DNS (détection DNS split)."""
    ts_ns = time.time_ns()
    url = f"https://{DOMAIN}{HEALTH_PATH}"

    t0 = time.monotonic()
    code, body = _http_get(url, timeout=timeout)
    latency_ms = round((time.monotonic() - t0) * 1000, 1)

    result = {
        "ts_ns": ts_ns,
        "domain": DOMAIN,
        "url": url,
        "http_code": code,
        "latency_ms": latency_ms,
        "api_ok": False,
        "git_sha": None,
        "error": None,
        "dns_split_suspected": False,
    }

    if code == 200:
        try:
            data = json.loads(body)
            result["api_ok"] = data.get("status") == "ok"
            result["git_sha"] = (data.get("git_sha") or "")[:12]
        except json.JSONDecodeError:
            result["error"] = "json_parse_error"
    else:
        result["error"] = body[:120]
        # L-054 : 502/404 sur domaine alors que les IPs directes répondent
        # → signe fort de DNS split
        if code in (502, 404, -1):
            result["dns_split_suspected"] = True

    return result


def _check_sha_divergence(node_results: list[dict], expected_sha: str | None) -> list[str]:
    """Retourne les avertissements de divergence SHA entre nœuds et HEAD local."""
    warnings = []
    local_sha = expected_sha or _git_sha_short()

    shas_live = {}
    for r in node_results:
        if r["api_ok"] and r.get("git_sha"):
            shas_live[r["ip"]] = r["git_sha"]

    for ip, sha in shas_live.items():
        if local_sha and sha and not local_sha.startswith(sha) and not sha.startswith(local_sha):
            warnings.append(
                f"SHA divergence: nœud {ip} = {sha} / HEAD local = {local_sha}"
            )

    # Divergence inter-nœuds
    unique_shas = set(shas_live.values())
    if len(unique_shas) > 1:
        warnings.append(
            f"SHA inter-nœuds divergents: {shas_live}"
        )

    return warnings


# ── Rapport forensic ─────────────────────────────────────────────────────────

def _write_log(report: dict) -> Path:
    sha = report["local_sha"]
    ts_ns = report["ts_ns"]
    fname = LOG_DIR / f"R402_health_{sha}_{ts_ns}.json"
    fname.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return fname


# ── Affichage ────────────────────────────────────────────────────────────────

def _icon(ok: bool | None) -> str:
    if ok is True:
        return "✅"
    if ok is False:
        return "❌"
    return "⚠️"


def _print_summary(report: dict) -> None:
    print()
    print("══════════════════════════════════════════════════════════")
    print(f"  ARTCB Health Check R402 — {report['timestamp_utc']}")
    print(f"  SHA local : {report['local_sha']}")
    print("══════════════════════════════════════════════════════════")

    # Nœuds IP directe
    for r in report["nodes"]:
        conf = next((n for n in NODE_CONFIG if n["ip"] == r["ip"]), {})
        label = conf.get("label", r["ip"])
        icon = _icon(r["api_ok"])
        sha_str = f"sha={r['git_sha']}" if r.get("git_sha") else "sha=?"
        lat_str = f"{r['latency_ms']}ms"
        fe_str = f"frontend={'✅' if r.get('frontend_ok') else '❌'}"
        err_str = f" ← {r['error'][:60]}" if r.get("error") else ""
        print(f"  {icon}  {label:6s} ({r['ip']})  HTTP={r['http_code']}  {sha_str}  {lat_str}  {fe_str}{err_str}")

    # Domaine
    d = report["domain"]
    d_icon = _icon(d["api_ok"])
    d_dns = " ⚠️ DNS SPLIT SUSPECTÉ (L-054)" if d.get("dns_split_suspected") else ""
    d_err = f" ← {d['error'][:60]}" if d.get("error") else ""
    print(f"  {d_icon}  {DOMAIN:6s} (domaine)  HTTP={d['http_code']}  lat={d['latency_ms']}ms{d_dns}{d_err}")

    # Avertissements SHA
    if report["sha_warnings"]:
        print()
        for w in report["sha_warnings"]:
            print(f"  ⚠️  {w}")

    # Diagnostic DNS split
    nodes_ok = sum(1 for r in report["nodes"] if r["api_ok"])
    if d.get("dns_split_suspected") and nodes_ok > 0:
        print()
        print("  ╔══════════════════════════════════════════════════════╗")
        print("  ║  DIAGNOSTIC : Nœuds UP en IP directe mais DOWN      ║")
        print("  ║  via domaine → probable DNS split côté client        ║")
        print("  ║  Solution : DNS → 1.1.1.1 / 8.8.8.8 en premier     ║")
        print("  ║  Test : curl --resolve 'artcb.me:443:151.80.107.29' ║")
        print("  ║         https://artcb.me/api/v1/health              ║")
        print("  ╚══════════════════════════════════════════════════════╝")

    # Résumé global
    print()
    global_ok = nodes_ok > 0
    global_icon = "✅" if global_ok else "❌"
    print(f"  {global_icon}  {nodes_ok}/{len(NODE_CONFIG)} nœuds UP via IP directe")
    print(f"       Log: {report.get('log_path', '?')}")
    print()


# ── Core ─────────────────────────────────────────────────────────────────────

def run_health_check(timeout: int = 8, expected_sha: str | None = None) -> dict:
    """Exécute le health check complet. Retourne le rapport."""
    ts_ns = time.time_ns()
    local_sha = expected_sha or _git_sha_short()
    timestamp_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Probes en séquence (fail-safe, pas de threads pour éviter les race conditions)
    node_results = []
    for conf in NODE_CONFIG:
        result = _probe_node(conf["ip"], timeout=timeout)
        result["node_id"] = conf["id"]
        result["node_label"] = conf["label"]
        node_results.append(result)

    domain_result = _probe_domain(timeout=timeout)

    sha_warnings = _check_sha_divergence(node_results, local_sha)

    nodes_ok = sum(1 for r in node_results if r["api_ok"])
    global_status = "ok" if nodes_ok > 0 else "all_down"

    report = {
        "ts_ns": ts_ns,
        "timestamp_utc": timestamp_utc,
        "probe_version": MODULE_VERSION,
        "local_sha": local_sha,
        "global_status": global_status,
        "nodes_up": nodes_ok,
        "nodes_total": len(NODE_CONFIG),
        "nodes": node_results,
        "domain": domain_result,
        "sha_warnings": sha_warnings,
        "dns_split_detected": domain_result.get("dns_split_suspected", False) and nodes_ok > 0,
        "certified_100": False,
        "note": "R402 — L-054 aware — OVH1 BLOCKED by user decision",
    }

    # Écriture log forensic
    try:
        log_path = _write_log(report)
        report["log_path"] = str(log_path.relative_to(REPO_ROOT))
    except Exception as e:
        report["log_path"] = f"ERROR:{e}"

    return report


# ── CLI ──────────────────────────────────────────────────────────────────────

def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="R402 — Post-push health check artcb.me + nœuds live"
    )
    p.add_argument("--timeout", "-t", type=int, default=8,
                   help="Timeout HTTP en secondes (défaut: 8)")
    p.add_argument("--expected-sha", "-s", default=None,
                   help="SHA git attendu sur les nœuds (ex: e5da415)")
    p.add_argument("--quiet", "-q", action="store_true",
                   help="Sortie minimale (pas d'affichage détaillé)")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    report = run_health_check(timeout=args.timeout, expected_sha=args.expected_sha)

    if not args.quiet:
        _print_summary(report)

    # Exit code : 0 si ≥1 nœud UP, 1 si tous DOWN
    return 0 if report["global_status"] == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())
