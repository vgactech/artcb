"""REST routes — CDC §8."""

from __future__ import annotations

import asyncio
import logging
import os
import uuid

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from src.artcb.ir.encoder import IREncoder
from src.artcb.ir.llm_encoder import LLMEncoder
from src.artcb.ir.models import sha256_text
from src.artcb.rtleg.events import RTLEGEvent
from src.artcb.authz.actions import READ
from src.artcb.authz.models import Principal

logger = logging.getLogger("artcb.api.routes")
router = APIRouter(prefix="/api/v1")


class EncodeRequest(BaseModel):
    text: str = Field(min_length=1)
    session_id: str = "sess_default"
    use_llm: bool = False


class DecodeRequest(BaseModel):
    graph_id: str


class SearchRequest(BaseModel):
    query: str = Field(min_length=1)
    graph_id: str | None = None
    top_k: int = 3


class StoreRequest(BaseModel):
    graph_id: str | None = None
    text: str | None = Field(default=None, min_length=1, description="Auto-encode si graph_id absent")
    session_id: str = "sess_default"
    visibility: str = "private"
    group_id: str | None = None
    actor_address: str | None = None
    wallet_name: str | None = Field(default=None, description="Wallet pour signature minage raisonnement")
    wallet_password: str | None = Field(default=None, description="Mot de passe du wallet")
    resource_id: str | None = Field(default=None, description="Identifiant de ressource ACL (document), hors consensus")
    subgroup_id: str | None = Field(default=None, description="Sous-groupe ACL, hors consensus")
    organization_id: str | None = Field(default=None, description="Organisation ACL, hors consensus")


class IrLearnRequest(BaseModel):
    """POST /ir/learn — encode + grave un bloc public."""
    wallet_address: str = Field(min_length=8, description="Adresse wallet du mineur")
    content: str = Field(min_length=1, description="Contenu a encoder et graver")
    visibility: str = Field(default="public", description="public | private | group")
    session_id: str = "sess_default"


class AgentRunRequest(BaseModel):
    text: str = Field(min_length=1)
    session_id: str = "sess_default"
    use_llm: bool = False
    llm_provider: str | None = Field(
        default=None,
        description="openai | anthropic | bob — utilise le connecteur utilisateur",
    )


def _state(request: Request):
    return request.app.state.artcb


def _authz(request: Request):
    return _state(request).authz


@router.get("/demo/wailly-excerpt")
def wailly_excerpt(request: Request, max_pages: int = 3) -> dict:
    """Load Wailly book excerpt for demo (D-010)."""
    from src.artcb.io.pdf_loader import extract_pdf_text, resolve_book_path

    path = resolve_book_path()
    state = _state(request)
    if path is None:
        fallback = state.settings.demo_book_pdf
        if fallback.is_file():
            path = fallback
    if path is None or not path.is_file():
        raise HTTPException(status_code=404, detail="Wailly PDF not found")
    text = extract_pdf_text(path, max_pages=max_pages)
    return {
        "source": "wailly_le_roi_de_l_inconnu.pdf",
        "max_pages": max_pages,
        "char_count": len(text),
        "text": text,
    }


@router.get("/health")
def health(request: Request) -> dict:
    state = _state(request)
    chain_status = {"available": False}
    try:
        chain_status = {"available": True, **state.chain.verify()}
    except FileNotFoundError as exc:
        chain_status = {"available": False, "message": str(exc)}
    from src.artcb.crypto.pqc import pqc_available
    from src.artcb.crypto_policy import public_health_block
    from src.artcb.release import release_identity

    identity = release_identity()
    pqc = pqc_available()
    return {
        "status": "ok",
        "debug": state.settings.debug,
        "llm_enabled": state.settings.llm_enabled,
        "bob_configured": bool(state.settings.bob_api_key),
        "demo_book": str(state.settings.demo_book_pdf),
        "chain": chain_status,
        "git_sha": identity["git_sha"],
        "git_branch": identity["git_branch"],
        "release_integrity": identity.get("release_integrity"),
        "pin_sha": identity.get("pin_sha"),
        "version": identity["version"],
        "bootstrap_mode": False,
        "pqc": public_health_block(pqc),
    }


