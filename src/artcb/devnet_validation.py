"""Distributed / operational validations DV-01…DV-07 (distinct from economic V-01…V-07).

Economic V-01…V-07 locked D-043 (operator GO 2026-09-01) at the values
already implemented and measured in simulation 167. This module also
records the 2026-08-31 user choices for live multi-node validation.
"""

from __future__ import annotations

from typing import Any, Final

# Economic series — DO NOT reuse these letters for identity/P2P/consensus.
ECONOMIC_V: Final[dict[str, str]] = {
    "V-01": "A — Snapshot at epoch start (locked D-043, sim 167)",
    "V-02": "next epoch — transfer does not rewrite P(N) mid-epoch (locked D-043)",
    "V-03": "reconnect grace = 24h live / 1s sim (locked D-043)",
    "V-04": "retirement effect = next snapshot (locked D-043)",
    "V-05": "economic finality N=2 confirmations; settlement BFT is DV-05 Q=3 (locked D-043)",
    "V-06": "H_adult_max = versioned DemographicReference model B; Q-E03 UN WPP 2024 18+ extract locked D-045 (no auto-refresh)",
    "V-07": "HBP 10→60→20 on existing absolute anchors 0 / 4.15e9 / 8.30e9 (locked D-043; ratio rewrite not invented)",
}
ECONOMIC_V_LOCKED: Final[bool] = True

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

# Operator 2026-09-01: launch remaining mainnet gates, do not invent certification.
DECISIONS_188: Final[dict[str, str]] = {
    "D-042": (
        "GO remaining mainnet gates — operator asked to launch mainnet now. "
        "Culture forbids renaming 174-devnet-1 or flipping "
        "certified_distributed_mainnet. Wire live prepare/commit BFT "
        "(N=4 F=1 Q=3) from replicated_settlement onto the four VMs. "
        "DV-05 PASS only after honest/offline/delay/double-proposal/"
        "divergence. Economic V-01…V-07 stay provisional (D-026). "
        "Ed25519 window stays until 2026-12-31 (D-032). Test probe "
        "blocks are not a mainnet genesis. Not certified mainnet."
    ),
}

# Operator 2026-09-01: freeze V-01…V-07 as already-running code; open mainnet identity.
DECISIONS_189: Final[dict[str, str]] = {
    "D-043": (
        "GO freeze V-01…V-07 at sim-167 code + open artcb-mainnet-1. "
        "Choices: V-01 A epoch-start snapshot; V-02/V-04 next epoch; "
        "V-03 24h grace; V-05 N=2 economic confirmations (BFT Q=3 is DV-05); "
        "V-06 DemographicReference model B not WPP freeze; V-07 HBP 10→60→20 "
        "absolute anchors already in hbp.py. New genesis: empty the 174 test "
        "probe book, keep wallets/chain.key. Faucet off. Ed25519 window "
        "unchanged until 2026-12-31 (D-032). certified_distributed_mainnet "
        "stays false while DV-02 C flood/chaos is not done."
    ),
}

# Operator 2026-09-01: validate D-043 locks; remaining mainnet tests without Replit wallet.
DECISIONS_190: Final[dict[str, str]] = {
    "D-044": (
        "GO operator validates D-043 V-01…V-07 and artcb-mainnet-1 genesis. "
        "Replit stays bootstrap: no wallet, no init-node. PIN may be an "
        "ancestor of the published tip (fast-forward). P2P mutations require "
        "operator Bearer; register-public is SSRF-allowlisted. Directory "
        "GET /api/v1/network/nodes needs no wallet. DV-02 live flood/partition "
        "is still not done on the mainnet book; local+bounded live probes only. "
        "certified_distributed_mainnet stays false."
    ),
}

# Operator 2026-09-01: identify machines, freeze WPP, chaos on live book, consume seeds.
# Certification is not automatic: all DV PASS is necessary, not sufficient.
OPERATOR_MAINNET_CERTIFICATION_GO: Final[bool] = False

DECISIONS_192: Final[dict[str, str]] = {
    "D-046": (
        "GO hardware-assurance A–E (physical TPM / vTPM / TEE / HSM / software) "
        "reported honestly on /health. Do not invent NitroTPM or SEV when "
        "/dev/tpm0 is absent. Register ovh-baremetal-1 as a 5th TEST machine "
        "(never reuse ovh-node-1). Order the cheapest Eco bare metal only after "
        "OVH3 API keys measure a credit >= SKU price and the SKU is in stock. "
        "Missing OVH3_APPLICATION_KEY / OVH3_NIC is a hard stop, not a guessed "
        "10 EUR balance. Replit CORS stays a platform regex. "
        "certified_distributed_mainnet stays false."
    ),
}

DECISIONS_193: Final[dict[str, str]] = {
    "D-047": (
        "The ~10 EUR is Public Cloud credit on nic xy4589-ovh (OVH4), not "
        "ovhAccount prepaid and not a third OVH3 nic. Measured 2026-09-01: "
        "GET /me 200 nic xy4589-ovh; GET /me/ovhAccount balance 0.00 EUR; "
        "GET /dedicated/server [] (no Eco in delivery); GET /cloud/project/"
        "…/credit 263152 available 10.00 EUR (Credit provisionning) + "
        "263153 available 199.84 EUR (Free Trial). Cloud credit cannot pay "
        "Eco dedicated. Do not order on vc491276-ovh. Do not destroy "
        "91.134.45.8. Eco KS-B 25skb012 9.99 EUR GRA unavailable; cheapest "
        "in-stock KS-5 24sk50-v1 17.99 EUR > prepaid 0.00. Do not charge "
        "the OVH4 CREDIT_CARD. ovh-baremetal-1 stays pending without IP. "
        "certified_distributed_mainnet stays false."
    ),
}

