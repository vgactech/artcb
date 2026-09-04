"""Group management — founder immutable, admin delegation."""

from __future__ import annotations

import json
import logging
import secrets
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from src.artcb.groups.policy import direct_member_invite_allowed

logger = logging.getLogger("artcb.groups")

GroupRole = Literal["founder", "admin", "contributor", "viewer"]
VALID_ROLES: set[str] = {"founder", "admin", "contributor", "viewer"}


def generate_join_code() -> str:
    return secrets.token_hex(4).upper()


class GroupError(Exception):
    """Base group error."""

    code = "GROUP_ERROR"


class FounderImmutableError(GroupError):
    code = "FOUNDER_IMMUTABLE"


class ForbiddenGroupAction(GroupError):
    code = "FORBIDDEN"


@dataclass
class GroupMember:
    address: str
    role: GroupRole
    joined_at: str

    def to_dict(self) -> dict:
        return {"address": self.address, "role": self.role, "joined_at": self.joined_at}


@dataclass
class Group:
    group_id: str
    name: str
    founder_address: str
    created_at: str
    join_code: str = ""
    dissolved: bool = False
    members: list[GroupMember] = field(default_factory=list)
    parent_group_id: str | None = None
    organization_id: str | None = None

    def to_dict(self) -> dict:
        return {
            "group_id": self.group_id,
            "name": self.name,
            "founder_address": self.founder_address,
            "created_at": self.created_at,
            "join_code": self.join_code,
            "dissolved": self.dissolved,
            "members": [m.to_dict() for m in self.members],
            "parent_group_id": self.parent_group_id,
            "organization_id": self.organization_id,
        }


