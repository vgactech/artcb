#!/usr/bin/env python3
"""CI / local Stripe JobPayment test (test mode). Never prints the secret. Never mints."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.artcb.payments.stripe_jobs import (  # noqa: E402
    BLOCK_REWARD_KIND,
    JOB_PAYMENT_KIND,
    StripeJobError,
    StripeJobLedger,
    create_priority_job_payment,
    stripe_secret,
)


def _has_secret_name() -> bool:
    return any(os.environ.get(n) for n in ("KEY_API_STRIPE_ACTION", "STRIPE_SECRET_KEY", "STRIPE_API_KEY"))


def main() -> int:
    if _has_secret_name() and stripe_secret():
        key = stripe_secret() or ""
        if key.startswith("sk_live"):
            print("REFUSED: live Stripe key in CI path (sk_test required)")
            return 2
        ledger = StripeJobLedger(Path("/tmp/artcb_stripe_ci.json"))
        try:
            rec = create_priority_job_payment(job_id="ci_priority_164", ledger=ledger)
        except StripeJobError as exc:
            print(f"STRIPE_LIVE_KO reason={exc}")
            return 1
        payload = rec.to_dict()
        print(json.dumps({
            "ok": True,
            "kind": payload["kind"],
            "mints": payload["mints"],
            "distinct_from": payload["distinct_from"],
            "status": payload["status"],
            "payment_intent_id": payload["payment_intent_id"],
            "amount_cents": payload["amount_cents"],
        }))
        assert payload["kind"] == JOB_PAYMENT_KIND
        assert payload["mints"] is False
        assert payload["distinct_from"] == BLOCK_REWARD_KIND
        return 0
    print(json.dumps({
        "ok": True,
        "stripe_skipped": True,
        "reason": "KEY_API_STRIPE_ACTION not injected in this runtime",
        "kind": JOB_PAYMENT_KIND,
        "mints": False,
        "distinct_from": BLOCK_REWARD_KIND,
        "workflow_secret_name": "KEY_API_STRIPE_ACTION",
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
