"""Tests — R356 PBFT Publisher pour REASONING_RECORD.

Couvre les scénarios identifiés dans l'audit R372 :
  - Publication normale (mock quorum OK)
  - Record non scellé → refus immédiat
  - Nœud primary mort (timeout / 0 connexion)
  - Quorum insuffisant (< Q=3)
  - Double proposition (409 equivocation)
  - Idempotence (already_published)
  - Partition réseau simulée (certains nœuds injoignables)
  - Séparation données privées / publiques (final_hash only)

HONNÊTETÉ : ces tests utilisent des mocks HTTP (pas de nœuds live).
La couverture live est séparée (scripts/certif_r356_live.py).
CERTIFIED_100=false.
"""
from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import os
os.environ.setdefault("ARTCB_DATA_DIR", str(ROOT / "data"))

from src.artcb.reasoning.record import (
    ReasoningRecord,
    RecordAction,
    RecordOutcome,
    ReasoningRecordStore,
    record_from_dict,
)
from src.artcb.reasoning.first_reflex import FirstReflex
from src.artcb.reasoning.reference_id import ref_rule
from src.artcb.reasoning.pbft_publisher import (
    ReasoningPbftPublisher,
    PublishResult,
    _build_block_payload,
    _build_graph_id,
    R356_PROTOCOL_VERSION,
)


# ─── Fixtures ─────────────────────────────────────────────────────────────────


def make_sealed_record(session_id: str = "r356-test") -> ReasoningRecord:
    """Crée un ReasoningRecord scellé pour les tests."""
    fr = FirstReflex(
        session_id=session_id,
        trigger_name="REFLEX_MEMORY",
        priority=0,
        evidence={"keywords": ["mémoire"]},
    )
    r = ReasoningRecord(
        session_id=session_id,
        agent_id="bob-ide",
        context_summary="Test R356",
        first_reflex=fr,
        action=RecordAction.IMPLEMENT,
    )
    r.add_observation("file_modified", path="src/artcb/reasoning/pbft_publisher.py")
    r.add_reference(ref_rule(rule_name="R356"))
    r.seal(outcome=RecordOutcome.PASS, outcome_detail="R356 test sealed", learning="test R356")
    return r


# ─────────────────────────────────────────────────────────────────────────────
# Utilitaires de construction
# ─────────────────────────────────────────────────────────────────────────────

class TestBuildHelpers:

    def test_build_block_payload_contains_final_hash(self):
        """R356 : le payload public contient final_hash."""
        payload = _build_block_payload("rec_id_abc", "final_hash_xyz", session_id="sess1")
        assert payload["final_hash"] == "final_hash_xyz"
        assert payload["record_id"] == "rec_id_abc"
        assert payload["protocol_version"] == R356_PROTOCOL_VERSION

    def test_build_block_payload_hashes_session_id(self):
        """R356 / audit R372 point 9 : session_id_hash ≠ session_id brut."""
        payload = _build_block_payload("r", "f", session_id="my_private_session")
        assert "session_id_hash" in payload
        assert payload["session_id_hash"] != "my_private_session"
        # C'est un hash tronqué du session_id
        expected = hashlib.sha256("my_private_session".encode()).hexdigest()[:16]
        assert payload["session_id_hash"] == expected

    def test_build_block_payload_no_context_summary(self):
        """R356 : le payload public NE contient PAS context_summary (données privées)."""
        payload = _build_block_payload("r", "f", session_id="s")
        assert "context_summary" not in payload
        assert "observations" not in payload
        assert "learning" not in payload

    def test_graph_id_deterministic(self):
        g1 = _build_graph_id("rec_abc", "hash_xyz")
        g2 = _build_graph_id("rec_abc", "hash_xyz")
        assert g1 == g2

    def test_graph_id_different_for_different_records(self):
        g1 = _build_graph_id("rec_aaa", "hash_xyz")
        g2 = _build_graph_id("rec_bbb", "hash_xyz")
        assert g1 != g2

    def test_graph_id_starts_with_prefix(self):
        from src.artcb.reasoning.pbft_publisher import R356_GRAPH_PREFIX
        g = _build_graph_id("r", "f")
        assert g.startswith(R356_GRAPH_PREFIX)