@router.post("/encode")
def encode(body: EncodeRequest, request: Request) -> dict:
    state = _state(request)
    graph_id = f"g_{uuid.uuid4().hex[:12]}"
    llm_encoder = LLMEncoder(encoder=state.encoder)
    graph = llm_encoder.encode(body.text, use_llm=body.use_llm, session_id=graph_id)
    state.register_graph(graph)
    state.vectors.index_graph(graph)

    state.timeline.append(
        RTLEGEvent(
            session_id=body.session_id,
            agent="explorer",
            event_type="encode",
            graph_id=graph.graph_id,
            payload={"node_count": len(graph.nodes), "use_llm": body.use_llm},
        )
    )

    compression = IREncoder.compression_ratio(graph)
    return {
        "graph_id": graph.graph_id,
        "node_count": len(graph.nodes),
        "edge_count": len(graph.edges),
        "compression_ratio": compression,
        "pol_score": None,
        "nodes_preview": [n.model_dump() for n in graph.nodes[:5]],
    }


@router.post("/decode")
def decode(body: DecodeRequest, request: Request) -> dict:
    state = _state(request)
    graph = state.get_graph(body.graph_id)
    if not graph:
        raise HTTPException(status_code=404, detail="graph not found")
    _authz(request).assert_graph(request, body.graph_id, READ)
    metrics = state.decoder.decode_with_metrics(graph)
    return {
        "original_text": metrics["text"],
        "similarity": metrics["similarity"],
        "reversible": metrics["reversible"],
    }


@router.get("/graph/{graph_id}")
def get_graph(graph_id: str, request: Request) -> dict:
    state = _state(request)
    graph = state.get_graph(graph_id)
    if not graph:
        raise HTTPException(status_code=404, detail="graph not found")
    _authz(request).assert_graph(request, graph_id, READ)
    return graph.to_canonical_dict()


@router.get("/node/status")
def node_status_inline(request: Request) -> dict:
    """Etat du noeud courant — node_id, version, mode (alias prioritaire sur /node/{id})."""
    state = _state(request)
    node_id = "unknown"
    try:
        node_id = state.p2p_identity.node_id
    except AttributeError:
        import hashlib as _hl, socket as _sock
        node_id = "node_" + _hl.sha256(_sock.gethostname().encode()).hexdigest()[:12]
    return {
        "node_id": node_id,
        "version": "0.3.0",
        "debug": state.settings.debug,
        "status": "running",
    }


@router.get("/node/{node_id}")
def get_node(
    node_id: str,
    request: Request,
    graph_id: str | None = Query(default=None),
) -> dict:
    state = _state(request)
    if graph_id:
        graph = state.get_graph(graph_id)
        if not graph:
            raise HTTPException(status_code=404, detail="graph not found")
        _authz(request).assert_graph(request, graph_id, READ)
        for node in graph.nodes:
            if node.id == node_id:
                return node.model_dump()
        raise HTTPException(status_code=404, detail="node not found")

    if node_id in state.node_index:
        gid, _ = state.node_index[node_id]
        _authz(request).assert_graph(request, gid, READ)
        graph = state.get_graph(gid)
        if graph:
            for node in graph.nodes:
                if node.id == node_id:
                    return {**node.model_dump(), "graph_id": gid}
    raise HTTPException(status_code=404, detail="node not found")


@router.post("/search")
def search(body: SearchRequest, request: Request) -> dict:
    state = _state(request)
    principal = _authz(request).resolve(request)
    results = state.vectors.search(body.query, graph_id=body.graph_id, top_k=body.top_k)
    allowed = []
    for row in results:
        gid = row.get("graph_id")
        if not gid:
            continue
        if _authz(request).decide(principal, READ, _authz(request).resource_for_graph(gid)).allowed:
            allowed.append(row)
    return {"query": body.query, "results": allowed, "count": len(allowed)}


