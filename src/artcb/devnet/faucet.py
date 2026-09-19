"""Faucet tARTCB — artcb-devnet uniquement."""

from __future__ import annotations
MODULE_VERSION = '1.0.0'  # R390 — auto-versioning

import json
import logging
import uuid
from datetime import UTC, datetime
from pathlib import Path

logger = logging.getLogger("artcb.devnet.faucet")

DEFAULT_FAUCET_AMOUNT_SATOSHI = 1_000_000_000  # 10 tARTCB
MAX_REQUESTS_PER_ADDRESS = 3


class FaucetError(Exception):
    pass


class DevnetFaucet:
    """Distribue tARTCB de test — ledger separe de la chaine PoL."""

    def __init__(self, data_dir: Path, *, amount_satoshi: int = DEFAULT_FAUCET_AMOUNT_SATOSHI) -> None:
        self.ledger_path = Path(data_dir) / "devnet" / "faucet_ledger.jsonl"
        self.ledger_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.ledger_path.is_file():
            self.ledger_path.write_text("", encoding="utf-8")
        self.amount_satoshi = amount_satoshi

    def _read_entries(self) -> list[dict]:
        entries: list[dict] = []
        for line in self.ledger_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                entries.append(json.loads(line))
        return entries

    def count_for_address(self, address: str) -> int:
        return sum(1 for e in self._read_entries() if e.get("address") == address)

    def total_for_address(self, address: str) -> int:
        return sum(
            int(e.get("amount_satoshi", 0))
            for e in self._read_entries()
            if e.get("address") == address
        )

    def request(self, address: str) -> dict:
        if not address.startswith("artcb1"):
            raise FaucetError("Adresse ARTCB invalide — doit commencer par artcb1")
        count = self.count_for_address(address)
        if count >= MAX_REQUESTS_PER_ADDRESS:
            raise FaucetError(f"Limite faucet atteinte ({MAX_REQUESTS_PER_ADDRESS} requetes)")

        entry = {
            "tx_id": f"faucet_{uuid.uuid4().hex[:16]}",
            "address": address,
            "amount_satoshi": self.amount_satoshi,
            "coin": "tARTCB",
            "network": "artcb-devnet-1",
            "timestamp": datetime.now(UTC).isoformat(),
        }
        with self.ledger_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False, separators=(",", ":")) + "\n")
        logger.info("Faucet credited %s satoshi to %s", self.amount_satoshi, address[:16])
        return {
            **entry,
            "balance_faucet_satoshi": self.total_for_address(address),
            "requests_remaining": MAX_REQUESTS_PER_ADDRESS - count - 1,
        }

    def ledger_summary(self) -> dict:
        entries = self._read_entries()
        return {
            "network": "artcb-devnet-1",
            "coin": "tARTCB",
            "total_requests": len(entries),
            "total_distributed_satoshi": sum(int(e.get("amount_satoshi", 0)) for e in entries),
            "amount_per_request": self.amount_satoshi,
            "max_requests_per_address": MAX_REQUESTS_PER_ADDRESS,
        }
