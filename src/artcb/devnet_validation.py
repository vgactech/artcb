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
        "rule": "Implements D-032 B + D-034 A: hybrid verify is AND (Ed25519 and ML-DSA). Capability history bound to KEM fingerprint + signed card. Unsigned PQC claims are not trusted.",
    },
}

PROFILE: Final[str] = "B-balanced"

# Expert 2026-08-31 numbering collided with existing D-033 (DV profile).
# Locked as D-034/D-035/D-036.
DECISIONS_174: Final[dict[str, str]] = {
    "D-034": "A — hybrid verify AND (both legs). Expert labelled this D-033 A; D-033 already used.",
    "D-035": "B — all possible tests on the 3 live nodes; NODE4 later. Expert D-034 B.",
    "D-036": "B — keep OVH1 on 5b4b24ae for inter-version DV-03. Expert D-035 B.",
}

# Operator 2026-08-31: NODE4 credentials + project ready after PRE-DV-04 PASS.
DECISIONS_175: Final[dict[str, str]] = {
    "D-037": (
        "GO NODE4 — create OVH4 on nic xy4589-ovh / project "
        "926bb1d6755e4f2c98ae9db06ef44e4f (GRA11 d2-8). Amends D-035 "
        "(NODE4 later) because PRE-DV-04 already PASS. OVH1 stays on "
        "5b4b24ae (D-036). Protocol remains 174-devnet-1 so OVH2/AWS3/OVH4 "
        "are homogeneous. DV-04 C still needs 4 protocol-compatible nodes; "
        "OVH1 legacy does not count."
    ),
}

DECISIONS_177: Final[dict[str, str]] = {
    "D-038": (
        "Replit substitutes OVH1 role for 174 tests. Do not redeploy "
        "152.228.144.34. Replit must pull cursor/replit-sync-ready-16d8."
    ),
}

DECISIONS_178: Final[dict[str, str]] = {
    "D-039": (
        "Adversarial Replit audit before wallet init. Health PQC available "
        "is not path enforcement. Git sync pins SHA (Architecture A)."
    ),
}

# Operator 2026-09-01: explicit exception — update every OVH node including OVH1.
DECISIONS_186: Final[dict[str, str]] = {
    "D-040": (
        "GO OVH1 174 — explicit exception to D-036. Deploy "
        "cursor/replit-sync-ready-16d8 (same tip as OVH2/OVH4/AWS3). "
        "Preserve wallets: git fetch + restart, no install.sh. "
        "Replit Autoscale paused. DV-04 C still needs identical "
        "last_hash on four live machines after a public TX."
    ),
}

# Operator 2026-09-01: put OVH1 on the same public book as OVH2/AWS3/OVH4.
DECISIONS_187: Final[dict[str, str]] = {
    "D-041": (
        "GO OVH1 same public book — operator authorized all four nodes. "
        "OVH1 orphan genesis 8d542e49 (2026-08-29) cannot extend the "
        "homogeneous chain genesis cc61f710 (2026-08-31); P2P pull is "
        "not a merge. Adopt the existing 7-block public book from OVH2, "
        "backup the orphan file, keep wallets/chain.key. DV-04 C PASS "
        "only after a public TX then one restart with four identical "
        "last_hash and public_state_digest. Not certified mainnet."
    ),
}


def public_lock() -> dict[str, Any]:
    return {
        "economic_v_series": ECONOMIC_V,
        "economic_v_locked": False,
        "distributed_profile": PROFILE,
        "distributed": DV,
        "distributed_certified": False,
        "decisions_174": DECISIONS_174,
        "decisions_175": DECISIONS_175,
        "decisions_177": DECISIONS_177,
        "decisions_178": DECISIONS_178,
        "decisions_186": DECISIONS_186,
        "decisions_187": DECISIONS_187,
        "note": "Choosing DV letters is the validation protocol, not a PASS.",
    }