@router.post("/store")
async def store(body: StoreRequest, request: Request) -> dict:
    state = _state(request)

    # BUG-P0-2 : auto-encode si text fourni sans graph_id
    if not body.graph_id and body.text:
        graph_id = f"g_{uuid.uuid4().hex[:12]}"
        from src.artcb.ir.llm_encoder import LLMEncoder
        llm_encoder = LLMEncoder(encoder=state.encoder)
        graph = await asyncio.to_thread(
            lambda: llm_encoder.encode(body.text, use_llm=False, session_id=graph_id)
        )
        state.register_graph(graph)
        state.vectors.index_graph(graph)
    elif body.graph_id:
        graph = state.get_graph(body.graph_id)
        if not graph:
            raise HTTPException(status_code=404, detail="graph not found")
    else:
        raise HTTPException(status_code=422, detail="graph_id ou text requis")

    if body.visibility not in ("private", "group", "public"):
        raise HTTPException(status_code=422, detail="visibility must be private, group, or public")

    group_id: str | None = None
    principal = _authz(request).resolve(request)
    wallet = None
    if body.wallet_name:
        from src.artcb.wallet.manager import WalletManager

        try:
            wallet = WalletManager().load_wallet(name=body.wallet_name, user_password=body.wallet_password)
        except Exception as exc:
            raise HTTPException(status_code=404, detail=f"wallet not found or wrong password: {body.wallet_name}") from exc
        if principal.address and principal.address != wallet.address:
            raise HTTPException(status_code=403, detail="actor_address_mismatch")
        principal = Principal(
            address=wallet.address,
            wallet_name=body.wallet_name,
            kind="human",
            source="wallet",
        )

    if body.actor_address and principal.address and body.actor_address != principal.address:
        raise HTTPException(status_code=403, detail="actor_address_mismatch")

    actor = principal.address
    if body.visibility == "group":
        if not body.group_id:
            raise HTTPException(status_code=422, detail="group_id required for visibility=group")
        if not actor:
            raise HTTPException(
                status_code=401,
                detail="authentication_required_for_group_store",
            )
        if not state.groups.is_member(body.group_id, actor):
            raise HTTPException(status_code=403, detail="not a group member")
        if body.subgroup_id and not state.groups.is_member(body.subgroup_id, actor):
            raise HTTPException(status_code=403, detail="not a subgroup member")
        group_id = body.group_id

    result = state.dual.critic.validate(graph)
    pol = result.pol
    if not pol.block_accepted:
        state.pol_state["blocks_rejected"] += 1
        raise HTTPException(
            status_code=422,
            detail={"message": "PoL below threshold", "pol": pol.to_dict()},
        )

    graph_root = sha256_text(graph.checksum).replace("sha256:", "")

    # Identity for rewards: session / API key / decrypted wallet. The JSON
    # field actor_address is never treated as proof (rapport 216 P0-2).
    if actor and not wallet:
        logger.warning(
            "POST /store: actor=%s without wallet signature — reward unsigned "
            "(session/API key identity is enough for ACL; mining signature still recommended)",
            actor[:16],
        )

    contributors = None
    if actor:
        from src.artcb.mining.pipeline import build_contributors

        contributors = build_contributors(
            actor_address=actor,
            pol_score=pol.pol_score,
            wallet=wallet,
            graph_root=graph_root,
            machine_registry=state.machine_registry,
            human_registry=state.human_registry,
            work_registry=state.work_registry,
            graph_id=graph.graph_id,
        )

    public_symbols = graph.orig_symbols if body.visibility == "public" and graph.orig_symbols else None

    block = state.chain.append_block(
        graph_id=graph.graph_id,
        graph_root=graph_root,
        pol_score=pol.pol_score,
        visibility=body.visibility,
        group_id=group_id,
        contributors=contributors,
        public_symbols=public_symbols,
    )
    if body.visibility == "public" and public_symbols:
        state.publish_public_symbols(
            public_symbols,
            block_index=block.index,
            graph_id=graph.graph_id,
        )
    state.pol_state["pol_score"] = pol.pol_score
    state.pol_state["delta_compression"] = pol.delta_compression
    state.pol_state["validation_rate"] = pol.validation_rate
    state.pol_state["retrieval_accuracy"] = pol.retrieval_accuracy
    state.pol_state["blocks_accepted"] += 1

    state.timeline.append(
        RTLEGEvent(
            session_id=body.session_id,
            agent="critic",
            event_type="block_stored",
            graph_id=graph.graph_id,
            payload={"index": block.index, "hash": block.hash, "pol": pol.pol_score},
        )
    )

    try:
        state.notifications.broadcast(
            event="block_stored",
            subject=f"ARTCB bloc #{block.index}",
            body=(
                f"Graphe {graph.graph_id} gravé — visibilité {block.visibility} — "
                f"PoL {pol.pol_score:.2f} — reward {block.block_reward / 1e8:.4f} ARTCB"
            ),
        )
    except Exception as exc:
        logger.warning("Notification broadcast failed (non bloquant): %s", exc)

    state.authz.index.record(
        graph_id=graph.graph_id,
        visibility=block.visibility,
        owner_address=actor,
        group_id=group_id,
        subgroup_id=body.subgroup_id,
        resource_id=body.resource_id,
        organization_id=body.organization_id,
        block_index=block.index,
    )

    return {
        "block_index": block.index,
        "hash": block.hash,
        "block_reward": block.block_reward,
        "contributors": block.contributors,
        "signature": block.signature,
        "pol_score": pol.pol_score,
        "graph_id": graph.graph_id,
        "visibility": block.visibility,
        "group_id": block.group_id,
        "resource_id": body.resource_id,
        "subgroup_id": body.subgroup_id,
    }


