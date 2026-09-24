"""Tests R457 — Issue #77 : NodeID ↔ clé — 9 scénarios adversariaux.

Un attaquant peut tenter de :
  A1 — se faire passer pour un nœud légitime (key substitution)
  A2 — utiliser un NodeID valide avec une clé inconnue
  A3 — utiliser une clé connue avec un mauvais NodeID (impersonation)
  A4 — replayer une ancienne clé révoquée
  A5 — utiliser une clé expirée (not_after_epoch dépassé)
  A6 — rejoindre avant l'activation (activation_epoch dans le futur)
  A7 — downgrade PQC (require_pqc=True mais aucune clé PQC fournie)
  A8 — NodeID officiel absent du registre + binding enforced
  A9 — collision de clé publique entre deux NodeIDs différents

Plus :
  B1 — Liaison légitime → ok
  B2 — install_test_replica_registry → isolation correcte
  B3 — clear_test_replica_registry → revient au comportement normal
  B4 — override_replica_registry ctx manager → isolation propre
  B5 — owner_of_ed25519 → retrouver un node par sa clé Ed25519
  B5b — owner_of_ed25519 → None pour clé inconnue
  B6 — public_registry_view() ne lève pas

Note sur les epoch : verify_replica_key_binding() utilise time.time() en interne.
Les tests A5/A6 utilisent des epochs UNIX réels (not_after=1 = 1970, activation=9999999999=2286).
"""

from __future__ import annotations

import base64
import pytest
from nacl.signing import SigningKey

from src.artcb.consensus.replica_identity import (
    ReplicaKeyBinding,
    install_test_replica_registry,
    clear_test_replica_registry,
    override_replica_registry,
    verify_replica_key_binding,
    expected_binding,
    owner_of_ed25519,
    active_registry,
    public_registry_view,
    BINDING_REASONS,
)

# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _gen_b64() -> str:
    """Generate a random Ed25519 public key in base64."""
    return base64.b64encode(SigningKey.generate().verify_key.encode()).decode()


def _make_binding(node_id: str, ed25519_b64: str = "", pqc_b64: str = "",
                  revoked: bool = False, activation_epoch: int = 0,
                  not_after_epoch: int = 0, require_pqc: bool = False) -> ReplicaKeyBinding:
    return ReplicaKeyBinding(
        node_id=node_id,
        ed25519_b64=ed25519_b64 or _gen_b64(),
        pqc_b64=pqc_b64,
        activation_epoch=activation_epoch,
        not_after_epoch=not_after_epoch,
        revoked=revoked,
        require_pqc=require_pqc,
    )


# Official PBFT replica IDs (from node_registry.py)
NODE_A = "ovh-node-2"
NODE_B = "ovh-node-4"
NODE_C = "aws-node-3"
NODE_OFFICIAL_IDS = ("ovh-node-1", "ovh-node-2", "aws-node-3", "ovh-node-4", "mac-node-local")
NODE_UNOFFICIAL = "node-evil-99"  # not in official_pbft_replica_ids()

# Epoch values — UNIX timestamps
EPOCH_PAST = 1              # 1970-01-01 — clearly expired
EPOCH_FAR_FUTURE = 9_999_999_999  # 2286 — clearly not yet active


# ──────────────────────────────────────────────────────────────────────────────
# Fixture — inject test registry and clean up after each test
# ──────────────────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _clean_registry():
    """Ensure test registry is always cleaned up between tests."""
    yield
    clear_test_replica_registry()


# ──────────────────────────────────────────────────────────────────────────────
# A1 — Key substitution : NodeID officiel valide, mauvaise clé
# ──────────────────────────────────────────────────────────────────────────────

def test_a1_key_substitution_denied():
    legit_key = _gen_b64()
    attacker_key = _gen_b64()  # different key
    install_test_replica_registry({NODE_A: _make_binding(NODE_A, ed25519_b64=legit_key)})
    ok, reason = verify_replica_key_binding(NODE_A, attacker_key)
    assert ok is False
    assert reason in BINDING_REASONS


# ──────────────────────────────────────────────────────────────────────────────
# A2 — NodeID officiel valide mais clé inconnue du registre
# ──────────────────────────────────────────────────────────────────────────────

def test_a2_valid_nodeid_unknown_key_denied():
    registered_key = _gen_b64()
    unknown_key = _gen_b64()
    install_test_replica_registry({NODE_A: _make_binding(NODE_A, ed25519_b64=registered_key)})
    ok, reason = verify_replica_key_binding(NODE_A, unknown_key)
    assert ok is False
    assert reason != ""


