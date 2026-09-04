"""Group REST routes — request-to-join (Solution 2), pas de clé privée partagée."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from src.artcb.groups.join_requests import JoinRequestManager
from src.artcb.groups.manager import (
    ForbiddenGroupAction,
    FounderImmutableError,
    GroupError,
    GroupManager,
)
from src.artcb.groups.signing import build_join_challenge

logger = logging.getLogger("artcb.api.groups")
router = APIRouter(prefix="/api/v1/groups", tags=["groups"])


class CreateGroupRequest(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    founder_address: str | None = Field(default=None, min_length=8)
    organization_id: str | None = None


class ActorRequest(BaseModel):
    actor_address: str | None = None


class InviteMemberRequest(ActorRequest):
    address: str = Field(min_length=8)
    role: str = "contributor"


class SetRoleRequest(ActorRequest):
    role: str


class CreateSubgroupRequest(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    actor_address: str | None = None


class DissolveGroupRequest(ActorRequest):
    confirm: str


class SubmitJoinRequest(BaseModel):
    join_code: str = Field(min_length=6, max_length=16)
    address: str = Field(min_length=8)
    public_key_hex: str = Field(min_length=32)
    signature: str = Field(min_length=32)
    timestamp: str
    pqc_public_key_hex: str | None = None


class WalletJoinRequest(BaseModel):
    """Devnet: signe avec wallet local serveur — clé privée jamais exposée à l'inviteur."""
    wallet_name: str = Field(min_length=1)
    wallet_password: str | None = Field(default=None, description="Mot de passe du wallet pour déchiffrer la clé privée (None = passphrase serveur)")
    join_code: str = Field(min_length=6, max_length=16)


def _state(request: Request):
    return request.app.state.artcb


def _groups(request: Request) -> GroupManager:
    return _state(request).groups


def _join_requests(request: Request) -> JoinRequestManager:
    return _state(request).join_requests


def _require_actor(request: Request, claimed: str | None = None) -> str:
    """Identity from session / API key / wallet — never from the JSON body alone."""
    from src.artcb.authz.identity import resolve_principal

    principal = resolve_principal(request)
    if not principal.address:
        raise HTTPException(status_code=401, detail="authentication_required")
    if claimed and claimed != principal.address:
        raise HTTPException(status_code=403, detail="actor_address_mismatch")
    return principal.address


def _group_http_error(exc: GroupError) -> HTTPException:
    if isinstance(exc, FounderImmutableError):
        logger.debug("FOUNDER_IMMUTABLE blocked: %s", exc)
        return HTTPException(status_code=403, detail={"code": exc.code, "message": str(exc)})
    if isinstance(exc, ForbiddenGroupAction):
        return HTTPException(status_code=403, detail={"code": exc.code, "message": str(exc)})
    return HTTPException(status_code=400, detail={"code": exc.code, "message": str(exc)})


@router.post("")
def create_group(body: CreateGroupRequest, request: Request) -> dict:
    founder = _require_actor(request, body.founder_address)
    mgr = _groups(request)
    group = mgr.create_group(body.name, founder, organization_id=body.organization_id)
    _state(request).authz.genesis.create_group_genesis(
        group_id=group.group_id,
        name=group.name,
        founder_address=founder,
        parent_org=body.organization_id,
        parent_group_id=None,
    )
    logger.debug("Group created id=%s join_code=%s", group.group_id, group.join_code)
    out = group.to_dict()
    genesis = _state(request).authz.genesis.get_group_genesis(group.group_id)
    if genesis:
        out["genesis_hash"] = genesis.content_hash
        out["genesis_projection"] = "hash_only_on_global_commitments"
    return out


@router.get("")
def list_groups(
    request: Request,
    address: str | None = Query(default=None, min_length=8, description="Ignoré si session : on utilise l'identité réelle"),
) -> dict:
    """Liste les groupes du principal authentifié — jamais ceux d'une autre adresse."""
    from src.artcb.authz.identity import resolve_principal

    principal = resolve_principal(request)
    target = principal.address
    if not target:
        raise HTTPException(status_code=401, detail="authentication_required")
    if address and address != target:
        raise HTTPException(status_code=403, detail="address_mismatch")
    mgr = _groups(request)
    groups = mgr.list_groups_for_address(target)
    return {"groups": [g.to_dict() for g in groups], "count": len(groups)}


@router.get("/by-code/{join_code}")
def group_by_join_code(join_code: str, request: Request) -> dict:
    """Info publique groupe — sans liste membres ni adresses."""
    jr = _join_requests(request)
    try:
        return jr.public_group_info(join_code)
    except GroupError as exc:
        raise _group_http_error(exc) from exc


@router.post("/join-requests")
def submit_join_request(body: SubmitJoinRequest, request: Request) -> dict:
    """
    Invité soumet une demande signée.
    Le fondateur ne connaît pas l'adresse avant cette étape.
    Clé privée reste chez l'invité — seule signature transmise.
    """
    jr = _join_requests(request)
    try:
        req = jr.submit_request(
            join_code=body.join_code,
            address=body.address,
            public_key_hex=body.public_key_hex,
            signature=body.signature,
            timestamp=body.timestamp,
            pqc_public_key_hex=body.pqc_public_key_hex,
        )
        return req.to_dict()
    except GroupError as exc:
        raise _group_http_error(exc) from exc


