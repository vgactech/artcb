"""IBM Bob HTTP client — inference via litellm-ibm-bob transport (signed requests)."""

from __future__ import annotations
MODULE_VERSION = '1.0.0'  # R390 — auto-versioning

import json
import logging
from typing import Any

from src.artcb.config import load_settings

logger = logging.getLogger("artcb.ir.bob_client")

try:
    from litellm_ibm_bob._transport import BobHTTPError, BobTransport, TransportConfig
except ImportError as exc:  # pragma: no cover - optional at install time
    BobTransport = None  # type: ignore[misc, assignment]
    TransportConfig = None  # type: ignore[misc, assignment]
    BobHTTPError = Exception  # type: ignore[misc, assignment]
    _IMPORT_ERROR = exc
else:
    _IMPORT_ERROR = None


class BobClient:
    """Real HTTP client for Bob inference API — no mock responses."""

    INFERENCE_PATH = "/inference/v1/chat/completions"

    def __init__(self) -> None:
        self.settings = load_settings()
        self._transport: BobTransport | None = None

    @property
    def available(self) -> bool:
        return bool(
            self.settings.llm_enabled
            and self.settings.bob_api_key
            and BobTransport is not None
        )

    def _transport_client(self) -> BobTransport:
        if BobTransport is None or TransportConfig is None:
            raise RuntimeError(
                "litellm-ibm-bob not installed — pip install litellm-ibm-bob"
            ) from _IMPORT_ERROR
        if self._transport is None:
            cfg = TransportConfig(
                api_key=self.settings.bob_api_key or "",
                base_url=self.settings.bob_api_base,
                team_id=self.settings.bob_team_id,
                instance_id=self.settings.bob_instance_id,
            )
            self._transport = BobTransport(cfg)
        return self._transport

    def chat_completion(self, messages: list[dict[str, str]], *, temperature: float = 0.1) -> str:
        if not self.settings.bob_api_key:
            raise RuntimeError("BOB_API_KEY missing — cannot call Bob inference.")

        payload = {
            "model": self.settings.bob_model,
            "messages": messages,
            "temperature": temperature,
        }
        transport = self._transport_client()
        logger.debug("Bob inference POST %s", self.INFERENCE_PATH)
        response = transport.request("POST", self.INFERENCE_PATH, body=payload)
        if not response.is_success:
            raise BobHTTPError(
                f"Bob inference failed status={response.status_code} body={response.text[:500]}",
                response=response,
            )
        data = response.json()
        return self._extract_content(data)

    @staticmethod
    def _extract_content(data: dict[str, Any]) -> str:
        choices = data.get("choices") or []
        if not choices:
            raise RuntimeError(f"Bob response missing choices: {json.dumps(data)[:300]}")
        message = choices[0].get("message") or {}
        content = message.get("content")
        if not content:
            raise RuntimeError("Bob response missing message content")
        return str(content).strip()

    def classify_sentences(self, sentences: list[str]) -> list[dict[str, str]] | None:
        """Ask Bob to classify sentences — returns None on failure (caller falls back to rules)."""
        if not self.available:
            logger.debug("Bob client unavailable — skip LLM enrichment")
            return None

        numbered = "\n".join(f"{i}: {s}" for i, s in enumerate(sentences))
        prompt = (
            "Classify each sentence for an IR knowledge graph. "
            "Return ONLY a JSON array of objects with keys: index (int), type (one of "
            "FACT, DECISION, HYPOTHESIS, REASON, GOAL, PROOF, EVENT, CONTEXT), "
            f"symbol (short USP code like O1M1).\n\nSentences:\n{numbered}"
        )
        try:
            raw = self.chat_completion([{"role": "user", "content": prompt}])
            start = raw.find("[")
            end = raw.rfind("]") + 1
            if start < 0 or end <= start:
                logger.warning("Bob response not JSON array: %s", raw[:200])
                return None
            parsed = json.loads(raw[start:end])
            if not isinstance(parsed, list):
                return None
            return [
                {
                    "index": str(item.get("index", "")),
                    "type": str(item.get("type", "FACT")),
                    "symbol": str(item.get("symbol", "")),
                }
                for item in parsed
            ]
        except Exception as exc:
            logger.error("Bob classify_sentences failed: %s", exc)
            return None

    def close(self) -> None:
        if self._transport is not None:
            self._transport.close()
            self._transport = None
