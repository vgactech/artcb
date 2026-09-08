#!/usr/bin/env python3
"""R273 — live A3/A7: K(ovh-node-1) claiming replica_id=ovh-node-2.

Does not wipe. Does not claim CERTIFIED_100. Writes primary campaign artefacts.
Expected after the binding fix: HTTP 409 invalid_replica_key_binding.
On a SHA without the fix, ACCEPT is recorded as GAP (not recast as PASS).
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for extra in (ROOT, ROOT / "src", ROOT / "scripts"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

import run_live265_pbft_e2e as l265  # noqa: E402
from artcb.consensus.campaign_artifacts import (  # noqa: E402
    final_status_from_attempts,
    record_attempt,
    write_campaign,
)
from artcb.consensus.replica_identity import load_official_registry  # noqa: E402
from artcb.node_registry import OFFICIAL_COMPUTE_NODE_IDS  # noqa: E402

HTTP = l265.HTTP
REMOTE = "/home/ubuntu/artcb"


def _collect_node(nid: str) -> dict:
    health = l265._http("GET", f"{HTTP[nid]}/health")
    view = l265._http("GET", f"{HTTP[nid]}/api/v1/consensus/pbft/view")
    finality = l265._http("GET", f"{HTTP[nid]}/api/v1/consensus/pbft/finality")
    attest = l265._http("GET", f"{HTTP[nid]}/api/v1/consensus/tip-attest")
    ident = l265._http("GET", f"{HTTP[nid]}/api/v1/consensus/replica-identity")
    return {
        "health": health,
        "pbft": {"view": view, "finality": finality},
        "network": {
            "http": HTTP[nid],
            "git_sha": health.get("git_sha"),
            "height": attest.get("height"),
            "last_hash": attest.get("last_hash"),
            "view": view.get("view"),
        },
        "attest": {
            "node_id": attest.get("node_id"),
            "producer_ed25519_b64": attest.get("producer_ed25519_b64"),
            "git_sha": attest.get("git_sha"),
            "height": attest.get("height"),
            "last_hash": attest.get("last_hash"),
        },
        "identity": ident,
    }


def _forge_on_ovh1() -> dict:
    remote = r"""
set -e
sudo -n bash -lc 'set -a; source /etc/artcb/doppler.env; set +a; cd /home/ubuntu/artcb; export PYTHONPATH=src; doppler run -- .venv/bin/python3 -' <<'PY'
import json
from nacl import encoding, signing
from artcb.config import load_settings
from artcb.wallet.encryption import decrypt_private_key, is_encrypted_key_blob

