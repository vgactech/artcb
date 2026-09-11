#!/usr/bin/env python3
"""R325 — parallel: runtime alignment + hard publisher-death B + 716 continuity + fidelity expand.

Never invent block 717. CERTIFIED_100=false.
Distinguishes:
  code_sha_measured (f739a6b era) vs docs_sha (63fdf71+) vs runtime health git_sha
  federation ≠ replication ≠ resilience
  hop=1 local-only ≠ stopping production publisher (honest note)
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

try:
    from artcb_dns_fix import install as _dns

    _dns()
except Exception:  # noqa: BLE001
    pass

TIP716 = "f79f6a1a71896e619f6d66cc998bbc918b2eb1d4649f3dcad2d6349cb6c9dd37"
SEEDS = (
    "https://artcb.me",
    "https://n2.artcb.me",
    "https://n3.artcb.me",
    "https://n4.artcb.me",
)
EXPECTED_CODE_FIX = "f739a6b"  # R324 code fix (measurement attribution)
# docs commit may be later; runtime must be >= fix


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


def _http_json(url: str, *, timeout: float = 30) -> tuple[int, dict | None]:
    try:
        with urllib.request.urlopen(
            urllib.request.Request(url, headers={"Accept": "application/json"}),
            timeout=timeout,
        ) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, None
    except Exception as exc:  # noqa: BLE001
        return 0, {"error": type(exc).__name__, "detail": str(exc)[:120]}


def _resolve(base: str, cid: str, *, hop: int) -> dict:
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
    except Exception as exc:  # noqa: BLE001
        return {"http": 0, "known": 0, "error": type(exc).__name__}


def axis_a_runtime() -> dict:
    rows = {}
    for base in SEEDS:
        code_h, health = _http_json(f"{base}/health")
        code_s, status = _http_json(f"{base}/api/v1/chain/status")
        h = health if isinstance(health, dict) else {}
        s = status if isinstance(status, dict) else {}
        sha = str(h.get("git_sha") or "")
        rows[base] = {
            "health_http": code_h,
            "status_http": code_s,
            "git_sha": sha,
            "git_sha12": sha[:12],
            "contains_r324_fix": EXPECTED_CODE_FIX in sha or sha.startswith(EXPECTED_CODE_FIX),
            "protocol_version": h.get("protocol_version"),
            "genesis_hash": h.get("genesis_hash"),
            "network_id": h.get("network_id"),
            "height": s.get("height") or h.get("height") or h.get("chain_height"),
            "last_hash": s.get("last_hash") or h.get("last_hash") or h.get("tip_hash"),
            "chain_valid": s.get("chain_valid"),
        }
    shas = {r["git_sha12"] for r in rows.values() if r.get("git_sha12")}
    heights = {r["height"] for r in rows.values()}
    tips = {str(r.get("last_hash") or "")[:16] for r in rows.values()}
    sha_ok = len(shas) == 1 and all(bool(r.get("git_sha12")) for r in rows.values())
    tip_ok = len(heights) == 1 and len({t for t in tips if t}) == 1
    if sha_ok and tip_ok:
        verdict = "PASS_ALIGNED"
    elif sha_ok and not tip_ok:
        verdict = "PARTIAL_SHA_OK_TIP_DIVERGE"
    else:
        verdict = "PARTIAL_OR_DIVERGE"
    return {
        "seeds": rows,
        "git_sha_unique": sorted(shas),
        "height_unique": sorted(str(x) for x in heights),
        "tip16_unique": sorted(tips),
        "all_same_sha": len(shas) == 1,
        "all_same_tip": tip_ok,
        "all_have_r324_fix_ancestor_or_sha": all(
            r.get("contains_r324_fix") or (r.get("git_sha12") or "").startswith("63fdf71")
            for r in rows.values()
        ),
        "ci_note": "Empty GitHub status checks ≠ CI PASS (operator audit).",
        "verdict": verdict,
    }


def axis_b_hard_publisher_death(tmp: Path) -> dict:
    """Hard B: warm stores, then hop=1 only (federation cut per-request).

    Does NOT stop production artcb.me (operator safety). Measures the
    equivalent: after warm, resolve with hop>=1 must succeed from local store
    with federated=0. Cold hop=1 before warm must miss.
    """
    from src.artcb.memory.agent_channel import AgentChannel
    from src.artcb.memory.concept_network import publish_bundle
    from src.artcb.memory.concept_store import ConceptStore

    k = _api_key()
    pub = "https://artcb.me"
    ch = AgentChannel(agent_id="r325", store=ConceptStore(tmp / "pub"))
    learn = ch.learn_from_text(
        f"R325 hard publisher-death unique lemma {time.time_ns()} zxqv{os.urandom(4).hex()}"
    )
    cid = learn.concept_ids[0]
    bundle = ch.export_bundle(learn.concept_ids)
    pub_res = publish_bundle(pub, bundle, api_key=k) if k else {"error": "no_key"}

    peers = {
        "n2": "https://n2.artcb.me",
        "n3": "https://n3.artcb.me",
        "n4": "https://n4.artcb.me",
    }
    per: dict = {}
    for name, base in peers.items():
        cold = _resolve(base, cid, hop=1)
        warm = _resolve(base, cid, hop=0)  # allow one-hop federate ingest
        local = _resolve(base, cid, hop=1)  # federation cut
        # Extra: hop=1 again (prove stable local)
        local2 = _resolve(base, cid, hop=1)
        per[name] = {
            "cold_hop1": cold,
            "warm_hop0": warm,
            "local_hop1": local,
            "local_hop1_repeat": local2,
            "native_ok": int(local.get("known") or 0) >= 1
            and str(local.get("federated") or "0") in {"0", ""},
            "cold_was_empty": int(cold.get("known") or 0) == 0,
        }

    all_native = all(v["native_ok"] for v in per.values())
    all_cold = all(v["cold_was_empty"] for v in per.values())
    return {
        "concept_id": cid,
        "publish_ok": isinstance(pub_res, dict) and "error" not in pub_res,
        "publish_keys": sorted(pub_res.keys()) if isinstance(pub_res, dict) else [],
        "peers": per,
        "verdict": {
            "B_hard_hop1_local_n2_n3_n4": all_native,
            "cold_empty_before_warm": all_cold,
            "publisher_process_stopped": False,
            "federation_cut_method": "X-ARTCB-Federation-Hop:1 (per-request)",
            "publisher_death_resilience_measured": bool(all_native and all_cold),
            "note": (
                "Production publisher not killed. Hard B = local resolve with "
                "federation hop cut after warm. Killing artcb.me left for "
                "controlled ops window — not claimed here."
            ),
        },
    }


def axis_c_continuity_716() -> dict:
    """Search for any block with prev_hash == tip716 across seeds + index scan."""
    out: dict = {"tip716": TIP716, "seeds": {}, "children_found": []}
    for base in SEEDS:
        row: dict = {"base": base}
        # tip status
        _, st = _http_json(f"{base}/api/v1/chain/status")
        if isinstance(st, dict):
            row["height"] = st.get("height")
            row["last_hash"] = str(st.get("last_hash") or "")[:16]
            row["chain_valid"] = st.get("chain_valid")
        # exact indices of interest
        for idx in (716, 717, 1073, 1074, 1140):
            c, body = _http_json(f"{base}/api/v1/chain/block/{idx}")
            blk = (body or {}).get("block") if isinstance(body, dict) else None
            if c == 200 and isinstance(blk, dict):
                prev = str(blk.get("prev_hash") or "")
                h = str(blk.get("hash") or "")
                entry = {
                    "http": 200,
                    "hash16": h[:16],
                    "prev16": prev[:16],
                    "prev_is_tip716": prev == TIP716,
                }
                row[f"b{idx}"] = entry
                if prev == TIP716:
                    out["children_found"].append({"base": base, "index": idx, "hash": h})
            else:
                row[f"b{idx}"] = {"http": c}
        # scan a window of public heights for prev==tip716 (sample, not full book)
        # Use blocks API if available
        c_blocks, blocks_body = _http_json(
            f"{base}/api/v1/chain/blocks?from_index=700&limit=50"
        )
        scan_hits = []
        if c_blocks == 200 and isinstance(blocks_body, dict):
            for blk in blocks_body.get("blocks") or []:
                if not isinstance(blk, dict):
                    continue
                if str(blk.get("prev_hash") or "") == TIP716:
                    scan_hits.append(
                        {
                            "index": blk.get("index"),
                            "hash16": str(blk.get("hash") or "")[:16],
                        }
                    )
                    out["children_found"].append(
                        {
                            "base": base,
                            "index": blk.get("index"),
                            "hash": str(blk.get("hash") or ""),
                            "via": "blocks_scan_700_50",
                        }
                    )
        row["scan_700_50_hits"] = scan_hits
        # also sample gap 717-730 and jump near 1074
        gap_present = []
        for idx in list(range(717, 731)) + [1000, 1050, 1070, 1071, 1072, 1073]:
            c, body = _http_json(f"{base}/api/v1/chain/block/{idx}")
            if c == 200:
                blk = (body or {}).get("block") if isinstance(body, dict) else None
                gap_present.append(idx)
                if isinstance(blk, dict) and str(blk.get("prev_hash") or "") == TIP716:
                    out["children_found"].append(
                        {"base": base, "index": idx, "hash": str(blk.get("hash") or "")}
                    )
        row["present_sampled"] = gap_present
        out["seeds"][base] = row

    # dedupe children
    uniq = []
    seen = set()
    for ch in out["children_found"]:
        key = (ch.get("index"), str(ch.get("hash") or "")[:32])
        if key in seen:
            continue
        seen.add(key)
        uniq.append(ch)
    out["children_found"] = uniq
    out["717_exists"] = any(
        (r.get("b717") or {}).get("http") == 200 for r in out["seeds"].values()
    )
    out["verdict"] = (
        "CHILD_FOUND"
        if uniq
        else "HOLE_CONFIRMED_NO_CHILD"
    )
    out["incident"] = (
        None
        if uniq
        else "PRODUCTION_CONTINUITY_GAP — not a Mac catch-up miss; never invent 717"
    )
    return out


def axis_d_compression_fidelity(tmp: Path) -> dict:
    from artcb.ir.concept import concept_id_from_node
    from artcb.ir.encoder import IREncoder
    from artcb.memory.agent_channel import AgentChannel
    from artcb.memory.concept_store import ConceptStore
    import artcb_compression_benchmark as bench

    enc = IREncoder(enable_cache=False)
    fidelity_cases = [
        ("beaucoup", "La voiture consomme beaucoup d'énergie."),
        ("peu", "La voiture consomme peu d'énergie."),
        ("neg_pas", "La voiture ne consomme pas d'énergie."),
        ("modal_peut", "La voiture peut consommer de l'énergie."),
        ("pluriel", "Les voitures consomment beaucoup d'énergie."),
    ]
    fid_rows = []
    for name, text in fidelity_cases:
        g = enc.encode(text)
        fid_rows.append(
            {
                "name": name,
                "text": text,
                "syms": [n.sym for n in g.nodes],
                "ids": [concept_id_from_node(n) for n in g.nodes],
            }
        )
    id_set = {tuple(r["ids"]) for r in fid_rows}
    # beaucoup vs peu must differ
    id_hi = next(r["ids"] for r in fid_rows if r["name"] == "beaucoup")
    id_lo = next(r["ids"] for r in fid_rows if r["name"] == "peu")
    art = bench.encode_artcb(list(bench.CORPUS_L4.values()), tmp / "d")
    t0 = time.perf_counter_ns()
    for _ in range(20):
        enc.encode(bench.CORPUS_L4["fr"])
    encode_ns = (time.perf_counter_ns() - t0) // 20
    # decode cost: packet roundtrip
    ch = AgentChannel(agent_id="d", store=ConceptStore(tmp / "dec"))
    learn = ch.learn_from_text(bench.CORPUS_L4["fr"])
    t1 = time.perf_counter_ns()
    ch.receive_packet(learn.packet)
    decode_ns = time.perf_counter_ns() - t1

    return {
        "byte_compression_L4_packet_vs_utf8": bench._ratio(
            art["sum_utf8"], art["packet_bytes"]
        ),
        "dictionary_amortization_bundle_vs_utf8": bench._ratio(
            art["sum_utf8"], art["bundle_bytes"]
        ),
        "install_overhead_bytes": art["bundle_bytes"] - art["packet_bytes"],
        "semantic_convergence_L4": {
            "n_phrases": art["n_phrases"],
            "n_unique_concepts": art["n_unique_concepts"],
            "unique_ids": art["unique_concept_ids"],
        },
        "information_fidelity_cases": fid_rows,
        "fidelity_beaucoup_neq_peu": id_hi != id_lo,
        "fidelity_case_distinct_bags": len(id_set),
        "encode_medianish_ns_fr_L4": encode_ns,
        "decode_packet_ns": decode_ns,
        "official_global_pct": None,
        "verdict": {
            "byte_packet_L4_ok": art["packet_bytes"] < art["sum_utf8"],
            "fidelity_intensity_ok": id_hi != id_lo,
            "global_compression_claimed": False,
        },
    }


def main() -> int:
    out_dir = ROOT / "logs" / "R325"
    out_dir.mkdir(parents=True, exist_ok=True)
    t0 = time.perf_counter_ns()
    tmp = Path(tempfile.mkdtemp(prefix="artcb_r325_"))
    commit = _git_sha()
    mid = f"R325_{time.strftime('%Y%m%dT%H%M%SZ')}_{commit[:12]}"

    a = axis_a_runtime()
    b = axis_b_hard_publisher_death(tmp)
    c = axis_c_continuity_716()
    d = axis_d_compression_fidelity(tmp)

    report = {
        "measurement_id": mid,
        "ts_ns": time.time_ns(),
        "commit_sha": commit,
        "code_fix_attributed": EXPECTED_CODE_FIX,
        "script": "scripts/artcb_r325_parallel_measure.py",
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "certified_100": False,
        "axis_a_runtime": a,
        "axis_b_publisher_death_hard": b,
        "axis_c_continuity_716": c,
        "axis_d_compression_fidelity": d,
        "dur_ns": time.perf_counter_ns() - t0,
        "distinctions": {
            "federation_ne_replication_ne_resilience": True,
            "r324_pass_ne_certified_100": True,
            "deployed_ne_native_replication_without_hop1_proof": True,
            "empty_ci_statuses_ne_ci_pass": True,
        },
    }

    (out_dir / "measurement.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    (out_dir / "commit_sha.txt").write_text(commit + "\n", encoding="utf-8")

    lines = [
        f"# R325 — parallel axes ({mid})",
        "",
        f"`commit_sha` = `{commit}` (docs/branch HEAD)",
        f"`code_fix_attributed` = `{EXPECTED_CODE_FIX}` (R324 fix for result attribution)",
        "",
        "`CERTIFIED_100=false`",
        "",
        "## A — Runtime alignment",
        "",
        f"- verdict: **{a['verdict']}**",
        f"- shas: `{a['git_sha_unique']}`",
        f"- heights: `{a['height_unique']}`",
        "",
        "## B — Publisher-death hard (hop=1 local)",
        "",
        f"- B n2/n3/n4 local: **{b['verdict']['B_hard_hop1_local_n2_n3_n4']}**",
        f"- cold empty: **{b['verdict']['cold_empty_before_warm']}**",
        f"- publisher process stopped: **{b['verdict']['publisher_process_stopped']}**",
        f"- resilience measured: **{b['verdict']['publisher_death_resilience_measured']}**",
        "",
        "## C — Continuity 716",
        "",
        f"- verdict: **{c['verdict']}**",
        f"- children_found: {len(c['children_found'])}",
        f"- incident: {c.get('incident')}",
        "",
        "## D — Compression + fidelity",
        "",
        f"- packet vs UTF-8 L4: {d['byte_compression_L4_packet_vs_utf8']}",
        f"- bundle vs UTF-8: {d['dictionary_amortization_bundle_vs_utf8']}",
        f"- fidelity beaucoup≠peu: **{d['fidelity_beaucoup_neq_peu']}**",
        f"- distinct fidelity bags: {d['fidelity_case_distinct_bags']}",
        f"- official_global_pct: {d['official_global_pct']}",
        "",
        "Never invent block 717.",
        "",
    ]
    (out_dir / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    dest = ROOT / "rapports" / f"325_parallel_{commit[:12]}.md"
    dest.write_text((out_dir / "report.md").read_text(encoding="utf-8"), encoding="utf-8")

    print(
        json.dumps(
            {
                "measurement_id": mid,
                "commit_sha": commit,
                "A": a["verdict"],
                "B": b["verdict"],
                "C": c["verdict"],
                "D": d["verdict"],
                "report": str(dest),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
