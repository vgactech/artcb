"""Tests R456 — Issue #90 : Single-use capability tokens (bypasses internes).

Matrice de tests :
  C01 — Emission OK pour rôle CONSENSUS/CAP_PRODUCE
  C02 — Emission refusée si rôle ne permet pas la capability (FAIL-CLOSED)
  C03 — Première rédemption → CONSUMED (allowed=True)
  C04 — Double rédemption → DENIED:already_consumed (bypass fermé)
  C05 — Triple rédemption → DENIED (idempotent sur le refus)
  C06 — Token inconnu → DENIED:unknown_token
  C07 — Token expiré → DENIED:token_expired
  C08 — Capability mismatch → DENIED:capability_mismatch
  C09 — Node mismatch → DENIED:node_mismatch
  C10 — Domain mismatch → DENIED:domain_mismatch
  C11 — Audit trail conservé après refus
  C12 — Audit trail conservé après succès
  C13 — count_by_state() exact
  C14 — Deux tokens distincts = deux token_id distincts (unicité nonce)
  C15 — token_id déterministe à partir de mêmes inputs ≠ (nonce random = toujours différent)
  C16 — Enregistrement duplicate → CapabilityTokenError
  C17 — Token non PENDING à l'enregistrement → CapabilityTokenError
  C18 — Rôle HOST_ONLY ne peut pas émettre CAP_PRODUCE
  C19 — Rôle GOVERNANCE peut émettre CAP_CHANGE_GOVERNANCE
  C20 — state_of() retourne None pour token inconnu
  C21 — state_of() retourne CONSUMED après rédemption
  C22 — get_audit_trail() filtré par token_id
  C23 — Rédemption concurrente (thread-safety) → un seul CONSUMED
  C24 — Token valid_until dans le futur = non expiré
  C25 — Raison "ok" dans audit trail sur succès
"""

from __future__ import annotations

import threading
import pytest

from src.artcb.authz.capability_token import (
    CapabilityTokenStore,
    CapabilityTokenError,
    issue_token,
    STATE_PENDING,
    STATE_CONSUMED,
    STATE_EXPIRED,
    STATE_DENIED,
    REASON_ALREADY_CONSUMED,
    REASON_EXPIRED,
    REASON_UNKNOWN_TOKEN,
    REASON_CAPABILITY_MISMATCH,
    REASON_NODE_MISMATCH,
    REASON_DOMAIN_MISMATCH,
)
from src.artcb.authz.node_roles import CAP_PRODUCE, CAP_VALIDATE, CAP_HOST, CAP_CHANGE_GOVERNANCE

# ──────────────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────────────

NODE_A = "node-artcb-ovh-2"
NODE_B = "node-artcb-ovh-4"
DOMAIN = "artcb-mainnet-1"
DOMAIN_OTHER = "artcb-devnet-1"
FUTURE = "2099-01-01T00:00:00Z"
PAST = "2000-01-01T00:00:00Z"


def _store() -> CapabilityTokenStore:
    return CapabilityTokenStore()


def _issue_and_register(store, *, node_id=NODE_A, domain_id=DOMAIN,
                         capability=CAP_PRODUCE, role="CONSENSUS",
                         valid_until=FUTURE):
    tok = issue_token(
        node_id=node_id,
        domain_id=domain_id,
        capability=capability,
        role=role,
        valid_until=valid_until,
    )
    store.register(tok)
    return tok


# ──────────────────────────────────────────────────────────────────────────────
# C01 — Emission OK rôle CONSENSUS / CAP_PRODUCE
# ──────────────────────────────────────────────────────────────────────────────

def test_c01_issue_ok_consensus_produce():
    tok = issue_token(
        node_id=NODE_A,
        domain_id=DOMAIN,
        capability=CAP_PRODUCE,
        role="CONSENSUS",
    )
    assert tok.state == STATE_PENDING
    assert tok.node_id == NODE_A
    assert tok.capability == CAP_PRODUCE
    assert len(tok.token_id) == 64  # SHA-256 hex
    assert len(tok.nonce) == 64     # 32 bytes hex


