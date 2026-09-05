"""Domain layers and the replication matrix (rapport 217).

Four different things share the word « Genesis » — they must not be stored
the same way:

    1. GLOBAL GENESIS   — protocol constitution, every consensus node
    2. ORG GENESIS      — organisation constitution, local domain + public hash
    3. GROUP GENESIS    — group constitution, local domain + public hash
    4. USER / RESOURCE  — private state, never a blockchain genesis

P2P already replicates ``visibility=public`` blocks only. Private org/group
JSON and policy files stay on the node that created them. The global chain
may carry a *commitment* (kind + id + content_hash) so the network can prove
« this constitution existed » without receiving members or documents.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Literal

DomainKind = Literal["global", "org", "group", "user", "resource", "domain"]
ReplicationClass = Literal[
    "all_consensus_nodes",
    "org_domain_nodes",
    "group_domain_nodes",
    "owner_only",
    "never_p2p",
]

# What a public node is allowed to know. Absence from this table = not public.
REPLICATION_MATRIX: dict[str, dict[str, str]] = {
    "GLOBAL_GENESIS": {
        "layer": "global",
        "replication": "all_consensus_nodes",
        "content": "full_protocol_rules",
        "cest_a_dire": "Tous les nœuds de consensus ont la même constitution ARTCB.",
    },
    "ORG_GENESIS_HASH": {
        "layer": "global",
        "replication": "all_consensus_nodes",
        "content": "kind+id+content_hash",
        "cest_a_dire": "Le réseau sait qu'ORG A existe et connaît le hash de sa constitution, pas ses documents.",
    },
    "ORG_GENESIS_BODY": {
        "layer": "org",
        "replication": "org_domain_nodes",
        "content": "constitution_without_documents",
        "cest_a_dire": "Qui gouverne ORG A, quelles actions existent — pas Document X.",
    },
    "GROUP_GENESIS_HASH": {
        "layer": "global",
        "replication": "all_consensus_nodes",
        "content": "kind+id+parent+content_hash",
        "cest_a_dire": "Le réseau sait que GROUP C existe et de quelle ORG il dépend.",
    },
    "GROUP_MEMBERS": {
        "layer": "group",
        "replication": "group_domain_nodes",
        "content": "membership_list",
        "cest_a_dire": "Les adresses des membres restent dans le domaine du groupe, pas dans le P2P public.",
    },
    "POLICY_TX": {
        "layer": "org",
        "replication": "org_domain_nodes",
        "content": "grant_revoke_delegate",
        "cest_a_dire": "A3→READ→doc-x est une transaction de politique, pas le Genesis.",
    },
    "PRIVATE_RESOURCE": {
        "layer": "resource",
        "replication": "never_p2p",
        "content": "ciphertext_or_local_file",
        "cest_a_dire": "Le texte de Document X n'est jamais un bloc public. P2P refuse visibility≠public.",
    },
    "USER_DOMAIN": {
        "layer": "user",
        "replication": "owner_only",
        "content": "identity_keys_mandates_resources",
        "cest_a_dire": "Un utilisateur n'a pas un Genesis blockchain par document.",
    },
    "DOMAIN_MANIFEST": {
        "layer": "global",
        "replication": "all_consensus_nodes",
        "content": "id+founder+genesis_hash+authorized_nodes",
        "cest_a_dire": "Le réseau peut connaître l'identité du domaine et qui l'héberge, pas le corps Genesis.",
    },
    "DOMAIN_BODY": {
        "layer": "org",
        "replication": "org_domain_nodes",
        "content": "genesis_body_on_authorized_hosts",
        "cest_a_dire": "Un nœud héberge le domaine. Il ne le possède pas. La copie n'est pas automatique sur les 4 nœuds officiels.",
    },
    "DOMAIN_COMMITMENT_BLOCK": {
        "layer": "global",
        "replication": "all_consensus_nodes",
        "content": "public_block_kind+id+hash_only",
        "cest_a_dire": "Le hash du domaine est un bloc public visibility=public, reward=0. Jamais le corps, les membres ou un document.",
    },
    "ORG_AUTHORITY": {
        "layer": "org",
        "replication": "org_domain_nodes",
        "content": "legal_owner+controller_not_genesis",
        "cest_a_dire": "Le Genesis reste immuable. LEGAL_OWNER et AUTHORIZED_CONTROLLER évoluent par transfert signé.",
    },
    "ORG_CONTROL_TRANSFER": {
        "layer": "global",
        "replication": "all_consensus_nodes",
        "content": "tx+subject+reason+old_new_controller_no_body",
        "cest_a_dire": "Le réseau peut auditer qui a cédé le contrôle. Jamais le Genesis, les membres ou un document.",
    },
}

P2P_SYNCS_PRIVATE_BLOCKS = False


def canonical_hash(payload: dict[str, Any]) -> str:
    """SHA-256 of a stable JSON encoding — the only thing the global chain needs."""
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def public_commitment(
    *,
    kind: DomainKind,
    domain_id: str,
    content_hash: str,
    parent_id: str | None,
    issuer: str,
    issued_at: str,
) -> dict[str, Any]:
    """Payload safe to show every consensus node. No members, no documents."""
    return {
        "layer": "GLOBAL_CONSENSUS",
        "kind": kind,
        "domain_id": domain_id,
        "content_hash": content_hash,
        "parent_id": parent_id,
        "issuer": issuer,
        "issued_at": issued_at,
        "contains_private_data": False,
    }
