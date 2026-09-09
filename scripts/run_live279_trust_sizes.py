#!/usr/bin/env python3
"""R279 live — platform trust levels + real blocks.jsonl sizes.

Does not recast CLOUD_ATTESTED as TPM_ATTESTED.
Does not recast NOT_PROVEN as PASS.
Does not wipe the book. Does not claim CERTIFIED_100.
Does not invent per-block sizes: reads the live file.
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for extra in (ROOT, ROOT / "src", ROOT / "scripts"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

import run_live265_pbft_e2e as l265  # noqa: E402
from artcb.consensus.campaign_artifacts import write_campaign  # noqa: E402
from artcb.node_registry import OFFICIAL_COMPUTE_NODE_IDS  # noqa: E402

HTTP = l265.HTTP
BOOK = "/home/ubuntu/artcb/data/chain/blocks.jsonl"

AUDIT_PY = r"""
import json, statistics
from pathlib import Path
p = Path("/home/ubuntu/artcb/data/chain/blocks.jsonl")
raw = p.read_bytes()
file_bytes = len(raw)
lines = raw.splitlines()
rows = []
claimed_mismatch = 0
missing_claimed = 0
tx = jobs = proofs = 0
for i, line in enumerate(lines):
    obj = json.loads(line)
    line_bytes = len(line)
    claimed = obj.get("block_size_bytes")
    if claimed is None:
        missing_claimed += 1
        match = None
    else:
        match = int(claimed) == line_bytes
        if not match:
            claimed_mismatch += 1
    ts = str(obj.get("timestamp") or "")
    contrib = obj.get("contributors") or []
    symbols = obj.get("public_symbols") or {}
    payload = dict(obj)
    payload.pop("block_size_bytes", None)
    payload_bytes = len(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode())
    rows.append({
        "index": obj.get("index", i),
        "timestamp": ts,
        "line_bytes": line_bytes,
        "file_record_bytes": line_bytes + 1,
        "payload_bytes": payload_bytes,
        "claimed_block_size_bytes": claimed,
        "claimed_matches_line": match,
        "contributors": len(contrib) if isinstance(contrib, list) else 0,
        "public_symbol_keys": len(symbols) if isinstance(symbols, dict) else 0,
        "visibility": obj.get("visibility"),
        "hash_prefix": str(obj.get("hash") or "")[:16],
        "prev_prefix": str(obj.get("prev_hash") or "")[:16],
    })
sizes = [r["line_bytes"] for r in rows]
def pct(xs, p):
    if not xs:
        return 0
    xs = sorted(xs)
    k = (len(xs)-1) * p / 100
    lo, hi = int(k), min(int(k)+1, len(xs)-1)
    return xs[lo] + (k-lo)*(xs[hi]-xs[lo])
# inter-block dt if timestamps parse
dts = []
from datetime import datetime
for a, b in zip(rows, rows[1:]):
    try:
        ta = datetime.fromisoformat(a["timestamp"].replace("Z","+00:00"))
        tb = datetime.fromisoformat(b["timestamp"].replace("Z","+00:00"))
        dts.append((tb-ta).total_seconds())
    except Exception:
        pass