DECISIONS_194: Final[dict[str, str]] = {
    "D-048": (
        "Operator GO on nic xy4589-ovh (OVH4) to order one cheapest currently "
        "available Eco/Kimsufi, including the registered preferred payment "
        "method (CREDIT_CARD) because Public Cloud credit cannot pay a dedicated. "
        "Re-read catalog + GET /dedicated/server first; do not double-order. "
        "Prefer FR datacenter GRA/RBX/SBG. Price the real in-stock FQN "
        "(base + RAM/disk extras), not the unavailable default 0 EUR disk. "
        "One checkout; HTTP 400/402 is terminal (no retry loop). Never destroy "
        "91.134.45.8. No install.sh wipe, no origin/main deploy, no invented "
        "TPM/IP/balance. certified_distributed_mainnet stays false."
    ),
    "D-049": (
        "Measured Eco public catalog FR: renew intervalUnit is month on every "
        "plan (0 hour). Operator 'horaire' is Public Cloud d2-8 consumption "
        "and/or availability 1H-low, not Eco billing. GET /dedicated/server "
        "on xy4589-ovh still []. Eco checkout already exists: orderId "
        "258100013 KS-5 24sk50-v1 rbx, details say '1 mois', status checking, "
        "followUp FRAUD_MANUAL_REVIEW, 44.98 EUR HT / 53.98 EUR TTC, paymentType "
        "debtAccount. This agent does not POST --order (no second server). "
        "VM 91.134.45.8 untouched. No IP invented. certified stays false."
    ),
}

DECISIONS_191: Final[dict[str, str]] = {
    "D-045": (
        "GO remaining live tests on the current mainnet book (genesis reset later). "
        "DV-01: honest TPM probe + cloud-instance binding (do not fake a TPM chip). "
        "Q-E03: freeze UN WPP 2024 World 18+ hashed extract; community updates later, "
        "no auto-refresh. Consume BOOTSTRAP_NODES at startup so clones and Replit "
        "detect all live nodes and can announce themselves without a wallet. "
        "Visitors cannot stop/hijack P2P (mutations Bearer; libp2p GET does not autostart). "
        "DV-06 packet-loss and DV-02 bounded flood run on the live height-1 book. "
        "Never bake a Replit account hostname into the protocol: clones detect "
        "REPLIT_DEV_DOMAIN / ARTCB_NODE_PUBLIC_URL and POST /api/v1/network/announce "
        "to the four always-on IPs. Replit stays bootstrap (no init-node). "
        "certified_distributed_mainnet stays false unless every DV letter is PASS "
        "and the operator says so."
    ),
}


def certification_gate(verdicts: dict[str, str] | None = None) -> dict[str, Any]:
    """Mainnet certification is AND of every locked letter + economics.

    A single DV PASS does not certify. Feeding every letter as PASS still does
    not certify until OPERATOR_MAINNET_CERTIFICATION_GO is True (operator says so).
    """
    v = verdicts or {}
    required_pass = ("DV-01", "DV-02", "DV-03", "DV-04", "DV-05", "DV-06", "DV-07")
    missing = [k for k in required_pass if v.get(k) != "PASS"]
    try:
        from src.artcb.consensus_spec import LIVE_BFT_IMPLEMENTED as live_bft
    except ModuleNotFoundError:
        from artcb.consensus_spec import LIVE_BFT_IMPLEMENTED as live_bft

    reasons = []
    if missing:
        reasons.append("dv_not_pass:" + ",".join(missing))
    if not live_bft:
        reasons.append("live_bft_off")
    if not ECONOMIC_V_LOCKED:
        reasons.append("economic_v_locked=false")
    if not OPERATOR_MAINNET_CERTIFICATION_GO:
        reasons.append("operator_certification_go=false")
    certified = (
        (not missing)
        and live_bft
        and ECONOMIC_V_LOCKED
        and OPERATOR_MAINNET_CERTIFICATION_GO
    )
    return {
        "certified_distributed_mainnet": certified,
        "economic_v_locked": ECONOMIC_V_LOCKED,
        "live_bft_implemented": live_bft,
        "operator_certification_go": OPERATOR_MAINNET_CERTIFICATION_GO,
        "dv_not_pass": missing,
        "reason": "; ".join(reasons),
    }


def public_lock() -> dict[str, Any]:
    return {
        "economic_v_series": ECONOMIC_V,
        "economic_v_locked": ECONOMIC_V_LOCKED,
        "distributed_profile": PROFILE,
        "distributed": DV,
        "distributed_certified": False,
        "decisions_174": DECISIONS_174,
        "decisions_175": DECISIONS_175,
        "decisions_177": DECISIONS_177,
        "decisions_178": DECISIONS_178,
        "decisions_186": DECISIONS_186,
        "decisions_187": DECISIONS_187,
        "decisions_188": DECISIONS_188,
        "decisions_189": DECISIONS_189,
        "decisions_190": DECISIONS_190,
        "decisions_191": DECISIONS_191,
        "decisions_192": DECISIONS_192,
        "decisions_193": DECISIONS_193,
        "decisions_194": DECISIONS_194,
        "note": "Choosing DV letters is the validation protocol, not a PASS.",
    }