# ─────────────────────────────────────────────────────────────────────────────
# PublishResult
# ─────────────────────────────────────────────────────────────────────────────

class TestPublishResult:

    def test_ok_result(self):
        pr = PublishResult(
            ok=True,
            record_id="abc",
            final_hash="def",
            block_index=100,
            block_hash="ghi",
            prepared_count=3,
        )
        assert pr.ok is True
        assert pr.block_index == 100

    def test_to_dict_has_required_keys(self):
        pr = PublishResult(ok=False, record_id="r", final_hash="f", error="no_quorum")
        d = pr.to_dict()
        for k in ("ok", "record_id", "final_hash", "error", "certified", "note", "protocol_version"):
            assert k in d

    def test_certified_is_false(self):
        pr = PublishResult(ok=True, record_id="r", final_hash="f")
        assert pr.certified is False

    def test_protocol_version(self):
        pr = PublishResult(ok=True, record_id="r", final_hash="f")
        assert pr.protocol_version == R356_PROTOCOL_VERSION

    def test_note_mentions_r356(self):
        pr = PublishResult(ok=False, record_id="r", final_hash="f")
        assert "R356" in pr.to_dict()["note"]


# ─────────────────────────────────────────────────────────────────────────────
# Scénario 1 — Record non scellé → refus immédiat
# ─────────────────────────────────────────────────────────────────────────────

class TestRecordNotSealed:

    def test_open_record_rejected(self):
        """R356 : un record non scellé est rejeté sans appel HTTP."""
        r = ReasoningRecord(session_id="s", action=RecordAction.ANALYZE)
        # Ne pas appeler seal()
        publisher = ReasoningPbftPublisher(api_url="https://example.invalid")
        result = publisher.publish(r)
        assert result.ok is False
        assert result.error == "record_not_sealed"

    def test_missing_final_hash_rejected(self):
        """R356 : final_hash vide → refus."""
        r = ReasoningRecord(session_id="s")
        # Simuler un record frozen sans final_hash (cas de corruption)
        object.__setattr__(r, "frozen", True)
        # final_hash reste vide
        publisher = ReasoningPbftPublisher(api_url="https://example.invalid")
        result = publisher.publish(r)
        assert result.ok is False
        assert result.error == "missing_final_hash"


# ─────────────────────────────────────────────────────────────────────────────
# Scénario 2 — Primary mort (timeout / connexion refusée)
# ─────────────────────────────────────────────────────────────────────────────

class TestPrimaryUnreachable:

    def test_primary_unreachable_returns_error(self):
        """R356 : si le primary est mort → error=primary_unreachable."""
        r = make_sealed_record()
        # Seeds pointant vers des URL invalides
        publisher = ReasoningPbftPublisher(
            api_url="http://192.0.2.1:8000",  # TEST-NET — aucune connexion possible
            seeds=[{"node_id": "dead-node", "base_url": "http://192.0.2.1:8000"}],
            timeout=0.1,  # timeout très court
        )
        result = publisher.publish(r)
        assert result.ok is False
        assert result.error in ("primary_unreachable", "block_construction_failed")

    def test_all_seeds_unreachable(self):
        """R356 : tous les seeds morts → primary_unreachable."""
        r = make_sealed_record()
        publisher = ReasoningPbftPublisher(
            seeds=[
                {"node_id": "n1", "base_url": "http://192.0.2.1:8000"},
                {"node_id": "n2", "base_url": "http://192.0.2.2:8000"},
            ],
            timeout=0.1,
        )
        result = publisher.publish(r)
        assert result.ok is False
        assert result.error == "primary_unreachable"


# ─────────────────────────────────────────────────────────────────────────────
# Scénario 3 — Quorum insuffisant (< Q=3)
# ─────────────────────────────────────────────────────────────────────────────

