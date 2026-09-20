"""Tests R382 — NetworkEligibilityGate.

Couvre les scénarios du rapport expert (§32) :
  T01–T05  : connectivité de base (outbound/inbound/relay)
  T06–T12  : états DIRECT / RELAYABLE / DEGRADED / SUSPENDED / INDETERMINATE
  T13–T16  : fenêtre de grâce DEGRADED → SUSPENDED
  T17–T20  : anti-flap (MIN_PASS_STREAK)
  T21–T25  : NetworkEligibilityGate (cycle de vie, on_network_change)
  T26–T30  : invariants de sécurité (economic_impact, séparation états)

CERTIFIED_100=false | MODE DEBUG actif
"""

from __future__ import annotations

import time
import pytest

from src.artcb.network.eligibility_gate import (
    NetworkCapability,
    NetworkEligibilityGate,
    NetworkState,
    NatClass,
    assess_network_capability,
    classify_network_state,
    DEGRADED_GRACE_S,
    MIN_PASS_STREAK,
)


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _cap(
    *,
    outbound: bool = True,
    inbound: bool = False,
    external: bool = False,
    external_count: int = 0,
    external_ok: int = 0,
    relay: bool = False,
    captive: bool = False,
    nat: NatClass = NatClass.RESTRICTED,
) -> NetworkCapability:
    """Construit une NetworkCapability synthétique pour les tests."""
    cap = NetworkCapability()
    cap.outbound_tcp = outbound
    cap.outbound_tls = outbound
    cap.outbound_websocket = outbound
    cap.inbound_listen = inbound
    cap.external_reachable = external
    cap.external_probe_count = external_count
    cap.external_probe_ok = external_ok
    cap.relay_available = relay
    cap.captive_portal = captive
    cap.nat_class = nat
    return cap


def _gate(*, port: int = 19999) -> NetworkEligibilityGate:
    """Crée un gate de test avec host inaccessible (pas de vraie connexion réseau)."""
    return NetworkEligibilityGate(
        node_id="test-node-artcb1",
        p2p_port=port,
        probe_host="127.0.0.254",   # IP locale non routable → outbound échoue toujours
        probe_port=19998,
    )


# ─── T01–T05 : NetworkCapability construction ────────────────────────────────

class TestNetworkCapability:
    def test_T01_default_values(self):
        """T01 — NetworkCapability créée avec valeurs conservatrices."""
        cap = NetworkCapability()
        assert cap.outbound_tcp is False
        assert cap.inbound_listen is False
        assert cap.external_reachable is False
        assert cap.relay_available is False
        assert cap.captive_portal is False
        assert cap.nat_class == NatClass.UNKNOWN

    def test_T02_to_dict_keys(self):
        """T02 — to_dict contient tous les champs obligatoires."""
        cap = _cap(outbound=True, inbound=True, external=True)
        d = cap.to_dict()
        for key in ["outbound_tcp", "inbound_listen", "external_reachable",
                    "relay_available", "nat_class", "captive_portal", "ts_ns"]:
            assert key in d, f"Champ manquant: {key}"

    def test_T03_assess_force_outbound_true(self):
        """T03 — _force_outbound=True => outbound_tcp/tls/ws tous True."""
        cap = assess_network_capability(
            _force_outbound=True,
            _force_inbound=False,
            probe_host="127.0.0.254",
            probe_port=19998,
        )
        assert cap.outbound_tcp is True
        assert cap.outbound_tls is True
        assert cap.outbound_websocket is True
        assert cap.captive_portal is False

    def test_T04_assess_force_outbound_false_captive(self):
        """T04 — outbound fail => captive_portal=True."""
        cap = assess_network_capability(
            _force_outbound=False,
            _force_inbound=False,
            probe_host="127.0.0.254",
            probe_port=19998,
        )
        assert cap.outbound_tcp is False
        assert cap.captive_portal is True

    def test_T05_assess_force_inbound(self):
        """T05 — _force_inbound=True => inbound_listen=True."""
        cap = assess_network_capability(
            _force_outbound=True,
            _force_inbound=True,
            probe_host="127.0.0.254",
            probe_port=19998,
        )
        assert cap.inbound_listen is True