class GroupManager:
    def __init__(self, groups_dir: Path) -> None:
        self.groups_dir = Path(groups_dir)
        self.groups_dir.mkdir(parents=True, exist_ok=True)
        self.audit_path = self.groups_dir / "groups_audit.jsonl"

    def _group_path(self, group_id: str) -> Path:
        return self.groups_dir / f"{group_id}.json"

    def _audit(self, event: str, group_id: str, actor: str, detail: str = "") -> None:
        entry = {
            "ts": datetime.now(UTC).isoformat(),
            "event": event,
            "group_id": group_id,
            "actor": actor,
            "detail": detail,
        }
        with self.audit_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
        logger.debug("Group audit: %s", entry)

    def create_group(
        self,
        name: str,
        founder_address: str,
        *,
        parent_group_id: str | None = None,
        organization_id: str | None = None,
    ) -> Group:
        group_id = f"g_{uuid.uuid4().hex[:12]}"
        now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        join_code = generate_join_code()
        group = Group(
            group_id=group_id,
            name=name,
            founder_address=founder_address,
            created_at=now,
            join_code=join_code,
            members=[
                GroupMember(address=founder_address, role="founder", joined_at=now),
            ],
            parent_group_id=parent_group_id,
            organization_id=organization_id,
        )
        self._save(group)
        self._audit("group_created", group_id, founder_address, name)
        return group

    def create_subgroup(self, parent_group_id: str, name: str, actor: str) -> Group:
        parent = self.get_group(parent_group_id)
        if not parent or parent.dissolved:
            raise GroupError("Parent group not found")
        role = self._role_of(parent, actor)
        if role not in ("founder", "admin"):
            raise ForbiddenGroupAction("Only founder or admin can create a subgroup")
        group = self.create_group(
            name,
            actor,
            parent_group_id=parent_group_id,
            organization_id=parent.organization_id,
        )
        self._audit("subgroup_created", group.group_id, actor, parent_group_id)
        return group

    def get_group(self, group_id: str) -> Group | None:
        path = self._group_path(group_id)
        if not path.is_file():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        members = [GroupMember(**m) for m in data.get("members", [])]
        return Group(
            group_id=data["group_id"],
            name=data["name"],
            founder_address=data["founder_address"],
            created_at=data["created_at"],
            join_code=data.get("join_code", ""),
            dissolved=data.get("dissolved", False),
            members=members,
            parent_group_id=data.get("parent_group_id"),
            organization_id=data.get("organization_id"),
        )

    def _save(self, group: Group) -> None:
        self._group_path(group.group_id).write_text(
            json.dumps(group.to_dict(), indent=2),
            encoding="utf-8",
        )

    def list_groups_for_address(self, address: str) -> list[Group]:
        groups: list[Group] = []
        for path in self.groups_dir.glob("g_*.json"):
            group = self.get_group(path.stem)
            if group and not group.dissolved and any(m.address == address for m in group.members):
                groups.append(group)
        return groups

    def _get_member(self, group: Group, address: str) -> GroupMember | None:
        for m in group.members:
            if m.address == address:
                return m
        return None

    def _role_of(self, group: Group, address: str) -> str | None:
        m = self._get_member(group, address)
        return m.role if m else None

    def _assert_founder_action(self, group: Group, actor: str) -> None:
        if actor != group.founder_address:
            raise ForbiddenGroupAction("Only founder can perform this action")

    def _assert_not_founder_target(self, group: Group, target: str) -> None:
        if target == group.founder_address:
            self._audit("FOUNDER_IMMUTABLE_BLOCKED", group.group_id, target)
            raise FounderImmutableError("Cannot modify founder membership")

    def add_member(
        self,
        group_id: str,
        actor: str,
        new_address: str,
        role: GroupRole = "contributor",
    ) -> Group:
        if not direct_member_invite_allowed():
            raise ForbiddenGroupAction(
                "Direct member add disabled — use join-request flow (POST /groups/join-requests)"
            )
        return self.add_member_approved(group_id, actor, new_address, role)

    def add_member_approved(
        self,
        group_id: str,
        actor: str,
        new_address: str,
        role: GroupRole = "contributor",
    ) -> Group:
        group = self.get_group(group_id)
        if not group or group.dissolved:
            raise GroupError("Group not found")
        actor_role = self._role_of(group, actor)
        if actor_role not in ("founder", "admin"):
            raise ForbiddenGroupAction("Only founder or admin can invite")
        if role == "founder":
            raise ForbiddenGroupAction("Cannot assign founder role")
        if self._get_member(group, new_address):
            raise GroupError("Member already exists")
        now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        group.members.append(GroupMember(address=new_address, role=role, joined_at=now))
        self._save(group)
        self._audit("member_added", group_id, actor, new_address)
        return group

    def set_member_role(
        self,
        group_id: str,
        actor: str,
        target: str,
        role: GroupRole,
    ) -> Group:
        group = self.get_group(group_id)
        if not group or group.dissolved:
            raise GroupError("Group not found")
        self._assert_founder_action(group, actor)
        self._assert_not_founder_target(group, target)
        if role == "founder":
            raise ForbiddenGroupAction("Cannot assign founder role via promote")
        if role not in VALID_ROLES:
            raise GroupError(f"Invalid role: {role}")
        member = self._get_member(group, target)
        if not member:
            raise GroupError("Member not found")
        member.role = role
        self._save(group)
        self._audit("role_changed", group_id, actor, f"{target}->{role}")
        return group

    def remove_member(self, group_id: str, actor: str, target: str) -> Group:
        group = self.get_group(group_id)
        if not group or group.dissolved:
            raise GroupError("Group not found")
        self._assert_not_founder_target(group, target)
        actor_role = self._role_of(group, actor)
        if actor_role not in ("founder", "admin"):
            raise ForbiddenGroupAction("Only founder or admin can remove members")
        if target == actor and actor == group.founder_address:
            raise ForbiddenGroupAction("Founder must dissolve group to leave")
        group.members = [m for m in group.members if m.address != target]
        self._save(group)
        self._audit("member_removed", group_id, actor, target)
        return group

    def dissolve_group(self, group_id: str, actor: str, confirm: str) -> Group:
        group = self.get_group(group_id)
        if not group or group.dissolved:
            raise GroupError("Group not found")
        self._assert_founder_action(group, actor)
        if confirm != "DISSOLVE":
            raise GroupError("Confirmation must be DISSOLVE")
        group.dissolved = True
        self._save(group)
        self._audit("group_dissolved", group_id, actor)
        return group

    def is_member(self, group_id: str, address: str) -> bool:
        group = self.get_group(group_id)
        if not group or group.dissolved:
            return False
        return any(m.address == address for m in group.members)