# ──────────────────────────────────────────────────────────────────────────────
# C02 — Emission refusée si rôle incompatible (FAIL-CLOSED)
# ──────────────────────────────────────────────────────────────────────────────

def test_c02_issue_denied_role_insufficient():
    with pytest.raises(CapabilityTokenError, match="role_does_not_grant_capability"):
        issue_token(
            node_id=NODE_A,
            domain_id=DOMAIN,
            capability=CAP_PRODUCE,
            role="HOST_ONLY",
        )


# ──────────────────────────────────────────────────────────────────────────────
# C03 — Première rédemption → CONSUMED
# ──────────────────────────────────────────────────────────────────────────────

def test_c03_first_redemption_consumed():
    store = _store()
    tok = _issue_and_register(store)
    result = store.redeem(
        tok.token_id,
        expected_node_id=NODE_A,
        expected_domain_id=DOMAIN,
        expected_capability=CAP_PRODUCE,
    )
    assert result.allowed is True
    assert result.reason == "ok"
    assert result.new_state == STATE_CONSUMED
    assert store.state_of(tok.token_id) == STATE_CONSUMED


# ──────────────────────────────────────────────────────────────────────────────
# C04 — Double rédemption → DENIED (bypass fermé)
# ──────────────────────────────────────────────────────────────────────────────

def test_c04_double_redemption_denied():
    store = _store()
    tok = _issue_and_register(store)
    # First redemption OK
    r1 = store.redeem(tok.token_id, expected_node_id=NODE_A,
                      expected_domain_id=DOMAIN, expected_capability=CAP_PRODUCE)
    assert r1.allowed is True
    # Second attempt must be DENIED
    r2 = store.redeem(tok.token_id, expected_node_id=NODE_A,
                      expected_domain_id=DOMAIN, expected_capability=CAP_PRODUCE)
    assert r2.allowed is False
    assert r2.reason == REASON_ALREADY_CONSUMED


# ──────────────────────────────────────────────────────────────────────────────
# C05 — Triple rédemption → DENIED (idempotent)
# ──────────────────────────────────────────────────────────────────────────────

def test_c05_triple_redemption_still_denied():
    store = _store()
    tok = _issue_and_register(store)
    store.redeem(tok.token_id, expected_node_id=NODE_A,
                 expected_domain_id=DOMAIN, expected_capability=CAP_PRODUCE)
    store.redeem(tok.token_id, expected_node_id=NODE_A,
                 expected_domain_id=DOMAIN, expected_capability=CAP_PRODUCE)
    r3 = store.redeem(tok.token_id, expected_node_id=NODE_A,
                      expected_domain_id=DOMAIN, expected_capability=CAP_PRODUCE)
    assert r3.allowed is False
    assert r3.reason == REASON_ALREADY_CONSUMED


# ──────────────────────────────────────────────────────────────────────────────
# C06 — Token inconnu → DENIED:unknown_token
# ──────────────────────────────────────────────────────────────────────────────

def test_c06_unknown_token_denied():
    store = _store()
    result = store.redeem(
        "deadbeef" * 8,
        expected_node_id=NODE_A,
        expected_domain_id=DOMAIN,
        expected_capability=CAP_PRODUCE,
    )
    assert result.allowed is False
    assert result.reason == REASON_UNKNOWN_TOKEN


# ──────────────────────────────────────────────────────────────────────────────
# C07 — Token expiré → DENIED:token_expired
# ──────────────────────────────────────────────────────────────────────────────

