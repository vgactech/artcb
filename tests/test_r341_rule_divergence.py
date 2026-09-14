"""R341 — divergence matrix honesty."""

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_divergence_matrix_no_certified_100() -> None:
    r = subprocess.run(
        ["python3", str(ROOT / "scripts" / "artcb_r341_rule_divergence_matrix.py")],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=True,
    )
    doc = json.loads((ROOT / "rules" / "rule_divergence_matrix.json").read_text())
    assert doc["certified_100"] is False
    assert doc["summary"]["certified"] == 0
    assert doc["honest"]["registered_neq_corpus"] is True
    assert len(doc["matrix"]) >= 18
    # No row may claim CERTIFIED
    assert all(row["status_max"] != "CERTIFIED" for row in doc["matrix"])
    # Pipeline certified always false
    assert all(row["pipeline"]["certified"] is False for row in doc["matrix"])
    # Unmapped buckets present (tokenomics/PoL/V01-07…)
    assert len(doc["unmapped_buckets"]) >= 5
    assert "summary" in json.loads(r.stdout)


def test_six_levels_not_collapsed() -> None:
    doc = json.loads((ROOT / "rules" / "rule_divergence_matrix.json").read_text())
    assert "DECIDED" in doc["levels"]
    assert "CERTIFIED" in doc["levels"]
    # At least one OPEN/NOT_PROVEN bucket or open rule
    assert doc["summary"]["open_flagged"] >= 1 or any(
        b["status_max"] in {"OPEN", "NOT_PROVEN", "SIMULATED_ONLY"} for b in doc["unmapped_buckets"]
    )
