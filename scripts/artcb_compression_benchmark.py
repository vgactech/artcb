#!/usr/bin/env python3
"""R323 — benchmark compression .artcb / ACBN vs baselines (mesuré, pas estimé).

Mesure trois compressions (audit opérateur) :
  C_physique  = 1 - octets_ACBN_or_packet / octets_UTF8_ref
  C_semantic  = 1 - n_concept_ids / n_tokens_linguistiques (approx whitespace)
  C_multilang = 1 - octets_unique_concept_payload / somme_utf8_N_langues

Baselines (stdlib + optionnels) :
  UTF-8, JSON, gzip, zlib ; brotli/zstd/cbor2/msgpack si installés.

Usage:
  PYTHONPATH=src:scripts python3 scripts/artcb_compression_benchmark.py
  PYTHONPATH=src:scripts python3 scripts/artcb_compression_benchmark.py --out-dir logs/R323
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from src.artcb.ir.concept import encode_concept_packet
from src.artcb.memory.agent_channel import AgentChannel
from src.artcb.memory.concept_store import ConceptStore

# 8-lang L4 bag (same semantic content as C2-B R321)
CORPUS_L4 = {
    "fr": "La voiture consomme beaucoup d'énergie.",
    "en": "The car consumes a lot of energy.",
    "es": "El coche consume mucha energía.",
    "pt": "O carro consome muita energia.",
    "it": "L'auto consuma molta energia.",
    "ru": "Автомобиль потребляет много энергии.",
    "la": "Vehiculum multam energiam consumit.",
    "zh": "汽车消耗大量能源。",
}

# Longer redundant paragraph (same idea repeated) — better physical compression case
CORPUS_LONG = {
    "fr": (
        "La voiture consomme beaucoup d'énergie. "
        "Quand la charge augmente, la consommation d'énergie de la voiture augmente. "
        "Il faut optimiser la capacité pour réduire la consommation d'énergie."
    ),
    "en": (
        "The car consumes a lot of energy. "
        "When the load increases, the car's energy consumption increases. "
        "We must optimize capacity to reduce energy consumption."
    ),
}


def _git_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip()
    except Exception:  # noqa: BLE001
        return ""


def _ratio(ref: int, cand: int) -> dict:
    if ref <= 0:
        return {"ref_bytes": ref, "cand_bytes": cand, "reduction_pct": None}
    return {
        "ref_bytes": ref,
        "cand_bytes": cand,
        "reduction_pct": round(100.0 * (1.0 - (cand / ref)), 4),
    }


def _try_import(name: str):
    try:
        return __import__(name)
    except Exception:  # noqa: BLE001
        return None


def baseline_sizes(payload: bytes, *, as_text: str | None = None) -> dict:
    out: dict = {
        "raw_bytes": len(payload),
        "gzip": len(gzip.compress(payload, compresslevel=9)),
        "zlib": len(zlib.compress(payload, level=9)),
    }
    if as_text is not None:
        out["utf8"] = len(as_text.encode("utf-8"))
        out["json_utf8"] = len(json.dumps({"text": as_text}, ensure_ascii=False).encode())
    brotli = _try_import("brotli")
    if brotli:
        out["brotli"] = len(brotli.compress(payload))
    zstd = _try_import("zstandard")
    if zstd:
        out["zstd"] = len(zstd.ZstdCompressor(level=19).compress(payload))
    cbor2 = _try_import("cbor2")
    if cbor2 and as_text is not None:
        out["cbor"] = len(cbor2.dumps({"text": as_text}))
    msgpack = _try_import("msgpack")
    if msgpack and as_text is not None:
        out["msgpack"] = len(msgpack.packb({"text": as_text}, use_bin_type=True))
    return out


def encode_artcb(texts: list[str], tmp: Path) -> dict:
    store = ConceptStore(tmp / f"store_{hashlib.sha256(''.join(texts).encode()).hexdigest()[:8]}")
    ch = AgentChannel(agent_id="bench", store=store)
    all_ids: list[str] = []
    per: list[dict] = []
    for t in texts:
        r = ch.learn_from_text(t)
        all_ids.extend(r.concept_ids)
        per.append(
            {
                "utf8": len(t.encode()),
                "concept_ids": r.concept_ids,
                "packet_bytes": len(r.packet),
                "tokens_ws": len(t.split()),
            }
        )
    # unique concept payload for multilingual bag
    uniq = list(dict.fromkeys(all_ids))
    packet = encode_concept_packet(uniq)
    bundle = ch.export_bundle(uniq)
    return {
        "per_phrase": per,
        "unique_concept_ids": uniq,
        "packet_bytes": len(packet),
        "bundle_bytes": len(bundle),
        "packet_sha256": hashlib.sha256(packet).hexdigest(),
        "bundle_sha256": hashlib.sha256(bundle).hexdigest(),
        "n_phrases": len(texts),
        "n_unique_concepts": len(uniq),
        "sum_utf8": sum(p["utf8"] for p in per),
        "sum_tokens_ws": sum(p["tokens_ws"] for p in per),
        "sum_packets_naive": sum(p["packet_bytes"] for p in per),
    }


def run_suite(name: str, corpus: dict[str, str], tmp: Path) -> dict:
    texts = list(corpus.values())
    joined = "\n".join(texts)
    art = encode_artcb(texts, tmp)
    utf8 = joined.encode("utf-8")
    bases = baseline_sizes(utf8, as_text=joined)
    # Physical: unique ACBN packet vs sum of UTF-8 phrases (multilang redundancy case)
    physical_packet = _ratio(art["sum_utf8"], art["packet_bytes"])
    physical_bundle = _ratio(art["sum_utf8"], art["bundle_bytes"])
    # vs gzip of all utf8
    vs_gzip = _ratio(bases["gzip"], art["packet_bytes"])
    semantic = _ratio(art["sum_tokens_ws"], art["n_unique_concepts"])
    return {
        "suite": name,
        "langs": list(corpus.keys()),
        "artcb": art,
        "baselines_joined_utf8": bases,
        "C_physique_packet_vs_sum_utf8": physical_packet,
        "C_physique_bundle_vs_sum_utf8": physical_bundle,
        "C_packet_vs_gzip_joined": vs_gzip,
        "C_semantic_concepts_vs_tokens": semantic,
        "note": (
            "Negative reduction_pct means ARTCB payload is larger than the reference. "
            "Short single phrases often expand; multilingual bags compress conceptually."
        ),
    }


def publisher_death_matrix(tmp: Path) -> dict:
    """Honest resilience matrix without shutting production artcb.me.

    A = federated resolve (fallback ON) after publish to publisher
    B = resolve via n2 with fallback OFF → expects FAIL if store empty
    C = after federated ingest, offline local resolve → PASS
    """
    try:
        from artcb_dns_fix import install as _dns

        _dns()
    except Exception:  # noqa: BLE001
        pass
    from src.artcb.memory.concept_network import HttpConceptResolver, publish_bundle

    def key() -> str:
        k = (os.environ.get("ARTCB_API_KEY") or "").strip()
        if len(k) >= 16:
            return k
        env = Path.home() / ".artcb" / "cursor_agent.env"
        if env.is_file():
            for line in env.read_text(encoding="utf-8").splitlines():
                if line.startswith("ARTCB_API_KEY="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
        return ""

    k = key()
    pub = "https://artcb.me"
    peer = "https://n2.artcb.me"
    ch = AgentChannel(agent_id="death", store=ConceptStore(tmp / "death_a"))
    learn = ch.learn_from_text(f"R323 publisher-death probe {time.time_ns()}")
    bundle = ch.export_bundle(learn.concept_ids)
    pub_res = publish_bundle(pub, bundle, api_key=k) if k else {"error": "no_key"}

    # A: cold → peer with fallback ON
    store_a = ConceptStore(tmp / "death_b_a")
    ra = HttpConceptResolver(peer, api_key=k, federate_fallback=True)
    rec_a = AgentChannel(agent_id="ba", store=store_a).receive_packet(
        learn.packet, resolver=ra
    )
    a_ok = bool(rec_a.found_graphs) and not rec_a.missing_concept_ids

    # B: fresh cold → peer with fallback OFF (publisher unreachable path)
    store_b = ConceptStore(tmp / "death_b_b")
    rb = HttpConceptResolver(peer, api_key=k, federate_fallback=False)
    rec_b = AgentChannel(agent_id="bb", store=store_b).receive_packet(
        learn.packet, resolver=rb
    )
    b_empty = (not rec_b.found_graphs) or bool(rec_b.missing_concept_ids)

    # C: offline after A ingested
    offline = AgentChannel(agent_id="bc", store=store_a).receive_packet(learn.packet)
    c_ok = bool(offline.found_graphs) and not offline.missing_concept_ids

    return {
        "publish_to_artcb_me": pub_res,
        "A_federated_resolve_via_n2": {
            "ok": a_ok,
            "via": ra.last_federated_from,
            "meaning": "federation PASS",
        },
        "B_n2_only_no_fallback": {
            "empty_or_missing": b_empty,
            "ok_independent_replica": not b_empty,
            "meaning": "FAIL expected if native replication OPEN",
        },
        "C_offline_after_federated_ingest": {
            "ok": c_ok,
            "meaning": "local persistence after fetch PASS",
        },
        "verdict": {
            "federation_level_A": a_ok,
            "replication_level_B": not b_empty,
            "local_persist_level_C": c_ok,
            "publisher_death_resilience": False,  # cannot claim without B PASS
            "note": "Did not stop production publisher; B isolates dependence on fallback.",
        },
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", default=str(ROOT / "logs" / "R323"))
    args = ap.parse_args()
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    t0 = time.perf_counter_ns()
    tmp = Path(tempfile.mkdtemp(prefix="artcb_r323_"))
    commit = _git_sha()
    measurement_id = f"R323_{time.strftime('%Y%m%dT%H%M%SZ')}_{commit[:12]}"

    suites = [
        run_suite("L4_8lang_same_meaning", CORPUS_L4, tmp),
        run_suite("LONG_2lang_redundant", CORPUS_LONG, tmp),
        # single short phrase — often expansion (honest)
        run_suite("SINGLE_fr_short", {"fr": CORPUS_L4["fr"]}, tmp),
    ]
    death = publisher_death_matrix(tmp)

    report = {
        "measurement_id": measurement_id,
        "ts_ns": time.time_ns(),
        "commit_sha": commit,
        "script": "scripts/artcb_compression_benchmark.py",
        "script_sha256": hashlib.sha256(
            (ROOT / "scripts" / "artcb_compression_benchmark.py").read_bytes()
        ).hexdigest(),
        "certified_100": False,
        "suites": suites,
        "publisher_death_matrix": death,
        "dur_ns": time.perf_counter_ns() - t0,
        "official_compression_pct": None,
        "official_compression_note": (
            "No single official % — see per-suite C_physique_* and C_semantic_*. "
            "Do not quote a global X% without naming suite+reference."
        ),
    }

    meas_path = out_dir / "measurement.json"
    meas_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (out_dir / "commit_sha.txt").write_text(commit + "\n", encoding="utf-8")
    (out_dir / "timestamps.json").write_text(
        json.dumps({"ts_ns": report["ts_ns"], "measurement_id": measurement_id}, indent=2) + "\n",
        encoding="utf-8",
    )

    # Markdown report from SAME object
    lines = [
        f"# R323 — compression + publisher-death matrix ({measurement_id})",
        "",
        f"`commit_sha` = `{commit}`",
        "",
        "`CERTIFIED_100=false`",
        "",
        "## Official compression %",
        "",
        "**NON ÉTABLI comme chiffre unique.** Voir tableaux par suite.",
        "",
        "## Suites",
        "",
    ]
    for s in suites:
        lines.append(f"### {s['suite']}")
        lines.append("")
        lines.append(f"- langs: {', '.join(s['langs'])}")
        lines.append(
            f"- sum UTF-8 phrases: {s['artcb']['sum_utf8']} B ; "
            f"unique packet: {s['artcb']['packet_bytes']} B ; "
            f"bundle: {s['artcb']['bundle_bytes']} B"
        )
        lines.append(
            f"- C_physique packet vs sum UTF-8: "
            f"**{s['C_physique_packet_vs_sum_utf8']['reduction_pct']}%**"
        )
        lines.append(
            f"- C_physique bundle vs sum UTF-8: "
            f"**{s['C_physique_bundle_vs_sum_utf8']['reduction_pct']}%**"
        )
        lines.append(
            f"- C_semantic concepts vs tokens: "
            f"**{s['C_semantic_concepts_vs_tokens']['reduction_pct']}%**"
        )
        lines.append(f"- baselines joined: `{json.dumps(s['baselines_joined_utf8'])}`")
        lines.append("")
    v = death["verdict"]
    lines += [
        "## Publisher-death matrix (simulated)",
        "",
        f"- A federation: **{v['federation_level_A']}**",
        f"- B independent replica (n2 no fallback): **{v['replication_level_B']}**",
        f"- C offline after ingest: **{v['local_persist_level_C']}**",
        f"- publisher_death_resilience: **{v['publisher_death_resilience']}**",
        "",
        f"measurement.json sha256 = "
        f"`{hashlib.sha256(meas_path.read_bytes()).hexdigest()}`",
        "",
    ]
    report_path = out_dir / "report.md"
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    # also copy under rapports with same measurement_id
    dest = ROOT / "rapports" / f"323_compression_{commit[:12]}_{measurement_id.split('_')[1]}.md"
    dest.write_text(report_path.read_text(encoding="utf-8"), encoding="utf-8")

    print(json.dumps({"measurement_id": measurement_id, "commit_sha": commit, "out_dir": str(out_dir), "report": str(dest), "summary": {
        s["suite"]: {
            "packet_vs_utf8_pct": s["C_physique_packet_vs_sum_utf8"]["reduction_pct"],
            "bundle_vs_utf8_pct": s["C_physique_bundle_vs_sum_utf8"]["reduction_pct"],
            "semantic_pct": s["C_semantic_concepts_vs_tokens"]["reduction_pct"],
        }
        for s in suites
    }, "publisher_death": v}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
