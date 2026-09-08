"""258 — ConceptID lexicon, binary sidecar, liveness observe, default limits.

No live node. No node stop. No rewrite of historical JSONL.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from artcb.chain.binary_log import append_record, iter_records, record_count
from artcb.chain.manager import ChainManager
from artcb.consensus.liveness import assess_liveness
from artcb.ir.concept import concept_id_from_node
from artcb.ir.encoder import IREncoder


PROBE = {
    "fr": "Le serveur doit vérifier la signature.",
    "en": "The server must verify the signature.",
    "es": "El servidor debe verificar la firma.",
}


def test_encoder_fr_en_es_probe_overlap() -> None:
    """The 254/257 live probe sentences — overlap must no longer be 0."""
    enc = IREncoder()
    ids = {}
    for lang, text in PROBE.items():
        graph = enc.encode(text, session_id=f"258_{lang}")
        ids[lang] = [concept_id_from_node(n) for n in graph.nodes]
        assert graph.nodes[0].sym.startswith("V1")
        assert "N1" in graph.nodes[0].sym
        assert "S2" in graph.nodes[0].sym
    overlap = set(ids["fr"]) & set(ids["en"]) & set(ids["es"])
    assert overlap, f"expected shared ConceptID, got {ids}"
    assert ids["fr"] == ids["en"] == ids["es"]


def test_unknown_sentence_does_not_false_converge() -> None:
    enc = IREncoder()
    a = concept_id_from_node(enc.encode("Un kiwi violet danse la java.").nodes[0])
    b = concept_id_from_node(enc.encode("Purple kiwi dances the java.").nodes[0])
    # Honest: no lexicon hit → minted originals may differ. Do not force equality.
    assert a.startswith("K") and b.startswith("K")


def test_binary_sidecar_does_not_replace_jsonl(tmp_path: Path) -> None:
    path = tmp_path / "chain" / "blocks.jsonl"
    chain = ChainManager(path, key_path=tmp_path / "k", enable_security=False)
    chain.append_block(graph_id="g0", graph_root="r", pol_score=0.1, visibility="public", source="ai:memo")
    chain.append_block(graph_id="g1", graph_root="r", pol_score=0.1, visibility="public", source="ai:memo")
    assert path.is_file()
    assert path.read_text(encoding="utf-8").count("\n") == 2
    assert record_count(path) == 2
    rows = list(iter_records(path))
    assert rows[0]["graph_id"] == "g0"
    assert rows[1]["graph_id"] == "g1"


def test_liveness_partition_matrix() -> None:
    four_up = assess_liveness(
        include_self=False,
        peer_reachable=[
            ("a", True, 1_000_000),
            ("b", True, 1_000_000),
            ("c", True, 1_000_000),
            ("d", True, 1_000_000),
        ],
    )
    assert four_up.n == 4 and four_up.q == 3
    assert four_up.partitioned is False
    one_down = assess_liveness(
        include_self=False,
        peer_reachable=[
            ("a", True, 1),
            ("b", True, 1),
            ("c", True, 1),
            ("d", False, 2_000_000),
        ],
    )
    assert one_down.reachable == 3
    assert one_down.below_quorum is False
    two_down = assess_liveness(
        include_self=False,
        peer_reachable=[
            ("a", True, 1),
            ("b", True, 1),
            ("c", False, 1),
            ("d", False, 1),
        ],
    )
    assert two_down.reachable == 2
    assert two_down.partitioned is True
    assert two_down.would_failover is False


def test_liveness_would_failover_only_if_quorum_holds() -> None:
    silent = assess_liveness(
        include_self=False,
        peer_reachable=[("a", True, 1), ("b", True, 1), ("c", True, 1), ("d", True, 1)],
        producer_silent=True,
    )
    assert silent.would_failover is True
    silent_part = assess_liveness(
        include_self=False,
        peer_reachable=[("a", True, 1), ("b", False, 1), ("c", False, 1), ("d", False, 1)],
        producer_silent=True,
    )
    assert silent_part.partitioned is True
    assert silent_part.would_failover is False


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("ARTCB_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("ARTCB_LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("ARTCB_SKIP_SEED_DISCOVERY", "1")
    return TestClient(create_app())


def test_chain_default_limit_and_concept_route(client: TestClient) -> None:
    state = client.app.state.artcb
    for i in range(8):
        state.chain.append_block(
            graph_id=f"lim{i}",
            graph_root="r",
            pol_score=0.1,
            visibility="public",
            source="ai:memo",
        )
    listed = client.get("/api/v1/chain?limit=3")
    assert listed.status_code == 200
    body = listed.json()
    assert body["count"] == 3
    assert body.get("truncated") is True
    r = client.get("/api/v1/ir/concept-ids", params={"q": PROBE["en"]})
    assert r.status_code == 200
    assert r.json()["concept_ids"]
    fr = client.get("/api/v1/ir/concept-ids", params={"q": PROBE["fr"]})
    assert fr.json()["concept_ids"] == r.json()["concept_ids"]
    liv = client.get("/api/v1/consensus/liveness")
    assert liv.status_code == 200
    assert liv.json()["nodes_not_stopped"] is True
    assert liv.json()["not_block_append_bft"] is True


def test_append_record_helper(tmp_path: Path) -> None:
    p = tmp_path / "blocks.jsonl"
    p.write_text("{}\n", encoding="utf-8")
    n = append_record(p, {"index": 0, "hash": "aa"})
    assert n > 0
    assert record_count(p) == 1
