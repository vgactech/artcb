"""Join requests — request-to-join (Solution 2), sans partage de clé privée."""

from __future__ import annotations
MODULE_VERSION = '1.0.0'  # R390 — auto-versioning

import json
import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from src.artcb.groups.manager import ForbiddenGroupAction, GroupError, GroupManager
from src.artcb.groups.signing import build_join_challenge, timestamp_fresh, verify_join_signature

logger = logging.getLogger("artcb.groups.join_requests")

JoinRequestStatus = Literal["pending", "approved", "rejected"]


@dataclass
class JoinRequest:
    request_id: str
    group_id: str
    join_code: str
    address: str
    public_key_hex: str
    signature: str
    timestamp: str
    status: JoinRequestStatus
    created_at: str
    resolved_at: str | None = None
    resolved_by: str | None = None
    pqc_public_key_hex: str | None = None

    def to_dict(self) -> dict:
        return {
            "request_id": self.request_id,
            "group_id": self.group_id,
            "join_code": self.join_code,
            "address": self.address,
            "public_key_hex": self.public_key_hex,
            "signature": self.signature,
            "timestamp": self.timestamp,
            "pqc_public_key_hex": self.pqc_public_key_hex,
            "status": self.status,
            "created_at": self.created_at,
            "resolved_at": self.resolved_at,
            "resolved_by": self.resolved_by,
        }


class JoinRequestManager:
    def __init__(self, groups_dir: Path, group_manager: GroupManager) -> None:
        self.groups_dir = Path(groups_dir)
        self.group_manager = group_manager

    def _requests_path(self, group_id: str) -> Path:
        return self.groups_dir / f"{group_id}_join_requests.jsonl"

    def _read_requests(self, group_id: str) -> list[JoinRequest]:
        path = self._requests_path(group_id)
        if not path.is_file():
            return []
        items: list[JoinRequest] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                data = json.loads(line)
                data.setdefault("pqc_public_key_hex", None)
                items.append(JoinRequest(**data))
        return items

    def _append_request(self, request: JoinRequest) -> None:
        path = self._requests_path(request.group_id)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(request.to_dict(), ensure_ascii=False) + "\n")

    def _rewrite_requests(self, group_id: str, requests: list[JoinRequest]) -> None:
        path = self._requests_path(group_id)
        with path.open("w", encoding="utf-8") as f:
            for req in requests:
                f.write(json.dumps(req.to_dict(), ensure_ascii=False) + "\n")

    def get_group_by_join_code(self, join_code: str):
        code = join_code.strip().upper()
        for path in self.groups_dir.glob("g_*.json"):
            group = self.group_manager.get_group(path.stem)
            if group and not group.dissolved:
                gcode = getattr(group, "join_code", None) or self._load_join_code(path)
                if gcode == code:
                    return group
        return None

    def _load_join_code(self, group_path: Path) -> str | None:
        data = json.loads(group_path.read_text(encoding="utf-8"))
        return data.get("join_code")

    def public_group_info(self, join_code: str) -> dict:
        group = self.get_group_by_join_code(join_code)
        if not group:
            raise GroupError("Invalid join code")
        return {
            "group_id": group.group_id,
            "name": group.name,
            "join_code": join_code.strip().upper(),
            "member_count": len(group.members),
        }

    def submit_request(
        self,
        *,
        join_code: str,
        address: str,
        public_key_hex: str,
        signature: str,
        timestamp: str,
        pqc_public_key_hex: str | None = None,
    ) -> JoinRequest:
        group = self.get_group_by_join_code(join_code)
        if not group:
            raise GroupError("Invalid join code")
        if self.group_manager.is_member(group.group_id, address):
            raise GroupError("Already a member")

        if not timestamp_fresh(timestamp):
            raise GroupError("Timestamp expired or invalid")

        message = build_join_challenge(group.group_id, join_code.strip().upper(), address, timestamp)
        if not verify_join_signature(
            public_key_hex=public_key_hex,
            address=address,
            signature_hex=signature,
            message=message,
            pqc_public_key_hex=pqc_public_key_hex,
        ):
            raise GroupError("Invalid signature")

        existing = self._read_requests(group.group_id)
        for req in existing:
            if req.address == address and req.status == "pending":
                raise GroupError("Pending request already exists")

        now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        request = JoinRequest(
            request_id=f"jr_{uuid.uuid4().hex[:12]}",
            group_id=group.group_id,
            join_code=join_code.strip().upper(),
            address=address,
            public_key_hex=public_key_hex,
            signature=signature,
            timestamp=timestamp,
            pqc_public_key_hex=pqc_public_key_hex,
            status="pending",
            created_at=now,
        )
        self._append_request(request)
        self.group_manager._audit("join_request_submitted", group.group_id, address, request.request_id)
        logger.debug("Join request %s for group %s", request.request_id, group.group_id)
        return request

    def list_requests(
        self,
        group_id: str,
        actor: str,
        status: JoinRequestStatus | None = None,
    ) -> list[JoinRequest]:
        group = self.group_manager.get_group(group_id)
        if not group or group.dissolved:
            raise GroupError("Group not found")
        role = self.group_manager._role_of(group, actor)
        if role not in ("founder", "admin"):
            raise ForbiddenGroupAction("Only founder or admin can list join requests")
        items = self._read_requests(group_id)
        if status:
            items = [r for r in items if r.status == status]
        return items

    def approve_request(self, group_id: str, actor: str, request_id: str) -> dict:
        group = self.group_manager.get_group(group_id)
        if not group or group.dissolved:
            raise GroupError("Group not found")
        role = self.group_manager._role_of(group, actor)
        if role not in ("founder", "admin"):
            raise ForbiddenGroupAction("Only founder or admin can approve")

        requests = self._read_requests(group_id)
        target = next((r for r in requests if r.request_id == request_id), None)
        if not target or target.status != "pending":
            raise GroupError("Join request not found or not pending")

        updated_group = self.group_manager.add_member_approved(
            group_id, actor, target.address, "contributor"
        )
        now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        for req in requests:
            if req.request_id == request_id:
                req.status = "approved"
                req.resolved_at = now
                req.resolved_by = actor
        self._rewrite_requests(group_id, requests)
        self.group_manager._audit("join_request_approved", group_id, actor, request_id)
        return {"group": updated_group.to_dict(), "request": target.to_dict()}

    def reject_request(self, group_id: str, actor: str, request_id: str) -> JoinRequest:
        group = self.group_manager.get_group(group_id)
        if not group or group.dissolved:
            raise GroupError("Group not found")
        role = self.group_manager._role_of(group, actor)
        if role not in ("founder", "admin"):
            raise ForbiddenGroupAction("Only founder or admin can reject")

        requests = self._read_requests(group_id)
        target = next((r for r in requests if r.request_id == request_id), None)
        if not target or target.status != "pending":
            raise GroupError("Join request not found or not pending")

        now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        for req in requests:
            if req.request_id == request_id:
                req.status = "rejected"
                req.resolved_at = now
                req.resolved_by = actor
        self._rewrite_requests(group_id, requests)
        self.group_manager._audit("join_request_rejected", group_id, actor, request_id)
        return target
