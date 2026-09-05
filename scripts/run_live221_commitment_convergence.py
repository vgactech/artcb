#!/usr/bin/env python3
"""Live 221 — measure public tip convergence on the four official nodes.

Never prints API keys / session tokens / seeds / PEMs / KEM material.
Never wipes blocks.jsonl. Does not flip certification. Does not stop OVH1.
"""

from __future__ import annotations

import json
import os
import ssl
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from artcb.node_registry import NODES, OFFICIAL_COMPUTE_NODE_IDS  # noqa: E402

CTX = ssl._create_unverified_context()
OVH1_HTTPS = "https://152.228.144.34:8443"
OVH1_SSH = Path.home() / ".ssh" / "artcb_ovh_deploy"
KNOWN = ROOT / "deploy" / "ovh_artcb_node_1.known_hosts"


def _http(method: str, url: str, *, body: dict | None = None, token: str | None = None, timeout: int = 30) -> tuple[int, dict | list | str]:
    data = None
    headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    ctx = CTX if url.startswith("https") else None
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            code = resp.status
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        code = exc.code
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return 0, {"error": type(exc).__name__, "detail": str(exc)[:160]}
    if not raw:
        return code, {}
    try:
        return code, json.loads(raw)
    except json.JSONDecodeError:
        return code, raw[:240]


def _blocks(payload: dict | list | str) -> list[dict]:
    if isinstance(payload, list):
        return [b for b in payload if isinstance(b, dict)]
    if isinstance(payload, dict):
        return [b for b in (payload.get("blocks") or []) if isinstance(b, dict)]
    return []


