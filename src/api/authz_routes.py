"""Authorization policy routes — GRANT / REVOKE / Genesis / decide.

Individual permissions are versioned transactions. Genesis is the
constitution (who may emit those transactions), not the permission DB.
Domain Manifest / Registry live here too: a node hosts, the founder owns.
"""

from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from src.artcb.authz.actions import ALL_ACTIONS, READ
from src.artcb.authz.domains import (
    P2P_SYNCS_PRIVATE_BLOCKS,
    REPLICATION_MATRIX,
    public_commitment,
)
from src.artcb.authz.models import Principal, ResourceRef
from src.artcb.authz.registry import (
    DomainError,
    DomainForbidden,
    DomainHashMismatch,
    STORAGE_MODES,
    build_export_bundle,
    verify_export_bundle,
)

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
    storage_mode: str = Field(default="artcb_managed")
    authorized_nodes: list[str] = Field(default_factory=list)


class AddReplicaRequest(BaseModel):
    node_id: str = Field(min_length=1, max_length=128)


class ImportDomainRequest(BaseModel):
    bundle: dict[str, Any]


def _host_node(request: Request) -> str:
    env = os.getenv("ARTCB_NODE_ID", "").strip()
    if env:
        return env
    ident = getattr(_state(request), "p2p_identity", None)
    if ident is not None and getattr(ident, "node_id", None):
        return str(ident.node_id)
    return "local-unbound-node"


def _register_domain(
    request: Request,
    *,
    domain_type: str,
    subject_id: str,
    founder_address: str,
    genesis_hash: str,
    storage_mode: str = "artcb_managed",
    authorized_nodes: list[str] | None = None,
    parent_id: str | None = None,
):
    gate = _gate(request)
    try:
        manifest = gate.domains.register(
            domain_type=domain_type,
            subject_id=subject_id,
            founder_address=founder_address,
            genesis_hash=genesis_hash,
            hosting_node_id=_host_node(request),
            storage_mode=storage_mode,
            authorized_nodes=authorized_nodes,
            parent_id=parent_id,
        )
    except DomainError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if not any(
        row.get("kind") == "domain" and row.get("domain_id") == manifest.domain_id
        for row in gate.genesis.commitments.list_all()
    ):
        gate.genesis.commitments.append(
            public_commitment(
                kind="domain",
                domain_id=manifest.domain_id,
                content_hash=genesis_hash,
                parent_id=parent_id,
                issuer=founder_address,
                issued_at=manifest.created_at,
            )
        )
    return manifest


def _hosted_here(gate, manifest) -> bool:
    if manifest.domain_type == "organization":
        return gate.genesis.get_org(manifest.subject_id) is not None
    return gate.genesis.get_group_genesis(manifest.subject_id) is not None


def _genesis_body(gate, manifest) -> dict[str, Any] | None:
    if manifest.domain_type == "organization":
        org = gate.genesis.get_org(manifest.subject_id)
        return org.to_dict() if org else None
    genesis = gate.genesis.get_group_genesis(manifest.subject_id)
    return genesis.to_dict() if genesis else None


@router.post("/orgs")
def create_org(body: CreateOrgRequest, request: Request) -> dict:
    gate = _gate(request)
    principal = gate.resolve(request, required=True)
    if not principal.address:
        raise HTTPException(status_code=401, detail="authentication_required")
    if body.storage_mode not in STORAGE_MODES:
        raise HTTPException(status_code=422, detail="unknown_storage_mode")
    org = gate.genesis.create_org(body.name, principal.address)
    manifest = _register_domain(
        request,
        domain_type="organization",
        subject_id=org.organization_id,
        founder_address=principal.address,
        genesis_hash=org.content_hash,
        storage_mode=body.storage_mode,
        authorized_nodes=body.authorized_nodes,
        parent_id="ARTCB",
    )
    host = _host_node(request)
    return {
        **org.to_dict(),
        "domain": manifest.public_view(),
        "ownership": {
            "founder_address": org.founder_address,
            "hosting_node_id": host,
            "node_owns_domain": False,
            "cest_a_dire": "Le nœud héberge le corps du Genesis. Le fondateur possède le domaine.",
        },
    }


