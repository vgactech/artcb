"""Stripe priority JobPayment — skip without KEY_API_STRIPE_ACTION / STRIPE_SECRET_KEY.

Never logs the secret. JobPayment ≠ BlockReward and never mints.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from src.artcb.economics.job_payment import JobPaymentLedger, stripe_secret_from_env
from src.artcb.payments.stripe_jobs import (
    JOB_PAYMENT_KIND,
    StripeJobError,
    StripeJobLedger,
    create_priority_job_payment,
    handle_stripe_webhook,
    stripe_secret,
)
from src.artcb.tokenomics import MAX_SUPPLY_SATOSHI


def _has_stripe_secret() -> bool:
    return bool(stripe_secret() or stripe_secret_from_env())


@pytest.mark.skipif(not _has_stripe_secret(), reason="KEY_API_STRIPE_ACTION / KEY_API_STRIPE / STRIPE_* unset")
def test_stripe_create_and_cancel_does_not_mint(tmp_path: Path) -> None:
    ledger = StripeJobLedger(tmp_path / "stripe.json")
    rec = create_priority_job_payment(
        job_id="job_ci_164",
        amount_cents=50,
        currency="eur",
        ledger=ledger,
    )
    assert rec.mints is False
    assert rec.kind == JOB_PAYMENT_KIND
    assert rec.payment_intent_id
    assert rec.distinct_from == "R_block"
    assert rec.status in {"canceled", "cancelled", "requires_payment_method", "requires_confirmation"}
    pay_ledger = JobPaymentLedger(tmp_path / "pays.json")
    stored = pay_ledger.record(
        job_id=rec.job_id,
        provider_address="A",
        amount_cents=rec.amount_cents,
        currency=rec.currency,
        stripe_id=rec.payment_intent_id,
        status=rec.status,
        mode="test",
        issued_so_far_satoshi=0,
    )
    assert stored.minted_satoshi == 0
    assert stored.remaining_supply_satoshi == MAX_SUPPLY_SATOSHI
    assert pay_ledger.total_minted_satoshi() == 0


def test_stripe_skipped_without_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("KEY_API_STRIPE_ACTION", raising=False)
    monkeypatch.delenv("KEY_API_STRIPE", raising=False)
    monkeypatch.delenv("STRIPE_SECRET_KEY", raising=False)
    monkeypatch.delenv("STRIPE_API_KEY", raising=False)
    assert stripe_secret() is None
    with pytest.raises(StripeJobError, match="no Stripe secret"):
        create_priority_job_payment(job_id="x")


def test_job_payment_ledger_never_mints(tmp_path: Path) -> None:
    ledger = JobPaymentLedger(tmp_path / "p.json")
    rec = ledger.record(
        job_id="j1",
        provider_address="A",
        amount_cents=200,
        issued_so_far_satoshi=50_00000000,
    )
    assert rec.minted_satoshi == 0
    assert rec.remaining_supply_satoshi == MAX_SUPPLY_SATOSHI - 50_00000000
    assert ledger.total_minted_satoshi() == 0


def test_webhook_idempotent_and_rejects_mint_claim(tmp_path: Path) -> None:
    ledger = StripeJobLedger(tmp_path / "s.json")
    event = {
        "id": "evt_1",
        "type": "payment_intent.canceled",
        "data": {"object": {"id": "pi_1", "status": "canceled", "metadata": {"artcb_mints": "false", "artcb_job_id": "j"}}},
    }
    first = handle_stripe_webhook(event, ledger=ledger)
    second = handle_stripe_webhook(event, ledger=ledger)
    assert first["duplicate"] is False
    assert first["mints"] is False
    assert second["duplicate"] is True
    evil = {
        "id": "evt_2",
        "type": "payment_intent.succeeded",
        "data": {"object": {"id": "pi_2", "metadata": {"artcb_mints": "true"}}},
    }
    with pytest.raises(StripeJobError, match="mint"):
        handle_stripe_webhook(evil, ledger=ledger)


def test_secret_not_in_env_dump_when_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("KEY_API_STRIPE_ACTION", raising=False)
    dumped = {k: v for k, v in os.environ.items() if "STRIPE" in k.upper() or k == "KEY_API_STRIPE_ACTION"}
    assert "KEY_API_STRIPE_ACTION" not in dumped or not dumped.get("KEY_API_STRIPE_ACTION")


def test_stripe_failure_is_not_consensus_dependency(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from src.artcb.payments.stripe_jobs import (
        attempt_job_payment_or_continue,
        stripe_is_consensus_dependency,
    )

    monkeypatch.delenv("KEY_API_STRIPE_ACTION", raising=False)
    monkeypatch.delenv("KEY_API_STRIPE", raising=False)
    monkeypatch.delenv("STRIPE_SECRET_KEY", raising=False)
    monkeypatch.delenv("STRIPE_API_KEY", raising=False)
    assert stripe_is_consensus_dependency() is False
    missing = attempt_job_payment_or_continue(job_id="job_missing")
    assert missing["ok"] is False
    assert missing["mints"] is False
    assert missing["consensus_blocked"] is False

    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_invalid_not_a_real_secret")
    pi_fail = attempt_job_payment_or_continue(
        job_id="job_pi_fail",
        ledger=StripeJobLedger(tmp_path / "stripe_fail.json"),
    )
    assert pi_fail["ok"] is False
    assert pi_fail["mints"] is False
    assert pi_fail["consensus_blocked"] is False
    assert pi_fail["stripe_is_consensus_dependency"] is False