class TestNoQuorum:

    def test_quorum_2_of_3_fails(self):
        """R356 : seulement 2 PREPARE → no_quorum."""
        r = make_sealed_record()

        # Mock : primary répond OK, mais seulement 2 PREPARE
        mock_responses = {
            "GET /api/v1/consensus/pbft/view": (200, {"primary": "n1", "view": 1, "seq": 1}),
            "GET /api/v1/chain/graph/": (404, {"found": False}),
            "POST /api/v1/consensus/pbft/propose": (200, {
                "ok": True,
                "block": {"index": 100, "hash": "abc", "visibility": "public", "prev_hash": "0" * 64},
                "pre_prepare": {"view": 1, "seq": 1, "digest": "d1"},
            }),
            "POST /api/v1/consensus/pbft/client-request": (200, {
                "ok": True,
                "pre_prepare": {"view": 1, "seq": 1, "digest": "d1"},
                "block": {"index": 100, "hash": "abc"},
            }),
        }

        prepare_count = [0]

        def fake_http(method, url, body=None, *, timeout=8.0, api_key=""):
            if "/pbft/view" in url:
                return 200, {"primary": "n1", "view": 1}
            if "/chain/graph/" in url:
                return 404, {"found": False}
            if "/pbft/propose" in url:
                return 200, {
                    "ok": True,
                    "block": {"index": 100, "hash": "abc", "visibility": "public",
                              "public_symbols": {}, "prev_hash": "0" * 64},
                }
            if "/pbft/client-request" in url:
                return 200, {
                    "ok": True,
                    "pre_prepare": {"view": 1, "seq": 1, "digest": "d1"},
                }
            if "/pbft/prepare" in url:
                prepare_count[0] += 1
                # Seulement 1 PREPARE accepté (< Q=3)
                if prepare_count[0] <= 1:
                    return 200, {"result": "prepared", "seq": 1}
                return 503, {"error": "unavailable"}
            if "/pbft/commit" in url:
                return 503, {"error": "no_quorum"}
            return 0, {"error": "unexpected"}

        with patch("src.artcb.reasoning.pbft_publisher._http_json", side_effect=fake_http):
            publisher = ReasoningPbftPublisher(
                api_url="http://fake-primary",
                seeds=[
                    {"node_id": "n1", "base_url": "http://fake-primary"},
                    {"node_id": "n2", "base_url": "http://fake-n2"},
                    {"node_id": "n3", "base_url": "http://fake-n3"},
                ],
            )
            result = publisher.publish(r)

        assert result.ok is False
        assert result.error in ("no_quorum", "commit_failed_503")


# ─────────────────────────────────────────────────────────────────────────────
# Scénario 4 — Double proposition (409 equivocation)
# ─────────────────────────────────────────────────────────────────────────────

class TestEquivocation:

    def test_equivocation_detected(self):
        """R356 : le primary retourne 409 equivocation → error=equivocation."""
        r = make_sealed_record()

        def fake_http(method, url, body=None, *, timeout=8.0, api_key=""):
            if "/pbft/view" in url:
                return 200, {"primary": "n1", "view": 1}
            if "/chain/graph/" in url:
                return 404, {"found": False}
            if "/pbft/propose" in url:
                return 200, {
                    "ok": True,
                    "block": {"index": 100, "hash": "abc", "visibility": "public",
                              "public_symbols": {}, "prev_hash": "0" * 64},
                }
            if "/pbft/client-request" in url:
                return 409, {"detail": "equivocation: block already proposed for this seq"}
            return 0, {"error": "unexpected"}

        with patch("src.artcb.reasoning.pbft_publisher._http_json", side_effect=fake_http):
            publisher = ReasoningPbftPublisher(
                api_url="http://fake-primary",
                seeds=[{"node_id": "n1", "base_url": "http://fake-primary"}],
            )
            result = publisher.publish(r)

        assert result.ok is False
        assert result.error == "equivocation"


# ─────────────────────────────────────────────────────────────────────────────
# Scénario 5 — Idempotence (already_published)
# ─────────────────────────────────────────────────────────────────────────────