@router.get("/chain")
def chain_list(
    request: Request,
    visibility: str | None = Query(None),
    group_id: str | None = Query(None),
) -> dict:
    state = _state(request)
    principal = _authz(request).resolve(request)
    blocks = state.chain.list_blocks(visibility=visibility, group_id=group_id)
    blocks = _authz(request).filter_blocks(principal, blocks, READ)
    return {"blocks": blocks, "count": len(blocks)}


@router.get("/chain/block/{block_index}")
def chain_block_detail(block_index: int, request: Request) -> dict:
    state = _state(request)
    blocks = state.chain._read_all_blocks()
    for block in blocks:
        if block.get("index") == block_index:
            _authz(request).assert_block(request, block, READ)
            return {"block": block}
    raise HTTPException(status_code=404, detail="block not found")


@router.get("/chain/verify")
def chain_verify(request: Request) -> dict:
    state = _state(request)
    return state.chain.verify()


@router.get("/chain/status")
def chain_status(request: Request) -> dict:
    """Etat courant de la chaine — hauteur, dernier hash, timestamp."""
    state = _state(request)
    blocks = state.chain.list_blocks()
    height = len(blocks)
    last_block = blocks[-1] if blocks else {}
    return {
        "height": height,
        "block_count": height,
        "last_hash": last_block.get("hash", "0" * 64),
        "last_timestamp": last_block.get("timestamp"),
        "last_index": last_block.get("index", -1),
        "chain_valid": state.chain.verify().get("valid", False),
    }


@router.get("/chain/blocks")
def chain_blocks(
    request: Request,
    visibility: str | None = Query(None),
    group_id: str | None = Query(None),
) -> dict:
    """Liste des blocs de la chaine — alias de GET /chain."""
    state = _state(request)
    principal = _authz(request).resolve(request)
    blocks = state.chain.list_blocks(visibility=visibility, group_id=group_id)
    blocks = _authz(request).filter_blocks(principal, blocks, READ)
    return {"blocks": blocks, "count": len(blocks)}


@router.get("/pol/score")
def pol_score(request: Request) -> dict:
    return _state(request).pol_state

