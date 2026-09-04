#!/usr/bin/env python3
"""Live retest 218 — Domain Registry on the four official nodes.

Measures only. Never prints API keys / session tokens / seeds / PEMs.
Never wipes blocks.jsonl. Does not flip certification.
"""

from __future__ import annotations

import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from artcb.node_registry import NODES, OFFICIAL_COMPUTE_NODE_IDS  # noqa: E402

CTX = ssl._create_unverified_context()
NODES_HTTP = {
    "ovh-node-1": "http://152.228.144.34:8000",
    "ovh-node-2": "http://151.80.107.29:8000",
    "ovh-node-3": "http://51.44.222.232:8000",
    "ovh-node-4": "http://91.134.45.8:8000",
}
# aws-node-3 key in registry, keep both aliases
NODES_HTTP["aws-node-3"] = NODES_HTTP["ovh-node-3"]
OVH1_HTTPS = "https://152.228.144.34:8443"


def _http(method: str, url: str, *, body: dict | None = None, token: str | None = None, timeout: int = 20) -> tuple[int, dict | list | str]:
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


def _redact_me(payload: dict) -> dict:
    keep = {}
    for key in ("key_id", "owner_address", "owner_wallet", "scopes", "label"):
        if key in payload:
            keep[key] = payload[key]
    keep["has_owner_address"] = bool(payload.get("owner_address"))
    return keep


def probe_node(node_id: str) -> dict:
    spec = NODES[node_id]
    base = spec.health_http or ""
    health_code, health = _http("GET", f"{base}/health")
    repl_code, repl = _http("GET", f"{base}/api/v1/authz/replication")
    dom_code, dom = _http("GET", f"{base}/api/v1/authz/domains")
    org_code, orgs = _http("GET", f"{base}/api/v1/authz/orgs")
    com_code, commits = _http("GET", f"{base}/api/v1/authz/commitments")
    chain_code, chain = _http("GET", f"{base}/api/v1/chain")
    groups_anon = _http("POST", f"{base}/api/v1/groups", body={"name": "X"})
    orgs_anon = _http("POST", f"{base}/api/v1/authz/orgs", body={"name": "X"})
    export_anon = _http("POST", f"{base}/api/v1/authz/domains/domain_missing/export", body={})
    p2p_code, p2p = _http("GET", f"{base}/api/v1/p2p/blocks/public")

    matrix = repl if isinstance(repl, dict) else {}
    domains = dom if isinstance(dom, dict) else {}
    orgs_body = orgs if isinstance(orgs, dict) else {}
    commits_body = commits if isinstance(commits, dict) else {}
    chain_body = chain if isinstance(chain, dict) else {}
    p2p_body = p2p if isinstance(p2p, dict) else {}
    blocks = chain_body.get("blocks") if isinstance(chain_body, dict) else None
    if blocks is None and isinstance(chain_body, list):
        blocks = chain_body
    vis = sorted({str(b.get("visibility")) for b in (blocks or []) if isinstance(b, dict)})
    p2p_blocks = p2p_body.get("blocks") if isinstance(p2p_body, dict) else []
    p2p_vis = sorted({str(b.get("visibility")) for b in (p2p_blocks or []) if isinstance(b, dict)})
    leaked = False
    blob = json.dumps(domains) + json.dumps(commits_body)
    if "members" in blob or "join_code" in blob or "genesis_body" in blob:
        leaked = True
    return {
        "node_id": node_id,
        "ip": spec.ssh_host,
        "health_http": health_code,
        "git_sha": health.get("git_sha") if isinstance(health, dict) else None,
        "git_sha_short": (health.get("git_sha") or "")[:7] if isinstance(health, dict) else None,
        "certified": health.get("certified_distributed_mainnet") if isinstance(health, dict) else None,
        "replication_http": repl_code,
        "p2p_syncs_private_blocks": matrix.get("p2p_syncs_private_blocks"),
        "has_domain_manifest": "DOMAIN_MANIFEST" in (matrix.get("matrix") or {}),
        "has_domain_body": "DOMAIN_BODY" in (matrix.get("matrix") or {}),
        "node_owns_domain": matrix.get("node_owns_domain"),
        "domains_http": dom_code,
        "domains_count": domains.get("count"),
        "domains_private": domains.get("contains_private_data"),
        "domains_on_chain": domains.get("commitment_anchored_on_chain"),
        "orgs_count": orgs_body.get("count"),
        "commitments_http": com_code,
        "commitments_private": commits_body.get("contains_private_data"),
        "chain_http": chain_code,
        "chain_block_count": len(blocks or []),
        "chain_visibilities": vis,
        "groups_anon": groups_anon[0],
        "orgs_anon": orgs_anon[0],
        "export_anon": export_anon[0],
        "p2p_http": p2p_code,
        "p2p_visibilities": p2p_vis,
        "leaked_private_in_public_domain_or_commitments": leaked,
    }


