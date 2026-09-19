"""Client Gradium TTS — avec fallback documente."""

from __future__ import annotations
MODULE_VERSION = '1.0.0'  # R390 — auto-versioning

import logging
from typing import Any

import httpx

from src.artcb.config import ArtcbSettings, load_settings

logger = logging.getLogger("artcb.integrations.gradium")


class GradiumError(Exception):
    pass


def synthesize_speech(
    text: str,
    *,
    settings: ArtcbSettings | None = None,
    voice: str = "default",
    language: str = "fr",
) -> dict[str, Any]:
    """
    Synthese vocale Gradium.
    Retourne audio_base64 si succes, sinon mode=fallback pour Web Speech API.
    """
    settings = settings or load_settings()
    if not text.strip():
        raise GradiumError("Texte vide")

    if not settings.gradium_api_key:
        return {
            "mode": "fallback",
            "provider": "webspeech",
            "text": text,
            "language": language,
            "message": "GRADIUM_API_KEY absente — utiliser speechSynthesis navigateur",
        }

    url = f"{settings.gradium_api_url.rstrip('/')}/v1/tts"
    headers = {
        "Authorization": f"Bearer {settings.gradium_api_key}",
        "Content-Type": "application/json",
    }
    payload = {"text": text, "voice": voice, "language": language}

    try:
        with httpx.Client(timeout=60.0) as client:
            r = client.post(url, json=payload, headers=headers)
            if r.status_code == 404:
                r = client.post(
                    f"{settings.gradium_api_url.rstrip('/')}/tts",
                    json=payload,
                    headers=headers,
                )
            r.raise_for_status()
            data = r.json()
    except httpx.HTTPError as exc:
        logger.warning("Gradium TTS failed: %s — fallback webspeech", exc)
        return {
            "mode": "fallback",
            "provider": "webspeech",
            "text": text,
            "language": language,
            "error": str(exc),
        }

    audio_b64 = data.get("audio_base64") or data.get("audio")
    if not audio_b64:
        return {
            "mode": "fallback",
            "provider": "webspeech",
            "text": text,
            "language": language,
            "message": "Reponse Gradium sans audio",
        }

    return {
        "mode": "gradium",
        "provider": "gradium",
        "audio_base64": audio_b64,
        "format": data.get("format", "mp3"),
        "text": text,
        "language": language,
    }
