"""Gestion des connecteurs — clés API stockées localement chiffrées AES-256-GCM."""

from __future__ import annotations
MODULE_VERSION = '1.0.0'  # R390 — auto-versioning

import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from src.artcb.wallet.encryption import decrypt_secret_blob, encrypt_secret_blob

logger = logging.getLogger("artcb.connectors.manager")

ConnectorProvider = Literal[
    "openai",
    "anthropic",
    "bob",
    "openrouter",
    "ollama",
    "cursor",
    "watsonx",
    "google_ai",
    "manus",
    "supabase",
    "postgres",
    "mysql",
    "sqlite",
    "local_folder",
    "pdf_file",
    "github",
    "wikipedia",
    "custom_webhook",
]

LLM_PROVIDERS: frozenset[str] = frozenset({"openai", "anthropic", "bob", "openrouter", "ollama", "cursor", "watsonx", "google_ai", "manus"})
DATA_SOURCE_PROVIDERS: frozenset[str] = frozenset({
    "supabase", "postgres", "mysql", "sqlite", "local_folder", "pdf_file", "github", "wikipedia",
})
# local_folder / pdf_file / sqlite : api_key = placeholder local (min 8 chars)
LOCAL_SOURCE_PROVIDERS: frozenset[str] = frozenset({"local_folder", "pdf_file", "sqlite", "wikipedia"})


class ConnectorError(Exception):
    """Connector operation failed."""


@dataclass
class ConnectorRecord:
    connector_id: str
    provider: ConnectorProvider
    label: str
    config: dict[str, Any]
    created_at: str
    updated_at: str
    enabled: bool = True
    last_test_ok: bool | None = None
    last_test_message: str | None = None
    _api_key: str | None = field(default=None, repr=False)

    def public_dict(self) -> dict[str, Any]:
        """Export sans secrets — pour API et UI."""
        masked = None
        if self._api_key:
            k = self._api_key
            masked = f"{k[:4]}…{k[-4:]}" if len(k) > 8 else "****"
        return {
            "connector_id": self.connector_id,
            "provider": self.provider,
            "label": self.label,
            "config": {k: v for k, v in self.config.items() if k != "api_key"},
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "enabled": self.enabled,
            "last_test_ok": self.last_test_ok,
            "last_test_message": self.last_test_message,
            "api_key_masked": masked,
            "kind": "llm" if self.provider in LLM_PROVIDERS else "data_source",
        }


class ConnectorManager:
    """
    Stocke les clés API des plateformes externes sur le disque local de l'utilisateur.
    Jamais envoyées vers Supabase ARTCB ni cloud ARTCB — uniquement data/connectors/.
    """

    def __init__(self, data_dir: Path) -> None:
        self.store_path = Path(data_dir) / "connectors" / "connectors.json"
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.store_path.is_file():
            self._write_raw({"connectors": []})

    def _read_raw(self) -> dict:
        return json.loads(self.store_path.read_text(encoding="utf-8"))

    def _write_raw(self, data: dict) -> None:
        self.store_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        self.store_path.chmod(0o600)

    def _now(self) -> str:
        return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    def list_connectors(self, *, kind: str | None = None) -> list[ConnectorRecord]:
        records = [self._load_record(item) for item in self._read_raw().get("connectors", [])]
        if kind == "llm":
            return [r for r in records if r.provider in LLM_PROVIDERS]
        if kind == "data_source":
            return [r for r in records if r.provider in DATA_SOURCE_PROVIDERS]
        return records

    def get_connector(self, connector_id: str) -> ConnectorRecord | None:
        for record in self.list_connectors():
            if record.connector_id == connector_id:
                return record
        return None

    def _load_record(self, item: dict) -> ConnectorRecord:
        api_key = None
        if item.get("secret_encrypted"):
            try:
                api_key = decrypt_secret_blob(bytes.fromhex(item["secret_encrypted"])).decode("utf-8")
            except Exception as exc:
                logger.warning("Failed to decrypt connector %s: %s", item.get("connector_id"), exc)
        return ConnectorRecord(
            connector_id=item["connector_id"],
            provider=item["provider"],
            label=item["label"],
            config=item.get("config", {}),
            created_at=item["created_at"],
            updated_at=item.get("updated_at", item["created_at"]),
            enabled=item.get("enabled", True),
            last_test_ok=item.get("last_test_ok"),
            last_test_message=item.get("last_test_message"),
            _api_key=api_key,
        )

    def save_connector(
        self,
        *,
        provider: ConnectorProvider,
        label: str,
        api_key: str,
        config: dict[str, Any] | None = None,
        connector_id: str | None = None,
    ) -> ConnectorRecord:
        if not api_key or (len(api_key.strip()) < 8 and provider != "github"):
                raise ConnectorError("api_key requise (min 8 caractères)")
        if provider == "github" and not api_key.strip():
                api_key = "github-public"  # placeholder pour dépôts publics
        if provider not in LLM_PROVIDERS | DATA_SOURCE_PROVIDERS:
            raise ConnectorError(f"Provider inconnu: {provider}")
        if provider in LOCAL_SOURCE_PROVIDERS and api_key.strip().startswith("local-"):
            pass  # placeholder autorisé pour sources locales

        now = self._now()
        raw = self._read_raw()
        items = raw.get("connectors", [])
        cid = connector_id or f"conn_{uuid.uuid4().hex[:12]}"
        secret_hex = encrypt_secret_blob(api_key.strip().encode("utf-8")).hex()
        public_config = dict(config or {})

        updated = False
        for item in items:
            if item["connector_id"] == cid:
                item["provider"] = provider
                item["label"] = label
                item["config"] = public_config
                item["secret_encrypted"] = secret_hex
                item["updated_at"] = now
                item["enabled"] = True
                updated = True
                break

        if not updated:
            items.append({
                "connector_id": cid,
                "provider": provider,
                "label": label,
                "config": public_config,
                "secret_encrypted": secret_hex,
                "created_at": now,
                "updated_at": now,
                "enabled": True,
            })

        raw["connectors"] = items
        self._write_raw(raw)
        logger.info("Saved connector id=%s provider=%s", cid, provider)
        return self.get_connector(cid)  # type: ignore[return-value]

    def delete_connector(self, connector_id: str) -> bool:
        raw = self._read_raw()
        before = len(raw.get("connectors", []))
        raw["connectors"] = [c for c in raw.get("connectors", []) if c["connector_id"] != connector_id]
        if len(raw["connectors"]) == before:
            return False
        self._write_raw(raw)
        return True

    def set_test_result(self, connector_id: str, ok: bool, message: str) -> None:
        raw = self._read_raw()
        for item in raw.get("connectors", []):
            if item["connector_id"] == connector_id:
                item["last_test_ok"] = ok
                item["last_test_message"] = message
                item["updated_at"] = self._now()
                break
        self._write_raw(raw)

    def get_active_llm_key(self, provider: str) -> tuple[ConnectorRecord, str] | None:
        for record in self.list_connectors(kind="llm"):
            if record.enabled and record.provider == provider and record._api_key:
                return record, record._api_key
        return None