# ─── T06–T12 : classify_network_state ────────────────────────────────────────

class TestClassifyNetworkState:
    def test_T06_direct_by_external_probe(self):
        """T06 — external_reachable + external_probe_ok > 0 → DIRECT."""
        cap = _cap(outbound=True, external=True, external_count=3, external_ok=3,
                   nat=NatClass.RESTRICTED)
        result = classify_network_state(cap)
        assert result.network_state == NetworkState.DIRECT
        assert result.recommended_action == "none"
        assert result.economic_impact == "none"

    def test_T07_direct_by_public_ip(self):
        """T07 — IP publique (nat=NONE) + inbound_listen → DIRECT."""
        cap = _cap(outbound=True, inbound=True, nat=NatClass.NONE)
        result = classify_network_state(cap)
        assert result.network_state == NetworkState.DIRECT

    def test_T08_relayable(self):
        """T08 — outbound ok, inbound fail, relay disponible → RELAYABLE."""
        cap = _cap(outbound=True, inbound=False, relay=True, external=False)
        result = classify_network_state(cap)
        assert result.network_state == NetworkState.RELAYABLE
        assert result.recommended_action == "use_relay"

    def test_T09_degraded_first_time(self):
        """T09 — outbound ok, inbound fail, relay absent, première fois → DEGRADED."""
        cap = _cap(outbound=True, inbound=False, relay=False, external_count=1, external_ok=0)
        result = classify_network_state(cap, degraded_since_ts_ns=None)
        assert result.network_state == NetworkState.DEGRADED
        assert result.grace_remaining_s == DEGRADED_GRACE_S

    def test_T10_suspended_captive_portal(self):
        """T10 — captive portal → SUSPENDED."""
        cap = _cap(outbound=False, captive=True)
        result = classify_network_state(cap)
        assert result.network_state == NetworkState.SUSPENDED
        assert result.recommended_action == "suspend_node"
        assert result.grace_remaining_s == 0

    def test_T11_suspended_no_outbound(self):
        """T11 — pas de connectivité sortante → SUSPENDED."""
        cap = _cap(outbound=False, captive=False)
        result = classify_network_state(cap)
        assert result.network_state == NetworkState.SUSPENDED

    def test_T12_indeterminate_no_probe(self):
        """T12 — outbound ok, inbound fail, relay absent, aucune probe externe → INDETERMINATE."""
        cap = _cap(outbound=True, inbound=False, relay=False,
                   external=False, external_count=0, external_ok=0)
        result = classify_network_state(cap)
        assert result.network_state == NetworkState.INDETERMINATE
        assert result.recommended_action == "reassess"


# ─── T13–T16 : fenêtre de grâce DEGRADED ────────────────────────────────────

