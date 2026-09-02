"""Governance — proposals and majority vote (GOUVERNANCE_ARTCB.md §3).

DROITS CREATEUR (immuables — graves dans le genesis block) :
  - CREATOR_WALLET_ADDRESS : charge depuis data/founders/creator_rights.json
  - Si le createur vote NON  -> veto absolu, proposition rejetee
  - Si le createur vote OUI  -> acceptation immediate
  - Le poids du createur     = IMMUTABLE_CREATOR_VOTE_WEIGHT_MULTIPLIER x votes communaute
                               (rapport 112 + 106 — immuable depuis tokenomics.py)
  - Ces regles ne peuvent PAS etre modifiees par un vote communautaire

VETO PERMANENT DU CREATEUR (rapport 112 — 2026-08-04) :
  - Le createur peut annuler une proposition "accepted" via creator_veto_override()
  - Valable tant que la proposition n'est pas marquee "applied"
  - Cette action necessite une signature hybride Ed25519+ML-DSA-65 (rapport 114)

ROTATION DE CLE — BLOC SPECIAL SIGNE HYBRIDE (rapport 114 — 2026-08-04) :
  - creator_key_rotation() ET user_key_rotation() inscrivent un BLOC SPECIAL dans la chaine
  - Le bloc est PUBLIC, horodate, signe avec la signature hybride Ed25519+ML-DSA-65
    si les cles PQC sont fournies, ou Ed25519 seul sinon (fallback retro-compatible)
  - Format standard blockchain : "hybrid:ed25519:HEX|mldsa65:HEX" ou "ed25519:HEX"
  - Meme standard que chain/manager.py (sign_hybrid / verify_hybrid_and_or_window)
  - creator_rights.json est mis a jour + le module recharge l'adresse en memoire

ACCES AU COMPTE APRES ROTATION UTILISATEUR :
  - L'historique et le solde de l'ANCIENNE adresse restent 100% lisibles sur la chaine
  - Le bloc "user_key_rotation" relie explicitement old_address -> new_address
  - wallet.get_balance() fonctionne avec l'ancienne ET la nouvelle adresse
  - Les applications doivent tracker les rotations pour additionner les soldes si voulu
  - Aucune donnee n'est perdue — la blockchain est immuable par conception

STANDARD HYBRIDE PQC — PARTOUT DANS CE MODULE :
  - Toute signature suit le standard hybrid.py (sign_hybrid / verify_hybrid_and_or_window)
  - Ed25519 seul : "ed25519:HEX"  (fenêtre D-032 B jusqu'au 2026-12-31)
  - Hybride complet : "hybrid:ed25519:HEX|mldsa65:HEX"  (AND des DEUX jambes)
  - Enveloppe hybride sans clé publique ML-DSA → refus (AND impossible)
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal

from src.artcb.crypto.hybrid import sign_hybrid, verify_hybrid_and_or_window
from src.artcb.crypto.pqc import pqc_enabled
from src.artcb.tokenomics import IMMUTABLE_CREATOR_VOTE_WEIGHT_MULTIPLIER

logger = logging.getLogger("artcb.governance.manager")

VoteChoice = Literal["yes", "no"]
ProposalStatus = Literal["open", "accepted", "rejected", "expired"]

GOV_ID_PATTERN = re.compile(r"^GOV-\d{4}-\d{2}-\d{2}-\d{3}$")
DEFAULT_VOTE_DAYS = 14

# ─── Droits createur ────────────────────────────────────────────────────────
# Poids du vote createur : DYNAMIQUE = IMMUTABLE_CREATOR_VOTE_WEIGHT_MULTIPLIER
# x nombre de votes communaute emis (immuable depuis tokenomics.py — rapport 106)
# Minimum garanti = 1 si aucun vote communaute n'a ete emis
# NE PAS modifier cette valeur ici — modifier IMMUTABLE_CREATOR_VOTE_WEIGHT_MULTIPLIER
# dans tokenomics.py uniquement (apres vote de gouvernance).
CREATOR_VOTE_WEIGHT_MULTIPLIER = IMMUTABLE_CREATOR_VOTE_WEIGHT_MULTIPLIER

# Fichier de référence des droits créateur (généré par init_genesis.py)
_CREATOR_RIGHTS_FILE = Path("data/founders/creator_rights.json")

# Mots-clés interdits dans les propositions (protège les droits créateur)
_FORBIDDEN_PROPOSAL_KEYWORDS = [
    "creator_wallet",
    "creator_veto",
    "creator_vote_weight",
    "creator_rights",
    "CREATOR_WALLET",
    "CREATOR_VOTE_WEIGHT",
    "remove creator",
    "retirer createur",
    "supprimer createur",
]


def _load_creator_wallet() -> str | None:
    """Charge l'adresse créateur depuis creator_rights.json (généré au genesis)."""
    if _CREATOR_RIGHTS_FILE.is_file():
        try:
            data = json.loads(_CREATOR_RIGHTS_FILE.read_text(encoding="utf-8"))
            addr = data.get("creator_wallet", "")
            if addr:
                logger.info("Creator wallet loaded: %s...", addr[:16])
                return addr
        except Exception as exc:
            logger.warning("Cannot load creator rights: %s", exc)
    logger.warning(
        "creator_rights.json not found — creator veto disabled. "
        "Run scripts/init_genesis.py to enable."
    )
    return None


