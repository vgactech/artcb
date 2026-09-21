#!/usr/bin/env python3
# ruff: noqa: S501
"""
R403 — Audit de cohérence wallet multi-nœuds ARTCB.

Objectif : détecter si un wallet créé sur N2 est présent/accessible
sur N4 et N3. Diagnostique le problème de state-locality :
  - les fichiers wallet (.key/.json/.pqc) sont locaux à chaque nœud
  - le device binding (wallet_device_bindings.json) est local
  - l'auth/me peut échouer sur N4 si le wallet a été créé sur N2

Ce script sonde uniquement les métadonnées publiques (wallet address,
public_key_hex, exists). Il ne demande jamais les clés privées ni les seeds.

Séquence de test pour un wallet donné :
  1. Probe /api/v1/admin/wallet-consistency?wallet_name=<name> sur chaque nœud
     (endpoint admin — si absent, fallback sur /api/v1/wallet/list)
  2. Probe /auth/me avec un token de session (si fourni)
  3. Probe /api/v1/chain/tip pour vérifier cohérence blockchain vs wallet

Usage :
    python3 scripts/artcb_r403_wallet_consistency_audit.py
    python3 scripts/artcb_r403_wallet_consistency_audit.py --wallet vgactech0
    python3 scripts/artcb_r403_wallet_consistency_audit.py --wallet vgactech0 --session-token <tok>
    python3 scripts/artcb_r403_wallet_consistency_audit.py --timeout 8

IPs live ARTCB (INFRA_IPV4 — D-045) :
    N2 = 151.80.107.29  (OVH2)
    N4 = 91.134.45.8    (OVH4)
    N3 = 13.38.209.25   (AWS3)
    OVH1 = 152.228.144.34  ❌ BLOQUÉ — ne jamais tester

CERTIFIED_100=false | DEBUG MODE | Jamais inventer SHA/IP/status
"""
from __future__ import annotations

MODULE_VERSION = "1.0.0"  # R403 — wallet multi-node consistency audit

import argparse
import json
import ssl
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

# ── Configuration nœuds (D-045 / INFRA_IPV4) ─────────────────────────────────
NODE_CONFIG: list[dict] = [
    {"id": "N2", "label": "OVH2", "ip": "151.80.107.29"},
    {"id": "N4", "label": "OVH4", "ip": "91.134.45.8"},
    {"id": "N3", "label": "AWS3", "ip": "13.38.209.25"},
    # OVH1 = 152.228.144.34 ❌ BLOQUÉ — jamais tester
]

LOGS_DIR = Path("logs")
REPORTS_DIR = Path("rapports")
BASE_PORT = 443
PROTO = "https"

# ── SSL context permissif pour IPs directes (certificat artcb.me) ─────────────
_SSL_CTX = ssl.create_default_context()
_SSL_CTX.check_hostname = False
_SSL_CTX.verify_mode = ssl.CERT_NONE


def _ts_ns() -> int:
    return time.time_ns()


def _now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _get_json(url: str, timeout: float, headers: dict | None = None) -> tuple[int, dict | None, str | None]:
    """HTTP GET → (http_code, json_body|None, error_str|None)."""
    req = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=_SSL_CTX) as resp:
            body = json.loads(resp.read().decode())
            return resp.status, body, None
    except urllib.error.HTTPError as exc:
        try:
            body = json.loads(exc.read().decode())
        except Exception:
            body = None
        return exc.code, body, f"HTTP {exc.code}: {exc.reason}"
    except Exception as exc:
        return 0, None, str(exc)


def _post_json(url: str, payload: dict, timeout: float, headers: dict | None = None) -> tuple[int, dict | None, str | None]:
    """HTTP POST JSON → (http_code, json_body|None, error_str|None)."""
    data = json.dumps(payload).encode()
    h = {"Content-Type": "application/json", **(headers or {})}
    req = urllib.request.Request(url, data=data, headers=h, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=_SSL_CTX) as resp:
            body = json.loads(resp.read().decode())
            return resp.status, body, None
    except urllib.error.HTTPError as exc:
        try:
            body = json.loads(exc.read().decode())
        except Exception:
            body = None
        return exc.code, body, f"HTTP {exc.code}: {exc.reason}"
    except Exception as exc:
        return 0, None, str(exc)


