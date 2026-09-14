"""R347 — Identity layer cartography (canonical labels + invariants).

Does NOT implement HumanIdentity uniqueness or TPM attestation.
Does NOT delete device_wallet_limit — relocates the *meaning* of the rule.

Layers (must never be collapsed):
  USER / HUMAN   — economic / account subject (HumanRegistry exists; not wired to /wallet/create)
  WALLET         — signing keypair + address (WalletManager)
  NODE           — P2P/operator identity (NodeIdentity; often = operator wallet address)
  DEVICE_HOST    — server machine DeviceIdentity (hardware_identity)
  DEVICE_CLIENT  — browser UA + X-ARTCB-Device-Id (auth_routes.device_fingerprint) — R345
  AUTHENTICATOR  — WebAuthn / face_camera credential — ≠ UNIQUE_HUMAN
"""

from __future__ import annotations

from typing import Any

# Honest status of wiring as of R347 (code survey, not certification).
LAYER_STATUS: dict[str, dict[str, Any]] = {
    "USER_HUMAN": {
        "code": ["src/artcb/economics/identity.py::HumanRegistry"],
        "wired_to_wallet_create": False,
        "wired_to_webauthn": False,
        "unique_human_proven_by_default": False,
    },
    "WALLET": {
        "code": ["src/artcb/wallet/manager.py::WalletManager", "POST /api/v1/wallet/create"],
        "bound_today_to": "DEVICE_CLIENT (R345) or DEVICE_HOST fallback",
    },
    "NODE": {
        "code": [
            "src/artcb/p2p/node_identity.py::NodeIdentity",
            "POST /setup/init-node",
            "data/.node_config",
        ],
        "equals_operator_wallet_address": True,
        "must_not_equal_all_user_wallets": True,
    },
    "DEVICE_HOST": {
        "code": ["src/artcb/security/hardware_identity.py::DeviceIdentity"],
        "used_for_user_wallet_limit_after_r345": False,
        "note": "R345 barred host FP as global user limiter on shared artcb.me",
    },
    "DEVICE_CLIENT": {
        "code": [
            "src/api/auth_routes.py::device_fingerprint",
            "frontend X-ARTCB-Device-Id localStorage",
            "WalletDeviceBindingStore",
        ],
        "proves_physical_tpm": False,
        "spoofable_localstorage": True,
    },
    "AUTHENTICATOR": {
        "code": ["src/api/webauthn_routes.py", "webauthn_store"],
        "proves_unique_human": False,
    },
}


INVARIANTS: dict[str, str] = {
    "I1_NODE_NEQ_USER": "NodeIdentity is operator/infra — never the sole UserIdentity of every client on that host.",
    "I2_DEVICE_HOST_NEQ_USER": "Server DeviceIdentity must not decide whether user B may create an account on node owned/operated by A.",
    "I3_DEVICE_CLIENT_SCOPE": "device_wallet_limit (post-R345) applies to CLIENT device context only — anti-abuse, not HumanIdentity.",
    "I4_NODE_WALLET_NEQ_USER_WALLETS": "init-node operator wallet ≠ automatic wallet for every API client of that node.",
    "I5_NO_USER_PRIVKEY_UPLOAD": "User↔Node association must use challenge+signature; never upload UserPrivateKey to the node.",
    "I6_WEBAUTHN_NEQ_UNIQUE_HUMAN": "WebAuthn/face_camera success ≠ UNIQUE_HUMAN / HumanRegistry.VERIFIED.",
    "I7_R345_SCOPE": "CLIENT_DEVICE_BINDING_PASS ≠ HUMAN_IDENTITY_PASS ≠ CERTIFIED_100.",
    "I8_KEEP_ANTI_FRAUD": "Do not delete device_wallet_limit; relocate and label its scope (client vs human vs node).",
}


def identity_map_snapshot() -> dict[str, Any]:
    return {
        "protocol": "r347-identity-layers-v1",
        "layers": LAYER_STATUS,
        "invariants": INVARIANTS,
        "relations_today": [
            {"from": "NODE", "to": "WALLET", "via": "init-node / .node_config", "cardinality": "1 node → 1 operator wallet"},
            {"from": "DEVICE_CLIENT", "to": "WALLET", "via": "wallet_device_bindings.json", "cardinality": "1 client_fp → ≤1 wallet (unless ALLOW_MULTI)"},
            {"from": "AUTHENTICATOR", "to": "WALLET", "via": "webauthn_store by wallet name", "cardinality": "many creds → 1 wallet name"},
            {"from": "USER_HUMAN", "to": "WALLET", "via": "NOT WIRED at create", "cardinality": "MISSING"},
            {"from": "USER_HUMAN", "to": "NODE", "via": "NOT WIRED (signature association)", "cardinality": "MISSING"},
            {"from": "DEVICE_HOST", "to": "NODE", "via": "same process AppState", "cardinality": "1 host → 1 node process"},
        ],
        "target_relations": [
            {"from": "USER_HUMAN", "to": "NODE", "via": "challenge+UserSignature over NodePublicKey", "never": "UserPrivateKey upload"},
            {"from": "USER_HUMAN", "to": "WALLET", "via": "explicit bind after auth", "note": "multi-wallet policy separate"},
            {"from": "NODE", "to": "DEVICE_HOST", "via": "attestation optional", "note": "operator infra"},
            {"from": "USER_HUMAN", "to": "DEVICE_CLIENT", "via": "session/device allowlist", "note": "anti-abuse not uniqueness"},
        ],
        "certified_100": False,
        "unique_human": False,
        "r345_label": "CLIENT_DEVICE_BINDING_PASS",
    }


def assert_invariants_documented() -> None:
    """Structural self-check — presence of invariants, not live uniqueness."""
    assert "I5_NO_USER_PRIVKEY_UPLOAD" in INVARIANTS
    assert LAYER_STATUS["USER_HUMAN"]["wired_to_wallet_create"] is False
    assert LAYER_STATUS["AUTHENTICATOR"]["proves_unique_human"] is False
    assert LAYER_STATUS["DEVICE_CLIENT"]["proves_physical_tpm"] is False