def test_c07_expired_token_denied():
    store = _store()
    tok = issue_token(
        node_id=NODE_A,
        domain_id=DOMAIN,
        capability=CAP_PRODUCE,
        role="CONSENSUS",
        valid_until=PAST,  # already expired
    )
    store.register(tok)
    result = store.redeem(
        tok.token_id,
        expected_node_id=NODE_A,
        expected_domain_id=DOMAIN,
        expected_capability=CAP_PRODUCE,
        now="2025-01-01T00:00:00Z",  # now > valid_until
    )
    assert result.allowed is False
    assert result.reason == REASON_EXPIRED
    assert store.state_of(tok.token_id) == STATE_EXPIRED


# ──────────────────────────────────────────────────────────────────────────────
# C08 — Capability mismatch → DENIED
# ──────────────────────────────────────────────────────────────────────────────

def test_c08_capability_mismatch_denied():
    store = _store()
    tok = _issue_and_register(store, capability=CAP_PRODUCE)
    result = store.redeem(
        tok.token_id,
        expected_node_id=NODE_A,
        expected_domain_id=DOMAIN,
        expected_capability=CAP_VALIDATE,  # wrong capability
    )
    assert result.allowed is False
    assert result.reason == REASON_CAPABILITY_MISMATCH


# ──────────────────────────────────────────────────────────────────────────────
# C09 — Node mismatch → DENIED
# ──────────────────────────────────────────────────────────────────────────────

def test_c09_node_mismatch_denied():
    store = _store()
    tok = _issue_and_register(store, node_id=NODE_A)
    result = store.redeem(
        tok.token_id,
        expected_node_id=NODE_B,  # wrong node
        expected_domain_id=DOMAIN,
        expected_capability=CAP_PRODUCE,
    )
    assert result.allowed is False
    assert result.reason == REASON_NODE_MISMATCH


# ──────────────────────────────────────────────────────────────────────────────
# C10 — Domain mismatch → DENIED
# ──────────────────────────────────────────────────────────────────────────────

def test_c10_domain_mismatch_denied():
    store = _store()
    tok = _issue_and_register(store, domain_id=DOMAIN)
    result = store.redeem(
        tok.token_id,
        expected_node_id=NODE_A,
        expected_domain_id=DOMAIN_OTHER,  # wrong domain
        expected_capability=CAP_PRODUCE,
    )
    assert result.allowed is False
    assert result.reason == REASON_DOMAIN_MISMATCH


# ──────────────────────────────────────────────────────────────────────────────
# C11 — Audit trail conservé après refus
# ──────────────────────────────────────────────────────────────────────────────

def test_c11_audit_trail_after_denial():
    store = _store()
    fake_id = "aabbccdd" * 8
    store.redeem(fake_id, expected_node_id=NODE_A,
                 expected_domain_id=DOMAIN, expected_capability=CAP_PRODUCE)
    trail = store.get_audit_trail(fake_id)
    assert len(trail) == 1
    assert trail[0]["outcome"] == STATE_DENIED
    assert trail[0]["reason"] == REASON_UNKNOWN_TOKEN


# ──────────────────────────────────────────────────────────────────────────────
# C12 — Audit trail conservé après succès
# ──────────────────────────────────────────────────────────────────────────────

def test_c12_audit_trail_after_success():
    store = _store()
    tok = _issue_and_register(store)
    store.redeem(tok.token_id, expected_node_id=NODE_A,
                 expected_domain_id=DOMAIN, expected_capability=CAP_PRODUCE,
                 actor="node_process_1")
    trail = store.get_audit_trail(tok.token_id)
    assert len(trail) == 1
    assert trail[0]["outcome"] == STATE_CONSUMED
    assert trail[0]["reason"] == "ok"
    assert trail[0]["actor"] == "node_process_1"


# ──────────────────────────────────────────────────────────────────────────────
# C13 — count_by_state() exact
# ──────────────────────────────────────────────────────────────────────────────

