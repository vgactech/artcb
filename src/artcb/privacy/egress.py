"""Egress policy — deterministic pass before bytes leave a node (rapport 211, Phase 2-3).

Complement to the homomorphic layer, not a replacement: HE protects PoL vectors
in aggregation; this module stops credentials from leaving through outbound
HTTP a node makes on behalf of an agent (webhooks, LLM connectors).

Design ported in spirit from snoels/privacy.md (MIT):
  * deterministic, runs in microseconds, no model, no network;
  * redact by default (strip the field, let the call succeed), block only for
    private-key material;
  * a redaction that empties the payload escalates to block;
  * the ledger records counts and kinds, never values.

What it does NOT do: it does not decide whether a 64-hex string is a wallet seed
or a block hash. Those share a shape. Seeds are only redacted when the *field
name* says so (seed, secret, private, password, token...). This is documented,
not hidden.
"""

from __future__ import annotations

import ipaddress
import logging
import os
import re
import socket
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

from src.artcb.p2p.public_url import allow_local_peers

logger = logging.getLogger("artcb.privacy.egress")

REDACTED = "[redacted by ARTCB egress policy]"

OUTCOME_ALLOW = "allow"
OUTCOME_REDACT = "redact"
OUTCOME_BLOCK = "block"

TYPE_CREDENTIALS = "credentials"
TYPE_PRIVATE_KEY = "private_key"
TYPE_CONTACT = "contact"

# Field names that carry a secret whatever the value looks like.
SECRET_FIELD_RE = re.compile(
    r"^(api[_-]?key|apikey|secret|device[_-]?secret|token|session[_-]?token|password|passwd|pwd|"
    r"auth|authorization|bearer|private[_-]?key|ssh[_-]?key|client[_-]?secret|access[_-]?token|"
    r"refresh[_-]?token|credentials?|seed|seed[_-]?hex|mnemonic|signing[_-]?key|vault|pem|"
    r"doppler[_-]?token|stripe[_-]?key)$",
    re.IGNORECASE,
)

