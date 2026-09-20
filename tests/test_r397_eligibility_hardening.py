"""Tests R397 — NetworkEligibilityGate forensic hardening.

Couvre les 6 correctifs de l'audit expert :
  T31–T36  : ExternalProbeStore réel (record_external_probe / external_probe_summary)
  T37–T40  : ConnectivityFailure enum (NETWORK_DOWN vs ARTCB_UNREACHABLE vs TLS_INTERCEPTED)
  T41–T45  : Classification NAT étendue (CGNAT RFC6598, IPv6 ULA, link-local)
  T46–T48  : _get_local_ip() multi-fallback robuste
  T49–T52  : Multi-seeds outbound (artcb_reachable ≠ outbound_tcp)
  T53–T55  : on_network_change() réinitialise le store de probes externes
  T56–T58  : Invariants de sécurité R397 (economic_impact=none, to_dict complet)

CERTIFIED_100=false | MODE DEBUG actif
"""

from __future__ import annotations

import time
import ipaddress
import pytest

from src.artcb.network.eligibility_gate import (
    ConnectivityFailure,
    NatClass,
    NetworkCapability,
    NetworkEligibilityGate,
    NetworkState,
    _classify_connectivity_failure,
    _classify_nat,
    assess_network_capability,
    classify_network_state,
    MAX_EXTERNAL_PROBE_HISTORY,
)


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _gate(*, port: int = 19999) -> NetworkEligibilityGate:
    return NetworkEligibilityGate(
        node_id="test-r397-artcb1",
        p2p_port=port,
        probe_host="127.0.0.254",
        probe_port=19998,
    )


# ─── T31–T36 : ExternalProbeStore réel ───────────────────────────────────────

class TestExternalProbeStore:
    def test_T31_record_stores_probe(self):
        """T31 — record_external_probe() stocke la preuve (≠ stub vide R382)."""
        gate = _gate()
        gate.record_external_probe(success=True, probe_node_id="node-ovh2")
        summary = gate.external_probe_summary()
        assert summary["count"] == 1
        assert summary["ok"] == 1
        assert summary["fail"] == 0
        assert summary["reachable"] is True

    def test_T32_record_distinct_nodes(self):
        """T32 — distinct_nodes compte les nœuds sources uniques."""
        gate = _gate()
        gate.record_external_probe(success=True, probe_node_id="node-ovh2")
        gate.record_external_probe(success=True, probe_node_id="node-aws3")
        gate.record_external_probe(success=False, probe_node_id="node-ovh2")  # doublon
        summary = gate.external_probe_summary()
        assert summary["distinct_nodes"] == 2  # ovh2 + aws3
        assert summary["count"] == 3
        assert summary["ok"] == 2

    def test_T33_record_failure_decrements_ok(self):
        """T33 — probe failure ne compte pas dans ok."""
        gate = _gate()
        gate.record_external_probe(success=False, probe_node_id="node-ovh4")
        summary = gate.external_probe_summary()
        assert summary["ok"] == 0
        assert summary["fail"] == 1
        assert summary["reachable"] is False

    def test_T34_assess_uses_stored_probes(self):
        """T34 — assess() utilise les preuves stockées automatiquement."""
        gate = _gate()
        # Injecter 2 probes externes réussies AVANT assess
        gate.record_external_probe(success=True, probe_node_id="node-ovh2")
        gate.record_external_probe(success=True, probe_node_id="node-aws3")

        # assess() avec outbound forcé True — doit devenir DIRECT grâce aux probes externes
        result = gate.assess(_force_outbound=True, _force_inbound=False)
        assert result.network_state == NetworkState.DIRECT
        assert result.capability.external_reachable is True
        assert result.capability.external_probe_ok == 2

    def test_T35_probe_store_max_history(self):
        """T35 — le store ne dépasse pas MAX_EXTERNAL_PROBE_HISTORY entrées."""
        gate = _gate()
        for i in range(MAX_EXTERNAL_PROBE_HISTORY + 20):
            gate.record_external_probe(success=True, probe_node_id=f"node-{i}")
        assert gate._external_probe_count == MAX_EXTERNAL_PROBE_HISTORY + 20
        assert len(gate._external_probes) == MAX_EXTERNAL_PROBE_HISTORY  # taille max

    def test_T36_unknown_probe_node_not_counted_distinct(self):
        """T36 — probe_node_id='unknown' ne compte pas dans distinct_nodes."""
        gate = _gate()
        gate.record_external_probe(success=True, probe_node_id="unknown")
        gate.record_external_probe(success=True)  # défaut = "unknown"
        summary = gate.external_probe_summary()
        assert summary["distinct_nodes"] == 0  # "unknown" exclu


# ─── T37–T40 : ConnectivityFailure enum ──────────────────────────────────────

