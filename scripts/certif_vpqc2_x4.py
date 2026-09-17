#!/usr/bin/env python3
"""
V-PQC-2 — Script de certification ×4 nœuds (C5) — v2
R352 §1 backlog : script reproductible prouvant le contrôle ML-DSA-65 sur chaque nœud.

Ce script :
  1. Appelle POST /ops/pqc-challenge sur chaque nœud accessible
  2. Appelle POST /ops/pqc-verify  sur le même nœud avec wallet_name + user_password par nœud
  3. Vérifie vpqc2_pass=True, algorithm=ML-DSA-65, sig_len=3309
  4. Enregistre le résultat horodaté

Usage :
    python3 scripts/certif_vpqc2_x4.py [--output results.json]

Nœuds testés :
    ovh-node-4  91.134.45.8     wallet=pqc-certif-n4    passphrase=doppler artcb3/dev
    aws-node-3  13.38.209.25    wallet=pqc-test-aws3    passphrase=doppler artcb3/dev
    ovh-node-2  151.80.107.29   wallet=ovh-node-2       passphrase=doppler artcb-2/dev
    ovh-node-1  BLOQUÉ          → skipped (règle opérateur)

Honnêteté :
    - vpqc2_pass=True prouve que le nœud détient une clé ML-DSA-65 dans son wallet local
    - Cela ne prouve PAS que les 3 nœuds partagent la même clé PQC (wallets distincts)
    - CERTIFIED_100 reste false
"""
from __future__ import annotations

import argparse
import json
import ssl
import subprocess
import sys
import time
import urllib.request
import urllib.error
from dataclasses import dataclass, asdict, field
from typing import Any

# ─── Configuration par nœud ───────────────────────────────────────────────────
# wallet_name   : nom du wallet sur ce nœud (confirmé fonctionnel)
# pw_project    : projet Doppler depuis lequel lire ARTCB_WALLET_PASSPHRASE
# pw_config     : config Doppler (dev / prd)
NODES: dict[str, dict] = {
    "ovh-node-4": {
        "ip": "91.134.45.8",
        "port": 443,
        "hostname": "artcb.me",
        "doppler_project": "artcb-4",
        "wallet_name": "pqc-certif-n4",
        "pw_project": "artcb3",          # passphrase commune artcb3/dev
        "pw_config": "dev",
        "skip": False,
        "skip_reason": None,
    },
    "aws-node-3": {
        "ip": "13.38.209.25",
        "port": 443,
        "hostname": "artcb.me",
        "doppler_project": "artcb3",
        "wallet_name": "pqc-test-aws3",
        "pw_project": "artcb3",
        "pw_config": "dev",
        "skip": False,
        "skip_reason": None,
    },
    "ovh-node-2": {
        "ip": "151.80.107.29",
        "port": 443,
        "hostname": "artcb.me",
        "doppler_project": "artcb-2",
        "wallet_name": "ovh-node-2",
        "pw_project": "artcb-2",
        "pw_config": "dev",
        "skip": False,
        "skip_reason": None,
    },
    "ovh-node-1": {
        "ip": "152.228.144.34",
        "port": 443,
        "hostname": "artcb.me",
        "doppler_project": "artcb-blockchain",
        "wallet_name": None,
        "pw_project": None,
        "pw_config": None,
        "skip": True,
        "skip_reason": "ovh1_operator_blocked",
    },
}

# ─── Constantes V-PQC-2 ──────────────────────────────────────────────────────
ML_DSA_65_SIG_LEN  = 3309
ML_DSA_65_PUB_LEN  = 1952
TIMEOUT_S          = 12.0


@dataclass
class NodeVPQC2Result:
    node_id: str
    ip: str
    skipped: bool = False
    skip_reason: str | None = None

    # Étape 1 : challenge
    challenge_ok: bool = False
    challenge_hex: str | None = None
    challenge_algorithm: str | None = None

    # Étape 2 : verify
    vpqc2_pass: bool = False
    algorithm: str | None = None
    wallet_address: str | None = None
    wallet_address_v2: str | None = None
    pqc_public_key_len: int | None = None
    signature_len: int | None = None
    dur_ms: float | None = None

    error: str | None = None
    probed_at: float = field(default_factory=time.time)

    @property
    def fully_certified(self) -> bool:
        return (
            not self.skipped
            and self.challenge_ok
            and self.vpqc2_pass
            and self.algorithm == "ML-DSA-65"
            and (self.signature_len or 0) == ML_DSA_65_SIG_LEN
        )


