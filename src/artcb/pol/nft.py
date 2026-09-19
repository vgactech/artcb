"""PoL NFT — Tokens Non-Fongibles Sémantiques ARTCB.

Un PolNFT est une œuvre ou un actif unique encodé dans un graphe IR,
signé ML-DSA-65 + Ed25519, gravé de manière immuable dans la blockchain.

Avantages vs NFT Ethereum :
  - Contenu INTÉGRÉ dans la blockchain (pas un lien IPFS qui peut mourir)
  - Post-quantique natif (ML-DSA-65)
  - Sémantique riche : titre, auteur, description, droits, contexte
  - Ownership traçable via graph_id unique + bloc signé
  - Transferable via PolTransfer
"""

from __future__ import annotations
MODULE_VERSION = '1.0.0'  # R390 — auto-versioning

import json
import secrets
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


@dataclass
class PolNFT:
    """
    NFT PoL — Actif numérique unique gravé dans la blockchain ARTCB.

    Représentation IR :
        E  : Création de l'œuvre "titre" par "auteur"  (EVENT)
        F  : Hash contenu SHA-256 : abc123...           (FACT — preuve)
        C  : Contexte / description                     (CONTEXT)
        D  : Droits et licence                          (DECISION)
        G  : Objectif / usage prévu                     (GOAL, optionnel)
    """
    nft_id: str               # "nft_" + 16 hex chars — identifiant unique
    title: str                # titre de l'œuvre / de l'actif
    creator_wallet: str       # adresse ARTCB du créateur (artcb1...)
    owner_wallet: str         # adresse ARTCB du propriétaire actuel
    content_hash: str         # SHA-256 du fichier/contenu (peut être "" si texte pur)
    description: str = ""     # description sémantique riche
    content_text: str = ""    # texte court (si NFT texte/code — contenu intégré)
    license: str = "CC-BY-4.0"
    edition: str = "1/1"      # numérotation (ex: "3/100")
    created_at: str = ""
    block_index: int | None = None  # bloc où le NFT est gravé
    graph_id: str = ""        # graph_id du bloc de création
    transfer_history: list[dict] = field(default_factory=list)  # historique ownership
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.created_at:
            self.created_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        if not self.nft_id:
            self.nft_id = "nft_" + secrets.token_hex(8)
        if not self.owner_wallet:
            self.owner_wallet = self.creator_wallet

    def to_pol_text(self) -> str:
        """Texte naturel mémorisable via PoL — encode le NFT complètement."""
        lines = [
            f"NFT [{self.nft_id}] {self.title}",
            f"CREATEUR: {self.creator_wallet}",
            f"PROPRIETAIRE: {self.owner_wallet}",
            f"EDITION: {self.edition}",
            f"LICENCE: {self.license}",
            f"DATE_CREATION: {self.created_at}",
        ]
        if self.content_hash:
            lines.append(f"HASH_CONTENU: {self.content_hash}")
        if self.description:
            lines.append(f"DESCRIPTION: {self.description[:500]}")
        if self.content_text:
            lines.append(f"CONTENU: {self.content_text[:1000]}")
        return " | ".join(lines)

    def transfer_to(self, new_owner: str, transfer_id: str = "") -> PolNFT:
        """Retourne une copie du NFT avec le nouveau propriétaire."""
        history = list(self.transfer_history) + [{
            "from": self.owner_wallet,
            "to": new_owner,
            "transfer_id": transfer_id or f"ptx_{secrets.token_hex(8)}",
            "timestamp": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }]
        import dataclasses
        return dataclasses.replace(self, owner_wallet=new_owner, transfer_history=history)

    def to_dict(self) -> dict:
        return {
            "nft_id": self.nft_id,
            "title": self.title,
            "creator_wallet": self.creator_wallet,
            "owner_wallet": self.owner_wallet,
            "content_hash": self.content_hash,
            "description": self.description,
            "content_text": self.content_text,
            "license": self.license,
            "edition": self.edition,
            "created_at": self.created_at,
            "block_index": self.block_index,
            "graph_id": self.graph_id,
            "transfer_history": self.transfer_history,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, d: dict) -> PolNFT:
        return cls(
            nft_id=d["nft_id"],
            title=d["title"],
            creator_wallet=d["creator_wallet"],
            owner_wallet=d.get("owner_wallet", d["creator_wallet"]),
            content_hash=d.get("content_hash", ""),
            description=d.get("description", ""),
            content_text=d.get("content_text", ""),
            license=d.get("license", "CC-BY-4.0"),
            edition=d.get("edition", "1/1"),
            created_at=d.get("created_at", ""),
            block_index=d.get("block_index"),
            graph_id=d.get("graph_id", ""),
            transfer_history=d.get("transfer_history", []),
            metadata=d.get("metadata", {}),
        )


class NFTRegistry:
    """
    Registre local des PolNFT — data/pol_nfts.json
    Chaque NFT est aussi gravé dans la blockchain (graph_id immuable).
    """

    def __init__(self, path: str | None = None) -> None:
        self._path = Path(path) if path else Path("data") / "pol_nfts.json"
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def _load(self) -> list[PolNFT]:
        if not self._path.exists():
            return []
        try:
            return [PolNFT.from_dict(n) for n in json.loads(self._path.read_text())]
        except Exception:
            return []

    def _save(self, nfts: list[PolNFT]) -> None:
        self._path.write_text(json.dumps([n.to_dict() for n in nfts], indent=2, ensure_ascii=False))

    def mint(self, nft: PolNFT) -> PolNFT:
        """Enregistre un nouveau NFT."""
        nfts = self._load()
        if any(n.nft_id == nft.nft_id for n in nfts):
            raise ValueError(f"NFT {nft.nft_id} existe déjà")
        nfts.append(nft)
        self._save(nfts)
        return nft

    def get(self, nft_id: str) -> PolNFT | None:
        return next((n for n in self._load() if n.nft_id == nft_id), None)

    def by_owner(self, owner_wallet: str) -> list[PolNFT]:
        return [n for n in self._load() if n.owner_wallet == owner_wallet]

    def by_creator(self, creator_wallet: str) -> list[PolNFT]:
        return [n for n in self._load() if n.creator_wallet == creator_wallet]

    def transfer(self, nft_id: str, new_owner: str, transfer_id: str = "") -> PolNFT:
        """Transfère l'ownership d'un NFT."""
        nfts = self._load()
        for i, n in enumerate(nfts):
            if n.nft_id == nft_id:
                nfts[i] = n.transfer_to(new_owner, transfer_id)
                self._save(nfts)
                return nfts[i]
        raise ValueError(f"NFT {nft_id} introuvable")

    def list_all(self) -> list[PolNFT]:
        return self._load()


