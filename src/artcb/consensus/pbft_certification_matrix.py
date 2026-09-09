"""R270 — PBFT certification matrix (no percentage-as-safety).

A missing critical live proof is NOT PROVEN. CERTIFIED_100 requires
zero FAIL, zero NOT_PROVEN, zero SKIPPED, and every required row executed.
"""

from __future__ import annotations

from typing import Any

from src.artcb.consensus.live_bft import LIVE_BFT_PROTOCOL
from src.artcb.consensus.pbft_finality import FIRST_LIVE_CERTIFIED_SEQ, PBFT_FINALITY_PROTOCOL
from src.artcb.consensus.pbft_view import PBFT_VIEW_PROTOCOL
from src.artcb.node_registry import official_pbft_n_f_q, official_pbft_replica_ids

# ~~2026-09-08 original — conservé 2026-09-10T23:12:00Z~~
# N, F, Q = 4, 1, 3
# Barré 2026-09-09T21:55:00Z : lu depuis official_pbft_n_f_q() (N adaptatif).
N, F, Q = official_pbft_n_f_q()

# Critical rows that block CERTIFIED_100 if not live-proven on the SHA under test.
CRITICAL_IDS = (
    "PBFT-S01",
    "PBFT-S02",
    "PBFT-L01",
    "PBFT-F01",
    "PBFT-F02",
    "PBFT-F03",
    "PBFT-B01",
    "PBFT-B02",
    "PBFT-B03",
    "PBFT-R01",
    "PBFT-R02",
    "PBFT-N01",
    "PBFT-N02",
    "PBFT-N03",
    "PBFT-N04",
    "PBFT-Q01",
)

REQUIRED: tuple[dict[str, str], ...] = (
    {"id": "PBFT-P00", "property": "Freeze SHA/N/F/Q/genesis/view ×4", "min_level": "L4"},
    {"id": "PBFT-P01", "property": "Same protocol version ×4", "min_level": "L4"},
    {"id": "PBFT-S01", "property": "Safety: no two incompatible finalized values", "min_level": "L6"},
    {"id": "PBFT-S02", "property": "Finality irreversible without explicit procedure", "min_level": "L5"},
    {"id": "PBFT-S03", "property": "seq=index digest=hash binding", "min_level": "L4"},
    {"id": "PBFT-S04", "property": "Certificate ≠ block rejected", "min_level": "L4"},
    {"id": "PBFT-S05", "property": "Duplicate replica_id does not count as Q", "min_level": "L1"},
    {"id": "PBFT-L01", "property": "Liveness: honest Q progresses", "min_level": "L4"},
    {"id": "PBFT-L02", "property": "Liveness after leader timeout/view-change", "min_level": "L5"},
    {"id": "PBFT-F01", "property": "Primary process down, no new block (stay)", "min_level": "L5"},
    {"id": "PBFT-F02", "property": "Primary down + new certified block on majority", "min_level": "L5"},
    {"id": "PBFT-F03", "property": "Primary rejoin after majority progressed", "min_level": "L5"},
    {"id": "PBFT-F04", "property": "Replica crash/restart keeps public tip", "min_level": "L5"},
    {"id": "PBFT-B01", "property": "Byzantine primary dual propose / equivocation", "min_level": "L6"},
    {"id": "PBFT-B02", "property": "Byzantine PREPARE X/Y same seq", "min_level": "L6"},
    {"id": "PBFT-B03", "property": "Forged signatures / unknown key rejected", "min_level": "L6"},
    {"id": "PBFT-B04", "property": "Conflicting votes from one replica", "min_level": "L6"},
    {"id": "PBFT-B05", "property": "Prepared certificate required in VIEW-CHANGE", "min_level": "L4"},
    {"id": "PBFT-R01", "property": "Crash recovery persistence", "min_level": "L5"},
    {"id": "PBFT-R02", "property": "Protocol catch-up of lagging replica (not jsonl-append)", "min_level": "L5"},
    {"id": "PBFT-R03", "property": "Truncated PBFT state does not invent certificates", "min_level": "L5"},
    {"id": "PBFT-N01", "property": "Real 2–2 partition: neither side finalizes", "min_level": "L5"},
    {"id": "PBFT-N02", "property": "Heal after partition → convergence", "min_level": "L5"},
    {"id": "PBFT-N03", "property": "Asymmetric partition", "min_level": "L5"},
    {"id": "PBFT-N04", "property": "Packet loss sweep 1–50%", "min_level": "L5"},
    {"id": "PBFT-N05", "property": "Injected delay / jitter", "min_level": "L5"},
    {"id": "PBFT-N06", "property": "Message reordering middlebox", "min_level": "L5"},
    {"id": "PBFT-N07", "property": "Duplication 1x–1000x same message", "min_level": "L5"},
    {"id": "PBFT-N08", "property": "Combined loss+delay+reorder", "min_level": "L5"},
    {"id": "PBFT-Q01", "property": "Q<3 cannot produce valid finality", "min_level": "L4"},
    {"id": "PBFT-Q02", "property": "F=2 expected failure vs spec (not a protocol violation)", "min_level": "L4"},
    {"id": "PBFT-V01", "property": "VIEW-CHANGE Q=3 + NEW-VIEW", "min_level": "L5"},
    {"id": "PBFT-V02", "property": "Replay wrong-view rejected", "min_level": "L4"},
    {"id": "PBFT-C01", "property": "Byzantine + crash combined", "min_level": "L6"},
    {"id": "PBFT-C02", "property": "Crash + partition + delayed message", "min_level": "L6"},
    {"id": "PBFT-C03", "property": "Clock skew consensus independence", "min_level": "L5"},
    {"id": "PBFT-C04", "property": "Long-run thousands of blocks", "min_level": "L5"},
    {"id": "PBFT-C05", "property": "Membership change validators", "min_level": "L5"},
    {"id": "PBFT-A01", "property": "Agent identity conflict through consensus", "min_level": "L4"},
    {"id": "PBFT-A02", "property": "Agent idempotency conflict + public PBFT replicate", "min_level": "L4"},
    {"id": "PBFT-X01", "property": "BFT_SETTLEMENT (188) independent of block PBFT", "min_level": "L4"},
    {"id": "PBFT-X02", "property": "BFT_BLOCK_CONSENSUS exclusive public append", "min_level": "L4"},
    {"id": "PBFT-X03", "property": "All ARTCB product features via live consensus", "min_level": "L4"},
)