class TestConnectivityFailure:
    def test_T37_network_down_all_fail(self):
        """T37 — seeds_ok=0, tcp_ok=False → NETWORK_DOWN."""
        cf = _classify_connectivity_failure(
            seeds_ok=0, artcb_ok=False, tls_ok=False, tcp_ok=False
        )
        assert cf == ConnectivityFailure.NETWORK_DOWN

    def test_T38_artcb_unreachable_only_artcb_down(self):
        """T38 — seeds alternatifs ok mais artcb fail → ARTCB_UNREACHABLE."""
        cf = _classify_connectivity_failure(
            seeds_ok=2, artcb_ok=False, tls_ok=True, tcp_ok=True
        )
        assert cf == ConnectivityFailure.ARTCB_UNREACHABLE

    def test_T39_tls_intercepted_tcp_ok_tls_fail(self):
        """T39 — TCP ok mais TLS fail → TLS_INTERCEPTED."""
        cf = _classify_connectivity_failure(
            seeds_ok=1, artcb_ok=True, tls_ok=False, tcp_ok=True
        )
        assert cf == ConnectivityFailure.TLS_INTERCEPTED

    def test_T40_none_all_ok(self):
        """T40 — tout ok → NONE."""
        cf = _classify_connectivity_failure(
            seeds_ok=3, artcb_ok=True, tls_ok=True, tcp_ok=True
        )
        assert cf == ConnectivityFailure.NONE

    def test_T40b_force_outbound_false_sets_network_down(self):
        """T40b — _force_outbound=False → connectivity_failure=NETWORK_DOWN + captive_portal=True."""
        cap = assess_network_capability(
            _force_outbound=False,
            probe_host="127.0.0.254",
            probe_port=19998,
        )
        assert cap.connectivity_failure == ConnectivityFailure.NETWORK_DOWN
        assert cap.captive_portal is True

    def test_T40c_force_outbound_true_sets_none(self):
        """T40c — _force_outbound=True → connectivity_failure=NONE + captive_portal=False."""
        cap = assess_network_capability(
            _force_outbound=True,
            probe_host="127.0.0.254",
            probe_port=19998,
        )
        assert cap.connectivity_failure == ConnectivityFailure.NONE
        assert cap.captive_portal is False


# ─── T41–T45 : Classification NAT étendue ────────────────────────────────────

class TestNatClassification:
    def test_T41_cgnat_rfc6598(self):
        """T41 — 100.64.0.1 (RFC 6598 CGNAT) → NatClass.CGNAT."""
        nc = _classify_nat("100.64.0.1", external_reachable=False)
        assert nc == NatClass.CGNAT

    def test_T42_cgnat_rfc6598_boundary(self):
        """T42 — 100.127.255.255 (limite haute RFC 6598) → NatClass.CGNAT."""
        nc = _classify_nat("100.127.255.255", external_reachable=False)
        assert nc == NatClass.CGNAT

    def test_T43_rfc1918_restricted(self):
        """T43 — 192.168.1.1 sans preuve externe → RESTRICTED."""
        nc = _classify_nat("192.168.1.1", external_reachable=False)
        assert nc == NatClass.RESTRICTED

    def test_T44_rfc1918_full_cone_with_proof(self):
        """T44 — 10.0.0.5 avec preuve externe → FULL_CONE."""
        nc = _classify_nat("10.0.0.5", external_reachable=True)
        assert nc == NatClass.FULL_CONE

    def test_T45_ipv6_ula(self):
        """T45 — fc00::1 (IPv6 ULA fc00::/7) → IPV6_ULA."""
        nc = _classify_nat("fc00::1", external_reachable=False)
        assert nc == NatClass.IPV6_ULA

    def test_T45b_link_local(self):
        """T45b — 169.254.1.1 (link-local) → LINK_LOCAL."""
        nc = _classify_nat("169.254.1.1", external_reachable=False)
        assert nc == NatClass.LINK_LOCAL

    def test_T45c_public_ip(self):
        """T45c — IP publique routable → NONE."""
        nc = _classify_nat("151.80.107.29", external_reachable=False)
        assert nc == NatClass.NONE

    def test_T45d_loopback(self):
        """T45d — 127.0.0.1 (loopback) → UNKNOWN."""
        nc = _classify_nat("127.0.0.1", external_reachable=False)
        assert nc == NatClass.UNKNOWN


# ─── T46–T48 : _get_local_ip multi-fallback ──────────────────────────────────

class TestGetLocalIp:
    def test_T46_returns_string(self):
        """T46 — _get_local_ip() retourne une chaîne non vide."""
        from src.artcb.network.eligibility_gate import _get_local_ip
        ip = _get_local_ip()
        assert isinstance(ip, str)
        assert len(ip) > 0

    def test_T47_parseable_as_ip(self):
        """T47 — _get_local_ip() retourne une adresse IP valide ou '127.0.0.1'."""
        from src.artcb.network.eligibility_gate import _get_local_ip
        ip = _get_local_ip()
        try:
            ipaddress.ip_address(ip)
        except ValueError:
            pytest.fail(f"_get_local_ip() a retourné une valeur non-IP: {ip!r}")

    def test_T48_not_empty_string(self):
        """T48 — _get_local_ip() ne retourne jamais une chaîne vide."""
        from src.artcb.network.eligibility_gate import _get_local_ip
        ip = _get_local_ip()
        assert ip != ""
        assert ip != "0.0.0.0"