out = {
    "path": str(p),
    "file_bytes": file_bytes,
    "line_count": len(lines),
    "first_index": rows[0]["index"] if rows else None,
    "last_index": rows[-1]["index"] if rows else None,
    "claimed_mismatch": claimed_mismatch,
    "missing_claimed": missing_claimed,
    "line_bytes": {
        "min": min(sizes) if sizes else 0,
        "max": max(sizes) if sizes else 0,
        "avg": int(sum(sizes)/len(sizes)) if sizes else 0,
        "p50": int(pct(sizes, 50)),
        "p90": int(pct(sizes, 90)),
        "p95": int(pct(sizes, 95)),
        "p99": int(pct(sizes, 99)),
        "stdev": int(statistics.pstdev(sizes)) if len(sizes) > 1 else 0,
        "sum": sum(sizes),
        "sum_bits": sum(sizes)*8,
    },
    "dt_s": {
        "count": len(dts),
        "min": min(dts) if dts else None,
        "max": max(dts) if dts else None,
        "avg": (sum(dts)/len(dts)) if dts else None,
        "p50": pct(dts, 50) if dts else None,
    },
    "head": rows[:3],
    "tail": rows[-3:],
    "largest": sorted(rows, key=lambda r: r["line_bytes"], reverse=True)[:5],
    "smallest": sorted(rows, key=lambda r: r["line_bytes"])[:5],
    "note": "line_bytes = UTF-8 JSON without newline. file_record_bytes includes newline. Not wire_bytes. Bodies omitted.",
}
print(json.dumps(out, separators=(",", ":")))
"""


def _row(status: str, **extra) -> dict:
    return {"status": status, "certified_100": False, **extra}


def _platform(nid: str) -> dict:
    return l265._http("GET", f"{HTTP[nid]}/api/v1/consensus/platform-attest", timeout=25)


def _ident(nid: str) -> dict:
    return l265._http("GET", f"{HTTP[nid]}/api/v1/consensus/replica-identity", timeout=25)


def _block_sizes(nid: str) -> dict:
    return l265._http("GET", f"{HTTP[nid]}/api/v1/chain/block-sizes?top_n=5", timeout=40, auth=True)


def _audit_book(nid: str) -> dict:
    got = l265._ssh(nid, "python3 -", timeout=120, stdin=AUDIT_PY)
    text = (got.get("stdout") or "").strip()
    try:
        return {"ok": got.get("returncode") == 0, "audit": json.loads(text), "stderr": (got.get("stderr") or "")[:200]}
    except json.JSONDecodeError:
        return {"ok": False, "raw": text[-500:], "stderr": (got.get("stderr") or "")[:300]}


def main() -> int:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    health = {nid: l265._http("GET", f"{HTTP[nid]}/health", timeout=12) for nid in OFFICIAL_COMPUTE_NODE_IDS}
    shas = {nid: (health[nid].get("git_sha") or "")[:40] for nid in OFFICIAL_COMPUTE_NODE_IDS}
    platforms = {nid: _platform(nid) for nid in OFFICIAL_COMPUTE_NODE_IDS}
    idents = {nid: _ident(nid) for nid in OFFICIAL_COMPUTE_NODE_IDS}
    sizes_api = _block_sizes("ovh-node-1")
    book = _audit_book("ovh-node-1")

    recast = False
    cloud_ok = 0
    tpm_hw_available = 0
    mismatches = 0
    compact = {}
    for nid in OFFICIAL_COMPUTE_NODE_IDS:
        p = platforms[nid]
        overall = p.get("overall_platform_trust")
        hw = p.get("hardware_tpm_attestation")
        plat = p.get("platform_identity_attestation")
        if overall == "TPM_ATTESTED" and hw == "NOT_AVAILABLE":
            recast = True
        if p.get("certified_hardware_identity") and hw != "TPM_HARDWARE_ATTESTED":
            recast = True
        if overall == "CLOUD_ATTESTED":
            cloud_ok += 1
        if hw not in {"NOT_AVAILABLE", None}:
            tpm_hw_available += 1
        bind = p.get("binding") if isinstance(p.get("binding"), dict) else {}
        if bind.get("identity_mismatch"):
            mismatches += 1
        compact[nid] = {
            "class": p.get("platform_class"),
            "trust_level": p.get("trust_level"),
            "overall": overall,
            "hardware_tpm": hw,
            "platform_identity": plat,
            "certified_hardware": p.get("certified_hardware_identity"),
            "crypto_verified": p.get("attestation_crypto_verified"),
            "instance_id": (p.get("identity") or {}).get("provider", {}).get("instance_id")
            if isinstance(p.get("identity"), dict)
            else None,
            "binding_verified": bind.get("binding_verified"),
            "identity_mismatch": bind.get("identity_mismatch"),
            "sha": shas[nid],
        }

    audit = book.get("audit") if isinstance(book.get("audit"), dict) else {}
    results = {
        "platform_levels": _row(
            "PASS" if cloud_ok == 4 and tpm_hw_available == 0 and not recast else "FAIL",
            nodes=compact,
            recast_cloud_as_tpm=recast,
            note="four VMs should be CLOUD_ATTESTED / hardware TPM NOT_AVAILABLE — never TPM_ATTESTED",
        ),
        "node_platform_binding": _row(
            "PASS" if mismatches == 0 and all(c.get("binding_verified") for c in compact.values()) else "FAIL",
            mismatches=mismatches,
            nodes={nid: compact[nid] for nid in compact},
        ),
        "block_size_field_historical": _row(
            "MEASURED",
            claimed_mismatch=audit.get("claimed_mismatch"),
            missing_claimed=audit.get("missing_claimed"),
            line_count=audit.get("line_count"),
            file_bytes=audit.get("file_bytes"),
            stats=audit.get("line_bytes"),
            note="old engraved field may not equal line_bytes; that is the R279 bug being measured",
        ),
        "book_audit": _row("PASS" if book.get("ok") else "FAIL", **{k: audit.get(k) for k in ("line_count", "first_index", "last_index", "dt_s", "head", "tail", "largest", "smallest")}),
        "api_block_sizes": _row("MEASURED", distribution=(sizes_api.get("distribution") if isinstance(sizes_api, dict) else None)),
        "tpm_quote": _row("NOT_PROVEN", note="/dev/tpm0 absent on these VMs; quote not collected"),
        "c04_thousands": _row("NOT_PROVEN"),
        "n04_50": _row("FAIL", note="kept from R272/R278 — not recast"),
        "certified_100": False,
        "production_ready": False,
    }

    artefact = write_campaign(
        ROOT,
        campaign_id=f"279_{stamp}",
        code_sha=shas.get("ovh-node-1", ""),
        runner="scripts/run_live279_trust_sizes.py",
        environment={"shas": shas},
        nodes={nid: {"health": health[nid], "platform": compact[nid]} for nid in OFFICIAL_COMPUTE_NODE_IDS},
        results=results,
        extra_manifest={"book_audit": audit, "api_block_sizes": sizes_api if isinstance(sizes_api, dict) else {}},
    )
    out = {
        "stamp": stamp,
        "shas": shas,
        "results": {k: (v.get("status") if isinstance(v, dict) else v) for k, v in results.items()},
        "compact": compact,
        "book": {k: audit.get(k) for k in ("line_count", "file_bytes", "claimed_mismatch", "line_bytes", "dt_s")},
        "artefact": str(artefact) if artefact else None,
        "certified_100": False,
    }
    dest = ROOT / "logs" / f"279_trust_sizes_{stamp}.json"
    dest.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
