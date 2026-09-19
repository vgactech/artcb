"""Routes Phase 11 — IR v0.2 Rules + PoL Transfer + PoL NFT."""

from __future__ import annotations
MODULE_VERSION = '1.0.0'  # R390 — auto-versioning

import logging
import secrets
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from src.artcb.ir.rules import (
    ConditionOperator,
    IRRule,
    RuleAction,
    RuleCondition,
    RulesRegistry,
    parse_rule_from_text,
)
from src.artcb.pol.nft import NFTRegistry, PolNFT
from src.artcb.pol.transfer import PolTransfer, TransferLedger

logger = logging.getLogger("artcb.api.pol_routes")

router = APIRouter(prefix="/api/v1", tags=["pol-v2"])

# ── Helpers ─────────────────────────────────────────────────────────────────

def _rules_registry(request: Request) -> RulesRegistry:
    state = request.app.state.artcb
    return RulesRegistry(path=str(state.settings.data_dir / "ir_rules.json"))

def _nft_registry(request: Request) -> NFTRegistry:
    state = request.app.state.artcb
    return NFTRegistry(path=str(state.settings.data_dir / "pol_nfts.json"))

def _transfer_ledger(request: Request) -> TransferLedger:
    state = request.app.state.artcb
    return TransferLedger(path=str(state.settings.data_dir / "pol_transfers.jsonl"))


# ═══════════════════════════════════════════════════════════════════════════
#  SECTION A — IR v0.2 Smart Rules
# ═══════════════════════════════════════════════════════════════════════════

class CreateRuleRequest(BaseModel):
    label: str = Field(min_length=1, max_length=256)
    conditions: list[dict]  # [{variable, operator, value}]
    actions:    list[dict]  # [{target, action_type, value}]
    combinator: str = "AND"
    author_wallet: str = ""
    grave_in_chain: bool = True  # mémoriser dans la blockchain


class EvaluateRuleRequest(BaseModel):
    rule_id: str | None = None     # évaluer une règle spécifique
    evaluate_all: bool = False     # évaluer toutes les règles actives
    context: dict                  # {pol_score: 0.92, balance_artcb: 150, ...}


class ParseRuleRequest(BaseModel):
    text: str = Field(min_length=5, description="Texte naturel: SI x > 0.9 ALORS set(y, 1.0)")
    author_wallet: str = ""
    grave_in_chain: bool = True


@router.post("/ir/rules/create", summary="Créer une règle IR v0.2 (Smart Contract déclaratif)")
def create_rule(body: CreateRuleRequest, request: Request) -> dict:
    """
    Crée une règle déclarative PoL et l'enregistre dans le registre local.
    Si `grave_in_chain=True`, la règle est aussi mémorisée dans la blockchain
    via le pipeline PoL (/ai/memo) — immuable et vérifiable.
    """
    try:
        conds = [RuleCondition.from_dict(c) for c in body.conditions]
        acts  = [RuleAction.from_dict(a) for a in body.actions]
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Format conditions/actions invalide: {e}")

    rule_id = f"rule_{secrets.token_hex(8)}"
    rule = IRRule(
        rule_id=rule_id,
        label=body.label,
        conditions=conds,
        actions=acts,
        combinator=body.combinator,
        author_wallet=body.author_wallet,
        created_at=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    )

    registry = _rules_registry(request)
    registry.add(rule)

    block_info = None
    if body.grave_in_chain:
        try:
            state = request.app.state.artcb
            from src.artcb.chain.manager import ChainManager
            from src.artcb.ir.encoder import IREncoder
            from src.artcb.pol.scorer import PolScorer
            encoder = IREncoder()
            graph   = encoder.encode(rule.to_pol_text(), session_id=f"rule_{rule_id}")
            scorer  = PolScorer()
            metrics = scorer.score(graph)
            block   = state.chain.append_block(
                graph_id=graph.graph_id,
                graph_root=graph.checksum,
                pol_score=metrics.pol_score,
                visibility="public",
                public_symbols={"memo_type": "smart_rule", "rule_id": rule_id},
                source="ai:rule",
            )
            rule.block_index = block.index
            registry.add(rule)  # mise à jour avec block_index
            block_info = {"block_index": block.index, "graph_id": graph.graph_id}
        except Exception as exc:
            logger.warning("Rule chain grave failed: %s", exc)

    return {
        "rule_id": rule_id,
        "label": body.label,
        "conditions_count": len(conds),
        "actions_count": len(acts),
        "block": block_info,
        "pol_text": rule.to_pol_text()[:200],
    }


