#!/usr/bin/env python3
"""R324 — parallel measure: native replication B + fidelity + hole inventory hook.

Axes (same run, same commit_sha):
  A) fidelity: beaucoup vs peu must NOT share ConceptID
  B) dictionary cost: packet vs bundle vs UTF-8 (already in R323; re-measure)
  C) publisher-death B after server federation warm + hop=1 local-only
  D) hole 716 inventory (subprocess / import)

Does not invent blocks. CERTIFIED_100=false.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from src.artcb.memory.agent_channel import AgentChannel
from src.artcb.memory.concept_store import ConceptStore

try:
    from artcb_dns_fix import install as _dns

    _dns()
except Exception:  # noqa: BLE001
    pass


def _git_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip()
    except Exception:  # noqa: BLE001
        return ""


def _api_key() -> str:
    k = (os.environ.get("ARTCB_API_KEY") or "").strip()
    if len(k) >= 16:
        return k
    env = Path.home() / ".artcb" / "cursor_agent.env"
    if env.is_file():
        for line in env.read_text(encoding="utf-8").splitlines():
            if line.startswith("ARTCB_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def _get_resolve(base: str, cid: str, *, hop: int = 0) -> dict:
    url = f"{base}/api/v1/concepts/resolve?ids={cid}"
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/octet-stream",
            "X-ARTCB-Federation-Hop": str(hop),
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read()
            return {
                "http": resp.status,
                "known": int(resp.headers.get("X-ARTCB-Concept-Known") or 0),
                "federated": resp.headers.get("X-ARTCB-Concept-Federated", ""),
                "bytes": len(data),
            }
    except urllib.error.HTTPError as e:
        return {"http": e.code, "known": 0, "error": "HTTPError"}
    except Exception as exc:  # noqa: BLE001
        return {"http": 0, "known": 0, "error": type(exc).__name__}


def fidelity_suite(tmp: Path) -> dict:
    """Semantic fidelity: opposite adverbs must not collapse to one ConceptID."""
    a = "La voiture consomme beaucoup d'énergie."
    b = "La voiture consomme peu d'énergie."
    store = ConceptStore(tmp / "fidelity")
    ch = AgentChannel(agent_id="fid", store=store)
    ra = ch.learn_from_text(a)
    rb = ch.learn_from_text(b)
    same = set(ra.concept_ids) == set(rb.concept_ids) and len(ra.concept_ids) == 1
    overlap = sorted(set(ra.concept_ids) & set(rb.concept_ids))
    distinct = sorted(set(ra.concept_ids) ^ set(rb.concept_ids))
    # PASS if concept bags are not identical (information much/peu preserved somehow)
    # Strong PASS if bags differ; FAIL if identical single concept (lossy collapse)
    verdict = "FAIL_COLLAPSE" if same else ("PASS_DISTINCT" if distinct else "PARTIAL_OVERLAP")
    return {
        "phrase_a": a,
        "phrase_b": b,
        "ids_a": ra.concept_ids,
        "ids_b": rb.concept_ids,
        "overlap": overlap,
        "symmetric_diff": distinct,
        "verdict": verdict,
        "note": (
            "FAIL_COLLAPSE means beaucoup/peu lost. "
            "PASS_DISTINCT means encodings differ. Not full formal semantics."
        ),
    }


def publisher_death_native_b(tmp: Path) -> dict:
    """Warm n2 via server federation, then hop=1 local-only resolve (true B)."""
    from src.artcb.memory.concept_network import publish_bundle

    k = _api_key()
    pub = "https://artcb.me"
    n2 = "https://n2.artcb.me"
    ch = AgentChannel(agent_id="r324", store=ConceptStore(tmp / "pub"))
    learn = ch.learn_from_text(f"R324 native replica probe {time.time_ns()}")
    cid = learn.concept_ids[0]
    bundle = ch.export_bundle(learn.concept_ids)
    pub_res = publish_bundle(pub, bundle, api_key=k) if k else {"error": "no_key"}

    # Cold hop=1 on n2 — must miss if never warmed (proves empty start)
    cold = _get_resolve(n2, cid, hop=1)

    # Warm: hop=0 allows server federation to apex (fix R324 host skip)
    warm = _get_resolve(n2, cid, hop=0)

    # True B: hop=1 after warm — local store only, no peer fetch
    local = _get_resolve(n2, cid, hop=1)

    # Also warm n3/n4 for multi-seed native matrix
    peers = {
        "n2": n2,
        "n3": "https://n3.artcb.me",
        "n4": "https://n4.artcb.me",
    }
    multi = {}
    for name, base in peers.items():
        w = _get_resolve(base, cid, hop=0)
        loc = _get_resolve(base, cid, hop=1)
        multi[name] = {
            "warm": w,
            "local_hop1": loc,
            "native_ok": int(loc.get("known") or 0) >= 1,
        }

    b_ok = int(local.get("known") or 0) >= 1
    multi_ok = all(v["native_ok"] for v in multi.values())
    return {
        "concept_id": cid,
        "publish": {k2: pub_res.get(k2) for k2 in ("ok", "error", "http", "status") if k2 in pub_res}
        if isinstance(pub_res, dict)
        else {"raw_type": type(pub_res).__name__},
        "publish_keys": sorted(pub_res.keys()) if isinstance(pub_res, dict) else [],
        "cold_hop1_before_warm": cold,
        "warm_hop0": warm,
        "local_hop1_after_warm": local,
        "multi_seed": multi,
        "verdict": {
            "B_n2_native_after_federate": b_ok,
            "B_multi_n2_n3_n4": multi_ok,
            "publisher_death_resilience": bool(b_ok and multi_ok),
            "note": (
                "B = hop=1 after warm. Cold hop=1 before warm should be empty. "
                "Does not stop production publisher."
            ),
        },
    }


def dictionary_cost_sample(tmp: Path) -> dict:
    import artcb_compression_benchmark as bench

    art = bench.encode_artcb(list(bench.CORPUS_L4.values()), tmp)
    _ratio = bench._ratio
    return {
        "sum_utf8": art["sum_utf8"],
        "packet_bytes": art["packet_bytes"],
        "bundle_bytes": art["bundle_bytes"],
        "packet_vs_utf8": _ratio(art["sum_utf8"], art["packet_bytes"]),
        "bundle_vs_utf8": _ratio(art["sum_utf8"], art["bundle_bytes"]),
        "install_overhead_bytes": art["bundle_bytes"] - art["packet_bytes"],
        "mode_shared_knowledge": "packet",
        "mode_autonomous_transfer": "bundle",
    }


def main() -> int:
    out_dir = ROOT / "logs" / "R324"
    out_dir.mkdir(parents=True, exist_ok=True)
    t0 = time.perf_counter_ns()
    tmp = Path(tempfile.mkdtemp(prefix="artcb_r324_"))
    commit = _git_sha()
    mid = f"R324_{time.strftime('%Y%m%dT%H%M%SZ')}_{commit[:12]}"

    fidelity = fidelity_suite(tmp)
    dict_cost = dictionary_cost_sample(tmp)
    death = publisher_death_native_b(tmp)

    # hole inventory
    hole = {"skipped": True}
    inv = ROOT / "scripts" / "artcb_r324_hole716_inventory.py"
    if inv.is_file():
        try:
            subprocess.check_call(
                [sys.executable, str(inv)],
                cwd=ROOT,
                env={**os.environ, "PYTHONPATH": f"src:scripts:{ROOT}"},
                timeout=180,
            )
            hole_path = ROOT / "logs" / "324_hole716_inventory.json"
            if hole_path.is_file():
                hole = json.loads(hole_path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            hole = {"error": type(exc).__name__, "detail": str(exc)[:200]}

    report = {
        "measurement_id": mid,
        "ts_ns": time.time_ns(),
        "commit_sha": commit,
        "script": "scripts/artcb_r324_parallel_measure.py",
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "certified_100": False,
        "fidelity": fidelity,
        "dictionary_cost_L4": dict_cost,
        "publisher_death_native": death,
        "hole716": {
            "verdict": hole.get("verdict"),
            "717_exists_anywhere": hole.get("717_exists_anywhere"),
            "child_of_tip716_found": hole.get("child_of_tip716_found"),
        },
        "dur_ns": time.perf_counter_ns() - t0,
        "artcb_is_not_auto_memory": (
            "ARTCB is not a Cursor auto-forget switch. Reload main + OPEN list each turn. "
            "Documented ≠ fixed. Parallel OPEN work is mandatory (operator R317/R324)."
        ),
    }

    (out_dir / "measurement.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    (out_dir / "commit_sha.txt").write_text(commit + "\n", encoding="utf-8")

    v = death["verdict"]
    lines = [
        f"# R324 — parallel (replication + fidelity + hole) ({mid})",
        "",
        f"`commit_sha` = `{commit}`",
        "",
        "`CERTIFIED_100=false`",
        "",
        "## ARTCB auto-memory?",
        "",
        "**NON.** Pas un mode on/off Cursor. Recharger `main` + liste OPEN chaque tour.",
        "",
        "## Fidelity beaucoup/peu",
        "",
        f"- verdict: **{fidelity['verdict']}**",
        f"- ids_a: `{fidelity['ids_a']}`",
        f"- ids_b: `{fidelity['ids_b']}`",
        "",
        "## Dictionary cost L4",
        "",
        f"- UTF-8 sum: {dict_cost['sum_utf8']} B",
        f"- packet: {dict_cost['packet_bytes']} B",
        f"- bundle: {dict_cost['bundle_bytes']} B",
        f"- install_overhead: {dict_cost['install_overhead_bytes']} B",
        "",
        "## Publisher-death native B (hop=1 after warm)",
        "",
        f"- B n2: **{v['B_n2_native_after_federate']}**",
        f"- B multi n2/n3/n4: **{v['B_multi_n2_n3_n4']}**",
        f"- publisher_death_resilience: **{v['publisher_death_resilience']}**",
        f"- cold hop1 known: {death['cold_hop1_before_warm'].get('known')}",
        f"- warm hop0 known: {death['warm_hop0'].get('known')}",
        f"- local hop1 known: {death['local_hop1_after_warm'].get('known')}",
        "",
        "## Hole 716",
        "",
        f"- verdict: **{report['hole716'].get('verdict')}**",
        f"- 717 anywhere: {report['hole716'].get('717_exists_anywhere')}",
        f"- child of tip716: {report['hole716'].get('child_of_tip716_found')}",
        "",
        "Never invent a successor block.",
        "",
    ]
    report_md = out_dir / "report.md"
    report_md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    dest = ROOT / "rapports" / f"324_parallel_{commit[:12]}.md"
    dest.write_text(report_md.read_text(encoding="utf-8"), encoding="utf-8")

    print(
        json.dumps(
            {
                "measurement_id": mid,
                "commit_sha": commit,
                "fidelity": fidelity["verdict"],
                "publisher_death": v,
                "hole716": report["hole716"],
                "report": str(dest),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