settings = load_settings()
raw = (settings.data_dir / "chain.key").read_bytes()
seed = decrypt_private_key(raw) if is_encrypted_key_blob(raw) else raw[:32]
sk = signing.SigningKey(seed)
ed = sk.verify_key.encode(encoder=encoding.Base64Encoder).decode("ascii")
digest = "aa" * 32
msg = f"P|15|500|{digest}|ovh-node-2"
sig = sk.sign(msg.encode("utf-8")).signature
row = {
    "kind": "prepare",
    "protocol": "265-pbft-block-finality",
    "message": msg,
    "replica_id": "ovh-node-2",
    "signature": f"ed25519:{sig.hex()}",
    "producer_ed25519_b64": ed,
    "producer_pqc_b64": "",
    "view": 15,
    "seq": 500,
    "digest": digest,
}
print(json.dumps(row))
PY
"""
    got = l265._ssh("ovh-node-1", remote, timeout=60)
    raw = (got.get("stdout") or "").strip().splitlines()
    forged = None
    for line in reversed(raw):
        if line.startswith("{") and "replica_id" in line:
            try:
                forged = json.loads(line)
            except json.JSONDecodeError:
                continue
            break
    return {"ssh": {"returncode": got.get("returncode"), "stderr": (got.get("stderr") or "")[-200:]}, "forged": forged}


def main() -> int:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    origin_main = subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "origin/main"], text=True).strip()
    nodes = {nid: _collect_node(nid) for nid in OFFICIAL_COMPUTE_NODE_IDS}
    official = load_official_registry()
    key_match = {}
    for nid in OFFICIAL_COMPUTE_NODE_IDS:
        live_ed = ((nodes[nid].get("attest") or {}).get("producer_ed25519_b64") or "").strip()
        expected = official.get(nid)
        key_match[nid] = bool(expected and expected.ed25519_b64 == live_ed)
    forged = _forge_on_ovh1()
    row = forged.get("forged")
    posts = {}
    attempts: list[dict] = []
    if isinstance(row, dict):
        for nid in ("ovh-node-2", "aws-node-3", "ovh-node-4"):
            posts[nid] = l265._http("POST", f"{HTTP[nid]}/api/v1/consensus/pbft/prepare", {"prepare": row})
    BINDING_REJECT = {
        "invalid_replica_key_binding",
        "invalid_replica_pqc_binding",
        "unregistered_replica_key",
        "replica_key_revoked",
        "unknown_replica_id",
    }
    IDENTITY_PASSED_LATER = {"not_accepted", "wrong_view", "not_prepared"}
    binding_rejected = {}
    identity_passed = []
    for nid, got in posts.items():
        reason = str(got.get("detail") or got.get("reason") or "")
        if reason in BINDING_REJECT or got.get("http") == 409 and reason in BINDING_REJECT:
            binding_rejected[nid] = reason
        elif got.get("ok") is True or reason in IDENTITY_PASSED_LATER:
            identity_passed.append(nid)
    if identity_passed:
        record_attempt(attempts, result="FAIL", reason="k1_signature_accepted_as_ovh_node_2")
        verdict = "GAP"
        a3_ok = False
    elif binding_rejected and row:
        record_attempt(attempts, result="PASS", reason="invalid_replica_key_binding")
        verdict = "BOUND"
        a3_ok = True
    else:
        record_attempt(attempts, result="FAIL", reason="forge_or_post_failed")
        verdict = "NOT_PROVEN"
        a3_ok = False
    results = {
        "a3_k1_as_ovh2": {
            "ok": a3_ok,
            "verdict": verdict,
            "attempts": attempts,
            "final_status": final_status_from_attempts(attempts),
            "identity_passed": identity_passed,
            "binding_rejected": binding_rejected,
            "posts": {nid: {k: posts[nid].get(k) for k in ("ok", "http", "reason", "detail")} for nid in posts},
        },
        "official_keys_match_live": key_match,
        "certified_100": False,
        "n04_50_not_recast": True,
    }
    env = {
        "origin_main": origin_main,
        "live_sha": {nid: (nodes[nid].get("health") or {}).get("git_sha") for nid in OFFICIAL_COMPUTE_NODE_IDS},
        "binding_note": "sender-supplied producer_* is not the authority after R273",
    }
    artefact = write_campaign(
        ROOT,
        campaign_id=f"273_{stamp}",
        code_sha=str((nodes["ovh-node-1"].get("health") or {}).get("git_sha") or ""),
        runner="scripts/run_live273_identity_binding.py",
        environment=env,
        nodes={
            nid: {
                "health": nodes[nid]["health"],
                "pbft": nodes[nid]["pbft"],
                "network": nodes[nid]["network"],
                "attest": nodes[nid]["attest"],
            }
            for nid in OFFICIAL_COMPUTE_NODE_IDS
        },
        results=results,
        extra_manifest={"forged_present": isinstance(row, dict), "ssh": forged.get("ssh")},
    )
    payload = {
        "ok": a3_ok,
        "verdict": verdict,
        "certified_100": False,
        "production_ready": False,
        "key_match": key_match,
        "attempts": attempts,
        "final_status": final_status_from_attempts(attempts),
        "identity_passed": identity_passed,
        "binding_rejected": binding_rejected,
        "campaign": artefact,
        "origin_main": origin_main,
        "stamp": stamp,
    }
    out = ROOT / "logs"
    out.mkdir(exist_ok=True)
    (out / f"273_identity_{stamp}.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    (out / "273_identity_latest.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: payload[k] for k in ("ok", "verdict", "certified_100", "identity_passed", "binding_rejected", "final_status")}, indent=2))
    return 0 if a3_ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
