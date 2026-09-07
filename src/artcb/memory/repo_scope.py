"""Classify repo paths into ARTCB visibilities. Secrets are catalogued, never inlined."""

from __future__ import annotations

from pathlib import Path

Visibility = str  # public | organization | group | private

_SECRET_NAMES = {
    ".env",
    "cursor_agent.env",
    ".env.local",
    "id_rsa",
    "id_ed25519",
    "artcb_ovh_deploy",
}
_SECRET_SUFFIXES = {".pem", ".key", ".p12", ".pfx"}
_SECRET_PARTS = (
    "secret",
    "credential",
    "doppler",
    "private_key",
    "wallet_password",
)
_BINARY_SUFFIXES = {
    ".pdf",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".woff",
    ".woff2",
    ".ttf",
    ".wasm",
    ".pqc",
    ".bin",
    ".so",
    ".dylib",
    ".zip",
    ".gz",
    ".whl",
}

_ORG_PREFIXES = (
    "deploy/",
    ".github/",
    "docs/FOLLOW_MAIN.md",
    "docs/PROTOCOL_SOURCE_OF_TRUTH.md",
)
_ORG_NAMES = {
    "scripts/artcb_follow_main.sh",
    "scripts/provision_doppler_node_projects.py",
    "src/artcb/node_registry.py",
    "src/artcb/live.py",
}
_GROUP_PREFIXES = (
    ".cursor/",
    ".agents/",
    ".bob/",
)
_GROUP_NAMES = {
    "AUTO_PROMPT_ARTCB",
    "LECONS_APPRISES_ARTCB",
    "QUESTIONS_OUVERTES_ARTCB",
    "CHECKLIST_PRE_DEV_ARTCB",
}
_PRIVATE_PREFIXES = (
    "logs/",
    "data_local/",
    "data/",
    ".idea/",
    ".vscode/",
    ".devcontainer/",
)


def is_secret_path(rel: str) -> bool:
    name = Path(rel).name.lower()
    if name in _SECRET_NAMES or name.startswith(".env"):
        return True
    if Path(rel).suffix.lower() in _SECRET_SUFFIXES:
        return True
    low = rel.lower()
    return any(part in low for part in _SECRET_PARTS)


def is_binary_path(rel: str) -> bool:
    return Path(rel).suffix.lower() in _BINARY_SUFFIXES


def classify_path(rel: str) -> Visibility:
    """Logical scope. Chain visibility is public|private|group; org maps to private body + public hash."""
    if is_secret_path(rel):
        return "private"
    if rel.startswith(_PRIVATE_PREFIXES) or rel.startswith("logs/") or rel.startswith("data/"):
        return "private"
    if rel in _GROUP_NAMES or rel.startswith(_GROUP_PREFIXES):
        return "group"
    if rel in _ORG_NAMES or rel.startswith(_ORG_PREFIXES):
        return "organization"
    return "public"


def chain_visibility(scope: Visibility) -> str:
    """What `append_block(visibility=)` accepts. Org/group bodies stay off public P2P."""
    if scope == "public":
        return "public"
    return "private"


def looks_like_secret_line(line: str) -> bool:
    s = line.strip()
    if s.startswith("artcb_") and len(s) > 20:
        return True
    if "BEGIN " in s and "PRIVATE" in s:
        return True
    if "AKIA" in s and len(s) > 16:
        return True
    low = s.lower()
    if any(k in low for k in ("api_key=", "password=", "doppler_token=", "bearer ")):
        return True
    return False


def redact_text(text: str) -> tuple[str, int]:
    """Replace secret-looking lines. Returns (text, n_redacted)."""
    out: list[str] = []
    n = 0
    for line in text.splitlines(keepends=True):
        if looks_like_secret_line(line.rstrip("\n")):
            out.append("[REDACTED_SECRET_LINE]\n")
            n += 1
        else:
            out.append(line)
    return "".join(out), n
