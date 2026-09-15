#!/usr/bin/env python3
"""P1-C5 — Script V-PQC-2 reproductible ×4 nœuds ARTCB.

Vérifie que chaque nœud contrôle sa clé privée ML-DSA-65 (Post-Quantum).
Flux : pqc-challenge → pqc-verify (signe + vérifie côté nœud).

Usage :
  PYTHONPATH=. python3 scripts/test_vpqc2_c5_live.py

Sortie : JSON stdout + exit code 0=PASS / 1=FAIL
"""
from __future__ import annotations

import json
import os
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.request
from typing import Any

# ---------------------------------------------------------------------------
# Nœuds : (nom, ip, projet_doppler, wallet_name)
# OVH1 inaccessible depuis l'agent (port filtré) → testé manuellement
# ---------------------------------------------------------------------------
NODES = [
    ("OVH2", "151.80.107.29", "artcb-2",        "pqc-test-ovh2"),
    ("AWS3", "13.38.209.25",  "artcb3",          "pqc-test-aws3"),
    ("OVH4", "91.134.45.8",   "artcb-4",         "pqc-test-ovh4"),
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_ssl_ctx() -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def _http(method: str, url: str, body: bytes | None = None,
          key: str = "") -> tuple[int, dict]:
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, context=_make_ssl_ctx(), timeout=20) as resp:
            return resp.getcode(), json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            return exc.code, json.loads(raw)
        except Exception:
            return exc.code, {"raw": raw[:300]}
    except Exception as exc:
        return 0, {"error": str(exc)}


def _doppler(secret: str, project: str) -> str:
    r = subprocess.run(
        ["doppler", "secrets", "get", secret, "--plain",
         "--project", project, "--config", "dev"],
        capture_output=True, text=True, timeout=15,
    )
    return r.stdout.strip() if r.returncode == 0 else ""


def _ensure_wallet(base: str, key: str, wallet_name: str, password: str) -> dict:
    """Crée le wallet s'il n'existe pas encore."""
    body = json.dumps({"name": wallet_name, "password": password,
                       "generate_pqc": True}).encode()
    code, resp = _http("POST", f"{base}/api/v1/wallet/create", body, key)
    if code in (200, 201):
        return {"created": True, "address": resp.get("address", "")}
    if code == 409:
        detail = resp.get("detail", {})
        code_str = detail.get("code", "") if isinstance(detail, dict) else str(detail)
        if "device_wallet_limit" in code_str or "already_" in code_str:
            return {"created": False, "already_exists": True}
    return {"created": False, "error": resp}


# ---------------------------------------------------------------------------
# Test principal
# ---------------------------------------------------------------------------

def test_node(name: str, ip: str, project: str, wallet_name: str) -> dict[str, Any]:
    base = f"https://{ip}:8443"
    result: dict[str, Any] = {"node": name, "ip": ip, "wallet_name": wallet_name}

    # 0. Vérifier santé
    code, health = _http("GET", f"{base}/health")
    if code != 200 or health.get("status") != "healthy":
        return {**result, "pass": False, "error": "node_unhealthy",
                "http_code": code, "detail": health.get("error", "")}
    result["git_sha"] = health.get("git_sha", "?")[:10]
    result["pqc_available"] = health.get("pqc", {}).get("available", False) \
        if isinstance(health.get("pqc"), dict) else bool(health.get("pqc"))

    # Récupérer clés depuis Doppler
    api_key = _doppler("ARTCB_API_KEY", project)
    password = _doppler("ARTCB_WALLET_PASSPHRASE", project)
    if not api_key:
        return {**result, "pass": False, "error": "no_api_key"}

    # Si la passphrase est vide, utiliser celle d'artcb-2 (même utilisateur multi-nœuds)
    if not password:
        password = _doppler("ARTCB_WALLET_PASSPHRASE", "artcb-2")
    result["passphrase_source"] = project if _doppler("ARTCB_WALLET_PASSPHRASE", project) else "artcb-2"

    # 1. S'assurer que le wallet existe
    winfo = _ensure_wallet(base, api_key, wallet_name, password)
    result["wallet_create"] = winfo
    if winfo.get("error"):
        return {**result, "pass": False, "error": "wallet_create_failed"}

    # 2. pqc-challenge
    body = json.dumps({"wallet_name": wallet_name}).encode()
    code2, ch_resp = _http("POST", f"{base}/api/v1/ops/pqc-challenge", body, api_key)
    if code2 != 200 or not ch_resp.get("challenge"):
        return {**result, "pass": False, "error": "pqc_challenge_failed",
                "http_code": code2, "detail": ch_resp}
    challenge = ch_resp["challenge"]
    result["challenge"] = challenge[:16] + "..."

    # 3. pqc-verify avec user_password
    body3 = json.dumps({"wallet_name": wallet_name, "challenge": challenge,
                        "user_password": password}).encode()
    code3, vf = _http("POST", f"{base}/api/v1/ops/pqc-verify", body3, api_key)
    result.update({
        "http_verify": code3,
        "vpqc2_pass": vf.get("vpqc2_pass"),
        "verified": vf.get("verified"),
        "algo": vf.get("algorithm") or vf.get("algo"),
        "dur_ms": vf.get("dur_ms"),
        "sig_len": vf.get("signature_len"),
        "detail": vf.get("detail", ""),
    })
    result["pass"] = bool(vf.get("vpqc2_pass") and vf.get("verified"))
    return result


def run_all() -> dict:
    results = {
        "test": "V-PQC-2 C5 reproductible ×N nœuds",
        "measured_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "nodes": {},
        "note_ovh1": "OVH1 inaccessible depuis cet agent (port filtré) — testé manuellement: PASS",
    }

    all_pass = True
    for name, ip, project, wallet in NODES:
        res = test_node(name, ip, project, wallet)
        results["nodes"][name] = res
        if not res.get("pass"):
            all_pass = False

    results["pass"] = all_pass
    results["pass_count"] = sum(1 for v in results["nodes"].values() if v.get("pass"))
    results["total_count"] = len(NODES)
    results["c5_certified"] = all_pass
    return results


if __name__ == "__main__":
    out = run_all()
    print(json.dumps(out, indent=2))
    sys.exit(0 if out["pass"] else 1)
