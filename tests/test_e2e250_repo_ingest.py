"""Repo ingest: classify, pack, graph, parse. No live node."""

from __future__ import annotations

from pathlib import Path

from src.artcb.memory.repo_ingest import (
    FileRecord,
    build_ingest_graph,
    catalog_lines,
    pack_batches,
    parse_batch_files,
)
from src.artcb.memory.repo_scope import classify_path, redact_text


def test_classify_scopes() -> None:
    assert classify_path("rapports/248_x.md") == "public"
    assert classify_path("src/artcb/chain/manager.py") == "public"
    assert classify_path("AUTO_PROMPT_ARTCB") == "group"
    assert classify_path(".cursor/rules/artcb-live-node.mdc") == "group"
    assert classify_path("deploy/ovh_artcb_node_1.known_hosts") == "organization"
    assert classify_path("logs/220_live_latest.json") == "private"
    assert classify_path(".env") == "private"
    assert classify_path("secrets/foo.pem") == "private"


def test_redact_secret_line() -> None:
    text, n = redact_text("ok\npassword=hunter2\nARTCB_API_KEY=artcb_" + ("ab" * 20) + "\n")
    assert n == 2
    assert "hunter2" not in text
    assert "artcb_" not in text


def test_pack_includes_every_path_in_catalog(tmp_path: Path) -> None:
    records = [
        FileRecord("rapports/a.md", "aa" * 32, 3, "public", "# a\n"),
        FileRecord("AUTO_PROMPT_ARTCB", "bb" * 32, 3, "group", "GO\n"),
        FileRecord("deploy/x.sh", "cc" * 32, 3, "organization", "echo\n"),
        FileRecord("logs/x.log", "dd" * 32, 3, "private", "err\n"),
        FileRecord(".env", "ee" * 32, 10, "private", None, secret=True, skipped_reason="secret"),
    ]
    batches = pack_batches(records, git_sha="deadbeef")
    assert batches[0].kind == "repo_catalog"
    assert batches[0].chain_visibility == "public"
    catalog = catalog_lines(records, git_sha="deadbeef")
    assert "rapports/a.md" in catalog
    assert ".env" in catalog
    assert '"secret": true' in catalog
    scopes = {b.scope for b in batches[1:]}
    assert scopes == {"public", "group", "organization", "private"}
    for b in batches[1:]:
        assert b.chain_visibility == ("public" if b.scope == "public" else "private")
        graph = build_ingest_graph(b)
        assert graph.verify_integrity()
        parsed = parse_batch_files(graph.source_text)
        assert parsed
        assert all(p["path"] for p in parsed)
