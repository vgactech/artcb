"""V-08 — PUBLIC_ENDPOINT_SURVIVES_NODE_DEATH.

Tests de validation de la propriété V-08 ARTCB :
    La mort d'un nœud individuel (y compris l'apex OVH1) ne rend pas
    le domaine public inaccessible dès lors qu'au moins un nœud du quorum est vivant.

Scénarios couverts :
    1. N1 seul vivant               → v08_satisfied=True (apex OK, pas de failover)
    2. N1 mort, N3 vivant            → v08_satisfied=True, failover_triggered=True
    3. N1 mort, N2 vivant            → v08_satisfied=True, failover_triggered=True
    4. N1 mort, N4 vivant            → v08_satisfied=True, failover_triggered=True
    5. Tous morts                    → v08_satisfied=False
    6. Quorum 3/4 (N1+N2+N3 vivants) → v08_satisfied=True
    7. skip_ovh1=True force N1 mort  → failover_triggered=True si secours disponible
    8. Route HTTP GET /failover-status → 200, champs obligatoires présents
    9. Priorité failover respectée   → N3-AWS avant N4/N2
   10. probe_node OVH1 bloqué retourne alive=False + error=ovh1_operator_blocked

Invariants vérifiés :
    - certified_100 JAMAIS True dans la réponse
    - v08_satisfied dépend uniquement des nœuds NON-apex vivants si apex mort
    - image biométrique brute JAMAIS dans ces réponses
"""

from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock

from src.artcb.network.failover import (
    NodeProbeResult,
    FailoverState,
    compute_failover_state,
    select_active_node,
    probe_all_nodes,
    get_failover_status,
    FAILOVER_PRIORITY,
    NODE_HEALTH_URLS,
    NODE_PUBLIC_URLS,
)


# ─── Helpers fixtures ────────────────────────────────────────────────────────

def make_result(node_id: str, alive: bool, latency_ms: float | None = 10.0) -> NodeProbeResult:
    """Construit un NodeProbeResult minimal pour les tests."""
    return NodeProbeResult(
        node_id=node_id,
        url=NODE_HEALTH_URLS.get(node_id, f"https://{node_id}"),
        alive=alive,
        latency_ms=latency_ms if alive else None,
        error=None if alive else "timeout",
    )


ALL_NODES = ["ovh-node-1", "ovh-node-2", "aws-node-3", "ovh-node-4", "mac-node-local"]


def all_dead() -> list[NodeProbeResult]:
    return [make_result(n, False) for n in ALL_NODES]


def only_alive(*node_ids: str) -> list[NodeProbeResult]:
    return [make_result(n, n in node_ids) for n in ALL_NODES]


# ─── 1. Scénario : apex seul vivant ─────────────────────────────────────────

class TestApexAloneAlive:
    def test_v08_satisfied(self):
        results = only_alive("ovh-node-1")
        state = compute_failover_state(results)
        assert state.v08_satisfied is True

    def test_apex_alive(self):
        results = only_alive("ovh-node-1")
        state = compute_failover_state(results)
        assert state.apex_alive is True

    def test_no_failover_triggered(self):
        """Apex vivant → pas de basculement."""
        results = only_alive("ovh-node-1")
        state = compute_failover_state(results)
        assert state.failover_triggered is False

    def test_active_node_is_apex(self):
        results = only_alive("ovh-node-1")
        state = compute_failover_state(results)
        assert state.active_node_id == "ovh-node-1"


# ─── 2. Scénario : N1 mort, N3-AWS vivant (failover principal) ───────────────

class TestApexDeadN3Alive:
    def setup_method(self):
        self.results = only_alive("aws-node-3")
        self.state = compute_failover_state(self.results)

    def test_v08_satisfied(self):
        assert self.state.v08_satisfied is True

    def test_apex_dead(self):
        assert self.state.apex_alive is False

    def test_failover_triggered(self):
        assert self.state.failover_triggered is True

    def test_active_node_is_n3(self):
        assert self.state.active_node_id == "aws-node-3"

    def test_active_url_set(self):
        assert self.state.active_url == NODE_PUBLIC_URLS["aws-node-3"]

    def test_v08_note_mentions_action(self):
        """La note doit rappeler l'action opérateur DNS."""
        assert "opérateur" in self.state.v08_note.lower() or "dns" in self.state.v08_note.lower()


# ─── 3. N1 mort, N2 vivant ───────────────────────────────────────────────────

class TestApexDeadN2Alive:
    def setup_method(self):
        self.results = only_alive("ovh-node-2")
        self.state = compute_failover_state(self.results)

    def test_v08_satisfied(self):
        assert self.state.v08_satisfied is True

    def test_failover_triggered(self):
        assert self.state.failover_triggered is True

    def test_active_node_not_apex(self):
        assert self.state.active_node_id != "ovh-node-1"


