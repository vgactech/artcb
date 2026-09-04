"""Authorization policy routes — GRANT / REVOKE / Genesis / decide.

Individual permissions are versioned transactions. Genesis is the
constitution (who may emit those transactions), not the permission DB.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from src.artcb.authz.actions import ALL_ACTIONS, READ
from src.artcb.authz.models import ResourceRef

router = APIRouter(prefix="/api/v1/authz", tags=["authz"])


def _state(request: Request):
    return request.app.state.artcb


def _gate(request: Request):
    return _state(request).authz


class ResourceBody(BaseModel):
    visibility: str | None = None
    owner_address: str | None = None
    organization_id: str | None = None
    group_id: str | None = None
    subgroup_id: str | None = None
    resource_id: str | None = None
    graph_id: str | None = None
    block_index: int | None = None


class GrantRequest(BaseModel):
    subject: str = Field(min_length=4)
    action: str = Field(default=READ)
    resource: ResourceBody
    effect: str = Field(default="ALLOW")
    subject_kind: str = Field(default="human")
    parent_subject: str | None = None
    expires_at: str | None = None
    delegation: bool = False


class RevokeRequest(BaseModel):
    grant_id: str = Field(min_length=4)


class CreateOrgRequest(BaseModel):
    name: str = Field(min_length=1, max_length=128)


@router.post("/orgs")
def create_org(body: CreateOrgRequest, request: Request) -> dict:
    gate = _gate(request)
    principal = gate.resolve(request, required=True)
    if not principal.address:
        raise HTTPException(status_code=401, detail="authentication_required")
    org = gate.genesis.create_org(body.name, principal.address)
    return org.to_dict()


@router.get("/orgs")
def list_orgs(request: Request) -> dict:
    orgs = _gate(request).genesis.list_orgs()
    return {"orgs": [o.to_dict() for o in orgs], "count": len(orgs)}


@router.post("/grants")
def create_grant(body: GrantRequest, request: Request) -> dict:
    gate = _gate(request)
    principal = gate.resolve(request, required=True)
    if not principal.address:
        raise HTTPException(status_code=401, detail="authentication_required")
    action = body.action.upper()
    if action not in ALL_ACTIONS and action != "*":
        raise HTTPException(status_code=422, detail="unknown_action")
    if body.effect not in ("ALLOW", "DENY"):
        raise HTTPException(status_code=422, detail="effect must be ALLOW or DENY")
    if body.subject_kind == "agent" and not body.parent_subject:
        raise HTTPException(status_code=422, detail="agent_grant_requires_parent_subject")

    resource = ResourceRef.from_dict(body.resource.model_dump())
    if resource.graph_id:
        resource = _merge_indexed(gate, resource)
    elif resource.resource_id:
        indexed = gate.index.as_resource_id(resource.resource_id)
        if indexed:
            resource = ResourceRef(
                visibility=resource.visibility or indexed.visibility,
                owner_address=resource.owner_address or indexed.owner_address,
                organization_id=resource.organization_id or indexed.organization_id,
                group_id=resource.group_id or indexed.group_id,
                subgroup_id=resource.subgroup_id or indexed.subgroup_id,
                resource_id=resource.resource_id,
                graph_id=resource.graph_id or indexed.graph_id,
                block_index=resource.block_index if resource.block_index is not None else indexed.block_index,
            )

    decision = gate.can_issue_grant(principal, resource)
    if not decision.allowed:
        # Founder/admin of the target group may grant without a prior GRANT action.
        if not _group_admin(gate, principal.address, resource):
            raise HTTPException(status_code=403, detail="cannot_grant")

    subject = body.subject
    if body.subject_kind == "agent" and not subject.startswith("agent:"):
        subject = f"agent:{body.subject}"

    tx = gate.policies.grant(
        subject=subject,
        action=action,
        resource=resource,
        issuer=principal.address,
        effect=body.effect,
        subject_kind=body.subject_kind,
        parent_subject=body.parent_subject,
        expires_at=body.expires_at,
        delegation=body.delegation,
    )
    gate.reload()
    return tx.to_dict()


@router.post("/revoke")
def revoke_grant(body: RevokeRequest, request: Request) -> dict:
    gate = _gate(request)
    principal = gate.resolve(request, required=True)
    if not principal.address:
        raise HTTPException(status_code=401, detail="authentication_required")
    try:
        existing = next(t for t in gate.policies.load() if t.tx_id == body.grant_id)
    except StopIteration as exc:
        raise HTTPException(status_code=404, detail="grant_not_found") from exc
    decision = gate.can_revoke(principal, existing.resource)
    if not decision.allowed and existing.issuer != principal.address:
        if not _group_admin(gate, principal.address, existing.resource):
            raise HTTPException(status_code=403, detail="cannot_revoke")
    tx = gate.policies.revoke(target_tx_id=body.grant_id, issuer=principal.address)
    gate.reload()
    return tx.to_dict()


@router.get("/grants")
def list_grants(request: Request) -> dict:
    principal = _gate(request).resolve(request, required=True)
    txs = _gate(request).policies.load()
    visible = [
        t.to_dict()
        for t in txs
        if t.subject in {principal.address, principal.subject_id(), f"agent:{principal.agent_id}"}
        or t.issuer == principal.address
    ]
    return {"grants": visible, "count": len(visible)}


@router.get("/decide")
def decide(
    request: Request,
    action: str = Query(default=READ),
    graph_id: str | None = Query(default=None),
    block_index: int | None = Query(default=None),
    resource_id: str | None = Query(default=None),
) -> dict:
    gate = _gate(request)
    principal = gate.resolve(request)
    if graph_id:
        resource = gate.resource_for_graph(graph_id)
    elif block_index is not None:
        block = next((b for b in gate.chain._read_all_blocks() if b.get("index") == block_index), None)
        if not block:
            raise HTTPException(status_code=404, detail="block not found")
        resource = gate.resource_for_block(block)
    else:
        resource = ResourceRef(resource_id=resource_id)
    decision = gate.decide(principal, action, resource)
    return {"principal": principal.address, "action": action, **decision.to_dict()}


def _merge_indexed(gate, resource: ResourceRef) -> ResourceRef:
    indexed = gate.resource_for_graph(resource.graph_id) if resource.graph_id else resource
    return ResourceRef(
        visibility=resource.visibility or indexed.visibility,
        owner_address=resource.owner_address or indexed.owner_address,
        organization_id=resource.organization_id or indexed.organization_id,
        group_id=resource.group_id or indexed.group_id,
        subgroup_id=resource.subgroup_id or indexed.subgroup_id,
        resource_id=resource.resource_id or indexed.resource_id,
        graph_id=resource.graph_id or indexed.graph_id,
        block_index=resource.block_index if resource.block_index is not None else indexed.block_index,
    )


def _group_admin(gate, address: str | None, resource: ResourceRef) -> bool:
    if not address:
        return False
    for gid in (resource.subgroup_id, resource.group_id):
        if not gid:
            continue
        group = gate.groups.get_group(gid)
        if not group or group.dissolved:
            continue
        for member in group.members:
            if member.address == address and member.role in ("founder", "admin"):
                return True
    return False
