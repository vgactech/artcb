"""R296/R297 — Context Contract is not the compact snippet and not thinking."""

from __future__ import annotations

from src.artcb.agent_context_contract import (
    CONTRACT_VERSION,
    SNIPPET_MEMO_CHARS,
    SNIPPET_MEMO_LIMIT,
    build_context_contract,
    classify_decision_lifecycle,
)
from src.artcb.memory.repo_scope import classify_path


def test_path_classifier_is_not_acl() -> None:
    assert classify_path(".cursor/rules/x.mdc") == "group"
    assert classify_path("logs/foo.log") == "private"
    assert classify_path("src/artcb/node_registry.py") == "organization"
    contract = build_context_contract()
    assert contract["scope"]["acl_resolved"] is False
    assert contract["scope"]["private"] == "classified_not_resolved"


def test_contract_hash_stable_and_no_thinking() -> None:
    a = build_context_contract(key_record={"label": "agent_test", "address": "artcb1demo"})
    b = build_context_contract(key_record={"label": "agent_test", "address": "artcb1demo"})
    assert a["version"] == CONTRACT_VERSION
    assert a["context_hash"] == b["context_hash"]
    assert len(a["context_hash"]) == 64
    assert a["includes_thinking"] is False
    assert a["includes_system_prompt"] is False
    assert a["snippet_is_not_contract"] is True
    assert a["snippet_limits"] == {"memos": SNIPPET_MEMO_LIMIT, "chars_per_memo": SNIPPET_MEMO_CHARS}
    assert a["parent_agent_id"] is None


def test_decision_lifecycle_not_invented() -> None:
    life = classify_decision_lifecycle(
        [{"type": "decision", "index": 1}, {"type": "decision", "index": 2}]
    )
    assert life["implemented"] is False
    assert life["revoked_decisions"] == []
    assert "supersedes" in life["note"]
    contract = build_context_contract()
    assert "decision_revoke_supersede" in contract["not_proven"]
    assert contract["revoked_decisions"] == []
