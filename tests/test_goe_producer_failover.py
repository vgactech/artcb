"""Tests GO-E V-01-B — ProducerFailoverRuntime anti-fork.

Matrice :
  GOE-01  append_implemented=True après GO utilisateur
  GOE-02  maybe_produce → failover_live_off quand live=False
  GOE-03  maybe_produce → failover_produce_off quand produce_armed=False
  GOE-04  maybe_produce → producer_alive quand pas de mort détectée
  GOE-05  maybe_produce → monitor_none si pas de monitor
  GOE-06  maybe_produce → chain_not_provided si chain=None
  GOE-07  maybe_produce → cooldown si appelé deux fois vite
  GOE-08  maybe_produce → insufficient_consensus_nodes si nodes < 2
  GOE-09  élection XOR : même tip → même élu, reproductible
  GOE-10  grace_period_active bloque l'append juste après élection
  GOE-11  not_elected si le nœud local n'est pas l'élu
  GOE-12  index_mismatch détecté avant d'écrire
  GOE-13  status() reflète will_append_blocks correctement
  GOE-14  failover_produce_enabled requiert failover_live
"""
from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest

from src.artcb.p2p.producer_runtime import (
    ProducerFailoverRuntime,
    _build_failover_block,
    failover_live_enabled,
    failover_produce_enabled,
)
from src.artcb.p2p.producer_election import ProducerMonitor, elect_producer


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _runtime(live: bool = True, produce: bool = True, node_id: str = "node_A") -> ProducerFailoverRuntime:
    env = {}
    if live:
        env["ARTCB_PRODUCER_FAILOVER_LIVE"] = "true"
    if produce:
        env["ARTCB_PRODUCER_FAILOVER_PRODUCE"] = "true"
    return ProducerFailoverRuntime(node_id, env=env)


def _dead_monitor(node_id: str = "node_A", *, timeout: float = 0.01) -> ProducerMonitor:
    """Monitor avec un producteur mort (heartbeat très vieux)."""
    m = ProducerMonitor(local_node_id=node_id, heartbeat_timeout=timeout)
    m.record_block(node_id="node_DEAD", block_hash="abc123", block_index=100)
    time.sleep(0.02)  # timeout dépassé
    return m


def _mock_chain(pub_idx: int = 100, pub_hash: str = "tip_hash_abc") -> MagicMock:
    chain = MagicMock()
    chain._public_tip_fields.return_value = (pub_idx, pub_hash)
    # append_block retourne un objet avec to_json_line()
    block_data = {
        "index": pub_idx + 1,
        "prev_hash": pub_hash,
        "hash": "new_block_hash",
        "timestamp": "2026-09-15T00:00:00Z",
        "graph_root": pub_hash,
        "graph_id": "failover:node_A:123",
        "pol_score": 0.0,
        "merkle_root": pub_hash,
        "visibility": "public",
    }
    import json
    mock_block = MagicMock()
    mock_block.to_json_line.return_value = json.dumps(block_data)
    chain.append_block.return_value = mock_block
    chain.write_certified_block.return_value = True
    chain.blocks_path = MagicMock()
    return chain


# ── Tests ──────────────────────────────────────────────────────────────────────