def alice_flow(want_sha: str) -> dict:
    """Create a throwaway org on OVH1 if the operator key is bound to a wallet."""
    token = os.environ.get("ARTCB_API_KEY", "").strip()
    out: dict = {
        "attempted": False,
        "reason": "no_key",
        "created_on_ovh1": False,
        "visible_on_other_nodes": None,
        "body_anonymous_ovh1": None,
    }
    if not token:
        return out
    me_code, me = _http("GET", f"{OVH1_HTTPS}/api/v1/api-keys/me", token=token)
    out["me_http"] = me_code
    out["me"] = _redact_me(me) if isinstance(me, dict) else {"error": "unparsed"}
    address = me.get("owner_address") if isinstance(me, dict) else None
    if not address:
        out["reason"] = "operator_key_has_no_wallet_address"
        return out
    out["attempted"] = True
    out["reason"] = "api_key_bound_to_wallet"
    name = f"ORG-E2E218-{datetime.now(UTC).strftime('%H%M%S')}"
    create_code, created = _http(
        "POST",
        f"{OVH1_HTTPS}/api/v1/authz/orgs",
        body={"name": name, "storage_mode": "artcb_managed"},
        token=token,
    )
    out["create_http"] = create_code
    if not isinstance(created, dict):
        out["reason"] = "create_unparsed"
        return out
    out["create_keys"] = sorted(created.keys())
    out["node_owns_domain"] = (created.get("ownership") or {}).get("node_owns_domain")
    out["commitment_anchored_on_chain"] = (created.get("domain") or {}).get(
        "commitment_anchored_on_chain"
    )
    out["storage_mode"] = (created.get("domain") or {}).get("storage_mode")
    domain_id = (created.get("domain") or {}).get("domain_id")
    content_hash = created.get("content_hash")
    out["has_domain_id"] = bool(domain_id)
    out["has_content_hash"] = bool(content_hash) and len(str(content_hash)) == 64
    out["founder_is_not_node"] = bool(created.get("founder_address")) and created.get(
        "founder_address"
    ) != (created.get("ownership") or {}).get("hosting_node_id")
    out["created_on_ovh1"] = create_code == 200 and bool(domain_id)
    if not domain_id:
        out["reason"] = f"create_failed_{create_code}"
        return out
    body_anon = _http("GET", f"http://152.228.144.34:8000/api/v1/authz/domains/{domain_id}/body")
    out["body_anonymous_ovh1"] = body_anon[0]
    others = {}
    for nid in ("ovh-node-2", "aws-node-3", "ovh-node-4"):
        spec = NODES[nid]
        code, payload = _http("GET", f"{spec.health_http}/api/v1/authz/domains")
        ids = []
        if isinstance(payload, dict):
            ids = [d.get("domain_id") for d in payload.get("domains") or []]
        others[nid] = {
            "http": code,
            "count": payload.get("count") if isinstance(payload, dict) else None,
            "has_this_domain": domain_id in ids,
        }
    out["other_nodes"] = others
    out["visible_on_other_nodes"] = any(row["has_this_domain"] for row in others.values())
    out["want_sha_prefix"] = want_sha[:7]
    return out


def main() -> int:
    want = ""
    try:
        want = (ROOT / ".git").exists() and os.popen("git rev-parse origin/main").read().strip()
    except OSError:
        want = ""
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    nodes = {nid: probe_node(nid) for nid in OFFICIAL_COMPUTE_NODE_IDS}
    https_code, https_health = _http("GET", f"{OVH1_HTTPS}/health")
    alice = alice_flow(want)
    shas = {nid: row.get("git_sha") for nid, row in nodes.items()}
    payload = {
        "stamp": stamp,
        "want_origin_main": want,
        "ovh1_https_health": https_code,
        "ovh1_https_sha": https_health.get("git_sha") if isinstance(https_health, dict) else None,
        "nodes": nodes,
        "alice_flow": alice,
        "all_sha_equal": len(set(shas.values())) == 1,
        "all_match_main": all(sha == want for sha in shas.values()) if want else False,
        "all_certified": all(row.get("certified") is True for row in nodes.values()),
        "all_have_registry": all(row.get("has_domain_manifest") for row in nodes.values()),
        "all_orgs_anon_401": all(row.get("orgs_anon") == 401 for row in nodes.values()),
        "all_groups_anon_401": all(row.get("groups_anon") == 401 for row in nodes.values()),
        "all_p2p_private_false": all(row.get("p2p_syncs_private_blocks") is False for row in nodes.values()),
        "no_private_leak": all(
            row.get("leaked_private_in_public_domain_or_commitments") is False for row in nodes.values()
        ),
    }
    out_dir = ROOT / "logs"
    out_dir.mkdir(exist_ok=True)
    dest = out_dir / f"218_live_{stamp}.json"
    dest.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    latest = out_dir / "218_live_latest.json"
    latest.write_text(dest.read_text(encoding="utf-8"), encoding="utf-8")
    summary = {
        "wrote": str(dest),
        "want": want,
        "shas": {nid: nodes[nid].get("git_sha_short") for nid in OFFICIAL_COMPUTE_NODE_IDS},
        "all_match_main": payload["all_match_main"],
        "all_certified": payload["all_certified"],
        "all_have_registry": payload["all_have_registry"],
        "all_orgs_anon_401": payload["all_orgs_anon_401"],
        "alice_created": alice.get("created_on_ovh1"),
        "alice_leaked_to_others": alice.get("visible_on_other_nodes"),
        "token_printed": False,
    }
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