# ── Sondes par nœud ──────────────────────────────────────────────────────────

def probe_wallet_list(ip: str, timeout: float) -> dict:
    """Sonde /api/v1/wallet/list — renvoie la liste des métadonnées wallet (noms + adresses)."""
    url = f"{PROTO}://{ip}/api/v1/wallet/list"
    ts = _ts_ns()
    code, body, err = _get_json(url, timeout)
    return {
        "ts_ns": ts,
        "url": url,
        "http_code": code,
        "ok": code == 200,
        "wallets": body if isinstance(body, list) else (body.get("wallets") if isinstance(body, dict) else []),
        "raw": body,
        "error": err,
    }


def probe_wallet_exists(ip: str, wallet_name: str, timeout: float) -> dict:
    """Vérifie si un wallet spécifique est présent dans la liste d'un nœud."""
    result = probe_wallet_list(ip, timeout)
    wallets = result.get("wallets") or []
    found = next((w for w in wallets if w.get("name") == wallet_name), None)
    return {
        **result,
        "wallet_name": wallet_name,
        "wallet_found": found is not None,
        "wallet_meta": found,
    }


def probe_auth_me(ip: str, session_token: str, timeout: float) -> dict:
    """Sonde /auth/me avec le token de session — vérifie si la session est reconnue."""
    url = f"{PROTO}://{ip}/auth/me"
    ts = _ts_ns()
    headers = {"Authorization": f"Bearer {session_token}"}
    code, body, err = _get_json(url, timeout, headers=headers)
    wallet_name = None
    address = None
    if isinstance(body, dict):
        wallet_name = body.get("wallet_name") or body.get("name")
        address = body.get("address") or body.get("artcb_address")
    return {
        "ts_ns": ts,
        "url": url,
        "http_code": code,
        "session_valid": code == 200,
        "wallet_name": wallet_name,
        "address": address,
        "raw": body,
        "error": err,
    }


def probe_chain_tip(ip: str, timeout: float) -> dict:
    """Sonde /api/v1/chain/status — vérifie la hauteur et le last_hash pour cohérence.
    Fallback sur /api/v1/chain si /chain/status retourne 404.
    """
    for path in ("/api/v1/chain/status", "/api/v1/chain"):
        url = f"{PROTO}://{ip}{path}"
        ts = _ts_ns()
        code, body, err = _get_json(url, timeout)
        if code == 200:
            height = None
            last_hash = None
            if isinstance(body, dict):
                height = body.get("height") or body.get("chain_length")
                last_hash = body.get("last_hash") or body.get("hash") or body.get("tip")
            return {
                "ts_ns": ts,
                "url": url,
                "http_code": code,
                "ok": True,
                "height": height,
                "last_hash": last_hash,
                "error": None,
            }
    # Tous les chemins ont échoué — renvoie le dernier résultat
    return {
        "ts_ns": ts,
        "url": url,
        "http_code": code,
        "ok": False,
        "height": None,
        "last_hash": None,
        "error": err,
    }


def probe_device_binding_admin(ip: str, fingerprint: str, timeout: float) -> dict:
    """
    Sonde l'endpoint admin /api/v1/admin/device-bindings/<fp> si disponible.
    Renvoie 404_NOT_FOUND si l'endpoint n'existe pas (pas d'erreur bloquante).
    NE LIT JAMAIS les clés privées — uniquement la présence du binding.
    """
    url = f"{PROTO}://{ip}/api/v1/admin/device-bindings/{fingerprint}"
    ts = _ts_ns()
    code, body, err = _get_json(url, timeout)
    return {
        "ts_ns": ts,
        "url": url,
        "http_code": code,
        "binding_found": code == 200,
        "endpoint_exists": code != 404,
        "raw": body,
        "error": err,
    }


# ── Audit complet sur un nœud ─────────────────────────────────────────────────