def test_c13_count_by_state():
    store = _store()
    t1 = _issue_and_register(store)
    t2 = _issue_and_register(store)
    t3 = _issue_and_register(store, valid_until=PAST)

    # consume t1
    store.redeem(t1.token_id, expected_node_id=NODE_A,
                 expected_domain_id=DOMAIN, expected_capability=CAP_PRODUCE)
    # expire t3
    store.redeem(t3.token_id, expected_node_id=NODE_A,
                 expected_domain_id=DOMAIN, expected_capability=CAP_PRODUCE,
                 now="2025-01-01T00:00:00Z")

    counts = store.count_by_state()
    assert counts[STATE_PENDING] == 1    # t2 still pending
    assert counts[STATE_CONSUMED] == 1   # t1
    assert counts[STATE_EXPIRED] == 1    # t3


# ──────────────────────────────────────────────────────────────────────────────
# C14 — Deux tokens = deux token_id distincts
# ──────────────────────────────────────────────────────────────────────────────

def test_c14_two_tokens_distinct_ids():
    t1 = issue_token(node_id=NODE_A, domain_id=DOMAIN,
                     capability=CAP_PRODUCE, role="CONSENSUS")
    t2 = issue_token(node_id=NODE_A, domain_id=DOMAIN,
                     capability=CAP_PRODUCE, role="CONSENSUS")
    assert t1.token_id != t2.token_id
    assert t1.nonce != t2.nonce


# ──────────────────────────────────────────────────────────────────────────────
# C15 — token_id dépend du nonce (random → toujours différent)
# ──────────────────────────────────────────────────────────────────────────────

def test_c15_token_id_nonce_dependent():
    ids = set()
    for _ in range(10):
        t = issue_token(node_id=NODE_A, domain_id=DOMAIN,
                        capability=CAP_PRODUCE, role="CONSENSUS",
                        issued_at="2026-01-01T00:00:00Z")
        ids.add(t.token_id)
    assert len(ids) == 10  # all unique


# ──────────────────────────────────────────────────────────────────────────────
# C16 — Enregistrement duplicate → CapabilityTokenError
# ──────────────────────────────────────────────────────────────────────────────

def test_c16_duplicate_registration_raises():
    store = _store()
    tok = issue_token(node_id=NODE_A, domain_id=DOMAIN,
                      capability=CAP_PRODUCE, role="CONSENSUS")
    store.register(tok)
    with pytest.raises(CapabilityTokenError, match="token_id_collision"):
        store.register(tok)


# ──────────────────────────────────────────────────────────────────────────────
# C17 — Token non PENDING à l'enregistrement → CapabilityTokenError
# ──────────────────────────────────────────────────────────────────────────────

def test_c17_non_pending_registration_raises():
    from src.artcb.authz.capability_token import CapabilityToken
    import hashlib, os
    nonce = os.urandom(32).hex()
    tid = hashlib.sha256(f"x:x:CAP_PRODUCE:{nonce}:2026-01-01T00:00:00Z".encode()).hexdigest()
    tok = CapabilityToken(
        token_id=tid,
        node_id=NODE_A,
        domain_id=DOMAIN,
        capability=CAP_PRODUCE,
        role="CONSENSUS",
        issued_at="2026-01-01T00:00:00Z",
        valid_until=None,
        nonce=nonce,
        state=STATE_CONSUMED,  # wrong state
    )
    store = _store()
    with pytest.raises(CapabilityTokenError, match="token_not_pending"):
        store.register(tok)


# ──────────────────────────────────────────────────────────────────────────────
# C18 — Rôle HOST_ONLY ne peut pas émettre CAP_PRODUCE
# ──────────────────────────────────────────────────────────────────────────────

def test_c18_host_only_cannot_produce():
    with pytest.raises(CapabilityTokenError):
        issue_token(node_id=NODE_A, domain_id=DOMAIN,
                    capability=CAP_PRODUCE, role="HOST_ONLY")


# ──────────────────────────────────────────────────────────────────────────────
# C19 — Rôle GOVERNANCE peut émettre CAP_CHANGE_GOVERNANCE
# ──────────────────────────────────────────────────────────────────────────────

