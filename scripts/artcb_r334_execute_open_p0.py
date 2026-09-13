#!/usr/bin/env python3
"""R334 — execute open P0s in parallel: ReasoningID v2 live, ORG ACL probe, fan-out authz matrix.

CERTIFIED_100 stays false unless all critical rows PASS_LIVE on one SHA.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

try:
    from artcb_dns_fix import install as _dns

    _dns()
except Exception:  # noqa: BLE001
    pass

from src.artcb.reasoning.canonical import PROTOCOL, canonicalize_structured, semantic_identity_report

SEEDS = {
    "ovh-node-1": "https://artcb.me",
    "ovh-node-2": "https://n2.artcb.me",
    "aws-node-3": "https://n3.artcb.me",
    "ovh-node-4": "https://n4.artcb.me",
}


def _key() -> str:
    k = (os.environ.get("ARTCB_API_KEY") or "").strip()
    if len(k) >= 16:
        return k
    env = Path.home() / ".artcb" / "cursor_agent.env"
    if env.is_file():
        for line in env.read_text(encoding="utf-8").splitlines():
            if line.startswith("ARTCB_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def http(method: str, url: str, *, body: dict | None = None, auth: bool = False, timeout: float = 45.0, raw: bytes | None = None, headers: dict | None = None) -> tuple[int, dict | bytes]:
    hdrs = {"Accept": "application/json", **(headers or {})}
    key = _key()
    if auth and len(key) >= 16:
        hdrs["Authorization"] = f"Bearer {key}"
    data = raw
    if body is not None:
        data = json.dumps(body).encode()
        hdrs["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw_b = r.read()
            if (r.headers.get("Content-Type") or "").startswith("application/json") or raw_b[:1] == b"{":
                return int(r.status), json.loads(raw_b.decode() if raw_b else "{}")
            return int(r.status), raw_b
    except urllib.error.HTTPError as e:
        raw_b = e.read()
        try:
            return int(e.code), json.loads(raw_b.decode())
        except Exception:  # noqa: BLE001
            return int(e.code), {"detail": raw_b[:400].decode(errors="replace")}
    except Exception as exc:  # noqa: BLE001
        return 0, {"error": type(exc).__name__, "detail": str(exc)[:200]}


def probe_reasoning_v2() -> dict:
    texts = {
        "fr": "La voiture consomme beaucoup d'énergie.",
        "en": "The car consumes a lot of energy.",
        "zh": "汽车消耗大量能源。",
    }
    rep = semantic_identity_report(texts)
    # Multiset structural check
    a = canonicalize_structured(
        premise_concept_ids=["KA", "KA"],
        conclusion_concept_ids=["KB"],
        relation_triples=[("KA", "⇒", "KB"), ("KA", "⇒", "KB")],
    )
    b = canonicalize_structured(
        premise_concept_ids=["KA"],
        conclusion_concept_ids=["KB"],
        relation_triples=[("KA", "⇒", "KB")],
    )
    # Anchor
    key = _key()
    anchor = {"http": 0}
    if key:
        c, body = http(
            "POST",
            f"{SEEDS['ovh-node-1']}/api/v1/ai/memo",
            body={
                "content": json.dumps(
                    {
                        "kind": "r334_reasoning_v2_anchor",
                        "protocol": PROTOCOL,
                        "multiset_differs": a.reasoning_id() != b.reasoning_id(),
                        "t3": rep,
                    },
                    sort_keys=True,
                ),
                "visibility": "public",
                "memo_type": "reasoning_canonical_v2",
                "graph_id": f"r334_{a.reasoning_id()}",
            },
            auth=True,
            timeout=90,
        )
        anchor = {"http": c, "block_index": body.get("block_index") if isinstance(body, dict) else None}
    return {
        "protocol": PROTOCOL,
        "multiset_distinct": a.reasoning_id() != b.reasoning_id(),
        "premises_ne_conclusions": a.premise_concept_ids != a.conclusion_concept_ids,
        "t3_intersection": bool(rep.get("intersection_nonempty")),
        "t3_same_id": bool(rep.get("same_reasoning_id")),
        "anchor": anchor,
        "pass": bool(
            a.reasoning_id() != b.reasoning_id()
            and a.premise_concept_ids != a.conclusion_concept_ids
            and rep.get("intersection_nonempty")
        ),
    }


def probe_fanout_authz() -> dict:
    """Measure write authz matrix + replica-signed fanout (R334-C)."""
    from src.artcb.memory.agent_channel import AgentChannel
    from src.artcb.memory.concept_network import fanout_bundle, publish_bundle
    from src.artcb.memory.concept_store import ConceptStore
    import tempfile

    tmp = Path(tempfile.mkdtemp(prefix="artcb_r334_fan_"))
    a = AgentChannel(agent_id="r334_fan", store=ConceptStore(tmp / "a"))
    learn = a.learn_from_text(f"R334 fanout authz probe nonce={time.time_ns()}")
    bundle = a.export_bundle(learn.concept_ids)
    key = _key()
    rows = {}
    for nid, base in SEEDS.items():
        bad = publish_bundle(base, bundle, api_key="artcb_invalid_key_for_acl_probe_xxxxxx")
        good = publish_bundle(base, bundle, api_key=key) if key else {"error": "no_key"}
        none = publish_bundle(base, bundle, api_key="")
        rows[nid] = {
            "bad_key_rejected": bool(bad.get("http") in (401, 403) or bad.get("error")),
            "empty_key_rejected": bool(none.get("http") in (401, 403) or none.get("error")),
            "operator_key_http": good.get("http") or (200 if good.get("bundle_sha256") else 0),
            "operator_key_ok": bool(good.get("graphs") or good.get("bundle_sha256")) and not good.get("error"),
        }
    fan = fanout_bundle(SEEDS["ovh-node-1"], bundle, api_key=key) if key else {"error": "no_key"}
    peers = fan.get("peers") if isinstance(fan, dict) else {}
    return {
        "rows": rows,
        "replica_fanout": {
            "http": fan.get("http"),
            "error": fan.get("error"),
            "peers_ok": fan.get("peers_ok"),
            "fanout_pass": bool(fan.get("fanout_pass")),
            "from_replica_id": fan.get("from_replica_id"),
            "peers": {
                k: {pk: pv for pk, pv in (v or {}).items() if pk in ("http", "ok", "skipped", "error", "body")}
                for k, v in (peers or {}).items()
            }
            if isinstance(peers, dict)
            else {},
        },
        "note": "direct API-key write to n2–n4 may stay 401; R334-C fanout uses replica-signed peer-ingest",
        "pass_authz_rejects": all(r["bad_key_rejected"] and r["empty_key_rejected"] for r in rows.values()),
        "pass_fanout_writes": bool(fan.get("fanout_pass")) if isinstance(fan, dict) else False,
    }


def probe_org_acl_live() -> dict:
    """Live: list public org hashes; export without session must fail closed."""
    out: dict = {"pass": False}
    c, b = http("GET", f"{SEEDS['ovh-node-1']}/api/v1/authz/orgs")
    orgs = (b or {}).get("orgs") if isinstance(b, dict) else []
    out["org_count"] = len(orgs or [])
    out["hashes"] = sorted({str(o.get("content_hash") or "")[:16] for o in (orgs or []) if o.get("content_hash")})
    # domains
    cd, bd = http("GET", f"{SEEDS['ovh-node-1']}/api/v1/authz/domains")
    domains = (bd or {}).get("domains") if isinstance(bd, dict) else []
    org_dom = next((d for d in domains or [] if d.get("domain_type") == "organization"), None)
    out["domain_id"] = (org_dom or {}).get("domain_id")
    if org_dom:
        # unauthenticated export
        ce0, be0 = http("POST", f"{SEEDS['ovh-node-1']}/api/v1/authz/domains/{org_dom['domain_id']}/export")
        # bearer API key (not session controller)
        ce1, be1 = http(
            "POST",
            f"{SEEDS['ovh-node-1']}/api/v1/authz/domains/{org_dom['domain_id']}/export",
            auth=True,
        )
        out["export_no_auth"] = {"http": ce0, "detail": (be0 or {}).get("detail") if isinstance(be0, dict) else None}
        out["export_api_key"] = {"http": ce1, "detail": (be1 or {}).get("detail") if isinstance(be1, dict) else None}
        # PASS ACL if no-auth and non-controller are denied (401/403)
        denied = ce0 in (401, 403) and ce1 in (401, 403)
        out["pass"] = bool(denied)
        out["body_leaked"] = bool(
            isinstance(be1, dict) and (be1.get("genesis_body") or be1.get("bundle"))
        )
        if out["body_leaked"]:
            out["pass"] = False
            out["note"] = "FAIL: body returned to non-controller"
        else:
            out["note"] = "export denied without org controller session (ACL closed for this path)"
    else:
        out["note"] = "no_org_domain_listed"
    return out


def main() -> int:
    for p in (Path.home() / ".artcb/cursor_agent.env", Path.home() / ".artcb/cursor_hooks.env"):
        if p.is_file():
            for line in p.read_text().splitlines():
                if "=" in line and not line.strip().startswith("#"):
                    k, _, v = line.partition("=")
                    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    out = {
        "measurement_id": f"R334_{time.strftime('%Y%m%dT%H%M%SZ')}_{commit[:12]}",
        "ts_ns": time.time_ns(),
        "commit_sha": commit,
        "certified_100": False,
    }
    out["reasoning_v2"] = probe_reasoning_v2()
    out["fanout_authz"] = probe_fanout_authz()
    out["org_acl"] = probe_org_acl_live()
    out["criteria"] = {
        "reasoning_v2_pass": bool(out["reasoning_v2"].get("pass")),
        "fanout_authz_rejects": bool(out["fanout_authz"].get("pass_authz_rejects")),
        "fanout_writes_x4": bool(out["fanout_authz"].get("pass_fanout_writes")),
        "org_acl_export_closed": bool(out["org_acl"].get("pass")),
        "O_certified_100": False,
    }
    d = ROOT / "logs" / "R334"
    d.mkdir(parents=True, exist_ok=True)
    path = d / "measurement.json"
    path.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"wrote": str(path), "criteria": out["criteria"], "reasoning": out["reasoning_v2"], "org_acl": {k: out["org_acl"].get(k) for k in ("pass", "note", "export_api_key")}}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