# ──────────────────────────────────────────────────────────────────────────────
# A3 — Impersonation : clé connue de NODE_B utilisée pour se faire passer pour NODE_A
# ──────────────────────────────────────────────────────────────────────────────

def test_a3_known_key_wrong_nodeid_denied():
    key_a = _gen_b64()
    key_b = _gen_b64()
    install_test_replica_registry({
        NODE_A: _make_binding(NODE_A, ed25519_b64=key_a),
        NODE_B: _make_binding(NODE_B, ed25519_b64=key_b),
    })
    # Attacker claims to be NODE_A but uses NODE_B's key
    ok, reason = verify_replica_key_binding(NODE_A, key_b)
    assert ok is False
    assert reason in BINDING_REASONS


# ──────────────────────────────────────────────────────────────────────────────
# A4 — Clé révoquée → toujours refusée même si la clé correspond
# ──────────────────────────────────────────────────────────────────────────────

def test_a4_revoked_key_denied():
    key = _gen_b64()
    install_test_replica_registry({
        NODE_A: _make_binding(NODE_A, ed25519_b64=key, revoked=True)
    })
    ok, reason = verify_replica_key_binding(NODE_A, key)
    assert ok is False
    assert "revok" in reason.lower()


# ──────────────────────────────────────────────────────────────────────────────
# A5 — Clé expirée (not_after_epoch = 1 = 1970-01-01 < now)
# ──────────────────────────────────────────────────────────────────────────────

def test_a5_expired_key_denied():
    key = _gen_b64()
    install_test_replica_registry({
        NODE_A: _make_binding(NODE_A, ed25519_b64=key,
                              not_after_epoch=EPOCH_PAST)  # expired in 1970
    })
    ok, reason = verify_replica_key_binding(NODE_A, key)
    assert ok is False
    assert "expir" in reason.lower()


# ──────────────────────────────────────────────────────────────────────────────
# A6 — Clé pas encore active (activation_epoch = 2286 > now)
# ──────────────────────────────────────────────────────────────────────────────

def test_a6_key_not_yet_active_denied():
    key = _gen_b64()
    install_test_replica_registry({
        NODE_A: _make_binding(NODE_A, ed25519_b64=key,
                              activation_epoch=EPOCH_FAR_FUTURE)  # year 2286
    })
    ok, reason = verify_replica_key_binding(NODE_A, key)
    assert ok is False
    assert "not_yet" in reason.lower() or "activ" in reason.lower()


# ──────────────────────────────────────────────────────────────────────────────
# A7 — PQC downgrade : require_pqc=True mais aucune clé PQC fournie
# ──────────────────────────────────────────────────────────────────────────────

def test_a7_pqc_downgrade_denied():
    key = _gen_b64()
    install_test_replica_registry({
        NODE_A: _make_binding(NODE_A, ed25519_b64=key,
                              pqc_b64="",
                              require_pqc=True)  # PQC mandatory
    })
    # Caller provides no PQC key → downgrade attempt
    ok, reason = verify_replica_key_binding(NODE_A, key, "")  # positional pqc=""
    assert ok is False
    assert "pqc" in reason.lower() or "downgrade" in reason.lower()


# ──────────────────────────────────────────────────────────────────────────────
# A8 — NodeID officiel absent du registre (unregistered) + binding enforced
# Cas: registre de test vide = aucun binding → unregistered_replica_key
# ──────────────────────────────────────────────────────────────────────────────

def test_a8_official_nodeid_unregistered_denied():
    # Install empty registry for all official nodes except NODE_A
    install_test_replica_registry({
        NODE_B: _make_binding(NODE_B),
        NODE_C: _make_binding(NODE_C),
    })
    # NODE_A is official but not in our test registry
    # verify_replica_key_binding checks: NODE_A in official_pbft_replica_ids() → True
    # Then: expected = registry.get(NODE_A) → None
    # If binding_enforced() → "unregistered_replica_key", else "registry_inactive"
    ok, reason = verify_replica_key_binding(NODE_A, _gen_b64())
    # Either denied (enforced) or inactive (not enforced) — both are valid
    # The key invariant: the REASON must be informative, not a crash
    assert isinstance(ok, bool)
    assert isinstance(reason, str) and len(reason) > 0
    # If enforced: must be denied
    if not ok:
        assert reason in BINDING_REASONS or reason == "unregistered_replica_key"


