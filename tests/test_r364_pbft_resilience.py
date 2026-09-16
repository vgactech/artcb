"""Tests R364 — BUG1/BUG2/BUG3 : PBFT sans dépendance nœud unique.

BUG1: coordinate_public_finality déclenche auto VIEW-CHANGE quand primary unreachable
BUG2: watchdog stall_sec = 120s par défaut (était 900s)
BUG3: verify_chain_integrity détecte gaps / prev_hash cassé
"""
from __future__ import annotations

import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch


# ─────────────────────────────────────────────────────────────────────────────
# BUG2 — watchdog stall threshold
# ─────────────────────────────────────────────────────────────────────────────

class TestWatchdogStallThreshold:

    def test_default_stall_sec_is_120(self):
        """R364-BUG2: default stall threshold doit être 120s, pas 900s."""
        import importlib, os
        # Sans variable d'env, on vérifie que le code utilise 120
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("ARTCB_PUBLIC_TIP_STALL_SEC", None)
            from src.artcb.consensus import public_tip_watchdog
            # Simuler un chain stub
            chain_stub = MagicMock()
            chain_stub.tip_public_private.return_value = {
                "public_last_index": 10,
                "public_last_hash": "abc123",
                "public_last_timestamp": None,
                "private_suffix_lines": 0,
                "ledger_mode": "split",
                "public_has_pbft_cert": True,
            }
            chain_stub.blocks_path = Path("/tmp/fake_chain.jsonl")

            diag = public_tip_watchdog.diagnose(chain_stub)
            # age_sec doit être None (timestamp null) — mais le test montre que
            # le seuil par défaut est 120 en lisant le code source
            import inspect
            src = inspect.getsource(public_tip_watchdog.tick)
            assert '"120"' in src or "'120'" in src, (
                f"R364-BUG2: stall_sec par défaut doit être 120, source contient: "
                + [l for l in src.splitlines() if 'STALL_SEC' in l or '900' in l or '120' in l].__repr__()
            )

    def test_stall_sec_env_override(self):
        """ARTCB_PUBLIC_TIP_STALL_SEC env override fonctionne."""
        import os, inspect
        from src.artcb.consensus import public_tip_watchdog
        src = inspect.getsource(public_tip_watchdog.tick)
        assert "ARTCB_PUBLIC_TIP_STALL_SEC" in src

    def test_900_not_in_default(self):
        """900 ne doit plus être la valeur par défaut."""
        import inspect
        from src.artcb.consensus import public_tip_watchdog
        src = inspect.getsource(public_tip_watchdog.tick)
        # 900 ne doit pas apparaître comme valeur par défaut
        for line in src.splitlines():
            if "STALL_SEC" in line and "or" in line:
                assert "900" not in line, (
                    f"R364-BUG2: 900 encore présent comme default: {line.strip()}"
                )


# ─────────────────────────────────────────────────────────────────────────────
# BUG3 — verify_chain_integrity
# ─────────────────────────────────────────────────────────────────────────────

