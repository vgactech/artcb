"""Stripe JobPayment for priority jobs — never mints R_block.

JobPayment (fiat, PaymentIntent) is a queue-priority fee. It is NOT the
block reward. Conservation of satoshi is unchanged.

Secrets: KEY_API_STRIPE_ACTION or STRIPE_SECRET_KEY / STRIPE_API_KEY.
Never log the key. Test-mode sk_test expected.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlencode

logger = logging.getLogger("artcb.payments.stripe_jobs")

STRIPE_API = "https://api.stripe.com/v1"
JOB_PAYMENT_KIND = "JobPayment"
BLOCK_REWARD_KIND = "R_block"
# Anti-spam floor for a priority job (USD cents). Parameter, not a D-xxx freeze.
PRIORITY_JOB_MIN_CENTS = 50
DEFAULT_PRIORITY_CENTS = 200  # $2.00 test


class StripeJobError(RuntimeError):
    pass


def stripe_secret() -> str | None:
    for name in ("KEY_API_STRIPE_ACTION", "STRIPE_SECRET_KEY", "STRIPE_API_KEY"):
        value = os.environ.get(name, "").strip()
        if value:
            return value
    return None


def _redact_key(key: str) -> str:
    if len(key) < 12:
        return "sk_***"
    return key[:7] + "…" + key[-4:]


def assert_test_key(key: str) -> str:
    """Return key mode. Live keys are allowed only for create+cancel (no capture)."""
    key = key.strip()
    if key.startswith(("sk_test", "rk_test")):
        return "test"
    if key.startswith(("sk_live", "rk_live")):
        logger.debug("LIVE stripe key detected — create+cancel only, never capture")
        return "live"
    logger.debug("Stripe key prefix is neither sk_test nor sk_live (value never logged)")
    return "unknown"


@dataclass
class JobPaymentRecord:
    job_id: str
    kind: str
    mints: bool
    amount_cents: int
    currency: str
    payment_intent_id: str | None
    status: str
    idempotency_key: str
    created_at: str
    distinct_from: str = BLOCK_REWARD_KIND

    def to_dict(self) -> dict:
        return asdict(self)


class StripeJobLedger:
    """Persists JobPayment intents + webhook event idempotence. No keys stored."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.is_file():
            self._write({"payments": [], "webhook_events": []})

    def _read(self) -> dict:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.error("stripe ledger unreadable %s %s", self.path, exc)
            return {"payments": [], "webhook_events": []}
        if not isinstance(data, dict):
            return {"payments": [], "webhook_events": []}
        data.setdefault("payments", [])
        data.setdefault("webhook_events", [])
        return data

    def _write(self, data: dict) -> None:
        self.path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        try:
            self.path.chmod(0o600)
        except OSError:
            pass

    def save_payment(self, rec: JobPaymentRecord) -> JobPaymentRecord:
        data = self._read()
        rows = data["payments"]
        for i, row in enumerate(rows):
            if row.get("job_id") == rec.job_id or row.get("idempotency_key") == rec.idempotency_key:
                rows[i] = rec.to_dict()
                self._write(data)
                return rec
        rows.append(rec.to_dict())
        self._write(data)
        return rec

    def get_by_idempotency(self, key: str) -> dict | None:
        for row in self._read()["payments"]:
            if row.get("idempotency_key") == key:
                return row
        return None

    def webhook_seen(self, event_id: str) -> bool:
        return any(e.get("id") == event_id for e in self._read()["webhook_events"])

    def record_webhook(self, event_id: str, event_type: str) -> bool:
        """Return False if duplicate (already processed)."""
        if self.webhook_seen(event_id):
            logger.debug("stripe webhook duplicate event_id=%s", event_id)
            return False
        data = self._read()
        data["webhook_events"].append(
            {
                "id": event_id,
                "type": event_type,
                "received_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            }
        )
        self._write(data)
        return True


def _stripe_post(path: str, fields: dict, *, key: str, idempotency_key: str) -> dict:
    import urllib.error
    import urllib.request

    mode = assert_test_key(key)
    body = urlencode(fields).encode("utf-8")
    req = urllib.request.Request(
        f"{STRIPE_API}{path}",
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {key}",
            "Idempotency-Key": idempotency_key,
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "ARTCB-stripe-jobs/164",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        logger.error("stripe HTTP %s (key not logged) body=%s", exc.code, detail)
        raise StripeJobError(f"stripe HTTP {exc.code}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        logger.error("stripe network error (key not logged) type=%s", type(exc).__name__)
        raise StripeJobError("stripe network error") from exc
    logger.debug(
        "stripe POST %s id=%s status=%s mode=%s",
        path,
        payload.get("id"),
        payload.get("status"),
        mode,
    )
    return payload


def create_priority_job_payment(
    *,
    job_id: str,
    amount_cents: int = DEFAULT_PRIORITY_CENTS,
    currency: str = "usd",
    ledger: StripeJobLedger | None = None,
    idempotency_key: str | None = None,
) -> JobPaymentRecord:
    if amount_cents < PRIORITY_JOB_MIN_CENTS:
        raise StripeJobError(
            f"priority JobPayment below anti-spam floor {PRIORITY_JOB_MIN_CENTS} cents"
        )
    key = stripe_secret()
    if not key:
        raise StripeJobError(
            "no Stripe secret in env (KEY_API_STRIPE_ACTION / STRIPE_SECRET_KEY / STRIPE_API_KEY)"
        )
    mode = assert_test_key(key)
    if mode == "live":
        amount_cents = min(int(amount_cents), PRIORITY_JOB_MIN_CENTS)
    idem = idempotency_key or hashlib.sha256(f"{job_id}|{amount_cents}|{currency}".encode()).hexdigest()
    if ledger:
        existing = ledger.get_by_idempotency(idem)
        if existing and existing.get("payment_intent_id"):
            logger.debug("stripe idempotent replay job=%s", job_id)
            return JobPaymentRecord(**{k: existing[k] for k in JobPaymentRecord.__dataclass_fields__})

    intent = _stripe_post(
        "/payment_intents",
        {
            "amount": str(amount_cents),
            "currency": currency,
            "capture_method": "manual",
            "automatic_payment_methods[enabled]": "true",
            "automatic_payment_methods[allow_redirects]": "never",
            "metadata[artcb_kind]": JOB_PAYMENT_KIND,
            "metadata[artcb_job_id]": job_id,
            "metadata[artcb_mints]": "false",
            "metadata[artcb_distinct_from]": BLOCK_REWARD_KIND,
            "description": f"ARTCB priority JobPayment {job_id} (not a block reward)",
        },
        key=key,
        idempotency_key=idem,
    )
    pi_id = str(intent.get("id") or "")
    status = str(intent.get("status") or "unknown")
    if pi_id:
        try:
            cancelled = _stripe_post(
                f"/payment_intents/{pi_id}/cancel",
                {},
                key=key,
                idempotency_key=f"{idem}:cancel",
            )
            status = str(cancelled.get("status") or status)
            logger.debug("stripe PI cancelled id=%s status=%s minted=0", pi_id, status)
        except StripeJobError:
            logger.debug("stripe PI cancel failed id=%s (no capture attempted)", pi_id)
    rec = JobPaymentRecord(
        job_id=job_id,
        kind=JOB_PAYMENT_KIND,
        mints=False,
        amount_cents=amount_cents,
        currency=currency,
        payment_intent_id=pi_id or None,
        status=status,
        idempotency_key=idem,
        created_at=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    )
    if ledger:
        ledger.save_payment(rec)
    return rec


def handle_stripe_webhook(
    event: dict,
    *,
    ledger: StripeJobLedger,
) -> dict:
    event_id = str(event.get("id") or "")
    event_type = str(event.get("type") or "")
    if not event_id:
        raise StripeJobError("webhook missing event id")
    first = ledger.record_webhook(event_id, event_type)
    if not first:
        return {"duplicate": True, "event_id": event_id, "mints": False}
    obj = (event.get("data") or {}).get("object") or {}
    meta = obj.get("metadata") or {}
    if meta.get("artcb_mints") == "true":
        raise StripeJobError("webhook claims mint=true — protocol forbids mint via Stripe")
    return {
        "duplicate": False,
        "event_id": event_id,
        "type": event_type,
        "kind": meta.get("artcb_kind", JOB_PAYMENT_KIND),
        "job_id": meta.get("artcb_job_id"),
        "mints": False,
        "distinct_from": BLOCK_REWARD_KIND,
        "payment_intent_id": obj.get("id"),
        "status": obj.get("status"),
    }


def stripe_is_consensus_dependency() -> bool:
    """JobPayment is a queue-priority fee. It is never a consensus input."""
    return False


def attempt_job_payment_or_continue(
    *,
    job_id: str,
    amount_cents: int = DEFAULT_PRIORITY_CENTS,
    currency: str = "usd",
    ledger: StripeJobLedger | None = None,
) -> dict:
    """Try Stripe JobPayment. Failures must not block block production.

    Missing secret, HTTP 401/5xx, or PaymentIntent errors are recorded.
    ``mints`` stays False. ``consensus_blocked`` stays False.
    """
    payload = {
        "kind": JOB_PAYMENT_KIND,
        "mints": False,
        "distinct_from": BLOCK_REWARD_KIND,
        "consensus_blocked": False,
        "stripe_is_consensus_dependency": False,
        "job_id": job_id,
    }
    try:
        rec = create_priority_job_payment(
            job_id=job_id,
            amount_cents=amount_cents,
            currency=currency,
            ledger=ledger,
        )
        payload.update(
            {
                "ok": True,
                "status": rec.status,
                "payment_intent_id": rec.payment_intent_id,
            }
        )
        logger.debug("stripe JobPayment ok job=%s status=%s minted=0", job_id, rec.status)
        return payload
    except StripeJobError as exc:
        payload.update({"ok": False, "reason": str(exc)})
        logger.warning(
            "Stripe JobPayment failed — consensus continues (JobPayment ≠ mint): %s",
            exc,
        )
        return payload


def new_job_id() -> str:
    return f"job_{uuid.uuid4().hex[:16]}"