@router.post("/join-requests/sign-with-wallet")
def sign_join_with_wallet(body: WalletJoinRequest, request: Request) -> dict:
    """
    Devnet dashboard: l'invité signe avec SON wallet (fichier local data/wallets/).
    L'inviteur ne voit jamais la clé privée — uniquement la demande résultante.
    """
    from src.artcb.wallet.manager import WalletManager

    jr = _join_requests(request)
    settings = _state(request).settings
    try:
        info = jr.public_group_info(body.join_code)
    except GroupError as exc:
        raise _group_http_error(exc) from exc

    wm = WalletManager(settings.data_dir / "wallets")
    try:
        wallet = wm.load_wallet(name=body.wallet_name, user_password=body.wallet_password)
    except Exception as exc:
        raise HTTPException(status_code=404, detail=f"Wallet not found or wrong password: {body.wallet_name}") from exc

    timestamp = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    message = build_join_challenge(info["group_id"], info["join_code"], wallet.address, timestamp)
    signature = wallet.sign(message)

    req = jr.submit_request(
        join_code=body.join_code,
        address=wallet.address,
        public_key_hex=wallet.public_key_hex,
        signature=signature,
        timestamp=timestamp,
        pqc_public_key_hex=wallet.pqc_public_key_hex,
    )
    return {"request": req.to_dict(), "message": "Join request submitted — awaiting admin approval"}


@router.post("/{group_id}/subgroups")
def create_subgroup(group_id: str, body: CreateSubgroupRequest, request: Request) -> dict:
    actor = _require_actor(request, body.actor_address)
    mgr = _groups(request)
    try:
        group = mgr.create_subgroup(group_id, body.name, actor)
    except GroupError as exc:
        raise _group_http_error(exc) from exc
    parent = mgr.get_group(group_id)
    _state(request).authz.genesis.create_group_genesis(
        group_id=group.group_id,
        name=group.name,
        founder_address=actor,
        parent_org=parent.organization_id if parent else None,
        parent_group_id=group_id,
    )
    out = group.to_dict()
    genesis = _state(request).authz.genesis.get_group_genesis(group.group_id)
    if genesis:
        out["genesis_hash"] = genesis.content_hash
    return out


@router.get("/{group_id}")
def get_group(group_id: str, request: Request) -> dict:
    from src.artcb.authz.identity import resolve_principal

    mgr = _groups(request)
    group = mgr.get_group(group_id)
    if not group or group.dissolved:
        raise HTTPException(status_code=404, detail="group not found")
    principal = resolve_principal(request)
    if principal.address and mgr.is_member(group_id, principal.address):
        return group.to_dict()
    return {
        "group_id": group.group_id,
        "name": group.name,
        "dissolved": group.dissolved,
        "member_count": len(group.members),
        "parent_group_id": group.parent_group_id,
        "projection": "public",
    }


@router.get("/{group_id}/join-requests")
def list_join_requests(
    group_id: str,
    request: Request,
    actor_address: str | None = Query(default=None, min_length=8),
    status: str | None = Query(None),
) -> dict:
    actor = _require_actor(request, actor_address)
    jr = _join_requests(request)
    try:
        items = jr.list_requests(group_id, actor, status)  # type: ignore[arg-type]
        return {"requests": [r.to_dict() for r in items], "count": len(items)}
    except GroupError as exc:
        raise _group_http_error(exc) from exc


@router.post("/{group_id}/join-requests/{request_id}/approve")
def approve_join_request(
    group_id: str,
    request_id: str,
    body: ActorRequest,
    request: Request,
) -> dict:
    actor = _require_actor(request, body.actor_address)
    jr = _join_requests(request)
    try:
        return jr.approve_request(group_id, actor, request_id)
    except GroupError as exc:
        raise _group_http_error(exc) from exc


@router.post("/{group_id}/join-requests/{request_id}/reject")
def reject_join_request(
    group_id: str,
    request_id: str,
    body: ActorRequest,
    request: Request,
) -> dict:
    actor = _require_actor(request, body.actor_address)
    jr = _join_requests(request)
    try:
        req = jr.reject_request(group_id, actor, request_id)
        return req.to_dict()
    except GroupError as exc:
        raise _group_http_error(exc) from exc


@router.post("/{group_id}/members")
def invite_member_direct_deprecated(group_id: str, body: InviteMemberRequest, request: Request) -> dict:
    """Désactivé par défaut — utiliser join-request. DEBUG: ARTCB_DEBUG_DIRECT_MEMBER=true"""
    actor = _require_actor(request, body.actor_address)
    mgr = _groups(request)
    try:
        group = mgr.add_member(group_id, actor, body.address, body.role)  # type: ignore[arg-type]
    except GroupError as exc:
        raise _group_http_error(exc) from exc
    return group.to_dict()


@router.post("/{group_id}/members/{target_address}/role")
def set_member_role(
    group_id: str,
    target_address: str,
    body: SetRoleRequest,
    request: Request,
) -> dict:
    actor = _require_actor(request, body.actor_address)
    mgr = _groups(request)
    try:
        group = mgr.set_member_role(
            group_id,
            actor,
            target_address,
            body.role,  # type: ignore[arg-type]
        )
    except GroupError as exc:
        raise _group_http_error(exc) from exc
    return group.to_dict()


@router.delete("/{group_id}/members/{target_address}")
def remove_member(
    group_id: str,
    target_address: str,
    request: Request,
    actor_address: str | None = Query(default=None, min_length=8),
) -> dict:
    actor = _require_actor(request, actor_address)
    mgr = _groups(request)
    try:
        group = mgr.remove_member(group_id, actor, target_address)
    except GroupError as exc:
        raise _group_http_error(exc) from exc
    return group.to_dict()


@router.post("/{group_id}/dissolve")
def dissolve_group(group_id: str, body: DissolveGroupRequest, request: Request) -> dict:
    actor = _require_actor(request, body.actor_address)
    mgr = _groups(request)
    try:
        group = mgr.dissolve_group(group_id, actor, body.confirm)
    except GroupError as exc:
        raise _group_http_error(exc) from exc
    return group.to_dict()