@router.get("/metrics")
def system_metrics(request: Request) -> dict:
    """Metriques temps reel + materiel + optimisations actives."""
    try:
        from src.artcb.system.hardware import detect_hardware, live_metrics
        from src.artcb.system.optimizer import build_optimization_profile

        state = request.app.state.artcb
        hw = state.hardware or detect_hardware()
        opt = state.optimization or build_optimization_profile(hw)
        live = live_metrics()
        hw_dict = hw.to_dict()
        return {
            **live,
            "system": hw_dict["platform"],
            "hardware": hw_dict,
            "optimization": opt.to_dict(),
        }
    except ImportError as exc:
        raise HTTPException(status_code=500, detail="psutil not installed") from exc
    except Exception as e:
        logger.error("Error fetching system metrics: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/system/hardware")
def system_hardware(request: Request) -> dict:
    """Profil materiel detecte (CPU, RAM, GPU, disque)."""
    from src.artcb.system.hardware import detect_hardware

    state = request.app.state.artcb
    hw = state.hardware or detect_hardware()
    return hw.to_dict()


@router.get("/system/optimization")
def system_optimization(request: Request) -> dict:
    """Profil d'optimisation runtime adapte au materiel."""
    from src.artcb.system.optimizer import build_optimization_profile

    state = request.app.state.artcb
    if state.optimization is not None:
        return state.optimization.to_dict()
    hw = state.hardware
    return build_optimization_profile(hw).to_dict()


# ============================================================================
# WALLET ROUTES — Rewards & Balance Tracking
# ============================================================================

class CreateWalletRequest(BaseModel):
    name: str = "default"
    password: str = Field(
        min_length=8,
        description=(
            "Mot de passe personnel (min 8 caractères). "
            "Chiffre la clé privée. Requis pour se connecter via /auth/login et pour toute opération signée."
        ),
    )


class WalletBalanceRequest(BaseModel):
    address: str


@router.post("/wallet/create")
def wallet_create(body: CreateWalletRequest, request: Request) -> dict:
    """Create new ARTCB wallet with Ed25519 + ML-DSA-65 hybrid keypair.

    PROTOCOLE :
      - Le mot de passe est OBLIGATOIRE et chiffre la clé privée sur le serveur.
      - La seed_hex est retournée UNE SEULE FOIS — l'utilisateur doit la sauvegarder.
      - Sans la seed_hex OU le mot de passe, le compte est inaccessible.
      - Le login ultérieur (POST /auth/login) utilise ce même mot de passe.
      - Un seul wallet par appareil (device fingerprint). Désactivable via ARTCB_ALLOW_MULTI_WALLET=true.
    """
    from src.artcb.wallet.manager import WalletManager
    from src.artcb.security.wallet_device_binding import WalletDeviceBindingError

    state = _state(request)
    wallet_mgr = WalletManager()

    # ANTI-FRAUDE : vérifier qu'aucun wallet n'existe déjà pour cet appareil
    if state.wallet_device_binding and state.device_identity:
        try:
            state.wallet_device_binding.check_and_bind(
                wallet_name=body.name,
                device_fingerprint=state.device_identity.device_fingerprint,
                env_type=state.device_identity.env_type,
            )
        except WalletDeviceBindingError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    try:
        # PROTOCOLE : chiffrer la seed avec le MOT DE PASSE de l'utilisateur,
        # pas uniquement avec la passphrase serveur.
        wallet = wallet_mgr.create_wallet(name=body.name, user_password=body.password)
        logger.info("Created wallet name=%s address=%s", body.name, wallet.address)
        # PROTOCOLE : la seed (clé privée) est retournée UNE SEULE FOIS à la création.
        # Elle n'est JAMAIS stockée en clair et ne sera plus jamais affichée.
        seed_hex = wallet.signing_key.encode().hex()
        response: dict = {
            "name": body.name,
            "address": wallet.address,
            "public_key_hex": wallet.public_key_hex,
            "public_key_b64": wallet.public_key_b64,
            "seed_hex": seed_hex,
            "WARNING": (
                "SAUVEGARDEZ votre seed_hex MAINTENANT — "
                "c'est votre clé privée, elle ne sera plus jamais affichée. "
                "Sans elle, votre compte est définitivement inaccessible."
            ),
            "hybrid": wallet.is_hybrid,
        }
        if wallet.address_v2:
            response["address_v2"] = wallet.address_v2
        logger.warning(
            "SEED RETURNED once at creation for wallet=%s — user must save it", body.name
        )
        return response
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


