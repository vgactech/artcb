#!/usr/bin/env python3
"""R322 — C2-D multi-hôte live (WAN HTTPS + Mac).

Preuve :
  1) health ×5 même SHA
  2) publish ACBN sur chaque hôte où une clé write est disponible
  3) cold ConceptStore + resolve WAN vers le publisher (artcb.me)
  4) cold resolve sur le store local de chaque hôte publié
  5) persistance hors-réseau après ingestion

Usage:
  PYTHONPATH=src:scripts python3 scripts/artcb_c2d_multihote_live.py
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

try:
    from artcb_dns_fix import install as _dns_install
except Exception:  # noqa: BLE001

    def _dns_install() -> None:
        return None

from src.artcb.memory.agent_channel import AgentChannel
from src.artcb.memory.concept_network import HttpConceptResolver, publish_bundle
from src.artcb.memory.concept_store import ConceptStore

HOSTS = [
    ("ovh-node-1", "https://artcb.me", ("artcb-blockchain", "prd"), ("artcb-blockchain", "dev")),
    ("ovh-node-2", "https://n2.artcb.me", ("artcb-2", "prd")),
    ("aws-node-3", "https://n3.artcb.me", ("artcb3", "prd")),
    ("ovh-node-4", "https://n4.artcb.me", ("artcb-4", "prd")),
    ("mac-node-local", "http://127.0.0.1:8001", ("artcb-1", "prd")),
]
PUBLISHER = "https://artcb.me"


def _file_key() -> str:
    k = (os.environ.get("ARTCB_API_KEY") or "").strip()
    if len(k) >= 16:
        return k
    env = Path.home() / ".artcb" / "cursor_agent.env"
    if env.is_file():
        for line in env.read_text(encoding="utf-8").splitlines():
            if line.startswith("ARTCB_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def _doppler_key(project: str, config: str) -> str:
    try:
        out = subprocess.check_output(
            ["doppler", "secrets", "get", "ARTCB_API_KEY", "-p", project, "-c", config, "--plain"],
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=45,
        ).strip()
        return out if len(out) >= 16 else ""
    except Exception:  # noqa: BLE001
        return ""


def _keys_for(node_specs: tuple) -> str:
    for project, config in node_specs:
        k = _doppler_key(project, config)
        if k:
            return k
    return _file_key()


def _health(base: str) -> dict:
    try:
        req = urllib.request.Request(
            f"{base.rstrip('/')}/health", headers={"Accept": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=25) as resp:
            body = json.loads(resp.read().decode())
            return {"http": resp.status, **body}
    except Exception as exc:  # noqa: BLE001
        return {"http": 0, "error": type(exc).__name__}


def main() -> int:
    _dns_install()
    t0 = time.perf_counter_ns()
    problem = (
        "R322 multi-hote WAN: charge IA — optimiser capacite pour reduire "
        f"consommation. nonce={time.time_ns()}"
    )
    report: dict = {
        "ts_ns": time.time_ns(),
        "certified_100": False,
        "publisher": PUBLISHER,
        "hosts": {},
    }

    tmp = Path(tempfile.mkdtemp(prefix="artcb_c2d5_"))
    a = AgentChannel(agent_id="agent_a_r322", store=ConceptStore(tmp / "a"))
    learn = a.learn_from_text(problem)
    bundle = a.export_bundle(learn.concept_ids)
    packet = learn.packet
    report["a"] = {
        "concept_ids": learn.concept_ids,
        "graph_id": learn.graph_id,
        "packet_sha256": hashlib.sha256(packet).hexdigest(),
        "bundle_sha256": hashlib.sha256(bundle).hexdigest(),
        "bundle_bytes": len(bundle),
    }

    # Resolve keys (never log values)
    key_map: dict[str, str] = {}
    for node_id, _base, *specs in HOSTS:
        flat: list[tuple[str, str]] = []
        for s in specs:
            if isinstance(s, tuple):
                flat.append(s)
        key_map[node_id] = _keys_for(tuple(flat)) if flat else _file_key()
    report["keys_present"] = {nid: bool(k) for nid, k in key_map.items()}

    publish_ok = 0
    self_resolve_ok = 0
    for node_id, base, *_rest in HOSTS:
        key = key_map.get(node_id) or _file_key()
        row: dict = {"base": base, "health": _health(base), "key_present": bool(key)}
        row["git_sha"] = str((row["health"] or {}).get("git_sha") or "")[:12]
        if row["health"].get("http") != 200:
            row["publish_ok"] = False
            row["self_resolve_ok"] = False
            report["hosts"][node_id] = row
            continue

        pub = publish_bundle(base, bundle, api_key=key)
        row["publish"] = {k: pub.get(k) for k in ("graphs", "bundle_sha256", "http", "error", "body") if k in pub or pub.get(k) is not None}
        row["publish_ok"] = bool(pub.get("graphs") or pub.get("bundle_sha256")) and not pub.get("error")
        if row["publish_ok"]:
            publish_ok += 1

        store_b = ConceptStore(tmp / f"self_{node_id}")
        b = AgentChannel(agent_id=f"b_self_{node_id}", store=store_b)
        resolver = HttpConceptResolver(base, api_key=key)
        rec = b.receive_packet(packet, resolver=resolver)
        row["self_resolve"] = {
            "http": resolver.last_status,
            "bundle_sha256": resolver.last_bundle_sha256,
            "missing_after": rec.missing_concept_ids,
            "found": len(rec.found_graphs),
            "ok": bool(rec.found_graphs) and not rec.missing_concept_ids,
            "transport": "WAN_HTTPS" if base.startswith("https://") else "LOCAL_HTTP",
        }
        row["self_resolve_ok"] = row["self_resolve"]["ok"]
        if row["self_resolve_ok"]:
            self_resolve_ok += 1
            offline = AgentChannel(agent_id=f"off_{node_id}", store=store_b).receive_packet(packet)
            row["offline_persist"] = {
                "ok": bool(offline.found_graphs) and not offline.missing_concept_ids
            }
        report["hosts"][node_id] = row

    # WAN: cold Mac-side store resolves from publisher URL (multi-host path)
    pub_key = key_map.get("ovh-node-1") or _file_key()
    # ensure publisher has bundle
    if not (report["hosts"].get("ovh-node-1") or {}).get("publish_ok"):
        publish_bundle(PUBLISHER, bundle, api_key=pub_key)
    wan_store = ConceptStore(tmp / "wan_cold")
    wan_agent = AgentChannel(agent_id="wan_cold", store=wan_store)
    wan_res = HttpConceptResolver(PUBLISHER, api_key=pub_key)
    wan_rec = wan_agent.receive_packet(packet, resolver=wan_res)
    report["wan_publisher_resolve"] = {
        "from": "cold_local_store",
        "via": PUBLISHER,
        "http": wan_res.last_status,
        "ok": bool(wan_rec.found_graphs) and not wan_rec.missing_concept_ids,
        "missing_after": wan_rec.missing_concept_ids,
        "found": len(wan_rec.found_graphs),
        "offline_ok": False,
    }
    if report["wan_publisher_resolve"]["ok"]:
        off = AgentChannel(agent_id="wan_off", store=wan_store).receive_packet(packet)
        report["wan_publisher_resolve"]["offline_ok"] = bool(off.found_graphs) and not off.missing_concept_ids

    shas = {r.get("git_sha") for r in report["hosts"].values() if r.get("git_sha")}
    healthy = sum(1 for r in report["hosts"].values() if (r.get("health") or {}).get("http") == 200)
    report["summary"] = {
        "healthy_hosts": healthy,
        "unique_git_shas": sorted(shas),
        "sha_aligned_5": healthy == 5 and len(shas) == 1,
        "publish_ok_hosts": publish_ok,
        "self_resolve_ok_hosts": self_resolve_ok,
        "wan_publisher_ok": report["wan_publisher_resolve"]["ok"],
        "wan_offline_ok": report["wan_publisher_resolve"]["offline_ok"],
        "c2d_multihote_pass": bool(
            report["wan_publisher_resolve"]["ok"]
            and report["wan_publisher_resolve"]["offline_ok"]
            and healthy >= 5
            and self_resolve_ok >= 1
        ),
        "c2d_five_store_fanout_pass": self_resolve_ok >= 5 and publish_ok >= 5,
        "honest_gaps": [
            "fan-out self-store on n2/n3/n4 needs per-node Doppler ARTCB_API_KEY in this agent env",
            "seed hole after 716 still blocks Mac tip catch-up (not invented)",
            "CERTIFIED_100 remains false",
        ],
        "dur_ns": time.perf_counter_ns() - t0,
    }
    text = json.dumps(report, indent=2, ensure_ascii=False)
    print(text)
    out = ROOT / "logs" / "322_c2d_multihote_latest.json"
    out.write_text(text + "\n", encoding="utf-8")
    print(f"wrote {out}", file=sys.stderr)
    return 0 if report["summary"]["c2d_multihote_pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