class TestDegradedGrace:
    def test_T13_degraded_within_grace(self):
        """T13 — DEGRADED depuis 10s (< DEGRADED_GRACE_S) → reste DEGRADED."""
        degraded_since = time.time_ns() - 10 * 1_000_000_000  # 10 secondes
        cap = _cap(outbound=True, inbound=False, relay=False,
                   external_count=1, external_ok=0)
        result = classify_network_state(cap, degraded_since_ts_ns=degraded_since)
        assert result.network_state == NetworkState.DEGRADED
        assert result.grace_remaining_s is not None
        assert result.grace_remaining_s > 0
        assert result.grace_remaining_s < DEGRADED_GRACE_S

    def test_T14_degraded_grace_expired(self):
        """T14 — DEGRADED depuis > DEGRADED_GRACE_S → SUSPENDED."""
        # Simuler grâce expirée
        expired_ts = time.time_ns() - (DEGRADED_GRACE_S + 60) * 1_000_000_000
        cap = _cap(outbound=True, inbound=False, relay=False,
                   external_count=1, external_ok=0)
        result = classify_network_state(cap, degraded_since_ts_ns=expired_ts)
        assert result.network_state == NetworkState.SUSPENDED
        assert result.grace_remaining_s == 0

    def test_T15_degraded_grace_resets_on_direct(self):
        """T15 — si la machine redevient DIRECT, la grâce se réinitialise."""
        gate = _gate()
        # Simuler DEGRADED + grâce non expirée
        gate._degraded_since_ts_ns = time.time_ns() - 10 * 1_000_000_000

        # Maintenant la machine est DIRECT (external_probe ok)
        result = gate.assess(
            _force_outbound=True,
            _force_inbound=True,
            external_reachable=True,
            external_probe_count=3,
            external_probe_ok=3,
        )
        assert result.network_state == NetworkState.DIRECT
        assert gate._degraded_since_ts_ns is None  # grâce réinitialisée

    def test_T16_economic_impact_always_none(self):
        """T16 — invariant : economic_impact='none' même en SUSPENDED."""
        expired_ts = time.time_ns() - (DEGRADED_GRACE_S + 60) * 1_000_000_000
        cap = _cap(outbound=True, inbound=False, relay=False,
                   external_count=1, external_ok=0)
        result = classify_network_state(cap, degraded_since_ts_ns=expired_ts)
        assert result.network_state == NetworkState.SUSPENDED
        assert result.economic_impact == "none"  # INVARIANT


# ─── T17–T20 : anti-flap ─────────────────────────────────────────────────────

class TestAntiFlap:
    def test_T17_antiflap_requires_streak(self):
        """T17 — 1 succès depuis SUSPENDED ne suffit pas (streak < MIN_PASS_STREAK)."""
        gate = _gate()
        gate._current_state = NetworkState.SUSPENDED  # forcer état SUSPENDED

        result = gate.assess(
            _force_outbound=True,
            _force_inbound=True,
            external_reachable=True,
            external_probe_count=3,
            external_probe_ok=3,
        )
        # Avec MIN_PASS_STREAK=2 et streak=0 avant, premier passage → streak=1 → reste SUSPENDED
        if MIN_PASS_STREAK > 1:
            assert result.network_state == NetworkState.SUSPENDED
            assert gate._pass_streak == 1
        else:
            # Si MIN_PASS_STREAK=1, un seul succès suffit
            assert result.network_state == NetworkState.DIRECT

    def test_T18_antiflap_passes_after_streak(self):
        """T18 — après MIN_PASS_STREAK succès consécutifs → DIRECT autorisé."""
        gate = _gate()
        gate._current_state = NetworkState.SUSPENDED
        gate._pass_streak = MIN_PASS_STREAK - 1  # dernier succès requis

        result = gate.assess(
            _force_outbound=True,
            _force_inbound=True,
            external_reachable=True,
            external_probe_count=3,
            external_probe_ok=3,
        )
        assert result.network_state == NetworkState.DIRECT

    def test_T19_antiflap_reset_on_fail(self):
        """T19 — un échec remet le streak à 0."""
        gate = _gate()
        gate._pass_streak = MIN_PASS_STREAK - 1

        gate.assess(_force_outbound=False)  # fail → streak reset
        assert gate._pass_streak == 0

    def test_T20_antiflap_not_triggered_from_unknown(self):
        """T20 — depuis UNKNOWN (pas SUSPENDED) → pas d'anti-flap."""
        gate = _gate()
        assert gate._current_state == NetworkState.UNKNOWN

        result = gate.assess(
            _force_outbound=True,
            _force_inbound=True,
            external_reachable=True,
            external_probe_count=2,
            external_probe_ok=2,
        )
        assert result.network_state == NetworkState.DIRECT
        assert gate._pass_streak == 0  # anti-flap non déclenché


# ─── T21–T25 : NetworkEligibilityGate cycle de vie ───────────────────────────

