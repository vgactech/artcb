"""Clients LLM utilisateur — OpenAI, Anthropic, Bob via clés connecteur."""

from __future__ import annotations

import json
import logging

import httpx

from src.artcb.connectors.manager import ConnectorRecord
from src.artcb.privacy import egress

logger = logging.getLogger("artcb.connectors.llm_router")


class LLMRouter:
    """Route les requêtes LLM vers le fournisseur choisi par l'utilisateur."""

    def classify_sentences(
        self,
        sentences: list[str],
        *,
        record: ConnectorRecord,
        api_key: str,
    ) -> list[dict[str, str]] | None:
        numbered = "\n".join(f"{i}: {s}" for i, s in enumerate(sentences))
        # Egress policy (rapport 211 Phase 3): credentials never leave the node
        # inside a prompt. The provider only sees the redacted text.
        numbered, findings = egress.redact_text(numbered)
        if findings:
            logger.info(
                "egress channel=llm_prompt recipient=%s findings=%s",
                record.provider,
                sorted({f.label for f in findings}),
            )
        prompt = (
            "Classify each sentence for an IR knowledge graph. "
            "Return ONLY a JSON array of objects with keys: index (int), type (one of "
            "FACT, DECISION, HYPOTHESIS, REASON, GOAL, PROOF, EVENT, CONTEXT), "
            f"symbol (short USP code like O1M1).\n\nSentences:\n{numbered}"
        )
        model = record.config.get("model")
        try:
            if record.provider == "openai":
                raw = self._openai_chat(api_key, prompt, model=model or "gpt-4o-mini")
            elif record.provider == "anthropic":
                raw = self._anthropic_chat(api_key, prompt, model=model or "claude-3-5-haiku-20241022")
            elif record.provider == "bob":
                raw = self._bob_chat(api_key, prompt, record, model=model)
            elif record.provider == "openrouter":
                raw = self._openrouter_chat(api_key, prompt, record, model=model)
            elif record.provider == "cursor":
                raw = self._cursor_chat(api_key, prompt, record, model=model)
            elif record.provider == "ollama":
                raw = self._ollama_chat(api_key, prompt, record, model=model)
            elif record.provider == "watsonx":
                raw = self._watsonx_chat(api_key, prompt, record, model=model)
            elif record.provider == "google_ai":
                raw = self._google_ai_chat(api_key, prompt, record, model=model)
            elif record.provider == "manus":
                raw = self._manus_chat(api_key, prompt, record, model=model)
            else:
                logger.warning("Unsupported LLM provider: %s", record.provider)
                return None
            return self._parse_classification(raw)
        except Exception as exc:
            logger.error("LLM classify via %s failed: %s", record.provider, exc)
            return None

    def _parse_classification(self, raw: str) -> list[dict[str, str]] | None:
        start = raw.find("[")
        end = raw.rfind("]") + 1
        if start < 0 or end <= start:
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

    def _openai_chat(self, api_key: str, prompt: str, *, model: str) -> str:
        with httpx.Client(timeout=60.0) as client:
            r = client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.1,
                },
            )
            r.raise_for_status()
            return str(r.json()["choices"][0]["message"]["content"]).strip()

    def _anthropic_chat(self, api_key: str, prompt: str, *, model: str) -> str:
        with httpx.Client(timeout=60.0) as client:
            r = client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "max_tokens": 4096,
                    "messages": [{"role": "user", "content": prompt}],
                },
            )
            r.raise_for_status()
            data = r.json()
            return str(data["content"][0]["text"]).strip()

    def _bob_chat(self, api_key: str, prompt: str, record: ConnectorRecord, *, model: str | None) -> str:
        from src.artcb.config import load_settings

        settings = load_settings()
        base = record.config.get("base_url") or settings.bob_api_base
        model_name = model or settings.bob_model
        from litellm_ibm_bob._transport import BobTransport, TransportConfig

        cfg = TransportConfig(
            api_key=api_key,
            base_url=base,
            team_id=record.config.get("team_id"),
            instance_id=record.config.get("instance_id"),
        )
        transport = BobTransport(cfg)
        try:
            response = transport.request(
                "POST",
                "/inference/v1/chat/completions",
                body={
                    "model": model_name,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.1,
                },
            )
            if not response.is_success:
                raise RuntimeError(f"Bob failed: {response.status_code} {response.text[:300]}")
            data = response.json()
            return str(data["choices"][0]["message"]["content"]).strip()
        finally:
            transport.close()

    def _openrouter_chat(self, api_key: str, prompt: str, record: ConnectorRecord, *, model: str | None) -> str:
        base = record.config.get("base_url", "https://openrouter.ai/api/v1")
        model_name = model or record.config.get("model", "anthropic/claude-3.5-haiku")
        with httpx.Client(timeout=90.0) as client:
            r = client.post(
                f"{base.rstrip('/')}/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": record.config.get("http_referer", "https://artcb.local"),
                    "X-Title": record.config.get("app_title", "ARTCB"),
                },
                json={
                    "model": model_name,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.1,
                },
            )
            r.raise_for_status()
            return str(r.json()["choices"][0]["message"]["content"]).strip()

    def _cursor_chat(self, api_key: str, prompt: str, record: ConnectorRecord, *, model: str | None) -> str:
        """Client natif Cursor IDE — API api.cursor.com/v1/messages (format Anthropic messages)."""
        base = record.config.get("base_url", "https://api.cursor.com")
        # Cursor expose ses modèles sous des IDs courts (claude-sonnet-5, gpt-5.6-sol, etc.)
        model_name = model or record.config.get("model", "claude-sonnet-4-6")
        with httpx.Client(timeout=90.0) as client:
            # Cursor utilise le format /v1/messages (Anthropic-compatible)
            r = client.post(
                f"{base.rstrip('/')}/v1/messages",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model_name,
                    "max_tokens": 1024,
                    "messages": [{"role": "user", "content": prompt}],
                },
            )
            if r.status_code == 404:
                # Fallback: essayons /v1/chat/completions (OpenAI-compatible)
                r = client.post(
                    f"{base.rstrip('/')}/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": model_name,
                        "messages": [{"role": "user", "content": prompt}],
                        "max_tokens": 1024,
                    },
                )
                r.raise_for_status()
                return str(r.json()["choices"][0]["message"]["content"]).strip()
            r.raise_for_status()
            data = r.json()
            # Format Anthropic: content est une liste
            if isinstance(data.get("content"), list):
                return str(data["content"][0].get("text", "")).strip()
            # Format OpenAI
            return str(data.get("content") or data["choices"][0]["message"]["content"]).strip()

    def _ollama_chat(self, api_key: str, prompt: str, record: ConnectorRecord, *, model: str | None) -> str:
        # Valeur par défaut Ollama locale — configurable via connecteur base_url ou ARTCB_OLLAMA_URL
        import os
        default_ollama = os.getenv("ARTCB_OLLAMA_URL", "http://127.0.0.1:11434")
        base = record.config.get("base_url", default_ollama)
        model_name = model or record.config.get("model", "llama3.2")
        headers = {"Content-Type": "application/json"}
        if api_key and not api_key.startswith("local-"):
            headers["Authorization"] = f"Bearer {api_key}"
        with httpx.Client(timeout=120.0) as client:
            r = client.post(
                f"{base.rstrip('/')}/api/chat",
                headers=headers,
                json={
                    "model": model_name,
                    "messages": [{"role": "user", "content": prompt}],
                    "stream": False,
                },
            )
            r.raise_for_status()
            return str(r.json()["message"]["content"]).strip()

    def _watsonx_chat(self, api_key: str, prompt: str, record: ConnectorRecord, *, model: str | None) -> str:
        """WatsonX Assistant IBM — échange IAM token puis appel inference."""
        import httpx
        # 1. Échanger la clé API contre un token IAM
        iam_resp = httpx.post(
            "https://iam.cloud.ibm.com/identity/token",
            data={"grant_type": "urn:ibm:params:oauth:grant-type:apikey", "apikey": api_key},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=15,
        )
        iam_resp.raise_for_status()
        access_token = iam_resp.json()["access_token"]

        # 2. Appel à WatsonX.ai inference (dallas ou au-syd)
        base = (record.base_url or "https://us-south.ml.cloud.ibm.com").rstrip("/")
        mdl = model or "ibm/granite-3-8b-instruct"
        resp = httpx.post(
            f"{base}/ml/v1/text/generation?version=2023-05-29",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            },
            json={
                "model_id": mdl,
                "input": prompt,
                "parameters": {"max_new_tokens": 512, "temperature": 0.2},
            },
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        return str(data["results"][0]["generated_text"]).strip()

    def _google_ai_chat(self, api_key: str, prompt: str, record: ConnectorRecord, *, model: str | None) -> str:
        """Google AI (Gemini) — API REST v1beta generateContent."""
        model_name = model or record.config.get("model", "gemini-1.5-flash")
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent"
        with httpx.Client(timeout=60.0) as client:
            r = client.post(
                url,
                params={"key": api_key},
                headers={"Content-Type": "application/json"},
                json={
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {"temperature": 0.1, "maxOutputTokens": 4096},
                },
            )
            r.raise_for_status()
            data = r.json()
            return str(data["candidates"][0]["content"]["parts"][0]["text"]).strip()


    def _manus_chat(self, api_key: str, prompt: str, record: ConnectorRecord, *, model: str | None) -> str:
        """Manus AI — API compatible OpenAI (chat/completions)."""
        base = record.config.get("base_url", "https://api.manus.im/v1")
        model_name = model or record.config.get("model", "claude-sonnet-4-5")
        with httpx.Client(timeout=60.0) as client:
            r = client.post(
                f"{base}/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model_name,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.1,
                    "max_tokens": 4096,
                },
            )
            r.raise_for_status()
            data = r.json()
            return str(data["choices"][0]["message"]["content"]).strip()