# ─── T49–T52 : Multi-seeds outbound ──────────────────────────────────────────

class TestMultiSeeds:
    def test_T49_force_outbound_true_sets_artcb_reachable(self):
        """T49 — _force_outbound=True → artcb_reachable=True."""
        cap = assess_network_capability(
            _force_outbound=True,
            probe_host="127.0.0.254",
            probe_port=19998,
        )
        assert cap.artcb_reachable is True
        assert cap.outbound_seeds_ok > 0

    def test_T50_force_outbound_false_sets_artcb_unreachable(self):
        """T50 — _force_outbound=False → artcb_reachable=False, seeds_ok=0."""
        cap = assess_network_capability(
            _force_outbound=False,
            probe_host="127.0.0.254",
            probe_port=19998,
        )
        assert cap.artcb_reachable is False
        assert cap.outbound_seeds_ok == 0

    def test_T51_artcb_reachable_in_to_dict(self):
        """T51 — artcb_reachable présent dans to_dict()."""
        cap = assess_network_capability(
            _force_outbound=True,
            probe_host="127.0.0.254",
            probe_port=19998,
        )
        d = cap.to_dict()
        assert "artcb_reachable" in d
        assert "outbound_seeds_ok" in d
        assert "connectivity_failure" in d

    def test_T52_connectivity_failure_in_to_dict(self):
        """T52 — connectivity_failure présent et valeur valide dans to_dict()."""
        cap = assess_network_capability(
            _force_outbound=False,
            probe_host="127.0.0.254",
            probe_port=19998,
        )
        d = cap.to_dict()
        assert d["connectivity_failure"] == ConnectivityFailure.NETWORK_DOWN.value


# ─── T53–T55 : on_network_change réinitialise le store ───────────────────────

class TestNetworkChangeResetsStore:
    def test_T53_on_network_change_clears_external_probes(self):
        """T53 — on_network_change() réinitialise le store de probes externes."""
        gate = _gate()
        gate.record_external_probe(success=True, probe_node_id="node-ovh2")
        gate.record_external_probe(success=True, probe_node_id="node-aws3")
        assert gate._external_probe_count == 2

        gate.on_network_change(reason="wifi_changed")
        assert gate._external_probe_count == 0
        assert gate._external_probe_ok == 0
        assert len(gate._external_distinct_nodes) == 0

    def test_T54_external_probe_summary_after_reset(self):
        """T54 — external_probe_summary() après reset = zéro propre."""
        gate = _gate()
        gate.record_external_probe(success=True, probe_node_id="node-ovh2")
        gate.on_network_change()
        summary = gate.external_probe_summary()
        assert summary["count"] == 0
        assert summary["ok"] == 0
        assert summary["reachable"] is False
        assert summary["last_ts_ns"] is None

    def test_T55_to_dict_includes_external_probe_summary(self):
        """T55 — to_dict() contient external_probe_summary."""
        gate = _gate()
        gate.record_external_probe(success=True, probe_node_id="node-ovh2")
        gate.assess(_force_outbound=True)
        d = gate.to_dict()
        assert "external_probe_summary" in d
        assert d["external_probe_summary"]["count"] >= 1


# ─── T56–T58 : Invariants R397 ───────────────────────────────────────────────

class TestR397Invariants:
    def test_T56_economic_impact_none_with_new_fields(self):
        """T56 — economic_impact='none' même avec connectivity_failure=NETWORK_DOWN."""
        cap = assess_network_capability(
            _force_outbound=False,
            probe_host="127.0.0.254",
            probe_port=19998,
        )
        assert cap.connectivity_failure == ConnectivityFailure.NETWORK_DOWN
        result = classify_network_state(cap)
        assert result.economic_impact == "none"

    def test_T57_module_version_updated(self):
        """T57 — MODULE_VERSION = 1.1.0 (R397)."""
        from src.artcb.network import eligibility_gate
        assert eligibility_gate.MODULE_VERSION == "1.1.0"

    def test_T58_nat_cgnat_does_not_imply_suspended(self):
        """T58 — CGNAT seul ne provoque pas SUSPENDED (outbound ok + relay)."""
        # CGNAT : relay_available=True → doit donner RELAYABLE, pas SUSPENDED
        cap = NetworkCapability()
        cap.outbound_tcp = True
        cap.nat_class = NatClass.CGNAT
        cap.relay_available = True
        cap.external_probe_count = 0
        cap.external_reachable = False
        result = classify_network_state(cap)
        # CGNAT + relay → RELAYABLE (pas SUSPENDED)
        assert result.network_state == NetworkState.RELAYABLE
        assert result.economic_impact == "none"