@router.post("/ir/rules/parse", summary="Parser une règle depuis texte naturel")
def parse_rule(body: ParseRuleRequest, request: Request) -> dict:
    """
    Parse une règle en langage naturel :
    - "SI pol_score >= 0.9 ALORS set(bonus, 0.5)"
    - "IF balance_artcb > 100 THEN transfer(artcb1bob, 10.0)"
    """
    rule_id = f"rule_{secrets.token_hex(8)}"
    rule = parse_rule_from_text(body.text, rule_id=rule_id, author=body.author_wallet)
    if rule is None:
        raise HTTPException(
            status_code=422,
            detail="Impossible de parser la règle. Format attendu: "
                   "'SI <variable> <op> <valeur> ALORS <action>(<target>, <val>)'"
        )

    registry = _rules_registry(request)
    registry.add(rule)

    block_info = None
    if body.grave_in_chain:
        try:
            state = request.app.state.artcb
            from src.artcb.ir.encoder import IREncoder
            from src.artcb.pol.scorer import PolScorer
            encoder = IREncoder()
            graph   = encoder.encode(rule.to_pol_text(), session_id=f"rule_{rule_id}")
            metrics = PolScorer().score(graph)
            block   = state.chain.append_block(
                graph_id=graph.graph_id,
                graph_root=graph.checksum,
                pol_score=metrics.pol_score,
                visibility="public",
                public_symbols={"memo_type": "smart_rule", "rule_id": rule_id},
                source="ai:rule",
            )
            rule.block_index = block.index
            registry.add(rule)
            block_info = {"block_index": block.index, "graph_id": graph.graph_id}
        except Exception as exc:
            logger.warning("Rule chain grave failed: %s", exc)

    return {
        "rule_id": rule_id,
        "label": rule.label,
        "parsed": rule.to_dict(),
        "block": block_info,
    }


@router.post("/ir/rules/evaluate", summary="Évaluer une ou toutes les règles contre un contexte")
def evaluate_rules(body: EvaluateRuleRequest, request: Request) -> dict:
    """
    Évalue des règles IR contre un contexte fourni.

    Contexte exemple :
    ```json
    {
      "pol_score": 0.92,
      "balance_artcb": 150.0,
      "block_count": 521,
      "wallet_address": "artcb1xyz",
      "nft_owner": "artcb1xyz"
    }
    ```
    """
    registry = _rules_registry(request)

    if body.evaluate_all:
        results = registry.evaluate_all(body.context)
        triggered = [r.to_dict() for r in results if r.triggered]
        return {
            "evaluated": len(results),
            "triggered": len(triggered),
            "triggered_rules": triggered,
            "all_results": [r.to_dict() for r in results],
        }

    if body.rule_id:
        result = registry.evaluate_one(body.rule_id, body.context)
        if result is None:
            raise HTTPException(status_code=404, detail=f"Règle {body.rule_id} introuvable")
        return result.to_dict()

    raise HTTPException(status_code=422, detail="Fournir rule_id ou evaluate_all=true")


@router.get("/ir/rules", summary="Lister toutes les règles actives")
def list_rules(request: Request) -> dict:
    registry = _rules_registry(request)
    rules = registry.list_all()
    return {"rules": [r.to_dict() for r in rules], "count": len(rules)}


