"""Universal Dividend Vault — rapport 162.

Fees (already minted ARTCB) and net external priority revenue (fiat after
processor fees/taxes) go here. They do **not** increase RemainingSupply.
Eligible: verified adult AND no own active machine AND no external binding.
Equal monthly split (scenario A). Weighted-need variant is not frozen.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from src.artcb.economics.satoshi import allocate_satoshi

logger = logging.getLogger("artcb.economics.dividend")


class DividendError(ValueError):
    pass


@dataclass
class DividendVault:
    artcb_satoshi: int = 0
    fiat_net_minor: int = 0  # integer cents / euro-cents
    updated_at: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


class UniversalDividendVault:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.is_file():
            self._write(DividendVault(updated_at=_now()).to_dict())

    def _read(self) -> DividendVault:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return DividendVault(**data)
        except (OSError, json.JSONDecodeError, TypeError) as exc:
            logger.error("vault unreadable %s %s", self.path, exc)
            return DividendVault(updated_at=_now())

    def _write(self, payload: dict) -> None:
        self.path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    def credit_artcb_fees(self, satoshi: int) -> DividendVault:
        if satoshi < 0:
            raise DividendError("cannot credit negative ARTCB")
        vault = self._read()
        vault.artcb_satoshi += satoshi
        vault.updated_at = _now()
        self._write(vault.to_dict())
        logger.debug("vault +%s satoshi balance=%s", satoshi, vault.artcb_satoshi)
        return vault

    def credit_fiat_net(self, *, gross: float, processor_fee: float, taxes: float, refund_reserve: float = 0.0) -> float:
        net = gross - processor_fee - taxes - refund_reserve
        if net < 0:
            net = 0.0
        vault = self._read()
        vault.fiat_net_minor += int(round(net * 100))
        vault.updated_at = _now()
        self._write(vault.to_dict())
        logger.debug("vault fiat net=%.4f (does not mint ARTCB)", net)
        return net

    def snapshot_equal(self, eligible_addresses: list[str]) -> dict[str, int]:
        vault = self._read()
        if not eligible_addresses:
            logger.debug("no eligible dividend users")
            return {}
        split = allocate_satoshi({addr: 1.0 for addr in eligible_addresses}, vault.artcb_satoshi)
        vault.artcb_satoshi = 0
        vault.updated_at = _now()
        self._write(vault.to_dict())
        logger.debug("dividend snapshot n=%s", len(eligible_addresses))
        return split


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