class TestNetworkEligibilityGate:
    def test_T21_initial_state_unknown(self):
        """T21 — état initial = UNKNOWN."""
        gate = _gate()
        assert gate.current_state == NetworkState.UNKNOWN
        assert gate.last_result is None

    def test_T22_assess_updates_state(self):
        """T22 — assess() met à jour current_state."""
        gate = _gate()
        result = gate.assess(_force_outbound=False)
        assert gate.current_state == NetworkState.SUSPENDED
        assert gate.last_result is not None

    def test_T23_on_network_change_resets_grace(self):
        """T23 — on_network_change() réinitialise la fenêtre de grâce."""
        gate = _gate()
        gate._degraded_since_ts_ns = time.time_ns() - 60 * 1_000_000_000  # 60s

        gate.on_network_change(reason="wifi_changed")
        assert gate._degraded_since_ts_ns is None

    def test_T24_history_tracks_transitions(self):
        """T24 — historique enregistre les transitions."""
        gate = _gate()
        gate.assess(_force_outbound=False)  # SUSPENDED
        gate.assess(_force_outbound=False)  # SUSPENDED
        assert len(gate.history()) == 2
        assert gate.history()[0]["network_state"] == NetworkState.SUSPENDED.value

    def test_T25_to_dict_structure(self):
        """T25 — to_dict() retourne les champs attendus."""
        gate = _gate()
        gate.assess(_force_outbound=True, _force_inbound=False)
        d = gate.to_dict()
        assert "node_id" in d
        assert "current_state" in d
        assert "last_result" in d
        assert d["last_result"] is not None


# ─── T26–T30 : invariants de sécurité ────────────────────────────────────────

class TestSecurityInvariants:
    def test_T26_economic_impact_never_set(self):
        """T26 — invariant : economic_impact='none' dans tous les cas."""
        for outbound, inbound, relay in [
            (True, True, False),
            (True, False, True),
            (True, False, False),
            (False, False, False),
        ]:
            cap = _cap(outbound=outbound, inbound=inbound, relay=relay,
                       external_count=1 if not outbound else 0)
            result = classify_network_state(cap)
            assert result.economic_impact == "none", (
                f"economic_impact doit être 'none' — outbound={outbound} inbound={inbound} "
                f"relay={relay} → state={result.network_state}"
            )

    def test_T27_economic_state_unchanged_flag(self):
        """T27 — _economic_state_unchanged=True dans tous les résultats."""
        for force_out in [True, False]:
            gate = _gate()
            result = gate.assess(_force_outbound=force_out)
            assert result._economic_state_unchanged is True

    def test_T28_node_id_preserved_across_transitions(self):
        """T28 — node_id ne change pas après transitions réseau."""
        gate = _gate()
        node_id_before = gate.node_id
        gate.assess(_force_outbound=False)
        gate.on_network_change()
        gate.assess(_force_outbound=True, external_reachable=True,
                    external_probe_count=3, external_probe_ok=3)
        assert gate.node_id == node_id_before  # identité préservée

    def test_T29_suspended_does_not_wipe_history(self):
        """T29 — SUSPENDED ne supprime pas l'historique du nœud."""
        gate = _gate()
        gate.assess(_force_outbound=True, _force_inbound=True,
                    external_reachable=True, external_probe_count=2, external_probe_ok=2)
        gate.assess(_force_outbound=False)  # SUSPENDED
        assert len(gate.history()) == 2  # historique conservé
        assert gate.history()[0]["network_state"] == NetworkState.DIRECT.value

    def test_T30_eligibility_result_to_dict_complete(self):
        """T30 — EligibilityResult.to_dict() contient tous les champs attendus."""
        cap = _cap(outbound=True, relay=True)
        result = classify_network_state(cap)
        d = result.to_dict()
        required = [
            "ts_ns", "network_state", "reason", "recommended_action",
            "grace_remaining_s", "economic_impact", "economic_state_unchanged",
            "capability",
        ]
        for key in required:
            assert key in d, f"Champ manquant dans EligibilityResult.to_dict(): {key}"
        assert d["economic_impact"] == "none"
        assert d["economic_state_unchanged"] is True
