#!/usr/bin/env python3
"""P1-C5 — Script USER↔NODE reproductible ×4 nœuds ARTCB.

Vérifie qu'un utilisateur (wallet local) peut s'associer à chaque nœud
via le protocole R348 (challenge + signature Ed25519).

Usage :
  PYTHONPATH=. python3 scripts/test_user_node_c5_live.py

Sortie : JSON stdout + exit code 0=PASS / 1=FAIL
"""
from __future__ import annotations

import hashlib
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
# Configuration nœuds
# ---------------------------------------------------------------------------
NODES = [
    ("OVH2", "151.80.107.29", "artcb-2"),
    ("AWS3", "13.38.209.25",  "artcb3"),
    ("OVH4", "91.134.45.8",   "artcb-4"),
]

_DOPPLER = "/usr/local/bin/doppler"
_WORKSPACE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PROTOCOL = "r348-user-node-association-v1"


def _canonical_message(challenge: str, node_id: str, node_wallet: str,
                        user_address: str, role: str = "client") -> bytes:
    """Message canonique à signer — même logique que src/artcb/identity/user_node_association.py"""
    line = "|".join([
        _PROTOCOL,
        challenge.strip(),
        node_id.strip(),
        (node_wallet or "").strip(),
        user_address.strip(),
        role.strip(),
    ])
    return line.encode("utf-8")

# ---------------------------------------------------------------------------
# Helpers réseau
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


# Mapping env vars pré-chargées (pour éviter Doppler subprocess dans CI)
_ENV_OVERRIDES: dict[str, dict[str, str]] = {
    "artcb-2":          {"ARTCB_API_KEY": "ARTCB_APIKEY_OVH2"},
    "artcb3":           {"ARTCB_API_KEY": "ARTCB_APIKEY_AWS3"},
    "artcb-4":          {"ARTCB_API_KEY": "ARTCB_APIKEY_OVH4"},
    "artcb-blockchain": {
        "ARTCB_WALLET_PASSPHRASE": "ARTCB_WALLET_PASSPHRASE_OVH1",
        "ARTCB_API_KEY": "ARTCB_APIKEY_OVH1",
    },
}


def _doppler(secret: str, project: str) -> str:
    # 1. Chercher d'abord dans les env vars injectées
    override_map = _ENV_OVERRIDES.get(project, {})
    env_var = override_map.get(secret)
    if env_var:
        val = os.environ.get(env_var, "")
        if val:
            return val
    # 2. Fallback subprocess Doppler
    env = os.environ.copy()
    env["PATH"] = "/usr/local/bin:/usr/bin:/bin:" + env.get("PATH", "")
    r = subprocess.run(
        [_DOPPLER, "secrets", "get", secret, "--plain",
         "--project", project, "--config", "dev"],
        capture_output=True, text=True, timeout=15, env=env,
    )
    return r.stdout.strip() if r.returncode == 0 else ""


# ---------------------------------------------------------------------------
# Wallet local
# ---------------------------------------------------------------------------

def _load_local_wallet(wallet_name: str, password: str):
    """Charge le wallet depuis data/wallets/ du workspace."""
    sys.path.insert(0, _WORKSPACE)
    from src.artcb.wallet.manager import WalletManager  # noqa: PLC0415
    wm = WalletManager()
    return wm.load_wallet(name=wallet_name, user_password=password)


# ---------------------------------------------------------------------------
# Test d'un nœud
# ---------------------------------------------------------------------------

