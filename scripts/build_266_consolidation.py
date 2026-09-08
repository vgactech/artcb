#!/usr/bin/env python3
"""Consolidate 266 runner JSON: first FAIL vs retry PASS vs origin/main SHA."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load(name: str) -> dict:
    p = ROOT / "logs" / name
    if not p.is_file():
        return {"missing": True, "path": str(p)}
    return json.loads(p.read_text(encoding="utf-8"))


def main() -> int:
    first = _load("266_pbft_cert_20260908T155024Z.json")
    v01 = _load("266_v01_retry.json")
    v02 = _load("266_v02_retry.json")
    latest = _load("266_pbft_cert_latest.json")
    ingest267 = _load("267_ingest_20260908T162514Z.json")
    recert = _load("267_ingest_20260908T165526Z.json")
    want_main = ""
    try:
        import subprocess

        want_main = subprocess.check_output(["git", "rev-parse", "origin/main"], cwd=ROOT, text=True).strip()
    except Exception as exc:  # noqa: BLE001
        want_main = f"error:{type(exc).__name__}"
    sha_tested = "78cd8d61e08c1dee99d83bf24ae7aba0bdf3f007"
    sha_first = first.get("git_sha_agent") or (first.get("before") or {}).get("ovh-node-1", {}).get("git_sha")
    tests = (latest.get("tests") if isinstance(latest, dict) else None) or {}
    merged = {k: (v.get("result") if isinstance(v, dict) else v) for k, v in tests.items()} if isinstance(tests, dict) else {}
    if isinstance(v01, dict) and v01.get("V01"):
        merged["V01"] = v01.get("V01")
    if isinstance(v02, dict) and v02.get("V02"):
        merged["V02"] = v02.get("V02")
    after_recert = recert.get("after_sha") if isinstance(recert, dict) else None
    payload = {
        "stamp": datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ"),
        "origin_main": want_main,
        "sha_tested_266": sha_tested,
        "sha_first_runner": sha_first,
        "sha_equal_origin_main_now": want_main == sha_tested,
        "note": (
            "266 live V-01…V-07 measured on 78cd8d6. origin/main later moved "
            "(docs 230b8eb then ingest 267). First runner JSON has "
            "PBFT_LIVE_E2E_PASS=false; retries flipped V01/V02 to PASS on the same SHA. "
            "Do not read the first runner file as the final verdict."
        ),
        "first_run": {
            "file": "logs/266_pbft_cert_20260908T155024Z.json",
            "PBFT_LIVE_E2E_PASS": first.get("PBFT_LIVE_E2E_PASS"),
            "reason": "V01 client_request_failed (memo not on primary); V02 python3 without nacl/passphrase",
        },
        "retry": {
            "V01": v01.get("V01") if isinstance(v01, dict) else None,
            "V01_file": "logs/266_v01_retry.json",
            "V01_seq": v01.get("seq") if isinstance(v01, dict) else None,
            "V01_digest": v01.get("digest") if isinstance(v01, dict) else None,
            "V02": v02.get("V02") if isinstance(v02, dict) else None,
            "V02_file": "logs/266_v02_retry.json",
            "V02_dual_finality": v02.get("dual_finality") if isinstance(v02, dict) else None,
        },
        "final_tests": merged,
        "latest_tests_first_runner_only": {k: (v.get("result") if isinstance(v, dict) else v) for k, v in tests.items()} if isinstance(tests, dict) else {},
        "ingest_267_first_live": {
            "file": "logs/267_ingest_20260908T162514Z.json",
            "after_sha": ingest267.get("after_sha") if isinstance(ingest267, dict) else None,
            "block_index": (ingest267.get("ingest") or {}).get("ingest_block_index") if isinstance(ingest267, dict) else None,
        },
        "recert_b66f51a9": {
            "file": "logs/267_ingest_20260908T165526Z.json",
            "after_sha": after_recert,
            "block_index": (recert.get("ingest") or {}).get("ingest_block_index") if isinstance(recert, dict) else None,
            "block_hash": (recert.get("ingest") or {}).get("ingest_block_hash") if isinstance(recert, dict) else None,
            "cert_x4": recert.get("cert_x4") if isinstance(recert, dict) else None,
        },
        "not_100_percent_pbft": True,
        "p8_prepared_vc": "see R268 live",
    }
    dest = ROOT / "logs" / "266_pbft_cert_consolidated.json"
    dest.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps({"wrote": str(dest), "origin_main": want_main[:12]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