# Fields an anonymous caller may see (rapport 210 §9.6). Everything else in the
# wallet metadata (auth_methods, public keys ~4 KB, key format) needs a Bearer.
WALLET_LIST_PUBLIC_FIELDS = frozenset(
    {"name", "address", "address_v2", "hybrid", "created_at", "has_key_file"}
)


def _bearer_present(request: Request) -> bool:
    """True when a session (sess_) or API key (artcb_) Bearer is on the request.

    Validity is checked by the dedicated dependencies; here we only decide
    whether to return the full metadata or the public projection.
    """
    from src.api.api_keys_routes import verify_api_key
    from src.api.auth_routes import require_session

    authorization = request.headers.get("authorization")
    if not authorization:
        return False
    try:
        if authorization.startswith("Bearer sess_"):
            require_session(request, authorization)
            return True
        return verify_api_key(request, authorization) is not None
    except HTTPException:
        return False


@router.get("/wallet/list")
def wallet_list(request: Request) -> dict:
    """List wallets.

    Anonymous: public projection only (name, address, hybrid, created_at,
    has_key_file). With a valid Bearer: full metadata. Set
    ARTCB_WALLET_LIST_PUBLIC=0 to require a Bearer for any listing.
    """
    from src.artcb.wallet.manager import WalletManager

    authenticated = _bearer_present(request)
    public_allowed = os.getenv("ARTCB_WALLET_LIST_PUBLIC", "1").strip().lower() not in {"0", "false", "no"}
    if not authenticated and not public_allowed:
        raise HTTPException(status_code=401, detail="wallet_list_requires_bearer")

    wallets = WalletManager().list_wallets()
    if not authenticated:
        wallets = [{k: v for k, v in w.items() if k in WALLET_LIST_PUBLIC_FIELDS} for w in wallets]
    return {"wallets": wallets, "count": len(wallets), "projection": "full" if authenticated else "public"}


@router.post("/wallet/balance")
def wallet_balance(body: WalletBalanceRequest, request: Request) -> dict:
    """Get wallet balance from blockchain."""
    from src.artcb.wallet.manager import WalletManager

    state = _state(request)
    wallet_mgr = WalletManager()

    balance = wallet_mgr.get_balance_with_faucet(
        body.address,
        state.chain.blocks_path,
        state.faucet.ledger_path,
    )
    return balance


@router.get("/wallet/balance/{address}")
def wallet_balance_get(address: str, request: Request) -> dict:
    """Get wallet balance from blockchain (GET variant)."""
    from src.artcb.wallet.manager import WalletManager

    state = _state(request)
    wallet_mgr = WalletManager()

    balance = wallet_mgr.get_balance_with_faucet(
        address,
        state.chain.blocks_path,
        state.faucet.ledger_path,
    )
    return balance