# Value patterns. Ordered: private key material first, then well-known token shapes.
VALUE_PATTERNS: tuple[tuple[str, re.Pattern[str], str], ...] = (
    (TYPE_PRIVATE_KEY, re.compile(r"-----BEGIN (?:RSA |OPENSSH |EC |DSA |PGP |ENCRYPTED )?PRIVATE KEY-----"), "pem"),
    (TYPE_CREDENTIALS, re.compile(r"\bsk-ant-[A-Za-z0-9_-]{16,}"), "anthropic_key"),
    (TYPE_CREDENTIALS, re.compile(r"\bsk-[A-Za-z0-9_-]{20,}"), "openai_key"),
    (TYPE_CREDENTIALS, re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{20,}"), "github_token"),
    (TYPE_CREDENTIALS, re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}"), "github_pat"),
    (TYPE_CREDENTIALS, re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}"), "slack_token"),
    (TYPE_CREDENTIALS, re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "aws_access_key"),
    (TYPE_CREDENTIALS, re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b"), "google_api_key"),
    (TYPE_CREDENTIALS, re.compile(r"\bdp\.(?:pt|st|ct|sa)\.[A-Za-z0-9_-]{20,}"), "doppler_token"),
    (TYPE_CREDENTIALS, re.compile(r"\bartcb_[A-Za-z0-9]{24,}\b"), "artcb_api_key"),
    (TYPE_CREDENTIALS, re.compile(r"\bsess_[0-9a-f]{64}\b"), "artcb_session_token"),
    (TYPE_CREDENTIALS, re.compile(r"\b(?:sk|rk)_(?:live|test)_[A-Za-z0-9]{16,}"), "stripe_key"),
    (TYPE_CREDENTIALS, re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{20,}"), "bearer_header"),
    (TYPE_CONTACT, re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"), "email"),
)

# Only credentials are enforced by default. Contact detection is reported
# (ledger) but not stripped: an operator email in a memo is not a leak of a key.
ENFORCED_TYPES = frozenset({TYPE_CREDENTIALS, TYPE_PRIVATE_KEY})


@dataclass(frozen=True)
class Finding:
    path: tuple[str, ...]
    type: str
    label: str


@dataclass
class Decision:
    outcome: str
    payload: Any
    findings: list[Finding] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)

    @property
    def counts(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for f in self.findings:
            out[f.type] = out.get(f.type, 0) + 1
        return out


def _scan_text(text: str, path: tuple[str, ...]) -> list[Finding]:
    found: list[Finding] = []
    for ftype, pattern, label in VALUE_PATTERNS:
        if pattern.search(text):
            found.append(Finding(path=path, type=ftype, label=label))
    return found


def detect(payload: Any, _path: tuple[str, ...] = ()) -> list[Finding]:
    """Find secrets in a JSON-like payload. Returns one finding per (path, pattern)."""
    findings: list[Finding] = []
    if isinstance(payload, dict):
        for key, value in payload.items():
            here = (*_path, str(key))
            if SECRET_FIELD_RE.match(str(key)) and value not in (None, "", [], {}):
                findings.append(Finding(path=here, type=TYPE_CREDENTIALS, label="field_name"))
                continue
            findings.extend(detect(value, here))
    elif isinstance(payload, list):
        for index, value in enumerate(payload):
            findings.extend(detect(value, (*_path, str(index))))
    elif isinstance(payload, str):
        findings.extend(_scan_text(payload, _path))
    return findings


def _delete_in(obj: Any, path: tuple[str, ...]) -> Any:
    if not path:
        return obj
    head, *rest = path
    if isinstance(obj, dict):
        clone = dict(obj)
        if not rest:
            clone.pop(head, None)
        elif head in clone:
            clone[head] = _delete_in(clone[head], tuple(rest))
        return clone
    if isinstance(obj, list):
        clone = list(obj)
        idx = int(head)
        if idx < len(clone):
            if not rest:
                clone.pop(idx)
            else:
                clone[idx] = _delete_in(clone[idx], tuple(rest))
        return clone
    return obj


def redact_text(text: str) -> tuple[str, list[Finding]]:
    """Strip enforced patterns inside free text (prompts). Contact is left intact."""
    findings = _scan_text(text, ())
    out = text
    for ftype, pattern, _label in VALUE_PATTERNS:
        if ftype in ENFORCED_TYPES:
            out = pattern.sub(REDACTED, out)
    return out, findings


def check_payload(payload: Any) -> Decision:
    """Redact enforced findings from a JSON payload.

    * private key material anywhere -> block
    * credential in a named field   -> field removed
    * credential inside a string    -> substring replaced
    * nothing left after redaction  -> block (a broken call is not a policy win)
    """
    findings = detect(payload)
    if any(f.type == TYPE_PRIVATE_KEY for f in findings):
        return Decision(outcome=OUTCOME_BLOCK, payload=None, findings=findings)

    enforced = [f for f in findings if f.type in ENFORCED_TYPES]
    if not enforced:
        return Decision(outcome=OUTCOME_ALLOW, payload=payload, findings=findings)

    new_payload = payload
    removed: list[str] = []
    for f in sorted(enforced, key=lambda x: len(x.path), reverse=True):
        if f.label == "field_name":
            new_payload = _delete_in(new_payload, f.path)
            removed.append(".".join(f.path))
        else:
            new_payload = _rewrite_string_at(new_payload, f.path)
            removed.append(".".join(f.path) + "#inline")

    if new_payload in (None, {}, [], ""):
        return Decision(outcome=OUTCOME_BLOCK, payload=None, findings=findings, removed=removed)
    return Decision(outcome=OUTCOME_REDACT, payload=new_payload, findings=findings, removed=removed)


def _rewrite_string_at(obj: Any, path: tuple[str, ...]) -> Any:
    if not path:
        return redact_text(obj)[0] if isinstance(obj, str) else obj
    head, *rest = path
    if isinstance(obj, dict):
        clone = dict(obj)
        if head in clone:
            clone[head] = _rewrite_string_at(clone[head], tuple(rest))
        return clone
    if isinstance(obj, list):
        clone = list(obj)
        idx = int(head)
        if idx < len(clone):
            clone[idx] = _rewrite_string_at(clone[idx], tuple(rest))
        return clone
    return obj


def record(decision: Decision, *, recipient: str, channel: str) -> None:
    """Ledger line: counts and kinds only. Never the value, never the excerpt."""
    logger.info(
        "egress channel=%s recipient=%s outcome=%s findings=%s removed=%d",
        channel,
        recipient,
        decision.outcome,
        decision.counts or "{}",
        len(decision.removed),
    )


# --------------------------------------------------------------------------- #
#  Webhook destination allowlist (SSRF) — the P2P announce already has one,
#  outbound webhooks did not (rapport 210 / 211 §4.C-D).
# --------------------------------------------------------------------------- #

def webhook_hosts_allowlist() -> frozenset[str]:
    raw = os.getenv("ARTCB_WEBHOOK_HOSTS", "")
    return frozenset(x.strip().lower().rstrip(".") for x in raw.split(",") if x.strip())


def _resolve(host: str) -> list[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError:
        return []
    addrs = []
    for info in infos:
        try:
            addrs.append(ipaddress.ip_address(info[4][0].split("%")[0]))
        except ValueError:
            continue
    return addrs


def webhook_url_ok(url: str, *, resolve: bool = True) -> tuple[bool, str]:
    """Outbound webhook target policy.

    Refuses loopback / RFC1918 / link-local (cloud metadata) / reserved unless
    ARTCB_ALLOW_LOCAL_PEERS=1 (tests). If ARTCB_WEBHOOK_HOSTS is set, the host
    must be listed. DNS names are resolved so a public name pointing at a
    private address is still refused.
    """
    parsed = urlparse((url or "").strip())
    if parsed.scheme not in {"http", "https"}:
        return False, "scheme_forbidden"
    host = (parsed.hostname or "").lower().rstrip(".")
    if not host:
        return False, "host_missing"
    if parsed.username or parsed.password:
        return False, "userinfo_forbidden"

    allowlist = webhook_hosts_allowlist()
    if allowlist and host not in allowlist:
        return False, "host_not_in_ARTCB_WEBHOOK_HOSTS"

    if host in {"localhost", "0.0.0.0"}:
        return (True, "local_test") if allow_local_peers() else (False, "loopback_forbidden")

    try:
        candidates = [ipaddress.ip_address(host)]
    except ValueError:
        candidates = _resolve(host) if resolve else []
        if resolve and not candidates:
            return False, "dns_unresolved"

    for addr in candidates:
        if addr.is_link_local or addr.is_multicast or addr.is_reserved or addr.is_unspecified:
            return False, "link_local_or_reserved_forbidden"
        if addr.is_loopback or addr.is_private:
            if allow_local_peers():
                continue
            return False, "private_or_loopback_forbidden"
    return True, "public_host"


__all__ = [
    "REDACTED",
    "OUTCOME_ALLOW",
    "OUTCOME_REDACT",
    "OUTCOME_BLOCK",
    "Finding",
    "Decision",
    "detect",
    "redact_text",
    "check_payload",
    "record",
    "webhook_url_ok",
    "webhook_hosts_allowlist",
]