def _get_doppler_secret(secret_name: str, project: str, config: str) -> str:
    """Récupère un secret depuis Doppler."""
    r = subprocess.run(
        ["doppler", "secrets", "get", secret_name,
         "--project", project, "--config", config, "--plain"],
        capture_output=True, text=True, timeout=10,
    )
    if r.returncode == 0 and r.stdout.strip():
        return r.stdout.strip()
    return ""


def _get_api_key(doppler_project: str) -> str:
    """Récupère ARTCB_API_KEY depuis Doppler (dev ou prd)."""
    for cfg in ("dev", "prd"):
        key = _get_doppler_secret("ARTCB_API_KEY", doppler_project, cfg)
        if key:
            return key
    return ""


def _get_wallet_passphrase(pw_project: str, pw_config: str) -> str:
    """Récupère ARTCB_WALLET_PASSPHRASE depuis Doppler."""
    return _get_doppler_secret("ARTCB_WALLET_PASSPHRASE", pw_project, pw_config)


def _https_post(ip: str, port: int, path: str, hostname: str,
                api_key: str, body: dict | None = None) -> dict[str, Any]:
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    data = json.dumps(body or {}).encode()
    req = urllib.request.Request(
        f"https://{ip}:{port}{path}",
        data=data,
        headers={
            "Host": hostname,
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "ARTCB-VPQC2-C5/1.0",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT_S, context=ctx) as r:
        return json.loads(r.read())


def probe_node_vpqc2(node_id: str, spec: dict) -> NodeVPQC2Result:
    result = NodeVPQC2Result(node_id=node_id, ip=spec["ip"])

    if spec.get("skip"):
        result.skipped = True
        result.skip_reason = spec.get("skip_reason", "operator_rule")
        return result

    ip           = spec["ip"]
    port         = spec["port"]
    host         = spec["hostname"]
    proj         = spec["doppler_project"]
    wallet_name  = spec["wallet_name"]
    pw_project   = spec["pw_project"]
    pw_config    = spec["pw_config"]

    api_key = _get_api_key(proj)
    if not api_key:
        result.error = f"no_api_key_for_{proj}"
        return result

    # Récupérer la passphrase depuis Doppler
    user_password = _get_wallet_passphrase(pw_project, pw_config)
    if not user_password:
        result.error = f"no_wallet_passphrase_for_{pw_project}/{pw_config}"
        return result

    # ── Étape 1 : pqc-challenge ───────────────────────────────────────────────
    try:
        chal = _https_post(ip, port, "/api/v1/ops/pqc-challenge", host, api_key)
        challenge = chal.get("challenge", "")
        if len(challenge) == 64 and chal.get("algorithm") == "ML-DSA-65":
            result.challenge_ok = True
            result.challenge_hex = challenge
            result.challenge_algorithm = chal.get("algorithm")
        else:
            result.error = f"challenge_unexpected: {chal}"
            return result
    except urllib.error.HTTPError as e:
        result.error = f"challenge_http_{e.code}: {e.read().decode()[:200]}"
        return result
    except Exception as e:
        result.error = f"challenge_err: {e}"
        return result

    # ── Étape 2 : pqc-verify ─────────────────────────────────────────────────
    try:
        verify = _https_post(ip, port, "/api/v1/ops/pqc-verify", host, api_key, {
            "challenge": challenge,
            "wallet_name": wallet_name,
            "user_password": user_password,
        })
        result.vpqc2_pass      = bool(verify.get("vpqc2_pass"))
        result.algorithm       = verify.get("algorithm")
        result.wallet_address  = verify.get("wallet_address")
        result.wallet_address_v2 = verify.get("wallet_address_v2")
        result.pqc_public_key_len = verify.get("pqc_public_key_len")
        result.signature_len   = verify.get("signature_len")
        result.dur_ms          = verify.get("dur_ms")
    except urllib.error.HTTPError as e:
        body = e.read().decode()[:300]
        result.error = f"verify_http_{e.code}: {body}"
    except Exception as e:
        result.error = f"verify_err: {e}"

    return result


def run_certif_vpqc2_x4() -> dict[str, Any]:
    print(f"[V-PQC-2 C5 v2] Certification ×4 nœuds — {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}")
    print(f"[V-PQC-2 C5 v2] wallet_name par nœud (voir NODES config)\n")

    print(f"{'NODE':<14} {'IP':<18} {'CHAL':<6} {'PASS':<6} {'algo':<12} {'sig_len':<8} {'dur_ms':<8} status")
    print("-" * 95)

    results: list[NodeVPQC2Result] = []

    for node_id, spec in NODES.items():
        r = probe_node_vpqc2(node_id, spec)
        results.append(r)

        if r.skipped:
            print(f"{node_id:<14} {r.ip:<18} SKIP   SKIP   —            —        —        {r.skip_reason}")
            continue

        chal = "✅" if r.challenge_ok else "❌"
        pas  = "✅" if r.vpqc2_pass  else "❌"
        algo = r.algorithm or "?"
        slen = str(r.signature_len or "?")
        dur  = f"{r.dur_ms:.0f}" if r.dur_ms else "?"
        stat = "FULL_CERT" if r.fully_certified else ("ERR:" + (r.error or "?")[:30])
        print(f"{node_id:<14} {r.ip:<18} {chal:<6} {pas:<6} {algo:<12} {slen:<8} {dur:<8} {stat}")

    certified = [r for r in results if r.fully_certified]
    skipped   = [r for r in results if r.skipped]
    failed    = [r for r in results if not r.fully_certified and not r.skipped]

    # Vérifier cohérence clés PQC entre nœuds certifiés
    pub_key_lens = {r.node_id: r.pqc_public_key_len for r in certified}
    all_same_pub_len = len(set(pub_key_lens.values())) <= 1

    vpqc2_c5_pass = len(certified) >= 2  # au moins 2 nœuds non-apex (OVH1 bloqué)

    print(f"\n{'='*60}")
    print(f"  Certifiés  : {[r.node_id for r in certified]}")
    print(f"  Échoués    : {[r.node_id for r in failed]}")
    print(f"  Skippés    : {[r.node_id for r in skipped]}")
    print(f"  sig_len    : {ML_DSA_65_SIG_LEN} (ML-DSA-65 attendu)")
    print(f"  pub_key_len: {pub_key_lens}")
    print(f"  V-PQC-2 C5 : {'✅ PASS' if vpqc2_c5_pass else '❌ FAIL'} ({len(certified)}/{len(NODES)-len(skipped)} nœuds certifiés)")
    print(f"{'='*60}\n")

    return {
        "vpqc2_c5_version": 2,
        "vpqc2_c5_pass": vpqc2_c5_pass,
        "certified_nodes": [r.node_id for r in certified],
        "failed_nodes": [r.node_id for r in failed],
        "skipped_nodes": [r.node_id for r in skipped],
        "wallet_per_node": {nid: s["wallet_name"] for nid, s in NODES.items()},
        "ml_dsa_sig_len_expected": ML_DSA_65_SIG_LEN,
        "ml_dsa_pub_len_expected": ML_DSA_65_PUB_LEN,
        "all_certified_same_pub_key_len": all_same_pub_len,
        "pqc_public_key_lens": pub_key_lens,
        "probe_results": [asdict(r) for r in results],
        "probed_at": time.time(),
        "certified_100": False,
        "note": (
            "vpqc2_pass=True prouve que chaque nœud détient une clé ML-DSA-65 dans son wallet local. "
            "Les clés PQC diffèrent entre nœuds (wallets distincts — unicité inter-nœud non prouvée). "
            "CERTIFIED_100 reste false."
        ),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="V-PQC-2 C5 v2 — certification ML-DSA-65 ×4 nœuds")
    parser.add_argument("--output", default=None, help="Fichier JSON de sortie")
    args = parser.parse_args()

    report = run_certif_vpqc2_x4()

    if args.output:
        import pathlib
        pathlib.Path(args.output).write_text(json.dumps(report, indent=2, default=str))
        print(f"Rapport JSON écrit : {args.output}")

    sys.exit(0 if report["vpqc2_c5_pass"] else 1)