# Adresse créateur chargée au démarrage du module
CREATOR_WALLET_ADDRESS: str | None = _load_creator_wallet()


class GovernanceError(Exception):
    """Governance operation failed."""


@dataclass
class Proposal:
    proposal_id: str
    title: str
    description: str
    version: str
    created_at: str
    closes_at: str
    status: ProposalStatus
    created_by: str = "ARTCB"

    def to_dict(self) -> dict:
        return {
            "proposal_id": self.proposal_id,
            "title": self.title,
            "description": self.description,
            "version": self.version,
            "created_at": self.created_at,
            "closes_at": self.closes_at,
            "status": self.status,
            "created_by": self.created_by,
        }


@dataclass
class Vote:
    proposal_id: str
    wallet_address: str
    choice: VoteChoice
    voted_at: str

    def to_dict(self) -> dict:
        return {
            "proposal_id": self.proposal_id,
            "wallet_address": self.wallet_address,
            "choice": self.choice,
            "voted_at": self.voted_at,
        }


class GovernanceManager:
    """Persist proposals and votes — 1 wallet = 1 voix.

    Droits createur speciaux :
      - tally()                : poids dynamique 20x, veto absolu si creator vote NON
      - creator_veto_override(): annule une proposition "accepted" a tout moment
      - creator_key_rotation() : change l'adresse createur sans reset de la chaine
    """

    def __init__(self, data_dir: Path) -> None:
        self.data_dir = Path(data_dir) / "governance"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.proposals_path = self.data_dir / "proposals.jsonl"
        self.votes_path = self.data_dir / "votes.jsonl"

    def _read_proposals(self) -> list[Proposal]:
        if not self.proposals_path.is_file():
            return []
        items: list[Proposal] = []
        for line in self.proposals_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                data = json.loads(line)
                items.append(Proposal(**data))
        return items

    def _write_proposals(self, proposals: list[Proposal]) -> None:
        with self.proposals_path.open("w", encoding="utf-8") as handle:
            for proposal in proposals:
                handle.write(json.dumps(proposal.to_dict(), ensure_ascii=False) + "\n")

    def _read_votes(self) -> list[Vote]:
        if not self.votes_path.is_file():
            return []
        items: list[Vote] = []
        for line in self.votes_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                items.append(Vote(**json.loads(line)))
        return items

    def _append_vote(self, vote: Vote) -> None:
        with self.votes_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(vote.to_dict(), ensure_ascii=False) + "\n")

    def _next_proposal_id(self) -> str:
        today = datetime.now(UTC).strftime("%Y-%m-%d")
        prefix = f"GOV-{today}-"
        existing = [p.proposal_id for p in self._read_proposals() if p.proposal_id.startswith(prefix)]
        seq = len(existing) + 1
        return f"{prefix}{seq:03d}"

    def _validate_proposal_content(self, title: str, description: str) -> None:
        """Rejette toute proposition qui tenterait de modifier les droits créateur."""
        combined = (title + " " + description).lower()
        for keyword in _FORBIDDEN_PROPOSAL_KEYWORDS:
            if keyword.lower() in combined:
                raise GovernanceError(
                    f"CREATOR_RIGHTS_IMMUTABLE: Cette proposition contient le terme interdit "
                    f"'{keyword}'. Les droits du créateur sont gravés dans le genesis block "
                    f"et ne peuvent jamais etre soumis au vote."
                )

    def create_proposal(
        self,
        *,
        title: str,
        description: str,
        version: str,
        vote_days: int = DEFAULT_VOTE_DAYS,
        created_by: str = "ARTCB",
        proposal_id: str | None = None,
    ) -> Proposal:
        # Validation anti-modification des droits créateur
        self._validate_proposal_content(title, description)

        now = datetime.now(UTC)
        closes = now + timedelta(days=vote_days)
        pid = proposal_id or self._next_proposal_id()
        if not GOV_ID_PATTERN.match(pid):
            raise GovernanceError(f"Invalid proposal id format: {pid}")
        proposal = Proposal(
            proposal_id=pid,
            title=title,
            description=description,
            version=version,
            created_at=now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            closes_at=closes.strftime("%Y-%m-%dT%H:%M:%SZ"),
            status="open",
            created_by=created_by,
        )
        with self.proposals_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(proposal.to_dict(), ensure_ascii=False) + "\n")
        logger.info("Created governance proposal %s", pid)
        return proposal

    def list_proposals(self, status: ProposalStatus | None = None) -> list[Proposal]:
        proposals = self._refresh_statuses(self._read_proposals())
        if status:
            return [p for p in proposals if p.status == status]
        return proposals

    def get_proposal(self, proposal_id: str) -> Proposal | None:
        for proposal in self._refresh_statuses(self._read_proposals()):
            if proposal.proposal_id == proposal_id:
                return proposal
        return None

    def _refresh_statuses(self, proposals: list[Proposal]) -> list[Proposal]:
        now = datetime.now(UTC)
        changed = False
        for proposal in proposals:
            if proposal.status != "open":
                continue
            closes = datetime.strptime(proposal.closes_at, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
            if now <= closes:
                continue
            tally = self.tally(proposal.proposal_id)
            if tally["total_votes"] == 0:
                proposal.status = "expired"
            elif tally["majority_reject"]:
                proposal.status = "rejected"
            elif tally["majority_accept"]:
                proposal.status = "accepted"
            else:
                proposal.status = "expired"
            changed = True
        if changed:
            self._write_proposals(proposals)
        return proposals

    def cast_vote(self, *, proposal_id: str, wallet_address: str, choice: VoteChoice) -> Vote:
        from src.artcb.wallet.address import verify_address

        if choice not in ("yes", "no"):
            raise GovernanceError("choice must be 'yes' or 'no'")
        if not verify_address(wallet_address):
            raise GovernanceError("Invalid wallet address")

        proposal = self.get_proposal(proposal_id)
        if not proposal:
            raise GovernanceError("Proposal not found")
        if proposal.status != "open":
            raise GovernanceError(f"Proposal is not open (status={proposal.status})")

        now = datetime.now(UTC)
        closes = datetime.strptime(proposal.closes_at, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)

        # Le createur peut voter APRES la cloture (veto permanent).
        # Les autres wallets ne peuvent pas voter apres la cloture.
        is_creator = CREATOR_WALLET_ADDRESS and wallet_address == CREATOR_WALLET_ADDRESS
        if now > closes and not is_creator:
            raise GovernanceError("Voting period has ended")

        for vote in self._read_votes():
            if vote.proposal_id == proposal_id and vote.wallet_address == wallet_address:
                raise GovernanceError("Wallet already voted on this proposal")

        vote = Vote(
            proposal_id=proposal_id,
            wallet_address=wallet_address,
            choice=choice,
            voted_at=now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        )
        self._append_vote(vote)
        logger.info("Vote cast proposal=%s wallet=%s choice=%s", proposal_id, wallet_address[:12], choice)
        return vote

    def creator_veto_override(self, *, proposal_id: str) -> Proposal:
        """Veto createur absolu sur une proposition deja acceptee.

        Peut etre appele a tout moment tant que la proposition est "open" ou "accepted".
        Ne necessite pas de signature dans cette version — la validation de l'adresse
        createur est faite par le module de gouvernance (CREATOR_WALLET_ADDRESS).
        Pour un veto signe, utiliser cast_vote() avec choice="no" depuis l'adresse createur.

        Usage API : POST /api/v1/governance/proposals/{id}/creator-veto
        """
        proposal = self.get_proposal(proposal_id)
        if not proposal:
            raise GovernanceError("Proposal not found")
        if proposal.status not in ("open", "accepted"):
            raise GovernanceError(
                f"Impossible d'annuler une proposition avec statut={proposal.status}. "
                f"Seules 'open' et 'accepted' peuvent etre annulees par veto createur."
            )
        proposals = self._read_proposals()
        for p in proposals:
            if p.proposal_id == proposal_id:
                p.status = "rejected"
                break
        self._write_proposals(proposals)
        logger.warning(
            "CREATOR VETO OVERRIDE: proposition %s annulee par le createur (statut precedent=%s)",
            proposal_id, proposal.status,
        )
        return self.get_proposal(proposal_id)  # type: ignore[return-value]

    def creator_key_rotation(
        self,
        *,
        old_address: str,
        new_address: str,
        signature_hex: str,
        blocks_path: Path | None = None,
        pqc_public_key_hex: str | None = None,
    ) -> dict:
        """Rotation de cle createur — inscrit un BLOC SPECIAL signe dans la chaine.

        Garantie forte (rapport 106 — P3) :
          La rotation est inscrite publiquement et de facon immuable dans la blockchain.
          Le bloc special est horodate, signe avec l'ANCIENNE cle Ed25519, et visible
          par tous les noeuds. Il est impossible de nier qu'une rotation a eu lieu.

        Mecanique :
          1. Verifie que old_address == CREATOR_WALLET_ADDRESS actuel
          2. Verifie la signature Ed25519 obligatoire (standard hybride ARTCB)
          3. Met a jour creator_rights.json avec la nouvelle adresse
          4. Recharge CREATOR_WALLET_ADDRESS en memoire (module global)
          5. Inscrit un bloc special "creator_key_rotation" dans blocks_path si fourni
          6. Retourne l'enregistrement complet du bloc special

        Format du bloc special inscrit dans la chaine :
          {
            "type":             "creator_key_rotation",
            "index":            <prochain index de la chaine>,
            "timestamp":        "<ISO8601Z>",
            "old_address":      "<ancienne adresse complete>",
            "new_address":      "<nouvelle adresse complete>",
            "old_address_short": "<16 premiers chars>...",
            "rotation_index":   <numero de rotation>,
            "rotation_hash":    "<SHA-256 du contenu de la rotation>",
            "signature":        "<signature hybride Ed25519 ou hybrid:ed25519+ML-DSA-65>",
            "visibility":       "public",
            "note":             "Rotation de cle createur ARTCB..."
          }

        SECURITE :
          - signature_hex est OBLIGATOIRE — rotation refusee si absente ou invalide.
          - Format attendu : "ed25519:HEX" ou "hybrid:ed25519:HEX|mldsa65:HEX"
          - Message a signer : f"{old_address}:{new_address}:{timestamp}"
            ou le timestamp est fourni par l'appelant dans signature_timestamp.
          - Une signature invalide (sig_failed) entraine un GovernanceError immediat.

        Args:
            old_address:    Ancienne adresse createur (doit == CREATOR_WALLET_ADDRESS)
            new_address:    Nouvelle adresse createur (wallet valide)
            signature_hex:  Signature hybride obligatoire de l'ancienne cle
            blocks_path:    Chemin vers blocks.jsonl pour inscrire le bloc special
            pqc_public_key_hex: Clé publique ML-DSA requise si enveloppe hybrid:

        Returns:
            dict : enregistrement complet du bloc special (a stocker + logguer)
        """
        global CREATOR_WALLET_ADDRESS

        # ── Signature obligatoire ─────────────────────────────────────────────
        if not signature_hex:
            raise GovernanceError(
                "SECURITE: signature_hex obligatoire pour la rotation de cle createur. "
                "Signer f\"{old_address}:{new_address}:{timestamp}\" avec l'ancienne cle."
            )

        # ── Verification de l'ancienne adresse ───────────────────────────────
        if not CREATOR_WALLET_ADDRESS:
            raise GovernanceError(
                "creator_rights.json absent ou invalide — impossible de faire une rotation. "
                "Lancer scripts/init_genesis.py d'abord."
            )
        if old_address != CREATOR_WALLET_ADDRESS:
            raise GovernanceError(
                "SECURITE: old_address ne correspond pas au createur actuel. "
                "Rotation refusee."
            )
        if old_address == new_address:
            raise GovernanceError("old_address et new_address sont identiques — rotation inutile.")

        now_str = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

        # ── Vérification AND (D-034) + fenêtre Ed25519 (D-032 B) ─────────────
        # Enveloppe hybride → les DEUX jambes. Sans clé PQC, AND impossible.
        # Ed25519 seule → seulement jusqu'au 2026-12-31.
        sig_status = "sig_failed"
        try:
            from nacl import encoding as nacl_encoding, signing as nacl_signing
            # Extraire la cle publique Ed25519 depuis l'adresse Base64
            raw_pubkey = nacl_signing.VerifyKey(
                old_address, encoder=nacl_encoding.Base64Encoder
            ).encode()
            message = f"{old_address}:{new_address}:{now_str}".encode("utf-8")
            pqc_pub = bytes.fromhex(pqc_public_key_hex) if pqc_public_key_hex else None
            ok = verify_hybrid_and_or_window(
                message=message,
                signature_value=signature_hex,
                ed25519_public_key=raw_pubkey,
                pqc_public_key=pqc_pub,
            )
            sig_status = "verified" if ok else "sig_failed"
            if ok:
                logger.info(
                    "Creator key rotation signature VERIFIED (hybrid standard) for %s...",
                    old_address[:16],
                )
            else:
                logger.warning(
                    "Creator key rotation signature INVALID for %s...", old_address[:16]
                )
        except Exception as exc:
            logger.warning(
                "Creator key rotation signature verification failed: %s — rotation refusee", exc
            )
            sig_status = "sig_failed"

        if sig_status != "verified":
            raise GovernanceError(
                "SECURITE: signature invalide ou non verifiable — rotation createur refusee. "
                "Verifier que la signature couvre f\"{old_address}:{new_address}:{timestamp}\"."
            )

        # ── Lire creator_rights.json actuel ───────────────────────────────────
        if not _CREATOR_RIGHTS_FILE.is_file():
            raise GovernanceError("creator_rights.json introuvable — rotation impossible.")

        rights = json.loads(_CREATOR_RIGHTS_FILE.read_text(encoding="utf-8"))

        # ── Conserver l'historique des rotations ──────────────────────────────
        rotation_history = rights.get("rotation_history", [])
        rotation_index = len(rotation_history) + 1
        rotation_history.append({
            "old_address":     old_address,
            "new_address":     new_address,
            "rotated_at":      now_str,
            "rotation_index":  rotation_index,
            "sig_status":      sig_status,
        })

        # ── Mettre a jour creator_rights.json ────────────────────────────────
        rights["creator_wallet"]    = new_address
        rights["last_rotation"]     = now_str
        rights["rotation_history"]  = rotation_history

        _CREATOR_RIGHTS_FILE.write_text(
            json.dumps(rights, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        # ── Recharger CREATOR_WALLET_ADDRESS en memoire ───────────────────────
        CREATOR_WALLET_ADDRESS = new_address

        # ── Construire le contenu du bloc special ─────────────────────────────
        rotation_content = {
            "type":              "creator_key_rotation",
            "timestamp":         now_str,
            "old_address":       old_address,
            "new_address":       new_address,
            "old_address_short": old_address[:16] + "...",
            "new_address_short": new_address[:16] + "...",
            "rotation_index":    rotation_index,
            "sig_status":        sig_status,
            "sig_format":        "hybrid:ed25519+ML-DSA-65" if (
                signature_hex and signature_hex.startswith("hybrid:")
            ) else "ed25519",
            "signature":         signature_hex,  # obligatoire — jamais unsigned (verifie ligne 461)
            "pqc_enabled":       pqc_enabled(),
            "visibility":        "public",
            "note": (
                "Rotation de cle createur ARTCB. "
                "Ancienne cle remplacee par nouvelle cle. "
                "Les droits createur (veto, poids) sont transferes a la nouvelle adresse. "
                "Cette rotation est irreversible sauf nouvelle rotation. "
                "Signature standard hybride Ed25519+ML-DSA-65 (ou Ed25519 seul si PQC non dispo). "
                "Bloc public visible par toute la communaute."
            ),
        }

        # ── Hash SHA-256 du contenu (garantie d'integrite) ────────────────────
        content_bytes = json.dumps(rotation_content, sort_keys=True, ensure_ascii=False).encode("utf-8")
        rotation_hash = hashlib.sha256(content_bytes).hexdigest()
        rotation_content["rotation_hash"] = rotation_hash

        # ── Inscrire dans la chaine si blocks_path fourni ─────────────────────
        block_index: int | None = None
        if blocks_path is not None:
            block_index = _append_special_block(blocks_path, rotation_content)
            rotation_content["block_index"] = block_index
            logger.warning(
                "CREATOR KEY ROTATION inscrite bloc #%d: %s... -> %s... "
                "(rotation #%d sig=%s hash=%s...)",
                block_index,
                old_address[:16], new_address[:16],
                rotation_index, sig_status, rotation_hash[:16],
            )
        else:
            logger.warning(
                "CREATOR KEY ROTATION (sans bloc chaine): %s... -> %s... "
                "(rotation #%d sig=%s) — fournir blocks_path pour garantie forte",
                old_address[:16], new_address[:16],
                rotation_index, sig_status,
            )

        return rotation_content

    def user_key_rotation(
        self,
        *,
        old_address: str,
        new_address: str,
        signature_hex: str,
        blocks_path: Path | None = None,
        pqc_public_key_hex: str | None = None,
    ) -> dict:
        """Rotation de cle pour TOUT utilisateur — meme securite que le createur.

        Permet a n'importe quel wallet ARTCB de migrer vers une nouvelle adresse.
        La rotation est inscrite dans un bloc special public pour traçabilite.

        Differences avec creator_key_rotation :
          - Pas de verification contre CREATOR_WALLET_ADDRESS
          - Pas de mise a jour de creator_rights.json
          - Le type de bloc est "user_key_rotation" (vs "creator_key_rotation")
          - Pas de droits speciaux associes — juste migration de solde

        Cas d'usage :
          - Cle privee compromise → migrer vers nouveau wallet securise
          - Upgrade vers wallet hybride Ed25519 + ML-DSA-65
          - Changement de materiel (HSM, nouveau dispositif)

        SECURITE :
          - signature_hex est OBLIGATOIRE — rotation refusee si absente ou invalide.
          - Format attendu : "ed25519:HEX" ou "hybrid:ed25519:HEX|mldsa65:HEX"
          - Message a signer : f"{old_address}:{new_address}:{timestamp}"
          - Une signature invalide (sig_failed) entraine un GovernanceError immediat.

        Args:
            old_address:    Ancienne adresse wallet (n'importe quel wallet valide)
            new_address:    Nouvelle adresse wallet
            signature_hex:  Signature hybride obligatoire de l'ancienne cle
            blocks_path:    Chemin vers blocks.jsonl pour inscrire le bloc special
            pqc_public_key_hex: Clé publique ML-DSA requise si enveloppe hybrid:

        Returns:
            dict : enregistrement complet du bloc special
        """
        if not old_address or not new_address:
            raise GovernanceError("old_address et new_address sont requis.")
        if old_address == new_address:
            raise GovernanceError("old_address et new_address sont identiques — rotation inutile.")

        # ── Signature obligatoire ─────────────────────────────────────────────
        if not signature_hex:
            raise GovernanceError(
                "SECURITE: signature_hex obligatoire pour la rotation de cle utilisateur. "
                "Signer f\"{old_address}:{new_address}:{timestamp}\" avec l'ancienne cle."
            )

        now_str = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

        # ── Vérification AND (D-034) + fenêtre Ed25519 (D-032 B) ─────────────
        sig_status = "sig_failed"
        try:
            from nacl import encoding as nacl_encoding, signing as nacl_signing
            raw_pubkey = nacl_signing.VerifyKey(
                old_address, encoder=nacl_encoding.Base64Encoder
            ).encode()
            message = f"{old_address}:{new_address}:{now_str}".encode("utf-8")
            pqc_pub = bytes.fromhex(pqc_public_key_hex) if pqc_public_key_hex else None
            ok = verify_hybrid_and_or_window(
                message=message,
                signature_value=signature_hex,
                ed25519_public_key=raw_pubkey,
                pqc_public_key=pqc_pub,
            )
            sig_status = "verified" if ok else "sig_failed"
            if ok:
                logger.info(
                    "User key rotation signature VERIFIED (hybrid standard) for %s...",
                    old_address[:16],
                )
            else:
                logger.warning(
                    "User key rotation signature INVALID for %s...", old_address[:16]
                )
        except Exception as exc:
            logger.warning(
                "User key rotation signature verification failed: %s — rotation refusee", exc
            )
            sig_status = "sig_failed"

        if sig_status != "verified":
            raise GovernanceError(
                "SECURITE: signature invalide ou non verifiable — rotation utilisateur refusee. "
                "Verifier que la signature couvre f\"{old_address}:{new_address}:{timestamp}\"."
            )

        # ── Construire le contenu du bloc special ─────────────────────────────
        rotation_content = {
            "type":              "user_key_rotation",
            "timestamp":         now_str,
            "old_address":       old_address,
            "new_address":       new_address,
            "old_address_short": old_address[:16] + "...",
            "new_address_short": new_address[:16] + "...",
            "sig_status":        sig_status,
            "sig_format":        "hybrid:ed25519+ML-DSA-65" if (
                signature_hex and signature_hex.startswith("hybrid:")
            ) else "ed25519",
            "signature":         signature_hex,  # obligatoire — jamais unsigned (verifie ligne 635)
            "pqc_enabled":       pqc_enabled(),
            "visibility":        "public",
            "note": (
                "Rotation de cle utilisateur ARTCB. "
                "Ancienne adresse remplacee par nouvelle adresse. "
                "Le solde et l'historique de l'ancienne adresse restent 100% lisibles "
                "en interrogeant l'ancienne adresse sur la chaine. "
                "Le bloc user_key_rotation relie old_address -> new_address pour traçabilite. "
                "Signature standard hybride Ed25519+ML-DSA-65 (ou Ed25519 seul si PQC non dispo). "
                "Bloc public visible par toute la communaute."
            ),
        }

        # ── Hash SHA-256 du contenu (garantie d'integrite) ────────────────────
        content_bytes = json.dumps(rotation_content, sort_keys=True, ensure_ascii=False).encode("utf-8")
        rotation_hash = hashlib.sha256(content_bytes).hexdigest()
        rotation_content["rotation_hash"] = rotation_hash

        # ── Inscrire dans la chaine si blocks_path fourni ─────────────────────
        block_index = None
        if blocks_path is not None:
            block_index = _append_special_block(blocks_path, rotation_content)
            rotation_content["block_index"] = block_index
            logger.info(
                "USER KEY ROTATION inscrite bloc #%d: %s... -> %s... (sig=%s hash=%s...)",
                block_index, old_address[:16], new_address[:16], sig_status, rotation_hash[:16],
            )
        else:
            logger.info(
                "USER KEY ROTATION (sans bloc chaine): %s... -> %s... (sig=%s)",
                old_address[:16], new_address[:16], sig_status,
            )

        return rotation_content

    def tally(self, proposal_id: str) -> dict:
        """Calcule les resultats du vote avec droits createur.

        Regles createur (immuables) :
          - Vote OUI createur -> acceptation immediate (quelles que soient les autres voix)
          - Vote NON createur -> veto absolu (rejet immediat)
          - Poids createur    = CREATOR_VOTE_WEIGHT_MULTIPLIER x votes communaute emis
                                (minimum 1 si aucun vote communaute)
          - Ratio createur    = 20/21 = 95.24% constant quel que soit le nombre de votants
        """
        votes = [v for v in self._read_votes() if v.proposal_id == proposal_id]

        # ── Detecter le vote createur et compter les votes communaute ────
        creator_voted_yes = False
        creator_voted_no  = False
        creator_vote = None

        community_votes = []
        for v in votes:
            if CREATOR_WALLET_ADDRESS and v.wallet_address == CREATOR_WALLET_ADDRESS:
                creator_voted_yes = (v.choice == "yes")
                creator_voted_no  = (v.choice == "no")
                creator_vote = v
            else:
                community_votes.append(v)

        # ── Poids createur dynamique : 20 x votes communaute (min 1) ────
        community_vote_count = len(community_votes)
        creator_dynamic_weight = max(1, community_vote_count * CREATOR_VOTE_WEIGHT_MULTIPLIER)

        # ── Calcul pondere ───────────────────────────────────────────────
        yes_weight = 0
        no_weight  = 0
        for v in votes:
            is_creator = CREATOR_WALLET_ADDRESS and v.wallet_address == CREATOR_WALLET_ADDRESS
            weight = creator_dynamic_weight if is_creator else 1
            if v.choice == "yes":
                yes_weight += weight
            else:
                no_weight += weight

        total = yes_weight + no_weight
        majority_accept = total > 0 and yes_weight > total / 2
        majority_reject = total > 0 and no_weight  > total / 2

        # ── Droits createur absolus ──────────────────────────────────────
        if creator_voted_yes:
            majority_accept = True
            majority_reject = False
            logger.info(
                "CREATOR VOTE YES — proposal %s accepted by creator override "
                "(poids=%d, votes_communaute=%d)",
                proposal_id, creator_dynamic_weight, community_vote_count,
            )
        elif creator_voted_no:
            majority_reject = True
            majority_accept = False
            logger.warning(
                "CREATOR VETO NON — proposal %s rejected by creator veto "
                "(poids=%d, votes_communaute=%d)",
                proposal_id, creator_dynamic_weight, community_vote_count,
            )

        return {
            "proposal_id":            proposal_id,
            "yes":                    yes_weight,
            "no":                     no_weight,
            "total_votes":            total,
            "community_vote_count":   community_vote_count,
            "creator_dynamic_weight": creator_dynamic_weight,
            "majority_accept":        majority_accept,
            "majority_reject":        majority_reject,
            "requires_rollback":      majority_reject,
            "creator_voted_yes":      creator_voted_yes,
            "creator_voted_no":       creator_voted_no,
            "creator_veto_active":    creator_voted_no,
            "creator_override":       creator_voted_yes,
            "creator_rights_enabled": CREATOR_WALLET_ADDRESS is not None,
        }

    def proposal_with_tally(self, proposal_id: str) -> dict:
        proposal = self.get_proposal(proposal_id)
        if not proposal:
            raise GovernanceError("Proposal not found")
        return {
            "proposal": proposal.to_dict(),
            "tally": self.tally(proposal_id),
        }


# ─── Helpers module-level ────────────────────────────────────────────────────

def _append_special_block(blocks_path: Path, content: dict) -> int:
    """Inscrit un bloc special (rotation de cle, veto, etc.) dans blocks.jsonl.

    Le bloc special est public, horodate, avec son propre index sequentiel.
    Il ne contient pas de contributors ni de PoL score — c'est un evenement
    de gouvernance ou de securite, pas un bloc de minage.

    Format minimal du bloc special dans blocks.jsonl :
      {
        "index":         <prochain index>,
        "timestamp":     "<ISO8601Z>",
        "prev_hash":     "<hash du bloc precedent ou '000...0'>",
        "type":          "<creator_key_rotation | user_key_rotation | ...>",
        "visibility":    "public",
        "pol_score":     1.0,  # Toujours valide — bloc systeme
        "hash":          "<SHA-256 du contenu>",
        "hash_sha3":     null,
        "signature":     "<signature hybride verifiee — jamais unsigned>",
        "contributors":  [],
        "block_reward":  0,
        ...  # autres champs specifiques au type
      }

    Args:
        blocks_path : chemin vers blocks.jsonl
        content     : dict avec au moins "type", "timestamp", "signature"

    Returns:
        int : index du bloc special ecrit
    """
    import hashlib as _hashlib

    blocks_path.parent.mkdir(parents=True, exist_ok=True)

    # Calculer le prochain index
    block_index = 0
    prev_hash = "0" * 64
    if blocks_path.is_file():
        lines = [l.strip() for l in blocks_path.read_text(encoding="utf-8").splitlines() if l.strip()]
        block_index = len(lines)
        if lines:
            try:
                last = json.loads(lines[-1])
                prev_hash = last.get("hash", "0" * 64)
            except Exception:
                pass

    now_str = content.get("timestamp", datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"))

    # Construire le bloc minimal
    block: dict = {
        "index":        block_index,
        "timestamp":    now_str,
        "prev_hash":    prev_hash,
        "graph_root":   "special_block",
        "merkle_root":  "special_block",
        "pol_score":    1.0,
        "hash_sha3":    None,
        "signature":    content["signature"],
        "graph_id":     f"special_{content.get('type', 'unknown')}_{block_index}",
        "visibility":   "public",
        "block_reward": 0,
        "contributors": [],
    }
    # Fusionner le contenu specifique
    block.update(content)
    block["index"] = block_index  # Toujours imposer l'index correct

    # Hash SHA-256 du bloc
    block_bytes = json.dumps(
        {k: v for k, v in sorted(block.items()) if k != "hash"},
        ensure_ascii=False, separators=(",", ":"),
    ).encode("utf-8")
    block["hash"] = _hashlib.sha256(block_bytes).hexdigest()

    # Ecrire dans blocks.jsonl
    line = json.dumps(block, ensure_ascii=False, separators=(",", ":"))
    with blocks_path.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")

    return block_index
