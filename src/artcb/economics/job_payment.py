"""Priority job payment (Stripe) — off-chain money, never a mint.

JobPayment ≠ BlockReward. A successful Stripe PaymentIntent records a
priority-lane credit and (after processor fees) can fund the
UniversalDividendVault in fiat. Remaining 21M supply is untouched.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from src.artcb.economics.dividend import UniversalDividendVault
from src.artcb.tokenomics import MAX_SUPPLY_SATOSHI

logger = logging.getLogger("artcb.economics.job_payment")

STRIPE_API = "https://api.stripe.com/v1"
ENV_KEYS = ("KEY_API_STRIPE_ACTION", "STRIPE_SECRET_KEY")


class JobPaymentError(ValueError):
    pass


@dataclass
class JobPaymentRecord:
    payment_id: str
    job_id: str
    provider_address: str
    amount_cents: int
    currency: str
    stripe_id: str | None
    status: str
    minted_satoshi: int
    remaining_supply_satoshi: int
    created_at: str
    mode: str

    def to_dict(self) -> dict:
        return asdict(self)


def stripe_secret_from_env() -> str | None:
    for name in ENV_KEYS:
        raw = os.getenv(name, "").strip()
        if raw:
            return raw
    return None


def stripe_key_mode(secret: str) -> str:
    secret = secret.strip()
    if secret.startswith(("sk_test_", "rk_test_")):
        return "test"
    if secret.startswith(("sk_live_", "rk_live_")):
        return "live"
    return "unknown"


def _stripe_request(secret: str, method: str, path: str, fields: dict[str, str] | None = None) -> dict[str, Any]:
    url = f"{STRIPE_API}{path}"
    data = urlencode(fields or {}).encode("utf-8") if fields else None
    req = Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {secret}")
    if fields is not None:
        req.add_header("Content-Type", "application/x-www-form-urlencoded")
    try:
        with urlopen(req, timeout=20) as resp:  # noqa: S310 — Stripe HTTPS
            return json.loads(resp.read().decode("utf-8"))
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:300]
        logger.debug("stripe HTTP %s (secret never logged) body=%s", exc.code, body)
        raise JobPaymentError(f"stripe HTTP {exc.code}") from exc
    except (URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        raise JobPaymentError(f"stripe transport {type(exc).__name__}") from exc


def create_and_cancel_payment_intent(
    *,
    amount_cents: int = 50,
    currency: str = "eur",
    metadata: dict[str, str] | None = None,
    secret: str | None = None,
) -> dict[str, Any]:
    """Create a PaymentIntent then cancel it.

    Test keys: real Stripe TEST API.
    Live keys: still create+cancel a tiny amount — never capture, never leave
    money moving.
    """
    secret = secret or stripe_secret_from_env()
    if not secret:
        raise JobPaymentError("stripe secret unset (KEY_API_STRIPE_ACTION / STRIPE_SECRET_KEY)")
    mode = stripe_key_mode(secret)
    logger.debug("stripe PI create+cancel mode=%s amount_cents=%s (key not logged)", mode, amount_cents)
    if mode == "live":
        logger.debug("LIVE stripe key detected — create+cancel only, no capture")
        amount_cents = min(amount_cents, 50)
    fields = {
        "amount": str(int(amount_cents)),
        "currency": currency,
        "capture_method": "manual",
        "confirm": "false",
        "payment_method_types[]": "card",
    }
    for key, value in (metadata or {}).items():
        fields[f"metadata[{key}]"] = value
    created = _stripe_request(secret, "POST", "/payment_intents", fields)
    pi_id = str(created.get("id") or "")
    if not pi_id:
        raise JobPaymentError("stripe PaymentIntent missing id")
    cancelled = _stripe_request(secret, "POST", f"/payment_intents/{pi_id}/cancel", {})
    return {
        "id": pi_id,
        "status": cancelled.get("status") or created.get("status"),
        "amount": created.get("amount"),
        "currency": created.get("currency"),
        "mode": mode,
        "captured": False,
        "minted_satoshi": 0,
    }


class JobPaymentLedger:
    def __init__(self, path: Path, *, vault: UniversalDividendVault | None = None) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.is_file():
            self._write([])
        self.vault = vault

    def _read(self) -> list[dict]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.error("job payment ledger unreadable %s %s", self.path, exc)
            return []
        return data if isinstance(data, list) else []

    def _write(self, rows: list[dict]) -> None:
        self.path.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")

    def record(
        self,
        *,
        job_id: str,
        provider_address: str,
        amount_cents: int,
        currency: str = "eur",
        stripe_id: str | None = None,
        status: str = "recorded",
        mode: str = "offline",
        issued_so_far_satoshi: int = 0,
        processor_fee_cents: int = 0,
    ) -> JobPaymentRecord:
        if amount_cents < 0:
            raise JobPaymentError("amount_cents must be >= 0")
        remaining = MAX_SUPPLY_SATOSHI - issued_so_far_satoshi
        rec = JobPaymentRecord(
            payment_id=f"pay_{os.urandom(6).hex()}",
            job_id=job_id,
            provider_address=provider_address,
            amount_cents=amount_cents,
            currency=currency,
            stripe_id=stripe_id,
            status=status,
            minted_satoshi=0,
            remaining_supply_satoshi=remaining,
            created_at=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            mode=mode,
        )
        rows = self._read()
        rows.append(rec.to_dict())
        self._write(rows)
        if self.vault is not None and amount_cents > 0:
            gross = amount_cents / 100.0
            fee = processor_fee_cents / 100.0
            self.vault.credit_fiat_net(gross=gross, processor_fee=fee, taxes=0.0)
        logger.debug(
            "job payment recorded job=%s minted=0 remaining=%s stripe=%s",
            job_id,
            remaining,
            bool(stripe_id),
        )
        return rec

    def total_minted_satoshi(self) -> int:
        return sum(int(row.get("minted_satoshi") or 0) for row in self._read())
