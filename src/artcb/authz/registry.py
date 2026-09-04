"""Domain Manifest + Domain Registry (rapport 218).

A node *hosts* a domain. It does not *own* it.

    NODE = infrastructure that can host one or more domains
    DOMAIN = founder-owned constitution + local body + public hash

Alice can create an organisation from a browser with no personal node.
The receiving ARTCB process writes the Genesis *body* locally and records
a Domain Manifest: who the founder is, which node currently hosts the
body, and which nodes are *authorised* to host a replica.

Authorising a node is not the same as copying the body. Automatic
multi-node private replication is still P-217-3. Recovery is a
founder-authorised export / import that re-checks ``canonical_hash``.

The registry file itself is local to this process (same honesty as
``commitments.jsonl``). It is not gossiped to the four official nodes.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.artcb.authz.domains import canonical_hash

STORAGE_MODES = frozenset({"artcb_managed", "selected_nodes", "personal", "hybrid"})


class DomainError(ValueError):
    """Domain registry / migration error."""


class DomainHashMismatch(DomainError):
    """Presented Genesis body does not match the committed hash."""


class DomainForbidden(DomainError):
    """Caller is not the founder of this domain."""


def _now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class DomainManifest:
    """Public identity of a domain. The Genesis *body* is a separate object."""

    domain_id: str
    domain_type: str
    subject_id: str
    founder_address: str
    genesis_hash: str
    hosting_node_id: str
    authorized_nodes: list[str] = field(default_factory=list)
    storage_mode: str = "artcb_managed"
    parent_id: str | None = None
    recovery_enabled: bool = True
    min_replicas: int = 1
    created_at: str = ""
    version: int = 1
    body_replicated: bool = False
    commitment_anchored_on_chain: bool = False
    node_owns_domain: bool = False

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["node_owns_domain"] = False
        data["commitment_anchored_on_chain"] = False
        return data

    def public_view(self) -> dict[str, Any]:
        """Safe for any reader. No members, no documents, no Genesis body."""
        return {
            "domain_id": self.domain_id,
            "domain_type": self.domain_type,
            "subject_id": self.subject_id,
            "founder_address": self.founder_address,
            "genesis_hash": self.genesis_hash,
            "parent_id": self.parent_id,
            "hosting_node_id": self.hosting_node_id,
            "authorized_nodes": list(self.authorized_nodes),
            "storage_mode": self.storage_mode,
            "recovery_enabled": self.recovery_enabled,
            "min_replicas": self.min_replicas,
            "version": self.version,
            "created_at": self.created_at,
            "node_owns_domain": False,
            "body_replicated": self.body_replicated,
            "commitment_anchored_on_chain": False,
            "projection": "domain_manifest_public",
            "contains_private_data": False,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DomainManifest:
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        payload = {k: v for k, v in data.items() if k in known}
        payload["node_owns_domain"] = False
        payload["commitment_anchored_on_chain"] = False
        return cls(**payload)


def constitution_from_body(body: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in body.items() if k != "content_hash"}


def verify_genesis_hash(body: dict[str, Any], expected: str) -> str:
    recomputed = canonical_hash(constitution_from_body(body))
    if recomputed != expected:
        raise DomainHashMismatch("genesis_hash_mismatch")
    stored = body.get("content_hash")
    if stored and stored != recomputed:
        raise DomainHashMismatch("body_hash_mismatch")
    return recomputed


def build_export_bundle(
    manifest: DomainManifest,
    genesis_body: dict[str, Any],
    *,
    exported_by: str,
    policies: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    verify_genesis_hash(genesis_body, manifest.genesis_hash)
    payload = {
        "kind": "artcb_domain_export",
        "manifest": manifest.to_dict(),
        "genesis_body": genesis_body,
        "policies": policies or [],
        "exported_at": _now_iso(),
        "exported_by": exported_by,
    }
    payload["export_hash"] = canonical_hash(
        {
            "manifest": payload["manifest"],
            "genesis_body": constitution_from_body(genesis_body),
            "exported_by": exported_by,
        }
    )
    return payload


def verify_export_bundle(bundle: dict[str, Any]) -> str:
    if bundle.get("kind") != "artcb_domain_export":
        raise DomainError("invalid_export_kind")
    manifest = bundle.get("manifest") or {}
    body = bundle.get("genesis_body") or {}
    if not isinstance(manifest, dict) or not isinstance(body, dict):
        raise DomainError("invalid_export_shape")
    expected = str(manifest.get("genesis_hash") or "")
    return verify_genesis_hash(body, expected)


class DomainRegistry:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _read_all(self) -> list[dict[str, Any]]:
        if not self.path.is_file():
            return []
        return json.loads(self.path.read_text(encoding="utf-8") or "[]")

    def _write_all(self, rows: list[dict[str, Any]]) -> None:
        self.path.write_text(json.dumps(rows, indent=2), encoding="utf-8")

    def list_all(self) -> list[DomainManifest]:
        return [DomainManifest.from_dict(row) for row in self._read_all()]

    def get(self, domain_id: str) -> DomainManifest | None:
        for row in self._read_all():
            if row.get("domain_id") == domain_id:
                return DomainManifest.from_dict(row)
        return None

    def get_by_subject(self, subject_id: str) -> DomainManifest | None:
        for row in self._read_all():
            if row.get("subject_id") == subject_id:
                return DomainManifest.from_dict(row)
        return None

    def _upsert(self, manifest: DomainManifest) -> DomainManifest:
        rows = self._read_all()
        updated = False
        for index, row in enumerate(rows):
            if row.get("domain_id") == manifest.domain_id:
                rows[index] = manifest.to_dict()
                updated = True
                break
        if not updated:
            rows.append(manifest.to_dict())
        self._write_all(rows)
        return manifest

    def register(
        self,
        *,
        domain_type: str,
        subject_id: str,
        founder_address: str,
        genesis_hash: str,
        hosting_node_id: str,
        storage_mode: str = "artcb_managed",
        authorized_nodes: list[str] | None = None,
        parent_id: str | None = None,
    ) -> DomainManifest:
        if storage_mode not in STORAGE_MODES:
            raise DomainError(f"unknown_storage_mode:{storage_mode}")
        if domain_type not in {"organization", "group"}:
            raise DomainError(f"unknown_domain_type:{domain_type}")
        existing = self.get_by_subject(subject_id)
        if existing:
            return existing
        nodes = [n for n in (authorized_nodes or []) if n]
        if hosting_node_id and hosting_node_id not in nodes:
            nodes = [hosting_node_id, *nodes]
        if not nodes:
            nodes = [hosting_node_id]
        min_replicas = 2 if storage_mode == "hybrid" else 1
        manifest = DomainManifest(
            domain_id=f"domain_{uuid.uuid4().hex[:12]}",
            domain_type=domain_type,
            subject_id=subject_id,
            founder_address=founder_address,
            genesis_hash=genesis_hash,
            parent_id=parent_id,
            hosting_node_id=hosting_node_id,
            authorized_nodes=nodes,
            storage_mode=storage_mode,
            recovery_enabled=True,
            min_replicas=min_replicas,
            created_at=_now_iso(),
            body_replicated=False,
        )
        return self._upsert(manifest)

    def add_replica(self, domain_id: str, node_id: str, founder_address: str) -> DomainManifest:
        manifest = self.get(domain_id)
        if manifest is None:
            raise DomainError("domain_not_found")
        if manifest.founder_address != founder_address:
            raise DomainForbidden("founder_mismatch")
        if node_id not in manifest.authorized_nodes:
            manifest.authorized_nodes.append(node_id)
        # Listing a node is intent. It does not copy the private body.
        manifest.body_replicated = False
        manifest.version += 1
        return self._upsert(manifest)

    def record_import(self, manifest: DomainManifest, hosting_node_id: str) -> DomainManifest:
        if hosting_node_id and hosting_node_id not in manifest.authorized_nodes:
            manifest.authorized_nodes.append(hosting_node_id)
        manifest.hosting_node_id = hosting_node_id
        manifest.body_replicated = len(manifest.authorized_nodes) > 1
        manifest.version += 1
        return self._upsert(manifest)

    def locate(
        self,
        domain_id: str,
        *,
        this_node: str,
        hosted_here: bool,
    ) -> dict[str, Any]:
        manifest = self.get(domain_id)
        if manifest is None:
            raise DomainError("domain_not_found")
        return {
            **manifest.public_view(),
            "hosted_here": hosted_here,
            "this_node": this_node,
            "route": "local_domain_store" if hosted_here else "not_hosted_here",
            "recovery": "founder_signed_export_import",
            "cest_a_dire": (
                "Ce nœud héberge le corps du domaine."
                if hosted_here
                else "Ce nœud ne possède pas le corps. Le fondateur peut exporter depuis un hôte puis importer ici."
            ),
        }
