"""Pool E2E — ML-KEM chiffrement morceaux apprentissage/raisonnement."""

from __future__ import annotations
MODULE_VERSION = '1.0.0'  # R390 — auto-versioning

import json
from typing import Any

from src.artcb.crypto.kem import (
    POOL_CHUNK_CONTEXT,
    POOL_RESULT_CONTEXT,
    decrypt_payload,
    encrypt_payload,
)


def encrypt_chunk_payload(text: str, worker_kem_public_hex: str) -> dict[str, str]:
    """Chiffre un morceau de texte pour UN worker (jamais en clair sur le réseau)."""
    pk = bytes.fromhex(worker_kem_public_hex)
    body = json.dumps({"text": text, "v": 1}, ensure_ascii=False).encode("utf-8")
    return encrypt_payload(body, pk, context=POOL_CHUNK_CONTEXT)


def decrypt_chunk_payload(envelope: dict[str, str], worker_kem_secret_hex: str) -> str:
    sk = bytes.fromhex(worker_kem_secret_hex)
    data = json.loads(decrypt_payload(envelope, sk, context=POOL_CHUNK_CONTEXT).decode("utf-8"))
    return str(data["text"])


def encrypt_result_payload(result: dict[str, Any], owner_kem_public_hex: str) -> dict[str, str]:
    pk = bytes.fromhex(owner_kem_public_hex)
    body = json.dumps(result, ensure_ascii=False).encode("utf-8")
    return encrypt_payload(body, pk, context=POOL_RESULT_CONTEXT)


def decrypt_result_payload(envelope: dict[str, str], owner_kem_secret_hex: str) -> dict[str, Any]:
    sk = bytes.fromhex(owner_kem_secret_hex)
    return json.loads(decrypt_payload(envelope, sk, context=POOL_RESULT_CONTEXT).decode("utf-8"))