@router.post("/ir/learn", summary="Encoder + graver un contenu sur la blockchain (POST /ir/learn)")
async def ir_learn(body: IrLearnRequest, request: Request) -> dict:
    """Encode un contenu texte et grave un bloc sur la blockchain ARTCB.

    Shortcut combine encode + store pour les tests P2P et les clients externes.
    Equivalent a : POST /encode puis POST /store.

    Retourne graph_id et block_index si le bloc est grave avec succes.
    """
    state = _state(request)

    # Encode
    graph_id = f"g_{uuid.uuid4().hex[:12]}"
    from src.artcb.ir.llm_encoder import LLMEncoder
    llm_encoder = LLMEncoder(encoder=state.encoder)
    graph = await asyncio.to_thread(
        lambda: llm_encoder.encode(body.content, use_llm=False, session_id=graph_id)
    )
    state.register_graph(graph)
    state.vectors.index_graph(graph)

    if body.visibility not in ("private", "group", "public"):
        raise HTTPException(status_code=422, detail="visibility must be private, group, or public")

    # Valider via PoL
    result = state.dual.critic.validate(graph)
    pol = result.pol
    if not pol.block_accepted:
        state.pol_state["blocks_rejected"] += 1
        raise HTTPException(
            status_code=422,
            detail={"message": "PoL below threshold", "pol": pol.to_dict()},
        )

    graph_root = sha256_text(graph.checksum).replace("sha256:", "")

    # Construire contributors
    contributors = None
    if body.wallet_address:
        from src.artcb.mining.pipeline import build_contributors
        contributors = build_contributors(
            actor_address=body.wallet_address,
            pol_score=pol.pol_score,
            wallet=None,
            graph_root=graph_root,
            machine_registry=state.machine_registry,
            human_registry=state.human_registry,
            work_registry=state.work_registry,
            graph_id=graph.graph_id,
        )

    # Graver le bloc
    try:
        block = state.chain.append_block(
            graph_id=graph.graph_id,
            graph_root=graph_root,
            pol_score=pol.pol_score,
            visibility=body.visibility,
            contributors=contributors,
        )
    except ValueError as exc:
        state.pol_state["blocks_rejected"] += 1
        raise HTTPException(
            status_code=422,
            detail={"message": f"Block rejected: {exc}", "reason": str(exc)},
        ) from exc
    state.pol_state["pol_score"] = pol.pol_score
    state.pol_state["blocks_accepted"] += 1

    return {
        "graph_id": graph.graph_id,
        "block_index": block.index,
        "hash": block.hash,
        "pol_score": pol.pol_score,
        "visibility": block.visibility,
        "block_reward": block.block_reward,
    }


@router.post("/agents/run")
def agents_run(body: AgentRunRequest, request: Request) -> dict:
    state = _state(request)
    if body.use_llm:
        graph = LLMEncoder(encoder=state.encoder, connectors=state.connectors).encode(
            body.text,
            use_llm=True,
            session_id=f"g_{uuid.uuid4().hex[:12]}",
            llm_provider=body.llm_provider,
        )
        result = state.dual.critic.validate(graph)
    else:
        result = state.dual.run(body.text)

    graph = result.graph
    state.register_graph(graph)
    state.vectors.index_graph(graph)

    pol = result.pol
    state.pol_state["pol_score"] = pol.pol_score
    state.pol_state["compression_rate"] = pol.delta_compression
    state.pol_state["validation_rate"] = pol.validation_rate
    state.pol_state["retrieval_accuracy"] = pol.retrieval_accuracy
    if pol.block_accepted:
        state.pol_state["blocks_accepted"] += 1
    else:
        state.pol_state["blocks_rejected"] += 1

    state.timeline.append(
        RTLEGEvent(
            session_id=body.session_id,
            agent="critic",
            event_type="pol_validated",
            graph_id=graph.graph_id,
            payload=pol.to_dict(),
        )
    )

    return {
        "graph_id": graph.graph_id,
        "node_count": len(graph.nodes),
        "pol": pol.to_dict(),
        "nodes_validated": result.nodes_validated,
        "nodes_proposed": result.nodes_proposed,
        "symbol_proposals": [
            {"concept": p.concept, "symbol": p.symbol, "status": p.status, "reason": p.reason}
            for p in result.symbol_proposals
        ],
        "orig_symbols": graph.orig_symbols,
    }


@router.get("/rtleg/events")
def rtleg_events(
    request: Request,
    session_id: str | None = None,
    limit: int = 100,
) -> dict:
    state = _state(request)
    events = state.timeline.list_events(session_id=session_id, limit=limit)
    return {"events": [e.model_dump() for e in events], "count": len(events)}