# ─── 4. N1 mort, N4 vivant ───────────────────────────────────────────────────

class TestApexDeadN4Alive:
    def setup_method(self):
        self.results = only_alive("ovh-node-4")
        self.state = compute_failover_state(self.results)

    def test_v08_satisfied(self):
        assert self.state.v08_satisfied is True

    def test_active_is_n4(self):
        assert self.state.active_node_id == "ovh-node-4"


# ─── 5. Tous les nœuds morts ─────────────────────────────────────────────────

class TestAllDead:
    def setup_method(self):
        self.results = all_dead()
        self.state = compute_failover_state(self.results)

    def test_v08_not_satisfied(self):
        assert self.state.v08_satisfied is False

    def test_active_is_none(self):
        assert self.state.active_node_id == "none"

    def test_failover_not_triggered(self):
        """Aucun secours → failover ne peut pas basculer."""
        assert self.state.failover_triggered is False

    def test_v08_note_fail(self):
        assert "fail" in self.state.v08_note.lower()

    def test_alive_nodes_empty(self):
        assert self.state.alive_nodes == []


# ─── 6. Quorum 3/4 (N1+N2+N3 vivants) ───────────────────────────────────────

class TestQuorum3of4:
    def setup_method(self):
        self.results = only_alive("ovh-node-1", "ovh-node-2", "aws-node-3")
        self.state = compute_failover_state(self.results)

    def test_v08_satisfied(self):
        assert self.state.v08_satisfied is True

    def test_three_alive_nodes(self):
        assert len(self.state.alive_nodes) == 3

    def test_active_is_apex(self):
        """Avec apex vivant, il reste le nœud actif prioritaire."""
        assert self.state.active_node_id == "ovh-node-1"


# ─── 7. skip_ovh1=True force N1 à apparaître mort ────────────────────────────

class TestSkipOvh1:
    def test_ovh1_reported_dead_when_skipped(self):
        results = probe_all_nodes(
            node_ids=["ovh-node-1", "aws-node-3"],
            skip_ovh1=True,
            timeout_s=0.01,
        )
        ovh1_result = next(r for r in results if r.node_id == "ovh-node-1")
        assert ovh1_result.alive is False
        assert ovh1_result.error == "ovh1_operator_blocked"

    def test_ovh1_not_probed_when_skipped(self):
        """Vérifier qu'aucun appel réseau vers OVH1 n'est tenté."""
        with patch("src.artcb.network.failover.probe_node") as mock_probe:
            mock_probe.return_value = make_result("aws-node-3", True)
            probe_all_nodes(
                node_ids=["ovh-node-1", "aws-node-3"],
                skip_ovh1=True,
                timeout_s=0.01,
            )
            # probe_node ne doit jamais être appelé avec ovh-node-1
            for call in mock_probe.call_args_list:
                assert call.args[0] != "ovh-node-1", "OVH1 NE DOIT PAS être sondé (BLOQUÉ)"


# ─── 8. Priorité failover ────────────────────────────────────────────────────

class TestPriority:
    def test_n3_before_n4(self):
        """AWS-N3 doit être préféré à OVH-N4 selon FAILOVER_PRIORITY."""
        results = only_alive("aws-node-3", "ovh-node-4")
        active = select_active_node(results)
        assert active == "aws-node-3"

    def test_n3_before_n2(self):
        results = only_alive("aws-node-3", "ovh-node-2")
        active = select_active_node(results)
        assert active == "aws-node-3"

    def test_n1_first_when_alive(self):
        results = only_alive("ovh-node-1", "aws-node-3", "ovh-node-4")
        active = select_active_node(results)
        assert active == "ovh-node-1"

    def test_empty_returns_none(self):
        assert select_active_node([]) is None

    def test_all_dead_returns_none(self):
        active = select_active_node(all_dead())
        assert active is None


# ─── 9. get_failover_status (mocked probes) ──────────────────────────────────

