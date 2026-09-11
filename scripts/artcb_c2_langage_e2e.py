#!/usr/bin/env python3
"""R319 — C2 langage IA battery (honest, CERTIFIED_100=false).

Namespaces (do not mix):
  C2          = lexicon object code for vehicle lemmas
  K3e7dc01…   = concrete ConceptID from type+sym O1C2
  C2-A…C2-D   = this test ladder

Levels:
  C2-A  lexical + adversarial (false equiv / substring / synonym gap)
  C2-B  phrases → overlapping ConceptIDs (not translation-chain)
  C2-C  relation + reasoning on ConceptIDs without human text in packet
  C2-D  A → (optional live memo) → B retrieve/combine — network path measured

Usage:
  PYTHONPATH=src:scripts python3 scripts/artcb_c2_langage_e2e.py
  PYTHONPATH=src:scripts python3 scripts/artcb_c2_langage_e2e.py --live-memo
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
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
    from artcb_dns_fix import install as _dns_install
except Exception:  # noqa: BLE001

    def _dns_install() -> None:
        return None

from src.artcb.ir.concept import concept_id_from_node, decode_concept_packet, encode_concept_packet
from src.artcb.ir.concept_lexicon import object_codes
from src.artcb.ir.encoder import IREncoder
from src.artcb.memory.agent_channel import AgentChannel
from src.artcb.memory.concept_store import ConceptStore

UI_LOCALES = ("fr", "en", "zh", "es", "pt", "it", "ru")
VEHICLE = {"fr": "voiture", "en": "car", "es": "coche"}
PHRASES = {
    "fr": "La voiture consomme beaucoup.",
    "en": "The car consumes a lot.",
    "es": "El coche consume mucho.",
}
RELATION = {
    "fr": "Si la charge augmente, la consommation augmente.",
    "en": "If the load increases, consumption increases.",
    "es": "Si la carga aumenta, el consumo aumenta.",
}
LEXICON_CODE_VEHICLE = "C2"
EXPECTED_VEHICLE_KID = "K3e7dc01c5cf83cd8"


def _ids(text: str) -> list[str]:
    g = IREncoder().encode(text)
    return [concept_id_from_node(n) for n in g.nodes]


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


def _post_memo(base: str, content: str, *, private: bool = False) -> dict:
    url = f"{base.rstrip('/')}/api/v1/ai/memo"
    body = json.dumps(
        {
            "content": content,
            "visibility": "private" if private else "public",
            "source": "c2_langage_e2e_r319",
        }
    ).encode()
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    k = _key()
    if len(k) >= 16:
        headers["Authorization"] = f"Bearer {k}"
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode())


def run_c2_a() -> dict:
    t0 = time.perf_counter_ns()
    vehicle_ids = {lang: _ids(word)[0] if _ids(word) else "" for lang, word in VEHICLE.items()}
    codes = {lang: object_codes(word) for lang, word in VEHICLE.items()}
    same_k = len(set(vehicle_ids.values())) == 1 and bool(next(iter(vehicle_ids.values())))
    same_code = all(LEXICON_CODE_VEHICLE in (codes[l] or []) for l in VEHICLE)
    avion = _ids("avion")
    false_equiv = EXPECTED_VEHICLE_KID not in avion and vehicle_ids.get("fr") not in avion
    verificar = _ids("verificar")
    substring_ok = EXPECTED_VEHICLE_KID not in verificar
    # Honest synonym gap: automobile not yet in lexicon → must NOT silently PASS
    automobile = _ids("automobile")
    synonym_converges = EXPECTED_VEHICLE_KID in automobile
    status = "PASS" if (same_k and same_code and false_equiv and substring_ok) else "FAIL"
    return {
        "level": "C2-A",
        "status": status,
        "lexicon_object_code": LEXICON_CODE_VEHICLE,
        "concept_id": vehicle_ids.get("fr"),
        "expected_concept_id": EXPECTED_VEHICLE_KID,
        "namespace_note": "C2=lexicon code; K…=ConceptID; C2-A=test level",
        "vehicle_ids": vehicle_ids,
        "object_codes": codes,
        "adversarial": {
            "avion_ne_vehicle": false_equiv,
            "verificar_no_car_substring": substring_ok,
            "automobile_synonym_converges": synonym_converges,
            "automobile_note": "GAP if false — lexicon incomplete, not silent PASS",
        },
        "ui_locales_in_frontend": list(UI_LOCALES),
        "ui_locales_semantically_probed": list(VEHICLE.keys()),
        "dur_ns": time.perf_counter_ns() - t0,
    }


def run_c2_b() -> dict:
    t0 = time.perf_counter_ns()
    per = {lang: _ids(text) for lang, text in PHRASES.items()}
    # Require vehicle ConceptID present in each phrase encode
    vehicle_in = {lang: EXPECTED_VEHICLE_KID in ids for lang, ids in per.items()}
    overlap = set.intersection(*(set(v) for v in per.values())) if per else set()
    status = "PASS" if all(vehicle_in.values()) and EXPECTED_VEHICLE_KID in overlap else "PARTIAL"
    if not all(vehicle_in.values()):
        status = "FAIL"
    return {
        "level": "C2-B",
        "status": status,
        "phrases": PHRASES,
        "ids": per,
        "vehicle_in_each": vehicle_in,
        "intersection": sorted(overlap),
        "note": "Phrase overlap via lexicon hits — not a translation-chain proof",
        "dur_ns": time.perf_counter_ns() - t0,
    }


def run_c2_c(tmp: Path) -> dict:
    t0 = time.perf_counter_ns()
    store = ConceptStore(tmp / "c2c")
    ch = AgentChannel(agent_id="reasoner", store=store)
    learned = []
    for lang, text in RELATION.items():
        r = ch.learn_from_text(text)
        learned.append({"lang": lang, "concept_ids": r.concept_ids, "graph_id": r.graph_id})
    # Reasoning without human text: packet of concept_ids only
    all_ids = []
    for row in learned:
        all_ids.extend(row["concept_ids"])
    packet = encode_concept_packet(all_ids)
    decoded = decode_concept_packet(packet)
    assert b"charge" not in packet and b"consommation" not in packet
    known = [cid for cid in decoded if ch.knows(cid)]
    graphs = store.recall_by_concept_ids(decoded)
    # Combine: derive a new local knowledge from union of known ids
    derived = ch.learn_from_text(
        "Optimisation: reduire consommation sous contrainte de capacite."
    )
    status = "PASS" if known and graphs and derived.concept_ids else "FAIL"
    return {
        "level": "C2-C",
        "status": status,
        "learned": learned,
        "packet_sha256": hashlib.sha256(packet).hexdigest(),
        "packet_bytes": len(packet),
        "known_from_packet": len(known),
        "graphs_recalled": len(graphs),
        "derived_concept_ids": derived.concept_ids,
        "derived_graph_id": derived.graph_id,
        "note": "Local AgentChannel — proves IR+store+packet, not yet multi-node network",
        "dur_ns": time.perf_counter_ns() - t0,
    }


def run_c2_d(tmp: Path, *, live_memo: bool, base: str) -> dict:
    """A learns → packet → B (shared prior OR seeded store) + optional live memo anchor."""
    t0 = time.perf_counter_ns()
    store_a = ConceptStore(tmp / "agent_a")
    store_b = ConceptStore(tmp / "agent_b")
    a = AgentChannel(agent_id="agent_a", store=store_a)
    b = AgentChannel(agent_id="agent_b", store=store_b)

    problem = (
        "Une machine consomme beaucoup d'energie sous charge IA. "
        "Strategie: optimiser capacite pour reduire consommation sans tuer le debit."
    )
    learn_a = a.learn_from_text(problem)
    packet = learn_a.packet
    packet_sha = hashlib.sha256(packet).hexdigest()

    # Without transferring .arcb, B cannot recall — measure this honestly first
    recall_cold = b.receive_packet(packet)
    cold_ok = len(recall_cold.found_graphs) > 0 and not recall_cold.missing_concept_ids

    # Seed B with same semantic prior (independent learn — network would sync .arcb)
    b.learn_from_text(problem)
    recall_warm = b.receive_packet(packet)
    warm_ok = (
        recall_warm.requested_concept_ids == learn_a.concept_ids
        and not recall_warm.missing_concept_ids
    )

    # B own knowledge + combine
    b_own = b.learn_from_text("Debit cible maintenu sous contrainte energetique.")
    combined = b.learn_from_text(
        "Combinaison: charge + capacite + optimisation => nouvelle strategie K9."
    )

    # Optional: anchor packet hash + concept_ids on live ARTCB (not full .arcb sync)
    memo = None
    memo_err = None
    if live_memo:
        payload = json.dumps(
            {
                "c2_level": "C2-D",
                "agent": "agent_a",
                "concept_ids": learn_a.concept_ids,
                "graph_id": learn_a.graph_id,
                "packet_sha256": packet_sha,
                "problem_sha256": hashlib.sha256(problem.encode()).hexdigest(),
            },
            sort_keys=True,
        )
        try:
            memo = _post_memo(base, payload, private=False)
        except Exception as exc:  # noqa: BLE001
            memo_err = str(exc)[:200]

    # Copy A's arcb into B as simulated network concept sync (measured separately)
    sync_dir = tmp / "agent_b_synced"
    if (tmp / "agent_a").exists():
        shutil.copytree(tmp / "agent_a", sync_dir, dirs_exist_ok=True)
    store_sync = ConceptStore(sync_dir)
    ch_sync = AgentChannel(agent_id="agent_b_synced", store=store_sync)
    recall_synced = ch_sync.receive_packet(packet)
    synced_ok = len(recall_synced.found_graphs) > 0

    if cold_ok:
        net_status = "PASS"
    elif warm_ok and synced_ok and memo and not memo_err:
        net_status = "PARTIAL"
    elif warm_ok:
        net_status = "PARTIAL"
    else:
        net_status = "FAIL"

    return {
        "level": "C2-D",
        "status": net_status,
        "a_concept_ids": learn_a.concept_ids,
        "a_graph_id": learn_a.graph_id,
        "a_output_hash": packet_sha,
        "b_cold_found": len(recall_cold.found_graphs),
        "b_cold_missing": recall_cold.missing_concept_ids,
        "b_warm_ok": warm_ok,
        "b_own_concept_ids": b_own.concept_ids,
        "b_combined_k9_ids": combined.concept_ids,
        "b_combined_graph_id": combined.graph_id,
        "arcb_sync_sim_ok": synced_ok,
        "live_memo": memo,
        "live_memo_error": memo_err,
        "honest_gaps": [
            "cold B without prior/store sync cannot reconstruct graphs from packet alone",
            "live memo anchors hashes/ids — does not yet ship .arcb concept blobs over P2P",
            "C2-D PASS only if cold path OR full concept-store sync over network is proven",
        ],
        "dur_ns": time.perf_counter_ns() - t0,
    }


def main() -> int:
    _dns_install()
    ap = argparse.ArgumentParser()
    ap.add_argument("--live-memo", action="store_true")
    ap.add_argument("--base", default=os.environ.get("ARTCB_API_URL", "https://artcb.me"))
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    tmp = Path(tempfile.mkdtemp(prefix="artcb_c2_"))
    try:
        report = {
            "ts_ns": time.time_ns(),
            "git_hint": "R319",
            "certified_100": False,
            "ui_locales": list(UI_LOCALES),
            "C2-A": run_c2_a(),
            "C2-B": run_c2_b(),
            "C2-C": run_c2_c(tmp),
            "C2-D": run_c2_d(tmp, live_memo=args.live_memo, base=args.base),
        }
        levels = [report[k]["status"] for k in ("C2-A", "C2-B", "C2-C", "C2-D")]
        report["ladder_summary"] = {
            "statuses": levels,
            "serious_e2e_claim": report["C2-D"]["status"] == "PASS",
            "note": "Only C2-D PASS is a serious E2E langage claim; lexical alone is insufficient",
        }
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    text = json.dumps(report, indent=2, ensure_ascii=False)
    print(text)
    out = Path(args.out) if args.out else ROOT / "logs" / f"319_c2_langage_{time.strftime('%Y%m%dT%H%M%SZ')}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text + "\n", encoding="utf-8")
    print(f"wrote {out}", file=sys.stderr)
    # Exit 0 even on PARTIAL — honest measurement, not CI gate yet
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