def empty_row(spec: dict[str, str]) -> dict[str, Any]:
    return {
        "id": spec["id"],
        "property": spec["property"],
        "min_level": spec["min_level"],
        "critical": spec["id"] in CRITICAL_IDS,
        "local": "NOT_PROVEN",
        "multi_node": "NOT_PROVEN",
        "live_wan": "NOT_EXECUTED",
        "fault_injection": "NOT_EXECUTED",
        "byzantine": "NOT_EXECUTED",
        "level": "L0",
        "result": "NOT_PROVEN",
        "proof": "",
        "verdict": "NOT_PROVEN",
    }


def new_matrix() -> dict[str, Any]:
    rows = [empty_row(s) for s in REQUIRED]
    n, f, q = official_pbft_n_f_q()
    return {
        "protocol": "270-pbft-certification-matrix",
        "n": n,
        "f": f,
        "q": q,
        "replicas": list(official_pbft_replica_ids()),
        "settlement_protocol": LIVE_BFT_PROTOCOL,
        "view_protocol": PBFT_VIEW_PROTOCOL,
        "block_finality_protocol": PBFT_FINALITY_PROTOCOL,
        "exclusive_public_from_seq": FIRST_LIVE_CERTIFIED_SEQ,
        "hpc": False,
        "wipe": False,
        "rows": rows,
        "totals": tally(rows),
        "certified_100": False,
        "global_verdict": "NOT_PROVEN",
        "bft_settlement": "NOT_PROVEN",
        "bft_block_consensus": "NOT_PROVEN",
    }


def tally(rows: list[dict[str, Any]]) -> dict[str, int]:
    keys = ("PASS", "FAIL", "NOT_PROVEN", "NOT_EXECUTED", "SKIPPED")
    counts = {k: 0 for k in keys}
    for row in rows:
        verdict = str(row.get("verdict") or "NOT_PROVEN")
        counts[verdict] = counts.get(verdict, 0) + 1
    counts["TOTAL_REQUIRED"] = len(rows)
    counts["TOTAL_EXECUTED"] = sum(1 for r in rows if r.get("verdict") in ("PASS", "FAIL"))
    return counts


def apply_result(matrix: dict[str, Any], row_id: str, **fields: Any) -> None:
    for row in matrix["rows"]:
        if row["id"] == row_id:
            row.update(fields)
            return
    raise KeyError(row_id)


def finalize(matrix: dict[str, Any]) -> dict[str, Any]:
    matrix["totals"] = tally(matrix["rows"])
    t = matrix["totals"]
    critical_ok = all(
        r.get("verdict") == "PASS" for r in matrix["rows"] if r.get("critical")
    )
    matrix["certified_100"] = bool(
        t["TOTAL_REQUIRED"] == t["TOTAL_EXECUTED"]
        and t["FAIL"] == 0
        and t.get("NOT_PROVEN", 0) == 0
        and t.get("NOT_EXECUTED", 0) == 0
        and t.get("SKIPPED", 0) == 0
        and critical_ok
    )
    if matrix["certified_100"]:
        matrix["global_verdict"] = "CERTIFIED_100"
    elif t["FAIL"] > 0:
        matrix["global_verdict"] = "NOT_CERTIFIED"
    elif any(r.get("critical") and r.get("verdict") == "PASS" for r in matrix["rows"]):
        matrix["global_verdict"] = "PARTIALLY_VERIFIED"
    else:
        matrix["global_verdict"] = "NOT_PROVEN"
    by_id = {r["id"]: r.get("verdict") for r in matrix["rows"]}
    matrix["bft_settlement"] = by_id.get("PBFT-X01") or "NOT_PROVEN"
    x02 = by_id.get("PBFT-X02") or "NOT_PROVEN"
    matrix["bft_block_consensus"] = (
        "PARTIAL" if x02 == "PASS" and not matrix["certified_100"] else x02
    )
    return matrix


def independent_safety(snapshots: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Compare four node snapshots. Divergence of public tip is a safety alarm."""
    ids = list(official_pbft_replica_ids())
    heights = {(snapshots.get(n) or {}).get("height") for n in ids}
    hashes = {(snapshots.get(n) or {}).get("last_hash") for n in ids}
    views = {(snapshots.get(n) or {}).get("view") for n in ids}
    shas = {(snapshots.get(n) or {}).get("git_sha") for n in ids}
    return {
        "height_unique": len(heights),
        "hash_unique": len(hashes),
        "view_unique": len(views),
        "sha_unique": len(shas),
        "converged": len(heights) == 1 and len(hashes) == 1,
        "heights": {n: (snapshots.get(n) or {}).get("height") for n in ids},
        "hashes": {n: (snapshots.get(n) or {}).get("last_hash") for n in ids},
        "views": {n: (snapshots.get(n) or {}).get("view") for n in ids},
        "shas": {n: (snapshots.get(n) or {}).get("git_sha") for n in ids},
    }