def test_c19_governance_can_change_governance():
    tok = issue_token(node_id=NODE_A, domain_id=DOMAIN,
                      capability=CAP_CHANGE_GOVERNANCE, role="GOVERNANCE")
    assert tok.state == STATE_PENDING
    assert tok.capability == CAP_CHANGE_GOVERNANCE


# ──────────────────────────────────────────────────────────────────────────────
# C20 — state_of() → None pour token inconnu
# ──────────────────────────────────────────────────────────────────────────────

def test_c20_state_of_unknown_returns_none():
    store = _store()
    assert store.state_of("nope" * 16) is None


# ──────────────────────────────────────────────────────────────────────────────
# C21 — state_of() → CONSUMED après rédemption réussie
# ──────────────────────────────────────────────────────────────────────────────

def test_c21_state_consumed_after_redemption():
    store = _store()
    tok = _issue_and_register(store)
    assert store.state_of(tok.token_id) == STATE_PENDING
    store.redeem(tok.token_id, expected_node_id=NODE_A,
                 expected_domain_id=DOMAIN, expected_capability=CAP_PRODUCE)
    assert store.state_of(tok.token_id) == STATE_CONSUMED


# ──────────────────────────────────────────────────────────────────────────────
# C22 — get_audit_trail() filtré par token_id
# ──────────────────────────────────────────────────────────────────────────────

def test_c22_audit_trail_filtered():
    store = _store()
    t1 = _issue_and_register(store)
    t2 = _issue_and_register(store)
    store.redeem(t1.token_id, expected_node_id=NODE_A,
                 expected_domain_id=DOMAIN, expected_capability=CAP_PRODUCE)
    store.redeem(t2.token_id, expected_node_id=NODE_A,
                 expected_domain_id=DOMAIN, expected_capability=CAP_PRODUCE)

    trail_t1 = store.get_audit_trail(t1.token_id)
    trail_all = store.get_audit_trail()
    assert len(trail_t1) == 1
    assert len(trail_all) == 2
    assert all(e["token_id"] == t1.token_id for e in trail_t1)


# ──────────────────────────────────────────────────────────────────────────────
# C23 — Rédemption concurrente → un seul CONSUMED (thread-safety)
# ──────────────────────────────────────────────────────────────────────────────

def test_c23_concurrent_redemption_single_winner():
    store = _store()
    tok = _issue_and_register(store)
    results: list[bool] = []
    errors: list[Exception] = []

    def try_redeem():
        try:
            r = store.redeem(
                tok.token_id,
                expected_node_id=NODE_A,
                expected_domain_id=DOMAIN,
                expected_capability=CAP_PRODUCE,
            )
            results.append(r.allowed)
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=try_redeem) for _ in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors
    assert results.count(True) == 1   # exactly one winner
    assert results.count(False) == 19  # all others denied


# ──────────────────────────────────────────────────────────────────────────────
# C24 — valid_until dans le futur = non expiré lors de la rédemption
# ──────────────────────────────────────────────────────────────────────────────

def test_c24_future_valid_until_not_expired():
    store = _store()
    tok = _issue_and_register(store, valid_until=FUTURE)
    result = store.redeem(
        tok.token_id,
        expected_node_id=NODE_A,
        expected_domain_id=DOMAIN,
        expected_capability=CAP_PRODUCE,
        now="2026-01-01T00:00:00Z",  # well before FUTURE
    )
    assert result.allowed is True


# ──────────────────────────────────────────────────────────────────────────────
# C25 — Raison "ok" dans audit trail sur succès
# ──────────────────────────────────────────────────────────────────────────────

def test_c25_audit_trail_reason_ok_on_success():
    store = _store()
    tok = _issue_and_register(store)
    store.redeem(tok.token_id, expected_node_id=NODE_A,
                 expected_domain_id=DOMAIN, expected_capability=CAP_PRODUCE)
    trail = store.get_audit_trail(tok.token_id)
    assert trail[0]["reason"] == "ok"
    assert trail[0]["outcome"] == STATE_CONSUMED