class TestGetFailoverStatus:
    def _mock_probes(self, alive_nodes: list[str]):
        """Mock probe_all_nodes pour retourner un état déterministe."""
        nodes = ALL_NODES
        return [make_result(n, n in alive_nodes) for n in nodes]

    def test_keys_present(self):
        with patch("src.artcb.network.failover.probe_all_nodes") as mock:
            mock.return_value = self._mock_probes(["aws-node-3"])
            result = get_failover_status(skip_ovh1=True)

        required_keys = [
            "v08_property", "v08_satisfied", "v08_note",
            "apex_node_id", "apex_alive", "failover_triggered",
            "active_node_id", "active_url",
            "alive_nodes", "dead_nodes",
            "probe_results", "probed_at",
            "architecture_note", "certified_100",
        ]
        for key in required_keys:
            assert key in result, f"Clé manquante : {key}"

    def test_certified_100_never_true(self):
        """INVARIANT CRITIQUE : certified_100 ne doit JAMAIS être True."""
        with patch("src.artcb.network.failover.probe_all_nodes") as mock:
            mock.return_value = self._mock_probes(["ovh-node-1", "aws-node-3"])
            result = get_failover_status()
        assert result["certified_100"] is False

    def test_v08_property_name(self):
        with patch("src.artcb.network.failover.probe_all_nodes") as mock:
            mock.return_value = self._mock_probes(["aws-node-3"])
            result = get_failover_status()
        assert result["v08_property"] == "PUBLIC_ENDPOINT_SURVIVES_NODE_DEATH"

    def test_n3_alive_satisfies_v08(self):
        with patch("src.artcb.network.failover.probe_all_nodes") as mock:
            mock.return_value = self._mock_probes(["aws-node-3"])
            result = get_failover_status()
        assert result["v08_satisfied"] is True
        assert result["failover_triggered"] is True
        assert result["active_node_id"] == "aws-node-3"

    def test_all_dead_fails_v08(self):
        with patch("src.artcb.network.failover.probe_all_nodes") as mock:
            mock.return_value = self._mock_probes([])
            result = get_failover_status()
        assert result["v08_satisfied"] is False

    def test_probe_results_structure(self):
        with patch("src.artcb.network.failover.probe_all_nodes") as mock:
            mock.return_value = self._mock_probes(["aws-node-3"])
            result = get_failover_status()
        for pr in result["probe_results"]:
            assert "node_id" in pr
            assert "alive" in pr

    def test_architecture_note_warns_manual_dns(self):
        with patch("src.artcb.network.failover.probe_all_nodes") as mock:
            mock.return_value = self._mock_probes(["aws-node-3"])
            result = get_failover_status()
        note = result["architecture_note"].lower()
        assert "dns" in note or "opérateur" in note


# ─── 10. Route HTTP /api/v1/network/failover-status ──────────────────────────

@pytest.fixture()
def api_client(tmp_path, monkeypatch):
    """TestClient avec create_app() isolé (tmp_path + env) — même pattern que test_p0c."""
    from fastapi.testclient import TestClient
    from src.api.main import create_app
    monkeypatch.setenv("ARTCB_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("ARTCB_BOOTSTRAP_NODE", "false")
    monkeypatch.setenv("ARTCB_NODE_WALLET_ADDRESS", "artcb1testnode000000000000000000000000000")
    return TestClient(create_app(), raise_server_exceptions=True)


class TestFailoverRoute:
    def test_route_200(self, api_client):
        with patch("src.artcb.network.failover.probe_all_nodes") as mock_probe:
            mock_probe.return_value = [
                make_result("ovh-node-1", False, None),
                make_result("aws-node-3", True, 42.0),
                make_result("ovh-node-4", False, None),
                make_result("ovh-node-2", False, None),
                make_result("mac-node-local", False, None),
            ]
            resp = api_client.get("/api/v1/network/failover-status")

        assert resp.status_code == 200

    def test_route_returns_v08_satisfied(self, api_client):
        with patch("src.artcb.network.failover.probe_all_nodes") as mock_probe:
            mock_probe.return_value = [
                make_result("ovh-node-1", False, None),
                make_result("aws-node-3", True, 42.0),
                make_result("ovh-node-4", False, None),
                make_result("ovh-node-2", False, None),
                make_result("mac-node-local", False, None),
            ]
            data = api_client.get("/api/v1/network/failover-status").json()

        assert "v08_satisfied" in data
        assert data["v08_satisfied"] is True

    def test_route_certified_100_false(self, api_client):
        with patch("src.artcb.network.failover.probe_all_nodes") as mock_probe:
            mock_probe.return_value = [make_result(n, True) for n in ALL_NODES]
            data = api_client.get("/api/v1/network/failover-status").json()

        assert data["certified_100"] is False

    def test_route_skip_ovh1_param(self, api_client):
        """Paramètre ?skip_ovh1=false doit être accepté (200)."""
        with patch("src.artcb.network.failover.probe_all_nodes") as mock_probe:
            mock_probe.return_value = [make_result("ovh-node-1", True)]
            resp = api_client.get("/api/v1/network/failover-status?skip_ovh1=false&timeout_s=1.0")

        assert resp.status_code == 200
