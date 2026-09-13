#!/usr/bin/env python3
"""R337 — Anti-Sybil statistical campaign starter (honest: engine ≠ certification).

Measures live metrics; does NOT invent sample_count>=50 PASS.
Optional: enable study_mode (requires write actor) — operator may refuse.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))
try:
    from artcb_dns_fix import install as _dns

    _dns()
except Exception:
    pass

from artcb.rules.telemetry import RuleEvent, append_event  # noqa: E402


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


def get_metrics(base: str = "https://artcb.me") -> tuple[int, dict]:
    req = urllib.request.Request(
        f"{base.rstrip('/')}/api/v1/security/anti-sybil/metrics",
        headers={"Accept": "application/json", "Authorization": f"Bearer {_key()}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return int(r.status), json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")[:500]
        try:
            return int(e.code), json.loads(body)
        except Exception:
            return int(e.code), {"detail": body}
    except Exception as exc:
        return 0, {"error": type(exc).__name__, "detail": str(exc)[:200]}


def main() -> int:
    code, body = get_metrics()
    rec = (body or {}).get("recommendation") or {}
    dist = (body or {}).get("interval_distribution") or {}
    sample = int(rec.get("sample_count") or dist.get("sample_count") or 0)
    suggested = rec.get("suggested_limit_s")
    reliable = sample >= 50
    out = {
        "measurement_id": f"R337_SYBIL_{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}",
        "ts_ns": time.time_ns(),
        "http": code,
        "sample_count": sample,
        "suggested_limit_s": suggested,
        "recommendation_status": rec.get("status"),
        "quantity_gate_50": reliable,
        "campaign_certified": False,
        "honest": (
            "engine_present_but_campaign_not_certified; "
            f"sample_count={sample} (need >=50 quantity then full statistical analysis)"
        ),
        "totals": (body or {}).get("totals"),
        "interval_distribution": dist,
        "recommendation": rec,
        "certified_100": False,
    }
    dest = ROOT / "logs" / "R337" / "anti_sybil_baseline.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    # Telemetry: checked + not_proven (campaign incomplete)
    append_event(
        RuleEvent(
            rule_id="RT-SYBIL-076",
            kind="checked",
            turn_id=out["measurement_id"],
            task_type="anti_sybil_campaign",
            evidence_kind="http_status",
            evidence_ref=str(code),
            note=f"sample_count={sample}",
        )
    )
    append_event(
        RuleEvent(
            rule_id="RT-SYBIL-076",
            kind="not_proven",
            turn_id=out["measurement_id"],
            task_type="anti_sybil_campaign",
            evidence_kind="measurement_json",
            evidence_ref=str(dest),
            note="campaign_certified=false",
        )
    )
    if code == 200:
        append_event(
            RuleEvent(
                rule_id="RT-SYBIL-076",
                kind="applied_confirmed",
                turn_id=out["measurement_id"],
                task_type="anti_sybil_campaign",
                evidence_kind="measurement_json",
                evidence_ref=str(dest.relative_to(ROOT)),
                note="baseline_metrics_only_not_final_limit",
            )
        )

    print(json.dumps(out, indent=2, ensure_ascii=False))
    print(f"wrote {dest}", file=sys.stderr)
    return 0 if code == 200 else 2


if __name__ == "__main__":
    raise SystemExit(main())
