"""Distributed / operational validations DV-01…DV-07 (distinct from economic V-01…V-07).

Economic V-01…V-07 locked D-043 (operator GO 2026-09-01) at the values
already implemented and measured in simulation 167. This module also
records the 2026-08-31 user choices for live multi-node validation.
"""

from __future__ import annotations

import json
from pathlib import Path
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

# Operator 2026-09-02: all DV-01…07 PASS on the live book (sim 208 for DV-02/06).
# GO is explicit — flipping the badge without those PASS would have been a lie.
OPERATOR_MAINNET_CERTIFICATION_GO: Final[bool] = True

DECISIONS_208: Final[dict[str, str]] = {
    "D-056": (
        "GO certify after measured DV-02 + DV-06 PASS on the four live VMs "
        "(bounded HTTP flood 64×4 all 200; unauth delete/sync/gossip 401; "
        "SSRF announce 400; tc netem 25%/80ms on OVH4 restored). "
        "DV-01/03/04/05/07 already PASS. Economic V locked. Live BFT on. "
        "OPERATOR_MAINNET_CERTIFICATION_GO=True so /health can read True. "
        "Scope unchanged: DV-05 is settlement WorkID, not PBFT append_block. "
        "No SYN flood, no rescue, no genesis wipe."
    ),
}

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

DECISIONS_196: Final[dict[str, str]] = {
    "D-050": (
        "Hybrid verify AND (D-034 A) is implemented as verify_hybrid_and: "
        "Ed25519-only refused, ML-DSA-only refused, both legs required. "
        "verify_hybrid() still accepts Ed25519-only (legacy window D-032 B) — "
        "high_value_hybrid_enforced stays false until chain/governance/groups "
        "are wired. Hardware tpm_type=physical|virtual|absent; "
        "attestation_available only if /dev/tpm0 or /dev/nsm. "
        "No invented NitroTPM/quote. OVH1 Doppler isolation gap remains "
        "(shared artcb-blockchain — no new project invented). "
        "Replit CORS stays a platform regex. certified stays false."
    ),
}

DECISIONS_198: Final[dict[str, str]] = {
    "D-051": (
        "Wire verify_hybrid_and at chain/groups/governance via "
        "verify_hybrid_and_or_window: hybrid envelope requires BOTH legs "
        "(AND); Ed25519-only remains allowed only while D-032 B is open "
        "(until 2026-12-31T00:00:00Z). ML-DSA-only refused. Hybrid envelope "
        "without a PQC public key is refused (AND impossible). "
        "high_value_hybrid_enforced stays false during the Ed25519 window. "
        "peer_handshake still verifies Ed25519-only (not in this wiring). "
        "Replit CORS stays a platform regex. certified stays false."
    ),
}

# Operator 2026-09-02: merge artcb.me onto main, kill nginx default, new Replit PIN.
DECISIONS_201: Final[dict[str, str]] = {
    "D-052": (
        "GO merge origin/main and keep-book all four live VMs onto git_branch=main. "
        "artcb.me DNS already points at the four IPs; the nginx default site on :80 "
        "is why the domain showed 'Welcome to nginx' — replace it with a reverse "
        "proxy to 127.0.0.1:8000 (keep :8000 and :8443). Open AWS SG tcp/80+443. "
        "Let's Encrypt when certbot succeeds; otherwise HTTP:80 still serves ARTCB. "
        "Replit default branch is main; ARTCB_REPLIT_PIN_SHA is origin/main full SHA "
        "(ancestor fast-forward OK). CORS keeps artcb.space. "
        "certified_distributed_mainnet stays false: OPERATOR_MAINNET_CERTIFICATION_GO "
        "remains False and /health calls certification_gate() without DV verdicts. "
        "Do not flip the lock. No install.sh, no genesis wipe, no domain order."
    ),
}

DECISIONS_205: Final[dict[str, str]] = {
    "D-055": (
        "www.artcb.me enrollment is WebAuthn platform authenticator "
        "(fingerprint / Face ID) plus optional camera face-unlock for "
        "motor disability. Raw biometric samples are rejected and never "
        "stored on chain. SSH for live VMs is Doppler PEM, never rescue. "
        "OPERATOR_MAINNET_CERTIFICATION_GO stays False until DV-01…07 are "
        "all PASS on the live book AND the operator GO is explicit. "
        "No install.sh, no genesis wipe, no rescue."
    ),
}

# Operator 2026-09-02: homogenize four live VMs onto origin/main and start
# official benches on the real book. Certification lock unchanged.
DECISIONS_203: Final[dict[str, str]] = {
    "D-053": (
        "GO merge inventory+metrology onto origin/main and keep-book every "
        "reachable live VM onto that SHA. Official benches are four separate "
        "campaigns (machine, WAN mesh, local chain, distributed). "
        "bandwidth_mbps idle 100 is a fallback, not a speedtest — publish "
        "measured_bandwidth_mbps / estimated_bandwidth_mbps / "
        "fallback_bandwidth_mbps / bandwidth_source. /metrics RTT includes "
        "a voluntary sample sleep. Historical 90 TPS is lab 2026-08-03, not "
        "distributed mainnet. Do not publish a single magic TPS. "
        "OPERATOR_MAINNET_CERTIFICATION_GO stays False: operational mainnet "
        "means the four VMs run origin/main on the live book, not "
        "certified_distributed_mainnet=true. No install.sh, no genesis wipe."
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
    live_bft = False
    try:
        from src.artcb.consensus_spec import LIVE_BFT_IMPLEMENTED as live_bft
    except Exception:  # noqa: BLE001 — health must not 500; try src-less import
        try:
            from artcb.consensus_spec import LIVE_BFT_IMPLEMENTED as live_bft
        except Exception:  # noqa: BLE001
            live_bft = False
    live_bft = bool(live_bft)

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
        "decisions_196": DECISIONS_196,
        "decisions_198": DECISIONS_198,
        "decisions_201": DECISIONS_201,
        "decisions_203": DECISIONS_203,
        "decisions_205": DECISIONS_205,
        "decisions_208": DECISIONS_208,
        "note": "Choosing DV letters is the validation protocol, not a PASS.",
    }


def load_dv_verdicts() -> dict[str, str]:
    """Read validation/DV-*/RESULT.json. Missing file = not PASS."""
    root = Path(__file__).resolve().parents[2]
    out: dict[str, str] = {}
    for letter in ("DV-01", "DV-02", "DV-03", "DV-04", "DV-05", "DV-06", "DV-07"):
        path = root / "validation" / letter / "RESULT.json"
        if not path.is_file():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        status = str(payload.get("status") or "")
        if status:
            out[letter] = status
    return out