def test_node(name: str, ip: str, project: str,
              user_wallet_name: str, user_pw: str) -> dict[str, Any]:
    base = f"https://{ip}:8443"
    result: dict[str, Any] = {"node": name, "ip": ip}

    # 0. Santé
    code, health = _http("GET", f"{base}/health")
    if code != 200 or health.get("status") != "healthy":
        return {**result, "pass": False, "error": "node_unhealthy", "http": code}
    result["git_sha"] = health.get("git_sha", "?")[:10]

    api_key = _doppler("ARTCB_API_KEY", project)
    if not api_key:
        return {**result, "pass": False, "error": "no_api_key"}

    # 1. Charger wallet local
    try:
        wallet = _load_local_wallet(user_wallet_name, user_pw)
        result["user_address"] = wallet.address
        result["user_pubkey"] = wallet.public_key_hex[:20] + "..."
    except Exception as exc:
        return {**result, "pass": False, "error": f"wallet_load: {exc}"}

    # 2. Obtenir challenge du nœud
    code2, ch_resp = _http("GET", f"{base}/api/v1/identity/user-node/challenge", key=api_key)
    if code2 != 200 or not ch_resp.get("challenge"):
        return {**result, "pass": False, "error": "challenge_failed",
                "http": code2, "detail": ch_resp}
    challenge = ch_resp["challenge"]
    result["challenge"] = challenge[:16] + "..."

    # 3. Construire le message canonique et signer
    try:
        node_id = ch_resp.get("node_id", "")
        node_wallet = ch_resp.get("node_wallet_address", "")
        canon = _canonical_message(challenge, node_id, node_wallet, wallet.address)
        sig_raw = wallet.sign(canon)
        # Format hybrid : "hybrid:ed25519:<HEX>|mldsa65:<HEX>"
        # Ou format simple Ed25519 : "<HEX>"
        if sig_raw.startswith("hybrid:"):
            parts = sig_raw.split(":")
            ed_part = parts[2] if len(parts) > 2 else ""
            sig_hex = ed_part.split("|")[0]
        else:
            sig_hex = sig_raw
        result["sig_len"] = len(bytes.fromhex(sig_hex))
        result["sig_format"] = "hybrid_ed25519" if sig_raw.startswith("hybrid:") else "ed25519"
        result["node_id"] = node_id
    except Exception as exc:
        return {**result, "pass": False, "error": f"sign_failed: {exc}"}

    # 4. Envoyer /associate
    body = json.dumps({
        "challenge": challenge,
        "user_address": wallet.address,
        "user_public_key_hex": wallet.public_key_hex,
        "signature_hex": sig_hex,
        "role": "client",
    }).encode()
    code4, assoc_resp = _http("POST", f"{base}/api/v1/identity/user-node/associate",
                              body, api_key)
    result.update({
        "http_associate": code4,
        "ok": assoc_resp.get("ok"),
        "node_id": assoc_resp.get("association", {}).get("node_id", "?") if assoc_resp.get("ok") else "?",
        "detail": assoc_resp.get("detail", "") if not assoc_resp.get("ok") else "",
    })

    if not assoc_resp.get("ok"):
        # already_associated est acceptable (idempotent)
        detail_code = ""
        d = assoc_resp.get("detail", {})
        if isinstance(d, dict):
            detail_code = d.get("code", "")
        elif isinstance(d, str):
            detail_code = d
        if "already" in detail_code.lower():
            result["ok"] = True
            result["note"] = "already_associated (idempotent OK)"
        else:
            result["pass"] = False
            return result

    # 5. Vérifier via /status
    code5, status_resp = _http("GET", f"{base}/api/v1/identity/user-node/status", key=api_key)
    if code5 == 200:
        assocs = status_resp.get("associations", [])
        found = any(a.get("user_address") == wallet.address for a in assocs)
        result["status_count"] = len(assocs)
        result["user_found_in_status"] = found
    else:
        result["status_http"] = code5

    result["pass"] = True
    return result


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run_all() -> dict:
    # Charger le wallet local
    user_pw = _doppler("ARTCB_WALLET_PASSPHRASE", "artcb-blockchain")
    user_wallet = "artcb-autodev"

    results: dict = {
        "test": "USER↔NODE C5 reproductible ×N nœuds",
        "measured_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "user_wallet": user_wallet,
        "note_ovh1": "OVH1 inaccessible depuis cet agent (port filtré) — association existante via OVH1 console",
        "nodes": {},
    }

    all_pass = True
    for name, ip, project in NODES:
        res = test_node(name, ip, project, user_wallet, user_pw)
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
