"""R340 — corpus cartography honesty."""

from pathlib import Path

from src.artcb.rules.telemetry import badge_snapshot, summarize


def test_badge_labels_registry_not_global_corpus() -> None:
    snap = badge_snapshot()
    assert snap["honest"]["rules_total_is_registry_only"] is True
    assert snap["honest"]["registered_neq_global_corpus"] is True
    assert snap.get("registered_rules") == snap.get("rules_total")
    assert snap["honest"]["certified_100"] is False


def test_summarize_keeps_legacy_rules_total_as_registry() -> None:
    s = summarize()
    assert s["rules_total"] == s["registered_rules"]
    assert "corpus" in s
    assert "registry_only" in (s.get("note") or "")


def test_corpus_audit_script_outputs(tmp_path=None) -> None:
    # Run detections against live files
    import subprocess
    import json

    root = Path(__file__).resolve().parents[1]
    r = subprocess.run(
        ["python3", str(root / "scripts" / "artcb_r340_rule_corpus_audit.py")],
        cwd=str(root),
        capture_output=True,
        text=True,
        check=True,
    )
    out = json.loads(r.stdout)
    assert out["registered_rules"] >= 16
    assert out["certified_100"] is False
    assert (root / "rules" / "rule_sources.json").is_file()
    assert (root / "rules" / "rule_coverage.json").is_file()
    cov = json.loads((root / "rules" / "rule_coverage.json").read_text())
    assert cov["honest"]["no_honest_global_X_rules_without_canonical_map"] is True
    # After R340 sync, live-node must include R339
    assert cov["registry_coverage"]["live_node_includes_r339"] is True
    assert cov["registry_coverage"]["sync_gap_live_node_vs_registry"] is False