def test_connector(record: ConnectorRecord, api_key: str) -> dict:
    """Test rapide : envoie une phrase courte, vérifie la réponse."""
    router = LLMRouter()
    prompt = "Reply with exactly: OK"
    try:
        if record.provider == "openai":
            raw = router._openai_chat(api_key, prompt, model=record.config.get("model", "gpt-4o-mini"))
        elif record.provider == "anthropic":
            raw = router._anthropic_chat(api_key, prompt, model=record.config.get("model", "claude-3-5-haiku-20241022"))
        elif record.provider == "google_ai":
            raw = router._google_ai_chat(api_key, prompt, record, model=record.config.get("model", "gemini-1.5-flash"))
        elif record.provider == "openrouter":
            raw = router._openrouter_chat(api_key, prompt, record, model=record.config.get("model"))
        elif record.provider == "ollama":
            raw = router._ollama_chat(api_key, prompt, record, model=record.config.get("model", "llama3.2"))
        elif record.provider == "cursor":
            raw = router._cursor_chat(api_key, prompt, record, model=record.config.get("model"))
        elif record.provider == "watsonx":
            raw = router._watsonx_chat(api_key, prompt, record, model=record.config.get("model"))
        elif record.provider == "manus":
            raw = router._manus_chat(api_key, prompt, record, model=record.config.get("model"))
        else:
            return {"ok": False, "message": f"Test not supported for provider {record.provider}"}
        ok = bool(raw) and len(raw) > 0
        return {"ok": ok, "message": raw[:200] if ok else "Empty response"}
    except Exception as e:
        return {"ok": False, "message": str(e)[:300]}