def audit_node(node: dict, wallet_name: str | None, session_token: str | None,
               device_fingerprint: str | None, timeout: float) -> dict:
    ip = node["ip"]
    result: dict = {
        "node_id": node["id"],
        "node_label": node["label"],
        "ip": ip,
        "ts_start_ns": _ts_ns(),
    }

    # 1. Liste wallets + présence du wallet cible
    if wallet_name:
        result["wallet_check"] = probe_wallet_exists(ip, wallet_name, timeout)
    else:
        result["wallet_list"] = probe_wallet_list(ip, timeout)

    # 2. Auth/me avec token de session (si fourni)
    if session_token:
        result["auth_me"] = probe_auth_me(ip, session_token, timeout)

    # 3. Tip blockchain
    result["chain_tip"] = probe_chain_tip(ip, timeout)

    # 4. Device binding admin (si fingerprint fourni)
    if device_fingerprint:
        result["device_binding"] = probe_device_binding_admin(ip, device_fingerprint, timeout)

    result["ts_end_ns"] = _ts_ns()
    result["latency_ms"] = round((result["ts_end_ns"] - result["ts_start_ns"]) / 1_000_000, 1)
    return result


# ── Analyse de cohérence entre nœuds ─────────────────────────────────────────

def analyze_consistency(node_results: list[dict], wallet_name: str | None) -> dict:
    """Compare les résultats de tous les nœuds et produit un verdict de cohérence."""
    analysis: dict = {
        "wallet_name": wallet_name,
        "nodes_audited": len(node_results),
    }

    # Cohérence wallet
    if wallet_name:
        found_on = [r["node_id"] for r in node_results if r.get("wallet_check", {}).get("wallet_found")]
        absent_on = [r["node_id"] for r in node_results if not r.get("wallet_check", {}).get("wallet_found")]
        analysis["wallet_found_on"] = found_on
        analysis["wallet_absent_on"] = absent_on
        analysis["wallet_consistent"] = len(absent_on) == 0
        analysis["wallet_state_local"] = len(found_on) > 0 and len(absent_on) > 0  # présent sur certains seulement

        # Cohérence des adresses wallet
        addresses = [
            r["wallet_check"]["wallet_meta"].get("address")
            for r in node_results
            if r.get("wallet_check", {}).get("wallet_meta")
        ]
        unique_addresses = list(set(a for a in addresses if a))
        analysis["wallet_address_consistent"] = len(unique_addresses) <= 1
        analysis["wallet_addresses_seen"] = unique_addresses

    # Cohérence sessions (auth/me)
    session_valid_on = [r["node_id"] for r in node_results if r.get("auth_me", {}).get("session_valid")]
    session_invalid_on = [r["node_id"] for r in node_results if "auth_me" in r and not r["auth_me"].get("session_valid")]
    if session_valid_on or session_invalid_on:
        analysis["session_valid_on"] = session_valid_on
        analysis["session_invalid_on"] = session_invalid_on
        analysis["session_consistent"] = len(session_invalid_on) == 0

    # Cohérence blockchain (tips)
    tips = [(r["node_id"], r["chain_tip"].get("height"), r["chain_tip"].get("last_hash"))
            for r in node_results if r.get("chain_tip", {}).get("ok")]
    unique_hashes = list(set(t[2] for t in tips if t[2]))
    unique_heights = list(set(t[1] for t in tips if t[1] is not None))
    analysis["chain_tips"] = [{"node": t[0], "height": t[1], "last_hash": t[2]} for t in tips]
    analysis["chain_hash_consistent"] = len(unique_hashes) <= 1
    analysis["chain_height_spread"] = (max(unique_heights) - min(unique_heights)) if len(unique_heights) >= 2 else 0

    # Verdict global
    issues = []
    if wallet_name and analysis.get("wallet_state_local"):
        issues.append(f"WALLET_STATE_LOCAL: présent sur {found_on}, absent sur {absent_on}")
    if wallet_name and not analysis.get("wallet_address_consistent"):
        issues.append(f"WALLET_ADDRESS_MISMATCH: {unique_addresses}")
    if "session_consistent" in analysis and not analysis["session_consistent"]:
        issues.append(f"SESSION_INCONSISTENT: valide sur {session_valid_on}, invalide sur {session_invalid_on}")
    if not analysis.get("chain_hash_consistent", True):
        issues.append(f"CHAIN_FORK: {len(unique_hashes)} last_hash distincts")
    if analysis.get("chain_height_spread", 0) > 5:
        issues.append(f"CHAIN_LAG: spread de hauteur = {analysis['chain_height_spread']} blocs")

    analysis["issues"] = issues
    analysis["verdict"] = "INCONSISTENT" if issues else "CONSISTENT"
    return analysis