class TestIdempotence:

    def test_already_published_returns_ok(self):
        """R356 : si le graph_id est déjà dans la chaîne → ok=True, already_published=True."""
        r = make_sealed_record()
        graph_id = _build_graph_id(r.record_id, r.final_hash)

        def fake_http(method, url, body=None, *, timeout=8.0, api_key=""):
            if "/chain/graph/" in url and graph_id in url:
                return 200, {"found": True, "block_index": 42, "block_hash": "existing_hash"}
            return 200, {}

        with patch("src.artcb.reasoning.pbft_publisher._http_json", side_effect=fake_http):
            publisher = ReasoningPbftPublisher(
                api_url="http://fake-primary",
                seeds=[{"node_id": "n1", "base_url": "http://fake-primary"}],
            )
            result = publisher.publish(r)

        assert result.ok is True
        assert result.already_published is True
        assert result.block_index == 42


# ─────────────────────────────────────────────────────────────────────────────
# Scénario 6 — Succès complet avec quorum (mock)
# ─────────────────────────────────────────────────────────────────────────────

class TestSuccessfulPublication:

    def test_full_quorum_ok(self):
        """R356 : PRE-PREPARE → PREPARE × 3 → COMMIT → ok=True, block_index retourné."""
        r = make_sealed_record()
        prepare_count = [0]

        def fake_http(method, url, body=None, *, timeout=8.0, api_key=""):
            if "/pbft/view" in url:
                return 200, {"primary": "n1", "view": 1}
            if "/chain/graph/" in url:
                return 404, {"found": False}
            if "/pbft/propose" in url:
                return 200, {
                    "ok": True,
                    "block": {"index": 200, "hash": "final_block_hash", "visibility": "public",
                              "public_symbols": {}, "prev_hash": "0" * 64},
                }
            if "/pbft/client-request" in url:
                return 200, {
                    "ok": True,
                    "pre_prepare": {"view": 1, "seq": 42, "digest": "digest_abc"},
                }
            if "/pbft/prepare" in url:
                prepare_count[0] += 1
                return 200, {"result": "prepared", "seq": 42}
            if "/pbft/commit" in url:
                return 200, {
                    "ok": True,
                    "written": True,
                    "block": {"index": 200, "hash": "final_block_hash"},
                }
            return 0, {"error": f"unexpected: {method} {url}"}

        with patch("src.artcb.reasoning.pbft_publisher._http_json", side_effect=fake_http):
            publisher = ReasoningPbftPublisher(
                api_url="http://fake-primary",
                seeds=[
                    {"node_id": "n1", "base_url": "http://fake-primary"},
                    {"node_id": "n2", "base_url": "http://fake-n2"},
                    {"node_id": "n3", "base_url": "http://fake-n3"},
                ],
            )
            result = publisher.publish(r)

        assert result.ok is True
        assert result.block_index == 200
        assert result.block_hash == "final_block_hash"
        assert result.prepared_count >= 3
        assert result.final_hash == r.final_hash
        assert result.record_id == r.record_id

    def test_result_does_not_expose_private_data(self):
        """R356 / audit R372 point 9 : le résultat ne contient pas le raisonnement brut."""
        r = make_sealed_record()

        def fake_http(method, url, body=None, *, timeout=8.0, api_key=""):
            if "/pbft/view" in url:
                return 200, {"primary": "n1", "view": 1}
            if "/chain/graph/" in url:
                return 404, {"found": False}
            if "/pbft/propose" in url:
                return 200, {"ok": True,
                              "block": {"index": 1, "hash": "h", "visibility": "public",
                                        "public_symbols": {}, "prev_hash": "0" * 64}}
            if "/pbft/client-request" in url:
                return 200, {"ok": True,
                              "pre_prepare": {"view": 1, "seq": 1, "digest": "d"}}
            if "/pbft/prepare" in url:
                return 200, {"result": "prepared"}
            if "/pbft/commit" in url:
                return 200, {"ok": True, "block": {"index": 1, "hash": "h"}}
            return 0, {}

        with patch("src.artcb.reasoning.pbft_publisher._http_json", side_effect=fake_http):
            publisher = ReasoningPbftPublisher(
                api_url="http://fake-primary",
                seeds=[{"node_id": "n" + str(i), "base_url": f"http://fake-n{i}"}
                       for i in range(3)],
            )
            result = publisher.publish(r)

        d = result.to_dict()
        # Données privées absentes du résultat
        assert "context_summary" not in d
        assert "observations" not in d
        assert "learning" not in d
        # Données publiques présentes
        assert "final_hash" in d
        assert "record_id" in d


