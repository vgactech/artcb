#!/usr/bin/env python3
"""R316 parallel — langage IA live matrix (honest, not CERTIFIED_100).

Measures:
  - probe FR/EN/ES sentences → ConceptID overlap (expect 1 after lexicon)
  - voiture/car/coche universal pair (historically FAIL outside lexicon)
  - unit-adjacent local encode without claiming native language final

Usage:
  PYTHONPATH=src:scripts python3 scripts/artcb_langage_ia_live_matrix.py
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
import urllib.parse
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

PROBES = {
    "fr": "Le serveur doit verifier la signature.",
    "en": "The server must verify the signature.",
    "es": "El servidor debe verificar la firma.",
}
UNIVERSAL = {
    "fr": "voiture",
    "en": "car",
    "es": "coche",
}
UNKNOWN = "zzzxqyt_artcb_nonce_316_not_a_word"


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


def _concept_ids(base: str, q: str) -> dict:
    url = f"{base.rstrip('/')}/api/v1/ir/concept-ids?q={urllib.parse.quote(q)}"
    headers = {"Accept": "application/json"}
    k = _key()
    if len(k) >= 16:
        headers["Authorization"] = f"Bearer {k}"
    t0 = time.perf_counter_ns()
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=45) as resp:
        body = json.loads(resp.read().decode())
    dur = time.perf_counter_ns() - t0
    ids = body.get("concept_ids") or body.get("ids") or body.get("concepts") or []
    if isinstance(ids, dict):
        ids = list(ids.values())
    ids = [str(x) for x in ids]
    return {"q": q, "ids": ids, "dur_ns": dur, "raw_keys": sorted(body.keys())[:20]}


def _local_encode(text: str) -> list[str]:
    from src.artcb.ir.encoder import IREncoder

    g = IREncoder().encode(text)
    ids: list[str] = []
    nodes = getattr(g, "nodes", None) or []
    for n in nodes:
        cid = getattr(n, "concept_id", None)
        if cid:
            ids.append(str(cid))
    if not ids and hasattr(g, "to_dict"):
        for n in (g.to_dict().get("nodes") or []):
            if isinstance(n, dict) and n.get("concept_id"):
                ids.append(str(n["concept_id"]))
    # Fall back to symbol ids when concept_id absent
    if not ids and hasattr(g, "to_dict"):
        for n in (g.to_dict().get("nodes") or []):
            if isinstance(n, dict) and n.get("id"):
                ids.append(str(n["id"]))
    return ids


def _overlap(sets: list[set[str]]) -> int:
    if not sets:
        return 0
    acc = sets[0]
    for s in sets[1:]:
        acc = acc & s
    return len(acc)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", action="append", default=[])
    ap.add_argument("--out", default="logs/316_langage_ia_matrix_latest.json")
    args = ap.parse_args()
    _dns_install()
    seeds = args.seed or [
        "https://artcb.me",
        "https://n2.artcb.me",
        "https://n3.artcb.me",
        "https://n4.artcb.me",
    ]
    t0 = time.time_ns()
    seed_results = {}
    for base in seeds:
        try:
            probe = {lang: _concept_ids(base, text) for lang, text in PROBES.items()}
            univ = {lang: _concept_ids(base, text) for lang, text in UNIVERSAL.items()}
            unk = _concept_ids(base, UNKNOWN)
            probe_sets = [set(v["ids"]) for v in probe.values()]
            univ_sets = [set(v["ids"]) for v in univ.values()]
            seed_results[base] = {
                "ok": True,
                "probe": probe,
                "probe_overlap": _overlap(probe_sets),
                "universal": univ,
                "universal_overlap": _overlap(univ_sets),
                "unknown": unk,
                "unknown_false_converge": bool(unk["ids"]) and _overlap([set(unk["ids"]), *univ_sets]) > 0,
            }
        except Exception as exc:  # noqa: BLE001
            seed_results[base] = {"ok": False, "error": f"{type(exc).__name__}:{str(exc)[:160]}"}

    local = {}
    try:
        local_probe = {lang: _local_encode(text) for lang, text in PROBES.items()}
        local_univ = {lang: _local_encode(text) for lang, text in UNIVERSAL.items()}
        local = {
            "ok": True,
            "probe": local_probe,
            "probe_overlap": _overlap([set(v) for v in local_probe.values()]),
            "universal": local_univ,
            "universal_overlap": _overlap([set(v) for v in local_univ.values()]),
        }
    except Exception as exc:  # noqa: BLE001
        local = {"ok": False, "error": f"{type(exc).__name__}:{exc}"}

    probe_pass = all(
        (r.get("ok") and int(r.get("probe_overlap") or 0) >= 1) for r in seed_results.values()
    ) if seed_results else False
    universal_pass = all(
        (r.get("ok") and int(r.get("universal_overlap") or 0) >= 1) for r in seed_results.values()
    ) if seed_results else False

    report = {
        "ts_ns": time.time_ns(),
        "dur_ns": time.time_ns() - t0,
        "certified_100": False,
        "langage_ia_final": False,
        "verdict": {
            "unit_tests_this_tour": "run_separately",
            "live_probe_fr_en_es_overlap": "PASS" if probe_pass else "FAIL",
            "live_universal_voiture_car_coche": "PASS" if universal_pass else "FAIL_OR_NOT_PROVEN",
            "agent_ab_without_text": "NOT_PROVEN",
            "ledger_anchor_x4": "NOT_PROVEN",
            "native_language_e2e_r253": "NOT_PROVEN",
        },
        "seeds": seed_results,
        "local_encoder": local,
        "sha256_report": "",
    }
    blob = json.dumps(report, sort_keys=True).encode()
    report["sha256_report"] = hashlib.sha256(blob).hexdigest()
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    # ns trace
    ns = ROOT / "data" / "trace" / "ns.jsonl"
    ns.parent.mkdir(parents=True, exist_ok=True)
    with ns.open("a", encoding="utf-8") as f:
        f.write(
            json.dumps(
                {
                    "kind": "langage_ia_live_matrix",
                    "ts_ns": report["ts_ns"],
                    "dur_ns": report["dur_ns"],
                    "probe": report["verdict"]["live_probe_fr_en_es_overlap"],
                    "universal": report["verdict"]["live_universal_voiture_car_coche"],
                }
            )
            + "\n"
        )
    print(json.dumps({"ok": True, "verdict": report["verdict"], "out": str(out)}, indent=2))
    return 0 if probe_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