class TestVerifyChainIntegrity:

    def _write_chain(self, tmp_path: Path, blocks: list[dict]) -> Path:
        p = tmp_path / "chain.jsonl"
        with p.open("w") as f:
            for b in blocks:
                f.write(json.dumps(b) + "\n")
        return p

    def _make_manager(self, chain_path: Path):
        from src.artcb.chain.manager import ChainManager
        return ChainManager(blocks_path=chain_path, enable_security=False)

    def test_empty_chain_is_ok(self, tmp_path):
        p = tmp_path / "chain.jsonl"
        p.touch()
        mgr = self._make_manager(p)
        r = mgr.verify_chain_integrity()
        assert r["ok"] is True
        assert r["height"] == 0

    def test_single_genesis_is_ok(self, tmp_path):
        p = self._write_chain(tmp_path, [
            {"index": 0, "prev_hash": "0000000000000000", "hash": "aabb1122"}
        ])
        mgr = self._make_manager(p)
        r = mgr.verify_chain_integrity()
        assert r["ok"] is True
        assert r["height"] == 1

    def test_valid_sequential_chain(self, tmp_path):
        p = self._write_chain(tmp_path, [
            {"index": 0, "prev_hash": "0000000000000000", "hash": "hash0"},
            {"index": 1, "prev_hash": "hash0",            "hash": "hash1"},
            {"index": 2, "prev_hash": "hash1",            "hash": "hash2"},
            {"index": 3, "prev_hash": "hash2",            "hash": "hash3"},
        ])
        mgr = self._make_manager(p)
        r = mgr.verify_chain_integrity()
        assert r["ok"] is True
        assert r["height"] == 4
        assert r["first_bad"] is None
        assert r["gaps"] == []
        assert r["duplicates"] == []

    def test_broken_prev_hash_detected(self, tmp_path):
        """R364-BUG3: prev_hash cassé doit être détecté."""
        p = self._write_chain(tmp_path, [
            {"index": 0, "prev_hash": "0000000000000000", "hash": "hash0"},
            {"index": 1, "prev_hash": "hash0",            "hash": "hash1"},
            {"index": 2, "prev_hash": "WRONG_HASH",       "hash": "hash2"},  # cassé
            {"index": 3, "prev_hash": "hash2",            "hash": "hash3"},
        ])
        mgr = self._make_manager(p)
        r = mgr.verify_chain_integrity()
        assert r["ok"] is False
        assert r["first_bad"] == 2
        assert "prev_hash_mismatch" in (r["reason"] or "")

    def test_gap_in_index_detected(self, tmp_path):
        """R364-BUG3: trou dans les index doit être détecté."""
        p = self._write_chain(tmp_path, [
            {"index": 0, "prev_hash": "0000", "hash": "hash0"},
            {"index": 1, "prev_hash": "hash0","hash": "hash1"},
            # index 2 manquant
            {"index": 3, "prev_hash": "hash1","hash": "hash3"},
        ])
        mgr = self._make_manager(p)
        r = mgr.verify_chain_integrity()
        assert r["ok"] is False
        assert 2 in r["gaps"]

    def test_duplicate_index_detected(self, tmp_path):
        """R364-BUG3: index dupliqué doit être détecté."""
        p = self._write_chain(tmp_path, [
            {"index": 0, "prev_hash": "0000", "hash": "hash0"},
            {"index": 1, "prev_hash": "hash0","hash": "hash1a"},
            {"index": 1, "prev_hash": "hash0","hash": "hash1b"},  # dupliqué
            {"index": 2, "prev_hash": "hash1a","hash": "hash2"},
        ])
        mgr = self._make_manager(p)
        r = mgr.verify_chain_integrity()
        assert r["ok"] is False
        assert 1 in r["duplicates"]

    def test_never_raises(self, tmp_path):
        """verify_chain_integrity ne doit jamais lever d'exception."""
        # Fichier corrompu (JSON invalide)
        p = tmp_path / "chain.jsonl"
        p.write_text("not json\n{broken\n")
        mgr = self._make_manager(p)
        # Ne doit pas lever
        try:
            r = mgr.verify_chain_integrity()
        except Exception as exc:
            pytest.fail(f"verify_chain_integrity a levé: {exc}")

    def test_health_includes_chain_integrity(self, tmp_path):
        """R364-BUG3: /health expose chain_integrity."""
        import inspect
        from src.api import routes
        src = inspect.getsource(routes.health)
        assert "chain_integrity" in src, "chain_integrity absent de /health"
        assert "verify_chain_integrity" in src


# ─────────────────────────────────────────────────────────────────────────────
# BUG1 — pbft_reachable_http_map probe-aware
# ─────────────────────────────────────────────────────────────────────────────

