"""Distributed / operational validations DV-01…DV-07 (distinct from economic V-01…V-07).

Economic V-01…V-07 remain the tokenomics locks in economic_snapshot.py (still
provisional until a separate GO). This module records the 2026-08-31 user
choices for live multi-node validation.
"""

from __future__ import annotations

from typing import Any, Final

# Economic series — DO NOT reuse these letters for identity/P2P/consensus.
ECONOMIC_V: Final[dict[str, str]] = {
    "V-01": "Snapshot at epoch start (Solution A) — provisional",
    "V-02": "Transfer economic effect = next epoch — provisional",
    "V-03": "Reconnect grace = 24h — provisional",
    "V-04": "Retirement effect = next snapshot — provisional",
    "V-05": "Finality = N confirmations (default 2) — provisional",
    "V-06": "H_adult_max = versioned DemographicReference — provisional",
    "V-07": "HBP 10→60→20 on H_verified/H_adult_max — provisional",
}

# Operational series locked 2026-08-31 (user letters).
DV: Final[dict[str, dict[str, str]]] = {
    "DV-01": {
        "letter": "C",
        "title": "Identite hybride progressive",
        "rule": "Crypto identity mandatory now; TPM/hardware attestation when available; attestation required later for critical production.",
    },
    "DV-02": {
        "letter": "C",
        "title": "Connectivite P2P reseau hostile",
        "rule": "HTTP/HTTPS/P2P register+remove+reconnect+timeout+invalid peer, then disconnect/latency/flood scenarios on authorized testnet.",
    },
    "DV-03": {
        "letter": "B",
        "title": "Version protocolaire independante du SHA Git",
        "rule": "Peers may differ in git_sha; must match protocol_version + genesis_hash + network_id. No implicit negotiation, no silent downgrade. Evolution toward C later.",
    },
    "DV-04": {
        "letter": "C",
        "title": "Replication d etat sur 4 nœuds live",
        "rule": "PASS only when four live machines show identical state hashes after a transaction. Two-node WAN is a prerequisite, not the lock.",
    },
    "DV-05": {
        "letter": "C",
        "title": "Consensus Byzantine explicite",
        "rule": "Document N/F/Q against the actual code, then honest/offline/delay/double-proposal/divergence scenarios.",
    },
    "DV-06": {
        "letter": "B",
        "title": "Pannes realistes",
        "rule": "OFF, reboot, latency, packet loss, timeout, reconnection. Chaos (C) later on authorized env.",
    },
    "DV-07": {
        "letter": "C",
        "title": "Migration crypto hybride controlee",
        "rule": "Implements D-032 B: ML-DSA-65 preferred, Ed25519 temporary, hybrid signatures when PQC is present, advertised policy + end date, anti-downgrade.",
    },
}

PROFILE: Final[str] = "B-balanced"


def public_lock() -> dict[str, Any]:
    return {
        "economic_v_series": ECONOMIC_V,
        "economic_v_locked": False,
        "distributed_profile": PROFILE,
        "distributed": DV,
        "distributed_certified": False,
        "note": "Choosing DV letters is the validation protocol, not a PASS.",
    }