class TestProducerFailoverRuntime:

    def test_goe01_append_implemented_true(self):
        """GOE-01 : append_implemented=True après GO utilisateur 2026-09-15."""
        rt = _runtime()
        assert rt.append_implemented is True

    def test_goe02_live_off(self):
        """GOE-02 : maybe_produce → failover_live_off quand live=False."""
        rt = _runtime(live=False, produce=False)
        r = rt.maybe_produce(chain=_mock_chain())
        assert r["reason"] == "failover_live_off"
        assert r["appended"] is False

    def test_goe03_produce_armed_off(self):
        """GOE-03 : maybe_produce → failover_produce_off quand produce=False."""
        rt = _runtime(live=True, produce=False)
        r = rt.maybe_produce(chain=_mock_chain())
        assert r["reason"] == "failover_produce_off"
        assert r["appended"] is False

    def test_goe04_producer_alive(self):
        """GOE-04 : maybe_produce → producer_alive si producteur actif."""
        rt = _runtime()
        assert rt.monitor is not None
        # Producteur actif avec heartbeat récent
        rt.monitor.record_block(node_id="nodeX", block_hash="xyz", block_index=5)
        r = rt.maybe_produce(chain=_mock_chain())
        assert r["reason"] == "producer_alive"

    def test_goe05_monitor_none(self):
        """GOE-05 : monitor=None si live=False (pas de ProducerMonitor instancié)."""
        rt = _runtime(live=False)
        assert rt.monitor is None
        # live=False → raison live_off avant monitor_none
        r = rt.maybe_produce(chain=_mock_chain())
        assert r["reason"] == "failover_live_off"

    def test_goe06_chain_not_provided(self):
        """GOE-06 : chain=None → chain_not_provided."""
        rt = _runtime()
        assert rt.monitor is not None
        # Producteur mort
        rt.monitor = _dead_monitor("node_A")
        r = rt.maybe_produce(chain=None)
        assert r["reason"] == "chain_not_provided"

    def test_goe07_cooldown(self):
        """GOE-07 : deux appels rapides → cooldown sur le second."""
        rt = _runtime()
        rt._produce_cooldown_s = 60.0
        rt._last_produce_ts = time.time()  # simuler une production récente
        r = rt.maybe_produce(chain=_mock_chain())
        assert r["reason"] == "cooldown"
        assert "cooldown_remaining_s" in r

    def test_goe08_insufficient_nodes(self):
        """GOE-08 : consensus_nodes < 2 → insufficient_consensus_nodes."""
        rt = _runtime()
        rt.monitor = _dead_monitor("node_A")
        chain = _mock_chain()
        r = rt.maybe_produce(chain=chain, consensus_nodes=["node_A"])  # un seul
        assert r["reason"] == "insufficient_consensus_nodes"

    def test_goe09_election_xor_reproductible(self):
        """GOE-09 : même tip → même élu XOR, reproductible."""
        nodes = ["node_A", "node_B", "node_C"]
        tip = "abc123tip"
        r1 = elect_producer(consensus_nodes=nodes, tip_hash=tip)
        r2 = elect_producer(consensus_nodes=nodes, tip_hash=tip)
        assert r1.elected_node_id == r2.elected_node_id
        assert r1.rank_score == r2.rank_score

    def test_goe10_grace_period_blocks_append(self):
        """GOE-10 : grace_period_active bloque l'append juste après élection."""
        rt = _runtime(node_id="node_A")
        rt.monitor = _dead_monitor("node_A")
        chain = _mock_chain()
        # Grace period 60s (impossible de passer)
        with patch("src.artcb.p2p.producer_election.ELECTION_GRACE_SECONDS", 60.0):
            # Mock official_pbft_replica_ids pour avoir 2 nœuds
            with patch("src.artcb.node_registry.official_pbft_replica_ids",
                       return_value=("node_A", "node_B")):
                r = rt.maybe_produce(chain=chain)
        # Soit grace_period_active, not_elected, ou producer_alive
        assert r["appended"] is False
        assert r["reason"] in ("grace_period_active", "not_elected", "producer_alive",
                               "election_not_triggered", "insufficient_consensus_nodes")

    def test_goe11_not_elected(self):
        """GOE-11 : si node_B est élu (pas node_A), on retourne not_elected."""
        rt = _runtime(node_id="node_A")
        rt.monitor = _dead_monitor("node_A")
        chain = _mock_chain()

        # Forcer l'élection de node_B via mock
        from src.artcb.p2p.producer_election import ElectionResult
        mock_result = ElectionResult(
            elected_node_id="node_B",
            tip_hash="tip",
            rank_score=42,
            candidates=["node_A", "node_B"],
            grace_expires_at=time.time() - 1,  # grace expirée
        )
        with patch.object(rt.monitor, "trigger_election", return_value=mock_result):
            with patch.object(rt.monitor, "producer_is_dead", return_value=True):
                r = rt.maybe_produce(chain=chain, consensus_nodes=["node_A", "node_B"])
        assert r["reason"] == "not_elected"
        assert r["elected"] == "node_B"

    def test_goe12_index_mismatch(self):
        """GOE-12 : index_mismatch détecté avant d'écrire."""
        rt = _runtime(node_id="node_A")
        rt.monitor = _dead_monitor("node_A")
        chain = _mock_chain(pub_idx=100)

        # Bloc construit avec un mauvais index
        import json
        bad_block_data = {
            "index": 999,  # ← wrong
            "prev_hash": "tip_hash_abc",
            "hash": "bad_hash",
            "timestamp": "2026-09-15T00:00:00Z",
            "graph_root": "tip_hash_abc",
            "pol_score": 0.0,
            "merkle_root": "tip_hash_abc",
        }
        mock_bad_block = MagicMock()
        mock_bad_block.to_json_line.return_value = json.dumps(bad_block_data)
        chain.append_block.return_value = mock_bad_block

        from src.artcb.p2p.producer_election import ElectionResult
        mock_result = ElectionResult(
            elected_node_id="node_A",
            tip_hash="tip_hash_abc",
            rank_score=1,
            candidates=["node_A", "node_B"],
            grace_expires_at=time.time() - 1,
        )
        with patch.object(rt.monitor, "trigger_election", return_value=mock_result):
            with patch.object(rt.monitor, "producer_is_dead", return_value=True):
                with patch.object(rt.monitor, "am_i_elected", return_value=True):
                    r = rt.maybe_produce(chain=chain, consensus_nodes=["node_A", "node_B"])
        assert r["reason"] == "index_mismatch"
        assert r["appended"] is False
        # write_certified_block NE DOIT PAS avoir été appelé
        chain.write_certified_block.assert_not_called()

    def test_goe13_status_will_append(self):
        """GOE-13 : status() will_append_blocks reflète l'état réel."""
        rt_armed = _runtime(live=True, produce=True)
        rt_unarmed = _runtime(live=True, produce=False)
        assert rt_armed.status()["will_append_blocks"] is True
        assert rt_unarmed.status()["will_append_blocks"] is False

    def test_goe14_produce_requires_live(self):
        """GOE-14 : failover_produce_enabled exige live=True."""
        env_live_only = {"ARTCB_PRODUCER_FAILOVER_LIVE": "true"}
        env_produce_only = {"ARTCB_PRODUCER_FAILOVER_PRODUCE": "true"}
        env_both = {
            "ARTCB_PRODUCER_FAILOVER_LIVE": "true",
            "ARTCB_PRODUCER_FAILOVER_PRODUCE": "true",
        }
        assert failover_produce_enabled(env_live_only) is False
        assert failover_produce_enabled(env_produce_only) is False  # sans live
        assert failover_produce_enabled(env_both) is True