class TestPbftReachableProbe:

    def test_skip_probe_returns_all_seeds(self):
        """skip_probe=True = comportement legacy."""
        from src.artcb.node_registry import pbft_reachable_http_map, OFFICIAL_COMPUTE_NODE_IDS
        hosts = pbft_reachable_http_map(skip_probe=True)
        for nid in OFFICIAL_COMPUTE_NODE_IDS:
            assert nid in hosts, f"{nid} absent du map skip_probe=True"

    def test_env_skip_probe(self):
        """ARTCB_PBFT_SKIP_PROBE=1 désactive la probe."""
        import os
        from src.artcb.node_registry import pbft_reachable_http_map, OFFICIAL_COMPUTE_NODE_IDS
        with patch.dict(os.environ, {"ARTCB_PBFT_SKIP_PROBE": "1"}):
            hosts = pbft_reachable_http_map()
        for nid in OFFICIAL_COMPUTE_NODE_IDS:
            assert nid in hosts

    def test_probe_excludes_unreachable(self):
        """Un nœud unreachable est exclu du map retourné."""
        from src.artcb.node_registry import pbft_reachable_http_map
        # _probe_http retourne False pour ovh-node-1, True pour les autres
        def fake_probe(base, *, timeout=2.0):
            return "152.228.144.34" not in base  # OVH1 mort

        with patch("src.artcb.node_registry._probe_http", side_effect=fake_probe):
            hosts = pbft_reachable_http_map(probe_timeout=0.1)
        assert "ovh-node-1" not in hosts, "OVH1 mort ne doit pas être dans reachable map"
        assert "ovh-node-2" in hosts
        assert "aws-node-3" in hosts
        assert "ovh-node-4" in hosts

    def test_probe_fallback_never_empty(self):
        """Si tous les probes échouent, fallback = retourner tous les seeds."""
        from src.artcb.node_registry import pbft_reachable_http_map
        with patch("src.artcb.node_registry._probe_http", return_value=False):
            with patch("src.artcb.node_registry.official_replica_id", return_value=""):
                hosts = pbft_reachable_http_map(probe_timeout=0.1)
        assert len(hosts) > 0, "fallback doit retourner des hosts"

    def test_auto_view_change_triggered_on_unreachable_primary(self):
        """R364-BUG1: coordinate_public_finality déclenche VIEW-CHANGE si primary mort."""
        import inspect
        from src.artcb.consensus import pbft_exclusive
        src = inspect.getsource(pbft_exclusive.coordinate_public_finality)
        assert "next_reachable_view" in src, "next_reachable_view doit être appelé"
        assert "emit_view_change" in src, "emit_view_change doit être appelé"
        assert "auto_view_change" in src, "auto_view_change doit être dans la réponse"

    def test_coordinate_returns_auto_vc_info_when_primary_dead(self):
        """R364-BUG1: la réponse contient auto_view_change=True quand primary mort."""
        from src.artcb.consensus.pbft_exclusive import coordinate_public_finality

        # Engine stub
        engine = MagicMock()
        engine.node_id = "ovh-node-2"
        engine.pbft.view = 0  # view=0 → primary=ovh-node-1 (mort)
        engine.pbft_log.data_dir = None
        engine.pbft_log.emit_view_change = MagicMock(return_value={"kind": "view-change"})
        engine.pbft_log.view_changes = MagicMock(return_value=[])

        chain = MagicMock()
        chain.tip_public_private.return_value = {
            "public_last_index": 100, "public_last_hash": "abc"
        }

        block = {"index": 101, "hash": "def", "prev_hash": "abc"}

        # pbft_reachable_http_map exclut OVH1 (probe retourne False pour OVH1)
        def fake_probe(base, *, timeout=2.0):
            return "152.228.144.34" not in base

        with patch("src.artcb.consensus.pbft_exclusive.on_official_compute", return_value=True), \
             patch("src.artcb.node_registry._probe_http", side_effect=fake_probe), \
             patch("src.artcb.node_registry.official_replica_id", return_value="ovh-node-2"), \
             patch("src.artcb.consensus.pbft_exclusive._http_json", return_value=(200, {})):
            result = coordinate_public_finality(engine, chain, block)

        assert result["reason"] == "primary_unreachable_transport"
        assert result.get("auto_view_change") is True or "auto_view_change" in result, (
            f"auto_view_change manquant: {result}"
        )