# ─────────────────────────────────────────────────────────────────────────────
# Scénario 7 — Partition réseau (1 nœud sur 3 injoignable)
# ─────────────────────────────────────────────────────────────────────────────

class TestPartition:

    def test_partition_2_reachable_of_3_no_quorum(self):
        """R356 : 1 nœud sur 3 injoignable → Q=3 non atteint → no_quorum."""
        r = make_sealed_record()
        call_count = [0]

        def fake_http(method, url, body=None, *, timeout=8.0, api_key=""):
            if "/pbft/view" in url:
                return 200, {"primary": "n1", "view": 1}
            if "/chain/graph/" in url:
                return 404, {"found": False}
            if "/pbft/propose" in url:
                return 200, {"ok": True,
                              "block": {"index": 1, "hash": "h", "visibility": "public",
                                        "public_symbols": {}, "prev_hash": "0" * 64}}
            if "/pbft/client-request" in url:
                return 200, {"ok": True,
                              "pre_prepare": {"view": 1, "seq": 1, "digest": "d"}}
            if "/pbft/prepare" in url:
                call_count[0] += 1
                # n3 (3ème appel) est injoignable → partition
                if call_count[0] >= 3:
                    return 0, {"error": "connection_refused"}
                return 200, {"result": "prepared"}
            if "/pbft/commit" in url:
                return 503, {"error": "no_quorum"}
            return 0, {}

        with patch("src.artcb.reasoning.pbft_publisher._http_json", side_effect=fake_http):
            publisher = ReasoningPbftPublisher(
                api_url="http://fake-primary",
                seeds=[
                    {"node_id": "n1", "base_url": "http://fake-primary"},
                    {"node_id": "n2", "base_url": "http://fake-n2"},
                    {"node_id": "n3", "base_url": "http://fake-n3"},  # injoignable
                ],
            )
            result = publisher.publish(r)

        assert result.ok is False
        assert result.error in ("no_quorum", "commit_failed_503")

    def test_partition_3_reachable_quorum_ok(self):
        """R356 : 3 nœuds sur 4 joignables → Q=3 atteint → succès."""
        r = make_sealed_record()

        def fake_http(method, url, body=None, *, timeout=8.0, api_key=""):
            if "/pbft/view" in url:
                return 200, {"primary": "n1", "view": 1}
            if "/chain/graph/" in url:
                return 404, {"found": False}
            if "/pbft/propose" in url:
                return 200, {"ok": True,
                              "block": {"index": 5, "hash": "h5", "visibility": "public",
                                        "public_symbols": {}, "prev_hash": "0" * 64}}
            if "/pbft/client-request" in url:
                return 200, {"ok": True,
                              "pre_prepare": {"view": 1, "seq": 5, "digest": "d5"}}
            if "/pbft/prepare" in url:
                # n4 injoignable mais 3 autres répondent → Q=3
                if "fake-n4" in url:
                    return 0, {"error": "timeout"}
                return 200, {"result": "prepared"}
            if "/pbft/commit" in url:
                return 200, {"ok": True, "block": {"index": 5, "hash": "h5"}}
            return 0, {}

        with patch("src.artcb.reasoning.pbft_publisher._http_json", side_effect=fake_http):
            publisher = ReasoningPbftPublisher(
                api_url="http://fake-primary",
                seeds=[
                    {"node_id": "n1", "base_url": "http://fake-primary"},
                    {"node_id": "n2", "base_url": "http://fake-n2"},
                    {"node_id": "n3", "base_url": "http://fake-n3"},
                    {"node_id": "n4", "base_url": "http://fake-n4"},  # injoignable
                ],
            )
            result = publisher.publish(r)

        assert result.ok is True
        assert result.block_index == 5
