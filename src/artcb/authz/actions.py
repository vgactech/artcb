"""Actions the authorization engine understands.

Classification (`visibility=private`) is not an action. An action is what a
principal asks to do to a resource. Least privilege means granting the
narrowest action on the narrowest resource.
"""

from __future__ import annotations

READ = "READ"
WRITE = "WRITE"
CREATE = "CREATE"
UPDATE = "UPDATE"
DELETE = "DELETE"
SHARE = "SHARE"
EXPORT = "EXPORT"
GRANT = "GRANT"
REVOKE = "REVOKE"
ADMIN = "ADMIN"
AUDIT = "AUDIT"

ALL_ACTIONS: tuple[str, ...] = (
    READ,
    WRITE,
    CREATE,
    UPDATE,
    DELETE,
    SHARE,
    EXPORT,
    GRANT,
    REVOKE,
    ADMIN,
    AUDIT,
)

WRITE_LIKE = frozenset({WRITE, CREATE, UPDATE, DELETE, SHARE, EXPORT})
ADMIN_LIKE = frozenset({GRANT, REVOKE, ADMIN, AUDIT})
MEMBER_READ_ROLES = frozenset({"founder", "admin", "contributor", "viewer"})
MEMBER_WRITE_ROLES = frozenset({"founder", "admin", "contributor"})
MEMBER_ADMIN_ROLES = frozenset({"founder", "admin"})
