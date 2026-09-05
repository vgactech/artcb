#!/usr/bin/env python3
"""Live retest 220 — public hash anchor + transferable ORG authority.

Measures only. Never prints API keys / session tokens / seeds / PEMs.
Never wipes blocks.jsonl. Does not flip certification.
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


def _http(method: str, url: str, *, body: dict | None = None, token: str | None = None, timeout: int = 25) -> tuple[int, dict | list | str]:
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
        rows = payload.get("blocks") or payload.get("chain") or []
        return [b for b in rows if isinstance(b, dict)]
    return []


def _events(blocks: list[dict], name: str) -> list[dict]:
    return [b for b in blocks if (b.get("public_symbols") or {}).get("artcb_event") == name]


def probe_node(node_id: str) -> dict:
    spec = NODES[node_id]
    base = spec.health_http or ""
    health_code, health = _http("GET", f"{base}/health")
    repl_code, repl = _http("GET", f"{base}/api/v1/authz/replication")
    dom_code, dom = _http("GET", f"{base}/api/v1/authz/domains")
    chain_code, chain = _http("GET", f"{base}/api/v1/chain")
    orgs_anon = _http("POST", f"{base}/api/v1/authz/orgs", body={"name": "X"})
    xfer_anon = _http(
        "POST",
        f"{base}/api/v1/authz/orgs/org_x/transfer",
        body={"new_controller": "artcb1xxxxxxxx", "reason": "SALE"},
    )
    matrix = (repl or {}).get("matrix") if isinstance(repl, dict) else {}
    domains = dom if isinstance(dom, dict) else {}
    blocks = _blocks(chain)
    commit_n = len(_events(blocks, "DOMAIN_COMMITMENT"))
    xfer_n = len(_events(blocks, "ORG_CONTROL_TRANSFER"))
    leaked = False
    blob = json.dumps(domains) + json.dumps(chain if isinstance(chain, (dict, list)) else {})
    if "join_code" in blob or "genesis_body" in blob:
        leaked = True
    return {
        "node_id": node_id,
        "ip": spec.ssh_host,
        "health_http": health_code,
        "git_sha": health.get("git_sha") if isinstance(health, dict) else None,
        "git_sha_short": (health.get("git_sha") or "")[:7] if isinstance(health, dict) else None,
        "certified": health.get("certified_distributed_mainnet") if isinstance(health, dict) else None,
        "replication_http": repl_code,
        "has_commitment_block": "DOMAIN_COMMITMENT_BLOCK" in (matrix or {}),
        "has_authority": "ORG_AUTHORITY" in (matrix or {}),
        "has_control_transfer": "ORG_CONTROL_TRANSFER" in (matrix or {}),
        "domains_http": dom_code,
        "domains_count": domains.get("count") if isinstance(domains, dict) else None,
        "chain_http": chain_code,
        "chain_block_count": len(blocks),
        "domain_commitment_blocks": commit_n,
        "control_transfer_blocks": xfer_n,
        "orgs_anon": orgs_anon[0],
        "transfer_anon": xfer_anon[0],
        "leaked_private": leaked,
    }


def _ssh_create_wallet(name: str, password: str) -> dict:
    """Create a throwaway wallet on OVH1 disk. Never print seed/password."""
    remote = (
        "cd /home/ubuntu/artcb && .venv/bin/python -c "
        f"\"from artcb.wallet.manager import WalletManager; "
        f"w=WalletManager().create_wallet(name={name!r}, user_password={password!r}); "
        f"print(w.address)\""
    )
    cmd = [
        "ssh",
        "-i",
        str(OVH1_SSH),
        "-o",
        "StrictHostKeyChecking=yes",
        "-o",
        f"UserKnownHostsFile={KNOWN}",
        "ubuntu@152.228.144.34",
        remote,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    address = (proc.stdout or "").strip().splitlines()[-1] if proc.stdout.strip() else ""
    return {
        "ok": proc.returncode == 0 and address.startswith("artcb"),
        "has_address": bool(address),
        "address": address if address.startswith("artcb") else "",
        "address_len": len(address),
        "returncode": proc.returncode,
        "stderr_class": (proc.stderr or "")[:80],
        "name": name,
    }


def human_flow() -> dict:
    stamp = datetime.now(UTC).strftime("%H%M%S")
    password = f"Live220-{stamp}-x!"
    aline = _ssh_create_wallet(f"aline220_{stamp}", password)
    bob = _ssh_create_wallet(f"bob220_{stamp}", password)
    out: dict = {
        "aline_wallet_created": aline.get("ok"),
        "bob_wallet_created": bob.get("ok"),
        "password_printed": False,
        "seed_printed": False,
    }
    if not aline.get("ok") or not bob.get("ok"):
        out["reason"] = "wallet_create_failed"
        return out
    login_a = _http(
        "POST",
        f"{OVH1_HTTPS}/api/v1/auth/login",
        body={"name": aline["name"], "password": password},
    )
    login_b = _http(
        "POST",
        f"{OVH1_HTTPS}/api/v1/auth/login",
        body={"name": bob["name"], "password": password},
    )
    out["login_aline"] = login_a[0]
    out["login_bob"] = login_b[0]
    tok_a = (login_a[1] or {}).get("session_token") if isinstance(login_a[1], dict) else None
    tok_b = (login_b[1] or {}).get("session_token") if isinstance(login_b[1], dict) else None
    out["session_printed"] = False
    if not tok_a or not tok_b:
        out["reason"] = "login_failed"
        return out
    created = _http(
        "POST",
        f"{OVH1_HTTPS}/api/v1/authz/orgs",
        body={"name": f"ORG-220-{stamp}"},
        token=tok_a,
    )
    denied = 0
    try:
        req = urllib.request.Request(
            f"{OVH1_HTTPS}/api/v1/authz/orgs",
            data=json.dumps({"name": "Nope"}).encode(),
            headers={
                "Authorization": f"Bearer {tok_a}",
                "Content-Type": "application/json",
                "x-artcb-agent-id": "agent-aline-01",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=20, context=CTX) as resp:
            denied = resp.status
    except urllib.error.HTTPError as exc:
        denied = exc.code
    except Exception:
        denied = 0
    out["agent_create"] = denied
    out["create_http"] = created[0]
    body = created[1] if isinstance(created[1], dict) else {}
    out["create_ok"] = created[0] == 200
    out["anchored"] = (body.get("domain") or {}).get("commitment_anchored_on_chain")
    out["unique_human_proven"] = (body.get("actor_certification") or {}).get("unique_human_proven")
    out["node_owns_domain"] = (body.get("ownership") or {}).get("node_owns_domain")
    org_id = body.get("organization_id")
    domain_id = (body.get("domain") or {}).get("domain_id")
    out["has_org_id"] = bool(org_id)
    chain_code, chain = _http("GET", f"{OVH1_HTTPS}/api/v1/chain")
    commits = _events(_blocks(chain), "DOMAIN_COMMITMENT")
    out["ovh1_commitment_blocks"] = len(commits)
    out["commitment_hash_matches"] = bool(commits) and commits[-1].get("public_symbols", {}).get("content_hash") == body.get("content_hash")
    out["commitment_reward"] = commits[-1].get("block_reward") if commits else None
    # agent cannot transfer
    agent_xfer = urllib.request.Request(
        f"{OVH1_HTTPS}/api/v1/authz/orgs/{org_id}/transfer",
        data=json.dumps({"new_controller": "artcb1xxxxxxxx", "reason": "SALE"}).encode(),
        headers={
            "Authorization": f"Bearer {tok_a}",
            "Content-Type": "application/json",
            "x-artcb-agent-id": "agent-aline-01",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(agent_xfer, timeout=20, context=CTX) as resp:
            out["agent_transfer"] = resp.status
    except urllib.error.HTTPError as exc:
        out["agent_transfer"] = exc.code
    except Exception as exc:
        out["agent_transfer"] = type(exc).__name__
    bob_address = bob.get("address") or ((login_b[1] or {}).get("address") if isinstance(login_b[1], dict) else None)
    aline_address = aline.get("address") or ((login_a[1] or {}).get("address") if isinstance(login_a[1], dict) else None)
    out["has_bob_address"] = bool(bob_address)
    if org_id and bob_address:
        proposed = _http(
            "POST",
            f"{OVH1_HTTPS}/api/v1/authz/orgs/{org_id}/transfer",
            body={"new_controller": bob_address, "reason": "SALE"},
            token=tok_a,
        )
        out["propose_http"] = proposed[0]
        tx_id = (proposed[1] or {}).get("tx_id") if isinstance(proposed[1], dict) else None
        accepted = _http(
            "POST",
            f"{OVH1_HTTPS}/api/v1/authz/transfers/accept",
            body={"tx_id": tx_id},
            token=tok_b,
        ) if tx_id else (0, {})
        out["accept_http"] = accepted[0]
        acc = accepted[1] if isinstance(accepted[1], dict) else {}
        out["accept_status"] = acc.get("status")
        out["controller_is_bob"] = ((acc.get("authority") or {}).get("controller_address") == bob_address)
        out["founder_unchanged"] = ((acc.get("authority") or {}).get("founder_address") == aline_address)
        out["org_id_unchanged"] = acc.get("org_id_unchanged")
        if domain_id:
            old_exp = _http("POST", f"{OVH1_HTTPS}/api/v1/authz/domains/{domain_id}/export", token=tok_a)
            new_exp = _http("POST", f"{OVH1_HTTPS}/api/v1/authz/domains/{domain_id}/export", token=tok_b)
            out["old_controller_export"] = old_exp[0]
            out["new_controller_export"] = new_exp[0]
        chain2 = _http("GET", f"{OVH1_HTTPS}/api/v1/chain")
        xfers = _events(_blocks(chain2[1]), "ORG_CONTROL_TRANSFER")
        out["ovh1_transfer_blocks"] = len(xfers)
    others = {}
    for nid in ("ovh-node-2", "aws-node-3", "ovh-node-4"):
        spec = NODES[nid]
        code, payload = _http("GET", f"{spec.health_http}/api/v1/authz/domains")
        ids = [d.get("domain_id") for d in (payload.get("domains") or [])] if isinstance(payload, dict) else []
        others[nid] = {
            "http": code,
            "count": payload.get("count") if isinstance(payload, dict) else None,
            "has_this_domain": domain_id in ids if domain_id else False,
        }
    out["other_nodes"] = others
    out["body_copied_to_others"] = any(row["has_this_domain"] for row in others.values())
    return out


def main() -> int:
    want = ""
    try:
        want = os.popen("git -C /workspace rev-parse origin/main").read().strip()
    except OSError:
        want = ""
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    nodes = {nid: probe_node(nid) for nid in OFFICIAL_COMPUTE_NODE_IDS}
    https_code, https_health = _http("GET", f"{OVH1_HTTPS}/health")
    flow = human_flow()
    shas = {nid: row.get("git_sha") for nid, row in nodes.items()}
    payload = {
        "stamp": stamp,
        "want_origin_main": want,
        "ovh1_https_health": https_code,
        "ovh1_https_sha": https_health.get("git_sha") if isinstance(https_health, dict) else None,
        "nodes": nodes,
        "human_flow": flow,
        "all_sha_equal": len(set(shas.values())) == 1,
        "all_match_main": all(sha == want for sha in shas.values()) if want else False,
        "all_certified": all(row.get("certified") is True for row in nodes.values()),
        "all_have_220_matrix": all(
            row.get("has_commitment_block") and row.get("has_authority") and row.get("has_control_transfer")
            for row in nodes.values()
        ),
        "all_orgs_anon_401": all(row.get("orgs_anon") == 401 for row in nodes.values()),
        "all_transfer_anon_401": all(row.get("transfer_anon") == 401 for row in nodes.values()),
        "no_private_leak": all(row.get("leaked_private") is False for row in nodes.values()),
        "token_printed": False,
    }
    out_dir = ROOT / "logs"
    out_dir.mkdir(exist_ok=True)
    dest = out_dir / f"220_live_{stamp}.json"
    dest.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (out_dir / "220_live_latest.json").write_text(dest.read_text(encoding="utf-8"), encoding="utf-8")
    summary = {
        "wrote": str(dest),
        "want": want[:12],
        "shas": {nid: nodes[nid].get("git_sha_short") for nid in OFFICIAL_COMPUTE_NODE_IDS},
        "all_match_main": payload["all_match_main"],
        "all_certified": payload["all_certified"],
        "all_have_220_matrix": payload["all_have_220_matrix"],
        "create_ok": flow.get("create_ok"),
        "anchored": flow.get("anchored"),
        "controller_is_bob": flow.get("controller_is_bob"),
        "old_export": flow.get("old_controller_export"),
        "new_export": flow.get("new_controller_export"),
        "token_printed": False,
    }
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