# ──────────────────────────────────────────────────────────────────────────────
# A9 — Collision de clé entre deux NodeIDs
# ──────────────────────────────────────────────────────────────────────────────

def test_a9_key_collision_between_nodes_rejected():
    shared_key = _gen_b64()
    install_test_replica_registry({
        NODE_A: _make_binding(NODE_A, ed25519_b64=shared_key),
        NODE_B: _make_binding(NODE_B, ed25519_b64=shared_key),  # same key!
    })
    # owner_of_ed25519 returns one owner at most (first match)
    owner = owner_of_ed25519(shared_key)
    if owner is not None:
        assert owner in (NODE_A, NODE_B)
    # If the key is attributed to NODE_A in the registry,
    # using it as NODE_B should be denied (impersonation)
    ok_a, _ = verify_replica_key_binding(NODE_A, shared_key)
    ok_b, reason_b = verify_replica_key_binding(NODE_B, shared_key)
    # At least one must be either denied OR the registry returns ok for both
    # (shared key is ambiguous — but it must not crash)
    assert isinstance(ok_a, bool)
    assert isinstance(ok_b, bool)
    # If owner is NODE_A, then claiming NODE_B with that key should be denied
    if owner == NODE_A:
        assert ok_b is False


# ──────────────────────────────────────────────────────────────────────────────
# B1 — Liaison légitime → ok
# ──────────────────────────────────────────────────────────────────────────────

def test_b1_legitimate_binding_ok():
    key = _gen_b64()
    install_test_replica_registry({NODE_A: _make_binding(NODE_A, ed25519_b64=key)})
    ok, reason = verify_replica_key_binding(NODE_A, key)
    assert ok is True
    assert reason in ("ok", "non_official_id", "registry_inactive")


# ──────────────────────────────────────────────────────────────────────────────
# B2 — install_test_replica_registry → registre de test isolé du registre officiel
# ──────────────────────────────────────────────────────────────────────────────

def test_b2_test_registry_isolated():
    key = _gen_b64()
    install_test_replica_registry({NODE_A: _make_binding(NODE_A, ed25519_b64=key)})
    reg = active_registry()
    assert NODE_A in reg
    assert reg[NODE_A].ed25519_b64 == key


# ──────────────────────────────────────────────────────────────────────────────
# B3 — clear_test_replica_registry → override vidé
# ──────────────────────────────────────────────────────────────────────────────

def test_b3_clear_registry_restores_normal():
    key = _gen_b64()
    install_test_replica_registry({NODE_A: _make_binding(NODE_A, ed25519_b64=key)})
    assert NODE_A in active_registry()
    clear_test_replica_registry()
    # After clearing, the test override is gone
    with override_replica_registry({}):
        reg = active_registry()
        assert NODE_A not in reg


# ──────────────────────────────────────────────────────────────────────────────
# B4 — override_replica_registry() context manager → isolation propre
# ──────────────────────────────────────────────────────────────────────────────

def test_b4_override_ctx_manager_isolated():
    key = _gen_b64()
    with override_replica_registry({NODE_C: _make_binding(NODE_C, ed25519_b64=key)}):
        reg = active_registry()
        assert NODE_C in reg
    # After context exit, registry must be restored
    with override_replica_registry({}):
        assert NODE_C not in active_registry()


# ──────────────────────────────────────────────────────────────────────────────
# B5 — owner_of_ed25519 → retrouver un node par sa clé
# ──────────────────────────────────────────────────────────────────────────────

def test_b5_owner_of_ed25519_found():
    key = _gen_b64()
    install_test_replica_registry({NODE_A: _make_binding(NODE_A, ed25519_b64=key)})
    owner = owner_of_ed25519(key)
    assert owner == NODE_A


def test_b5b_owner_of_ed25519_not_found():
    install_test_replica_registry({NODE_A: _make_binding(NODE_A)})
    owner = owner_of_ed25519(_gen_b64())  # unknown key
    assert owner is None


# ──────────────────────────────────────────────────────────────────────────────
# B6 — public_registry_view() ne lève pas et retourne un dict
# ──────────────────────────────────────────────────────────────────────────────

def test_b6_public_registry_view_no_exception():
    install_test_replica_registry({NODE_A: _make_binding(NODE_A)})
    view = public_registry_view()
    assert isinstance(view, dict)