def _events(blocks: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for block in blocks:
        name = (block.get("public_symbols") or {}).get("artcb_event") or "other"
        counts[name] = counts.get(name, 0) + 1
    return counts


def tip_of(node_id: str) -> dict:
    spec = NODES[node_id]
    base = spec.health_http or ""
    health_code, health = _http("GET", f"{base}/health")
    status_code, status = _http("GET", f"{base}/api/v1/p2p/status")
    chain_code, chain = _http("GET", f"{base}/api/v1/chain")
    blocks = _blocks(chain)
    leaked = any(
        ("artcb1" in str((b.get("public_symbols") or {}).get(k) or "") and k in {"old_controller", "new_controller", "issuer"})
        for b in blocks
        for k in (b.get("public_symbols") or {})
    )
    return {
        "node_id": node_id,
        "health_http": health_code,
        "git_sha": health.get("git_sha") if isinstance(health, dict) else None,
        "certified": health.get("certified_distributed_mainnet") if isinstance(health, dict) else None,
        "p2p_http": status_code,
        "peer_count": status.get("peer_count") if isinstance(status, dict) else None,
        "public_blocks_local": status.get("public_blocks_local") if isinstance(status, dict) else None,
        "last_hash": status.get("last_hash") if isinstance(status, dict) else None,
        "public_state_digest": status.get("public_state_digest") if isinstance(status, dict) else None,
        "chain_http": chain_code,
        "chain_n": len(blocks),
        "events": _events(blocks),
        "leaked_controller_address": leaked,
    }


def _ssh_wallet(name: str, password: str) -> dict:
    remote = (
        "cd /home/ubuntu/artcb && PYTHONPATH=src .venv/bin/python -c "
        f"\"from artcb.wallet.manager import WalletManager; "
        f"w=WalletManager().create_wallet(name={name!r}, user_password={password!r}); "
        f"print(w.address)\""
    )
    proc = subprocess.run(
        [
            "ssh", "-i", str(OVH1_SSH),
            "-o", "StrictHostKeyChecking=yes",
            "-o", f"UserKnownHostsFile={KNOWN}",
            "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes",
            "ubuntu@152.228.144.34", remote,
        ],
        capture_output=True, text=True, timeout=60,
    )
    address = (proc.stdout or "").strip().splitlines()[-1] if proc.stdout.strip() else ""
    return {"ok": proc.returncode == 0 and address.startswith("artcb"), "address": address, "name": name}


def operator_sync() -> dict:
    token = os.environ.get("ARTCB_API_KEY", "").strip()
    out = {"attempted": bool(token)}
    if not token:
        return out
    for nid in OFFICIAL_COMPUTE_NODE_IDS:
        spec = NODES[nid]
        code, payload = _http("POST", f"{spec.health_http}/api/v1/p2p/sync", token=token)
        row = payload if isinstance(payload, dict) else {}
        out[nid] = {
            "http": code,
            "peer_count": row.get("peer_count"),
            "ok_peers": sum(1 for r in (row.get("results") or []) if r.get("ok")),
        }
    return out


def create_and_transfer() -> dict:
    stamp = datetime.now(UTC).strftime("%H%M%S")
    password = f"Live221{stamp}x"
    aline = _ssh_wallet(f"aline221_{stamp}", password)
    bob = _ssh_wallet(f"bob221_{stamp}", password)
    out = {"aline_ok": aline.get("ok"), "bob_ok": bob.get("ok"), "password_printed": False}
    if not aline.get("ok") or not bob.get("ok"):
        out["reason"] = "wallet_create_failed"
        return out
    login_a = _http("POST", f"{OVH1_HTTPS}/api/v1/auth/login", body={"name": aline["name"], "password": password})
    login_b = _http("POST", f"{OVH1_HTTPS}/api/v1/auth/login", body={"name": bob["name"], "password": password})
    tok_a = (login_a[1] or {}).get("session_token") if isinstance(login_a[1], dict) else None
    tok_b = (login_b[1] or {}).get("session_token") if isinstance(login_b[1], dict) else None
    out["login_aline"] = login_a[0]
    out["login_bob"] = login_b[0]
    out["session_printed"] = False
    if not tok_a or not tok_b:
        out["reason"] = "login_failed"
        return out
    created = _http("POST", f"{OVH1_HTTPS}/api/v1/authz/orgs", body={"name": f"ORG-221-{stamp}"}, token=tok_a)
    out["create_http"] = created[0]
    body = created[1] if isinstance(created[1], dict) else {}
    out["create_ok"] = created[0] == 200
    out["has_salt_in_http"] = "commitment_salt" in body
    org_id = body.get("organization_id")
    proposed = _http(
        "POST",
        f"{OVH1_HTTPS}/api/v1/authz/orgs/{org_id}/transfer",
        body={"new_controller": bob["address"], "reason": "SALE"},
        token=tok_a,
    ) if org_id else (0, {})
    out["propose_http"] = proposed[0]
    tx_id = (proposed[1] or {}).get("tx_id") if isinstance(proposed[1], dict) else None
    accepted = _http("POST", f"{OVH1_HTTPS}/api/v1/authz/transfers/accept", body={"tx_id": tx_id}, token=tok_b) if tx_id else (0, {})
    out["accept_http"] = accepted[0]
    second = _http(
        "POST",
        f"{OVH1_HTTPS}/api/v1/authz/orgs/{org_id}/transfer",
        body={"new_controller": aline["address"], "reason": "SALE"},
        token=tok_a,
    ) if org_id else (0, {})
    out["old_controller_second_propose"] = second[0]
    return out


def main() -> int:
    want = os.popen("git -C /workspace rev-parse origin/main").read().strip()
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    before = {nid: tip_of(nid) for nid in OFFICIAL_COMPUTE_NODE_IDS}
    flow = create_and_transfer()
    sync = operator_sync()
    after = {nid: tip_of(nid) for nid in OFFICIAL_COMPUTE_NODE_IDS}
    hashes = {nid: after[nid].get("last_hash") for nid in OFFICIAL_COMPUTE_NODE_IDS}
    digests = {nid: after[nid].get("public_state_digest") for nid in OFFICIAL_COMPUTE_NODE_IDS}
    payload = {
        "stamp": stamp,
        "want_origin_main": want,
        "before": before,
        "human_flow": flow,
        "operator_sync": sync,
        "after": after,
        "four_same_last_hash": len(set(hashes.values())) == 1 and all(hashes.values()),
        "four_same_digest": len(set(digests.values())) == 1 and all(digests.values()),
        "all_certified": all(after[nid].get("certified") is True for nid in OFFICIAL_COMPUTE_NODE_IDS),
        "all_match_main": all(after[nid].get("git_sha") == want for nid in OFFICIAL_COMPUTE_NODE_IDS) if want else False,
        "no_controller_leak": all(after[nid].get("leaked_controller_address") is False for nid in OFFICIAL_COMPUTE_NODE_IDS),
        "token_printed": False,
    }
    dest = ROOT / "logs" / f"221_live_{stamp}.json"
    dest.parent.mkdir(exist_ok=True)
    dest.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    evidence = ROOT / "rapports" / "evidence" / f"221_live_{stamp}.json"
    evidence.parent.mkdir(parents=True, exist_ok=True)
    evidence.write_text(dest.read_text(encoding="utf-8"), encoding="utf-8")
    print(json.dumps({
        "wrote": str(dest),
        "evidence": str(evidence),
        "four_same_last_hash": payload["four_same_last_hash"],
        "four_same_digest": payload["four_same_digest"],
        "create_ok": flow.get("create_ok"),
        "old_controller_second_propose": flow.get("old_controller_second_propose"),
        "token_printed": False,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
