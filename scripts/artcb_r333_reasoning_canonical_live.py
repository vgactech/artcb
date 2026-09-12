#!/usr/bin/env python3
"""R333 — live probe: canonical ReasoningID + multilingual views + ledger anchor.

CERTIFIED_100 stays false. Does not claim private model CoT equality.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

try:
    from artcb_dns_fix import install as _dns
except Exception:  # noqa: BLE001

    def _dns() -> None:
        return None

from src.artcb.reasoning.canonical import canonicalize_text, human_view, semantic_identity_report


TEXTS = {
    "fr": "La voiture consomme beaucoup d'énergie.",
    "en": "The car consumes a lot of energy.",
    "zh": "汽车消耗大量能源。",
    "es": "El coche consume mucha energía.",
    "ru": "Автомобиль потребляет много энергии.",
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


def main() -> int:
    _dns()
    t0 = time.perf_counter_ns()
    sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    rep = semantic_identity_report(TEXTS)
    # T1 live
    a = canonicalize_text(TEXTS["fr"])
    b = canonicalize_text(TEXTS["fr"])
    t1 = a.reasoning_id() == b.reasoning_id()
    # T4 live
    r1 = canonicalize_text("Cette méthode réduit le nombre d'opérations.")
    r2 = canonicalize_text(
        "Cette méthode réduit le nombre d'opérations, donc elle est toujours meilleure."
    )
    t4 = r1.reasoning_id() != r2.reasoning_id()
    views = {
        lang: human_view(reasoning_id=a.reasoning_id(), language=lang, text=text)
        for lang, text in TEXTS.items()
    }
    # Anchor ReasoningID (not human text) on public chain
    key = _key()
    memo = {"http": 0}
    if len(key) >= 16:
        body = json.dumps(
            {
                "content": json.dumps(
                    {
                        "kind": "r333_reasoning_canonical_anchor",
                        "reasoning_id": a.reasoning_id(),
                        "reasoning_hash": a.reasoning_hash(),
                        "concept_ids": list(a.concept_ids),
                        "multilingual_same_id": rep.get("same_reasoning_id"),
                        "concept_intersection": rep.get("concept_intersection"),
                    },
                    sort_keys=True,
                ),
                "visibility": "public",
                "memo_type": "reasoning_canonical_anchor",
                "graph_id": f"r333_{a.reasoning_id()}",
            }
        ).encode()
        req = urllib.request.Request(
            "https://artcb.me/api/v1/ai/memo",
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=90) as resp:
                memo = {"http": resp.status, **json.loads(resp.read().decode())}
        except Exception as exc:  # noqa: BLE001
            memo = {"http": 0, "error": f"{type(exc).__name__}:{exc}"}

    out = {
        "measurement_id": f"R333_{time.strftime('%Y%m%dT%H%M%SZ')}_{sha[:12]}",
        "ts_ns": time.time_ns(),
        "dur_ns": time.perf_counter_ns() - t0,
        "commit_sha": sha,
        "certified_100": False,
        "claims": {
            "private_model_cot_equal": False,
            "human_text_is_canonical": False,
            "canonical_is_conceptid_bag": True,
        },
        "T1_determinism": t1,
        "T3_multilingual": {
            "same_reasoning_id": rep.get("same_reasoning_id"),
            "intersection_nonempty": rep.get("intersection_nonempty"),
            "unique_ids": rep.get("unique_reasoning_ids"),
            "concept_intersection": rep.get("concept_intersection"),
        },
        "T4_different_premises": t4,
        "views_text_hashes_distinct": len({v["text_sha256"] for v in views.values()}) == len(TEXTS),
        "anchor": {
            "http": memo.get("http"),
            "block_index": memo.get("block_index"),
            "block_hash": str(memo.get("block_hash") or "")[:16],
        },
        "pass_partial": bool(t1 and rep.get("intersection_nonempty") and t4),
        "note": "PASS_PARTIAL ≠ CERTIFIED_100; no FR↔EN translator round-trip claimed",
    }
    d = ROOT / "logs" / "R333"
    d.mkdir(parents=True, exist_ok=True)
    path = d / "measurement.json"
    path.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"wrote": str(path), **{k: out[k] for k in ("pass_partial", "T1_determinism", "T3_multilingual", "T4_different_premises", "anchor", "certified_100")}}, indent=2))
    return 0 if out["pass_partial"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