@router.get("/orgs")
def list_orgs(request: Request) -> dict:
    """Public projection: existence + hash. Not the private domain body."""
    orgs = _gate(request).genesis.list_orgs()
    return {"orgs": [o.public_view() for o in orgs], "count": len(orgs)}


@router.get("/commitments")
def list_commitments(request: Request) -> dict:
    """Hashes only — what every consensus node may know."""
    rows = _gate(request).genesis.commitments.list_all()
    leaked = [r for r in rows if r.get("contains_private_data")]
    return {
        "commitments": rows,
        "count": len(rows),
        "contains_private_data": False,
        "leaked_private_rows": len(leaked),
    }


@router.get("/replication")
def replication_matrix() -> dict:
    return {
        "p2p_syncs_private_blocks": P2P_SYNCS_PRIVATE_BLOCKS,
        "matrix": REPLICATION_MATRIX,
        "note": "GLOBAL GENESIS is full on every node. ORG/GROUP bodies stay in the domain store. Only content_hash is a public commitment. A node hosts a domain; it does not own it.",
        "node_owns_domain": False,
    }


@router.get("/domains")
def list_domains(request: Request) -> dict:
    """Public Domain Registry projection — identity + hash + hosts, never the body."""
    rows = [_gate(request).domains.list_all()]
    manifests = rows[0]
    return {
        "domains": [m.public_view() for m in manifests],
        "count": len(manifests),
        "node_owns_domain": False,
        "contains_private_data": False,
        "commitment_anchored_on_chain": False,
    }


@router.get("/domains/{domain_id}")
def get_domain(domain_id: str, request: Request) -> dict:
    manifest = _gate(request).domains.get(domain_id)
    if manifest is None:
        raise HTTPException(status_code=404, detail="domain_not_found")
    return manifest.public_view()


@router.get("/domains/{domain_id}/locate")
def locate_domain(domain_id: str, request: Request) -> dict:
    gate = _gate(request)
    manifest = gate.domains.get(domain_id)
    if manifest is None:
        raise HTTPException(status_code=404, detail="domain_not_found")
    try:
        return gate.domains.locate(
            domain_id,
            this_node=_host_node(request),
            hosted_here=_hosted_here(gate, manifest),
        )
    except DomainError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/domains/{domain_id}/body")
def get_domain_body(domain_id: str, request: Request) -> dict:
    """Founder-only. The Genesis body never goes through public P2P."""
    gate = _gate(request)
    principal = gate.resolve(request, required=True)
    manifest = gate.domains.get(domain_id)
    if manifest is None:
        raise HTTPException(status_code=404, detail="domain_not_found")
    if principal.address != manifest.founder_address:
        raise HTTPException(status_code=403, detail="founder_mismatch")
    if not _hosted_here(gate, manifest):
        raise HTTPException(
            status_code=409,
            detail=gate.domains.locate(
                domain_id,
                this_node=_host_node(request),
                hosted_here=False,
            ),
        )
    body = _genesis_body(gate, manifest)
    if body is None:
        raise HTTPException(status_code=404, detail="genesis_body_missing")
    return {
        "domain": manifest.public_view(),
        "genesis_body": body,
        "node_owns_domain": False,
    }


@router.post("/domains/{domain_id}/export")
def export_domain(domain_id: str, request: Request) -> dict:
    gate = _gate(request)
    principal = gate.resolve(request, required=True)
    if not principal.address:
        raise HTTPException(status_code=401, detail="authentication_required")
    manifest = gate.domains.get(domain_id)
    if manifest is None:
        raise HTTPException(status_code=404, detail="domain_not_found")
    if principal.address != manifest.founder_address:
        raise HTTPException(status_code=403, detail="founder_mismatch")
    if not _hosted_here(gate, manifest):
        raise HTTPException(status_code=409, detail="domain_not_hosted_here")
    body = _genesis_body(gate, manifest)
    if body is None:
        raise HTTPException(status_code=404, detail="genesis_body_missing")
    policies = [
        tx.to_dict()
        for tx in gate.policies.load()
        if tx.resource.organization_id == manifest.subject_id
        or tx.resource.group_id == manifest.subject_id
    ]
    return build_export_bundle(
        manifest,
        body,
        exported_by=principal.address,
        policies=policies,
    )