@router.delete("/ir/rules/{rule_id}", summary="Supprimer une règle")
def delete_rule(rule_id: str, request: Request) -> dict:
    registry = _rules_registry(request)
    deleted = registry.delete(rule_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Règle {rule_id} introuvable")
    return {"deleted": True, "rule_id": rule_id}


# ═══════════════════════════════════════════════════════════════════════════
#  SECTION B — PoL NFT
# ═══════════════════════════════════════════════════════════════════════════

class MintNFTRequest(BaseModel):
    title: str = Field(min_length=1, max_length=256)
    creator_wallet: str = Field(min_length=10)
    description: str = ""
    content_text: str = ""     # contenu texte court (intégré dans la chaîne)
    content_hash: str = ""     # hash SHA-256 d'un fichier externe
    license: str = "CC-BY-4.0"
    edition: str = "1/1"
    metadata: dict = {}


class TransferNFTRequest(BaseModel):
    nft_id: str
    new_owner_wallet: str


@router.post("/pol/nft/mint", summary="Créer un NFT PoL (token non-fongible sémantique)")
def mint_nft(body: MintNFTRequest, request: Request) -> dict:
    """
    Crée un NFT PoL unique.
    Le contenu est gravé DIRECTEMENT dans la blockchain (pas de lien IPFS externe).
    Signé ML-DSA-65 + Ed25519 — post-quantique natif.

    Avantage : le contenu est immuable même si un serveur externe disparaît.
    """
    nft_id = "nft_" + secrets.token_hex(8)
    nft = PolNFT(
        nft_id=nft_id,
        title=body.title,
        creator_wallet=body.creator_wallet,
        owner_wallet=body.creator_wallet,
        content_hash=body.content_hash,
        description=body.description,
        content_text=body.content_text,
        license=body.license,
        edition=body.edition,
        metadata=body.metadata,
    )

    # Graver dans la blockchain
    state = request.app.state.artcb
    try:
        from src.artcb.ir.encoder import IREncoder
        from src.artcb.pol.scorer import PolScorer
        encoder = IREncoder()
        graph   = encoder.encode(nft.to_pol_text(), session_id=f"nft_{nft_id}")
        metrics = PolScorer().score(graph)
        block   = state.chain.append_block(
            graph_id=graph.graph_id,
            graph_root=graph.checksum,
            pol_score=metrics.pol_score,
            visibility="public",
            public_symbols={
                "memo_type": "nft",
                "nft_id": nft_id,
                "title": body.title[:64],
                "creator": body.creator_wallet[:20],
            },
            source="ai:nft",
        )
        nft.block_index = block.index
        nft.graph_id    = graph.graph_id
        logger.info("NFT minted: %s block=%d", nft_id, block.index)
    except Exception as exc:
        logger.error("NFT chain grave failed: %s", exc)
        raise HTTPException(status_code=500, detail=f"Erreur gravure blockchain: {exc}")

    # Enregistrer dans le registre local
    registry = _nft_registry(request)
    registry.mint(nft)

    return {
        "nft_id": nft_id,
        "title": body.title,
        "creator_wallet": body.creator_wallet,
        "edition": body.edition,
        "block_index": nft.block_index,
        "graph_id": nft.graph_id,
        "pol_score": metrics.pol_score,
        "message": "NFT gravé dans la blockchain ARTCB — immuable et post-quantique.",
    }


@router.get("/pol/nft/{nft_id}", summary="Récupérer un NFT par son ID")
def get_nft(nft_id: str, request: Request) -> dict:
    registry = _nft_registry(request)
    nft = registry.get(nft_id)
    if nft is None:
        raise HTTPException(status_code=404, detail=f"NFT {nft_id} introuvable")
    return nft.to_dict()


@router.post("/pol/nft/transfer", summary="Transférer l'ownership d'un NFT")
def transfer_nft(body: TransferNFTRequest, request: Request) -> dict:
    """Transfère un NFT PoL vers un nouveau propriétaire. Gravé dans la blockchain."""
    registry = _nft_registry(request)
    nft = registry.get(body.nft_id)
    if nft is None:
        raise HTTPException(status_code=404, detail=f"NFT {body.nft_id} introuvable")

    transfer_id = "ntx_" + secrets.token_hex(8)
    try:
        registry.transfer(body.nft_id, body.new_owner_wallet, transfer_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    # Graver le transfert dans la blockchain
    state = request.app.state.artcb
    try:
        from src.artcb.ir.encoder import IREncoder
        from src.artcb.pol.scorer import PolScorer
        text = (
            f"NFT TRANSFER [{transfer_id}] NFT [{body.nft_id}] '{nft.title}' "
            f"DE: {nft.owner_wallet} VERS: {body.new_owner_wallet}"
        )
        encoder = IREncoder()
        graph   = encoder.encode(text, session_id=f"ntx_{transfer_id}")
        metrics = PolScorer().score(graph)
        block   = state.chain.append_block(
            graph_id=graph.graph_id,
            graph_root=graph.checksum,
            pol_score=metrics.pol_score,
            visibility="public",
            public_symbols={
                "memo_type": "nft_transfer",
                "nft_id": body.nft_id,
                "from": nft.owner_wallet[:20],
                "to": body.new_owner_wallet[:20],
            },
            source="ai:nft_transfer",
        )
        block_index = block.index
    except Exception as exc:
        logger.warning("NFT transfer chain grave failed: %s", exc)
        block_index = None

    return {
        "transfer_id": transfer_id,
        "nft_id": body.nft_id,
        "from_wallet": nft.owner_wallet,
        "to_wallet": body.new_owner_wallet,
        "block_index": block_index,
    }


@router.get("/pol/nft", summary="Lister tous les NFTs (ou filtrer par owner)")
def list_nfts(request: Request, owner: str | None = None, creator: str | None = None) -> dict:
    registry = _nft_registry(request)
    if owner:
        nfts = registry.by_owner(owner)
    elif creator:
        nfts = registry.by_creator(creator)
    else:
        nfts = registry.list_all()
    return {"nfts": [n.to_dict() for n in nfts], "count": len(nfts)}


# ═══════════════════════════════════════════════════════════════════════════
#  SECTION C — PoL Transfer Protocol
# ═══════════════════════════════════════════════════════════════════════════

class CreateTransferRequest(BaseModel):
    from_wallet: str = Field(min_length=10)
    to_wallet: str   = Field(min_length=10)
    amount_artcb: float = Field(gt=0, le=21_000_000)
    memo: str = ""
    reference: str = ""


@router.post("/pol/transfer", summary="Créer un transfert PoL (transaction native ARTCB)")
def create_transfer(body: CreateTransferRequest, request: Request) -> dict:
    """
    Enregistre un transfert ARTCB comme transaction PoL :
    - Encodée dans un graphe IR sémantique (motif, contexte, preuve)
    - Signée ML-DSA-65 + Ed25519
    - Gravée de manière immuable dans la blockchain

    Avantage vs Bitcoin : encode le POURQUOI, pas juste le COMBIEN.
    """
    transfer_id = "ptx_" + secrets.token_hex(8)
    transfer = PolTransfer(
        transfer_id=transfer_id,
        from_wallet=body.from_wallet,
        to_wallet=body.to_wallet,
        amount_artcb=body.amount_artcb,
        memo=body.memo,
        reference=body.reference,
    )

    # Graver dans la blockchain
    state = request.app.state.artcb
    try:
        from src.artcb.ir.encoder import IREncoder
        from src.artcb.pol.scorer import PolScorer
        encoder = IREncoder()
        graph   = encoder.encode(transfer.to_pol_text(), session_id=f"ptx_{transfer_id}")
        metrics = PolScorer().score(graph)
        block   = state.chain.append_block(
            graph_id=graph.graph_id,
            graph_root=graph.checksum,
            pol_score=metrics.pol_score,
            visibility="public",
            public_symbols={
                "memo_type": "transfer",
                "transfer_id": transfer_id,
                "from": body.from_wallet[:20],
                "to": body.to_wallet[:20],
                "amount": str(body.amount_artcb),
            },
            source="ai:transfer",
        )
        transfer.block_index = block.index
        transfer.graph_id    = graph.graph_id
        transfer.pol_score   = metrics.pol_score
        logger.info("PoL transfer: %s %.8f ARTCB %s→%s block=%d",
                    transfer_id, body.amount_artcb, body.from_wallet[:12],
                    body.to_wallet[:12], block.index)
    except Exception as exc:
        logger.error("Transfer chain grave failed: %s", exc)
        raise HTTPException(status_code=500, detail=f"Erreur gravure blockchain: {exc}")

    # Enregistrer dans le ledger local
    ledger = _transfer_ledger(request)
    ledger.append(transfer)

    return {
        "transfer_id": transfer_id,
        "from_wallet": body.from_wallet,
        "to_wallet": body.to_wallet,
        "amount_artcb": body.amount_artcb,
        "memo": body.memo,
        "block_index": transfer.block_index,
        "graph_id": transfer.graph_id,
        "pol_score": transfer.pol_score,
        "message": "Transfert gravé dans la blockchain ARTCB — immuable et post-quantique.",
    }


@router.get("/pol/transfers/{address}", summary="Historique des transferts d'une adresse")
def get_transfers(address: str, request: Request) -> dict:
    ledger = _transfer_ledger(request)
    transfers = ledger.by_address(address)
    balance   = ledger.balance_of(address)
    return {
        "address": address,
        "transfer_count": len(transfers),
        "pol_transfer_balance_artcb": balance,
        "transfers": [t.to_dict() for t in transfers],
    }


@router.get("/pol/transfers", summary="Tous les transferts PoL")
def list_transfers(request: Request) -> dict:
    ledger = _transfer_ledger(request)
    transfers = ledger.all_transfers()
    return {"transfers": [t.to_dict() for t in transfers], "count": len(transfers)}


@router.get("/pol/balance/{address}", summary="Solde PoL-transfers d'une adresse")
def pol_balance(address: str, request: Request) -> dict:
    """Solde calculé depuis les transferts PoL (hors rewards mining)."""
    ledger = _transfer_ledger(request)
    balance = ledger.balance_of(address)
    return {"address": address, "pol_transfer_balance_artcb": balance}

