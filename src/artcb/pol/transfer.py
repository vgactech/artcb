"""PoL Transfer Protocol — transactions PoL natives ARTCB.

Une PolTransfer est une transaction financière encodée dans un graphe IR,
signée ML-DSA-65 + Ed25519, gravée de manière immuable dans la blockchain.

Avantages vs Bitcoin/Ethereum :
  - Contenu sémantique riche (motif, contexte, preuve)
  - Post-quantique natif (ML-DSA-65)
  - Contexte d'apprentissage intégré (pol_score)
  - Historique immuable avec graph_id unique
"""

from __future__ import annotations
MODULE_VERSION = '1.0.0'  # R390 — auto-versioning

import json
import secrets
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


@dataclass
class PolTransfer:
    """
    Transaction PoL native.

    Représentation IR :
        E  : Alice transfère N ARTCB à Bob  (EVENT)
        C  : motif / contexte               (CONTEXT)
        P  : preuve / référence             (PROOF, optionnel)
        D  : décision validée               (DECISION)
    """
    transfer_id: str              # "ptx_" + 16 hex chars
    from_wallet: str              # adresse ARTCB source  (artcb1...)
    to_wallet: str                # adresse ARTCB cible   (artcb1...)
    amount_artcb: float           # montant en ARTCB (unités décimales)
    memo: str = ""                # motif libre (encodé dans graphe IR)
    reference: str = ""           # référence externe (hash contrat, facture…)
    timestamp: str = ""           # ISO UTC
    block_index: int | None = None # bloc où la transaction est gravée
    graph_id: str = ""            # graph_id du bloc contenant la transaction
    pol_score: float = 0.0        # score PoL du bloc de transaction
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.timestamp:
            self.timestamp = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        if not self.transfer_id:
            self.transfer_id = "ptx_" + secrets.token_hex(8)

    def to_pol_text(self) -> str:
        """Texte naturel mémorisable via PoL — encode la transaction complètement."""
        lines = [
            f"TRANSFER [{self.transfer_id}]",
            f"DE: {self.from_wallet}",
            f"VERS: {self.to_wallet}",
            f"MONTANT: {self.amount_artcb:.8f} ARTCB",
            f"DATE: {self.timestamp}",
        ]
        if self.memo:
            lines.append(f"MOTIF: {self.memo}")
        if self.reference:
            lines.append(f"REFERENCE: {self.reference}")
        return " | ".join(lines)

    def to_dict(self) -> dict:
        return {
            "transfer_id": self.transfer_id,
            "from_wallet": self.from_wallet,
            "to_wallet": self.to_wallet,
            "amount_artcb": self.amount_artcb,
            "memo": self.memo,
            "reference": self.reference,
            "timestamp": self.timestamp,
            "block_index": self.block_index,
            "graph_id": self.graph_id,
            "pol_score": self.pol_score,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, d: dict) -> PolTransfer:
        return cls(
            transfer_id=d["transfer_id"],
            from_wallet=d["from_wallet"],
            to_wallet=d["to_wallet"],
            amount_artcb=d["amount_artcb"],
            memo=d.get("memo", ""),
            reference=d.get("reference", ""),
            timestamp=d.get("timestamp", ""),
            block_index=d.get("block_index"),
            graph_id=d.get("graph_id", ""),
            pol_score=d.get("pol_score", 0.0),
            metadata=d.get("metadata", {}),
        )


class TransferLedger:
    """
    Registre local des PolTransfers — data/pol_transfers.jsonl
    Append-only, immuable (chaque ligne = 1 transfert gravé en blockchain).
    """

    def __init__(self, path: str | None = None) -> None:
        self._path = Path(path) if path else Path("data") / "pol_transfers.jsonl"
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, transfer: PolTransfer) -> None:
        with self._path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(transfer.to_dict(), ensure_ascii=False) + "\n")

    def _load_all(self) -> list[PolTransfer]:
        if not self._path.exists():
            return []
        transfers = []
        with self._path.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        transfers.append(PolTransfer.from_dict(json.loads(line)))
                    except Exception:
                        pass
        return transfers

    def by_address(self, address: str) -> list[PolTransfer]:
        """Retourne tous les transferts impliquant cette adresse."""
        return [
            t for t in self._load_all()
            if t.from_wallet == address or t.to_wallet == address
        ]

    def by_id(self, transfer_id: str) -> PolTransfer | None:
        return next((t for t in self._load_all() if t.transfer_id == transfer_id), None)

    def balance_of(self, address: str) -> float:
        """Calcule le solde PoL-transferts d'une adresse (hors rewards mining)."""
        balance = 0.0
        for t in self._load_all():
            if t.to_wallet == address:
                balance += t.amount_artcb
            if t.from_wallet == address:
                balance -= t.amount_artcb
        return round(balance, 8)

    def all_transfers(self) -> list[PolTransfer]:
        return self._load_all()


