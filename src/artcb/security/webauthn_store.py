"""Persist WebAuthn public credentials and face-unlock device hashes.

Never stores raw fingerprint/face images. Files live under ARTCB_DATA_DIR.
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any

_lock = threading.Lock()

MODALITY_FINGERPRINT = "fingerprint"
MODALITY_FACE = "face"
MODALITY_BOTH = "both"
ALLOWED_MODALITIES = frozenset({MODALITY_FINGERPRINT, MODALITY_FACE, MODALITY_BOTH})


def _data_dir() -> Path:
    return Path(os.getenv("ARTCB_DATA_DIR", "./data")).resolve()


def store_path() -> Path:
    path = _data_dir() / "webauthn" / "credentials.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def face_path() -> Path:
    path = _data_dir() / "webauthn" / "face_unlock.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _load(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"credentials": [], "face": []}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"credentials": [], "face": []}
    if not isinstance(raw, dict):
        return {"credentials": [], "face": []}
    return raw


def _save(path: Path, payload: dict[str, Any]) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(path)
    path.chmod(0o600)


def load_credentials() -> list[dict[str, Any]]:
    with _lock:
        data = _load(store_path())
    creds = data.get("credentials") or []
    return [c for c in creds if isinstance(c, dict)]


def save_credential(record: dict[str, Any]) -> None:
    path = store_path()
    with _lock:
        data = _load(path)
        creds = [c for c in (data.get("credentials") or []) if isinstance(c, dict)]
        creds = [c for c in creds if c.get("credential_id") != record.get("credential_id")]
        creds.append(record)
        data["credentials"] = creds
        _save(path, data)


def find_credential(credential_id: str) -> dict[str, Any] | None:
    for rec in load_credentials():
        if rec.get("credential_id") == credential_id:
            return rec
    return None


def credentials_for_wallet(wallet_name: str) -> list[dict[str, Any]]:
    return [c for c in load_credentials() if c.get("wallet_name") == wallet_name]


def update_sign_count(credential_id: str, sign_count: int) -> None:
    path = store_path()
    with _lock:
        data = _load(path)
        creds = [c for c in (data.get("credentials") or []) if isinstance(c, dict)]
        for rec in creds:
            if rec.get("credential_id") == credential_id:
                rec["sign_count"] = sign_count
        data["credentials"] = creds
        _save(path, data)


def load_face() -> list[dict[str, Any]]:
    with _lock:
        data = _load(face_path())
    rows = data.get("face") or data.get("credentials") or []
    return [c for c in rows if isinstance(c, dict)]


def save_face(record: dict[str, Any]) -> None:
    path = face_path()
    with _lock:
        data = _load(path)
        rows = [c for c in (data.get("face") or []) if isinstance(c, dict)]
        rows = [c for c in rows if c.get("wallet_name") != record.get("wallet_name")]
        rows.append(record)
        data["face"] = rows
        if "credentials" in data and data.get("credentials") == []:
            data.pop("credentials", None)
        _save(path, data)


def find_face(wallet_name: str) -> dict[str, Any] | None:
    for rec in load_face():
        if rec.get("wallet_name") == wallet_name:
            return rec
    return None
