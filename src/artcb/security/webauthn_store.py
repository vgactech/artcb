"""Persist WebAuthn public credentials and face-unlock device hashes.
R387 (TASK-006 2026-09-19) : broadcast_credential() — fanout HTTP fire-and-forget
    vers les nœuds officiels seed_http_map() après save_credential().
    Les credentials WebAuthn sont des données PUBLIQUES (credential_id + public_key).
    La clé privée ne quitte jamais l'appareil de l'utilisateur.

Never stores raw fingerprint/face images. Files live under ARTCB_DATA_DIR.
"""

from __future__ import annotations
MODULE_VERSION = '1.0.0'  # R390 — auto-versioning

import json
import logging
import os
import threading
from pathlib import Path
from typing import Any

_lock = threading.Lock()
_log = logging.getLogger("artcb.security.webauthn_store")

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


# ──────────────────────────────────────────────────────────────────────────────
# R387 — TASK-006 : Réplication identité WebAuthn entre nœuds (fanout HTTP)
# ──────────────────────────────────────────────────────────────────────────────

# Champs publics autorisés dans le fanout (jamais de clé privée, jamais d'image)
_FANOUT_PUBLIC_FIELDS = frozenset({
    "credential_id",
    "cose_b64",       # clé publique COSE encodée — PUBLIQUE
    "sign_count",
    "wallet_name",
    "address",
    "modality",
    "rp_id",
})

# Délai réseau max pour chaque pair en fanout (secondes)
_FANOUT_TIMEOUT = 4.0

# Variable d'environnement pour désactiver le fanout (tests locaux, CI)
_FANOUT_DISABLED_ENV = "ARTCB_WEBAUTHN_FANOUT_DISABLED"


def _is_fanout_enabled() -> bool:
    """Fanout actif sauf si la variable d'env est définie à '1' ou 'true'."""
    val = os.getenv(_FANOUT_DISABLED_ENV, "").strip().lower()
    return val not in ("1", "true", "yes")


def _safe_fanout_record(record: dict[str, Any]) -> dict[str, Any]:
    """Ne renvoie que les champs publics autorisés — jamais de clé privée."""
    return {k: v for k, v in record.items() if k in _FANOUT_PUBLIC_FIELDS}


def broadcast_credential(record: dict[str, Any], *, source_node_id: str | None = None) -> dict[str, int]:
    """Fanout HTTP fire-and-forget du credential WebAuthn vers les nœuds pairs.

    R387 — TASK-006. Appelé APRÈS save_credential() local.

    Envoie uniquement les champs publics (_FANOUT_PUBLIC_FIELDS) au endpoint
    POST /api/v1/auth/webauthn/identity/receive de chaque pair officiel.

    Le fanout est:
      - Non bloquant : exécuté dans un thread daemon
      - Fail-safe : une erreur sur un pair n'empêche jamais l'enrollment local
      - Filtré : seuls les champs publics sont transmis (jamais clé privée/image)
      - Désactivable : ARTCB_WEBAUTHN_FANOUT_DISABLED=1 pour les tests/CI

    Args:
        record: Le credential complet (les champs privés sont filtrés avant envoi).
        source_node_id: node_id du nœud émetteur (pour éviter de se renvoyer à soi-même).

    Returns:
        dict {node_id: http_status_code} — résultats du fanout (vide si désactivé).
    """
    if not _is_fanout_enabled():
        _log.debug("broadcast_credential: fanout désactivé (ARTCB_WEBAUTHN_FANOUT_DISABLED)")
        return {}

    import threading
    results: dict[str, int] = {}

    def _do_fanout() -> None:
        import urllib.request
        import urllib.error

        try:
            from src.artcb.node_registry import seed_http_map, current_node_id
            peers = seed_http_map()
            my_id = source_node_id or current_node_id()
        except Exception as exc:  # noqa: BLE001
            _log.warning("broadcast_credential: impossible de résoudre les pairs — %s", exc)
            return

        payload_obj = _safe_fanout_record(record)
        if source_node_id:
            payload_obj["_source_node_id"] = source_node_id
        payload_bytes = json.dumps(payload_obj, ensure_ascii=False).encode("utf-8")

        for node_id, base_url in peers.items():
            if node_id == my_id:
                continue  # ne pas se renvoyer à soi-même
            url = f"{base_url.rstrip('/')}/api/v1/auth/webauthn/identity/receive"
            try:
                req = urllib.request.Request(
                    url,
                    data=payload_bytes,
                    headers={
                        "Content-Type": "application/json",
                        "X-ARTCB-Fanout-Source": str(my_id or "unknown"),
                    },
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=_FANOUT_TIMEOUT) as resp:
                    results[node_id] = resp.status
                    _log.info(
                        "broadcast_credential: OK node=%s wallet=%s status=%d",
                        node_id, record.get("wallet_name"), resp.status,
                    )
            except urllib.error.HTTPError as exc:
                results[node_id] = exc.code
                _log.warning(
                    "broadcast_credential: HTTP %d node=%s wallet=%s",
                    exc.code, node_id, record.get("wallet_name"),
                )
            except Exception as exc:  # noqa: BLE001
                results[node_id] = 0
                _log.warning(
                    "broadcast_credential: réseau node=%s wallet=%s — %s",
                    node_id, record.get("wallet_name"), exc,
                )

    # Fire-and-forget — ne jamais bloquer l'enrollment de l'utilisateur
    t = threading.Thread(target=_do_fanout, daemon=True, name="webauthn-fanout")
    t.start()
    return results  # retourné immédiatement (le thread tourne en arrière-plan)


def receive_credential(record: dict[str, Any]) -> bool:
    """Reçoit et stocke un credential WebAuthn venant d'un nœud pair (fanout R387).

    Appelé par POST /api/v1/auth/webauthn/identity/receive.
    Valide les champs obligatoires avant de sauvegarder.

    Returns:
        True si stocké (nouveau ou mis à jour), False si rejeté (champs manquants).
    """
    required = {"credential_id", "cose_b64", "wallet_name"}
    if not required.issubset(record.keys()):
        _log.warning(
            "receive_credential: rejeté — champs manquants %s",
            required - set(record.keys()),
        )
        return False
    # Filtrer les champs publics uniquement (sécurité défensive)
    clean = _safe_fanout_record(record)
    # Conserver le sign_count s'il est fourni
    if "sign_count" not in clean:
        clean["sign_count"] = 0
    save_credential(clean)
    _log.info(
        "receive_credential: stocké credential_id=%s wallet=%s modality=%s",
        str(record.get("credential_id") or "")[:16],
        record.get("wallet_name"),
        record.get("modality"),
    )
    return True