@router.post("/domains/import")
def import_domain(body: ImportDomainRequest, request: Request) -> dict:
    gate = _gate(request)
    principal = gate.resolve(request, required=True)
    if not principal.address:
        raise HTTPException(status_code=401, detail="authentication_required")
    bundle = body.bundle
    try:
        verify_export_bundle(bundle)
    except DomainHashMismatch as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except DomainError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    manifest_data = bundle.get("manifest") or {}
    if principal.address != manifest_data.get("founder_address"):
        raise HTTPException(status_code=403, detail="founder_mismatch")
    genesis_body = bundle.get("genesis_body") or {}
    domain_type = manifest_data.get("domain_type")
    try:
        if domain_type == "organization":
            imported = gate.genesis.import_org(genesis_body)
            subject_id = imported.organization_id
            genesis_hash = imported.content_hash
            parent_id = imported.parent_root
        elif domain_type == "group":
            imported = gate.genesis.import_group_genesis(genesis_body)
            subject_id = imported.group_id
            genesis_hash = imported.content_hash
            parent_id = imported.parent_org or imported.parent_group_id
        else:
            raise HTTPException(status_code=422, detail="unknown_domain_type")
    except DomainHashMismatch as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    from src.artcb.authz.registry import DomainManifest

    incoming = DomainManifest.from_dict(manifest_data)
    existing = gate.domains.get(incoming.domain_id) or gate.domains.get_by_subject(subject_id)
    if existing:
        manifest = gate.domains.record_import(existing, _host_node(request))
    else:
        incoming.hosting_node_id = _host_node(request)
        manifest = gate.domains.record_import(incoming, _host_node(request))
    if manifest.genesis_hash != genesis_hash:
        raise HTTPException(status_code=422, detail="genesis_hash_mismatch")
    return {
        "imported": True,
        "subject_id": subject_id,
        "domain": manifest.public_view(),
        "ownership": {
            "founder_address": manifest.founder_address,
            "hosting_node_id": _host_node(request),
            "node_owns_domain": False,
        },
        "parent_id": parent_id,
        "commitment_anchored_on_chain": False,
    }


@router.post("/domains/{domain_id}/replicas")
def add_domain_replica(domain_id: str, body: AddReplicaRequest, request: Request) -> dict:
    gate = _gate(request)
    principal = gate.resolve(request, required=True)
    if not principal.address:
        raise HTTPException(status_code=401, detail="authentication_required")
    try:
        manifest = gate.domains.add_replica(domain_id, body.node_id, principal.address)
    except DomainForbidden as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except DomainError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {
        "domain": manifest.public_view(),
        "body_copied": False,
        "cest_a_dire": "Le nœud est autorisé à héberger. Le corps n'a pas été copié automatiquement.",
    }


class CanIRequest(BaseModel):
    action: str = Field(default=READ)
    resource: ResourceBody
    agent_id: str | None = None


@router.post("/can-i")
def can_i(body: CanIRequest, request: Request) -> dict:
    """Agent/human asks its effective right before starting work."""
    gate = _gate(request)
    principal = gate.resolve(request)
    if body.agent_id:
        if not principal.address:
            raise HTTPException(status_code=401, detail="agent_requires_human_session")
        principal = Principal(
            address=principal.address,
            wallet_name=principal.wallet_name,
            kind="agent",
            agent_id=body.agent_id,
            parent_address=principal.address,
            source=principal.source,
        )
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
    decision = gate.decide(principal, body.action, resource)
    return {
        "effect": decision.effect,
        "allowed": decision.allowed,
        "reason": decision.reason,
        "policy_version": decision.policy_version,
        "matched_tx_ids": decision.matched_tx_ids,
        "principal": principal.subject_id(),
        "proof": {
            "issuer": "ARTCB_AUTHZ",
            "delegation": principal.kind == "agent",
            "parent": principal.parent_address,
            "policy_version": decision.policy_version,
        },
    }


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