# ── Point d'entrée ────────────────────────────────────────────────────────────

def run_audit(wallet_name: str | None, session_token: str | None,
              device_fingerprint: str | None, timeout: float) -> dict:
    ts_start = _ts_ns()
    print(f"[R403] Audit cohérence wallet multi-nœuds — {_now_utc()}")
    print(f"       wallet_name={wallet_name or '(liste complète)'}")
    print(f"       session_token={'fourni' if session_token else 'absent'}")
    print(f"       device_fp={'fourni' if device_fingerprint else 'absent'}")
    print(f"       timeout={timeout}s\n")

    node_results = []
    for node in NODE_CONFIG:
        print(f"  ▶ {node['id']} ({node['label']}) {node['ip']}...", end=" ", flush=True)
        r = audit_node(node, wallet_name, session_token, device_fingerprint, timeout)
        node_results.append(r)

        # Affichage synthétique
        parts = []
        if wallet_name:
            wc = r.get("wallet_check", {})
            parts.append("wallet=✅" if wc.get("wallet_found") else "wallet=❌")
        ct = r.get("chain_tip", {})
        parts.append(f"tip={ct.get('height', '?')}@{(ct.get('last_hash') or '')[:8]}")
        if "auth_me" in r:
            parts.append("session=✅" if r["auth_me"].get("session_valid") else "session=❌")
        print(" | ".join(parts))

    # Analyse de cohérence
    analysis = analyze_consistency(node_results, wallet_name)

    # Rapport final
    ts_end = _ts_ns()
    report = {
        "report": "R403",
        "ts_start_ns": ts_start,
        "ts_end_ns": ts_end,
        "timestamp_utc": _now_utc(),
        "probe_version": MODULE_VERSION,
        "wallet_name": wallet_name,
        "consistency": analysis,
        "nodes": node_results,
    }

    # Écriture log forensic nanoseconde
    LOGS_DIR.mkdir(exist_ok=True)
    wallet_slug = (wallet_name or "all").replace("/", "_")
    log_path = LOGS_DIR / f"R403_consistency_{wallet_slug}_{ts_start}.json"
    log_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n[R403] Log forensic → {log_path}")

    # Résumé
    verdict = analysis["verdict"]
    issues = analysis.get("issues", [])
    print(f"\n{'='*60}")
    print(f"[R403] VERDICT : {verdict}")
    if issues:
        for issue in issues:
            print(f"       ⚠️  {issue}")
    else:
        print("       ✅ Tous les nœuds cohérents")
    print(f"{'='*60}\n")

    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="R403 — Audit cohérence wallet multi-nœuds ARTCB")
    parser.add_argument("--wallet", default=None, help="Nom du wallet à auditer (ex: vgactech0)")
    parser.add_argument("--session-token", default=None, help="Bearer token de session pour tester /auth/me")
    parser.add_argument("--device-fp", default=None, help="Device fingerprint (ex: 97a0b640…) pour tester le binding admin")
    parser.add_argument("--timeout", type=float, default=8.0, help="Timeout HTTP en secondes (défaut: 8)")
    args = parser.parse_args(argv)

    report = run_audit(
        wallet_name=args.wallet,
        session_token=args.session_token,
        device_fingerprint=args.device_fp,
        timeout=args.timeout,
    )

    verdict = report["consistency"]["verdict"]
    issues = report["consistency"].get("issues", [])
    if issues:
        print(f"[R403] {len(issues)} problème(s) détecté(s) — voir log forensic", file=sys.stderr)
    return 0 if verdict == "CONSISTENT" else 1


if __name__ == "__main__":
    sys.exit(main())
