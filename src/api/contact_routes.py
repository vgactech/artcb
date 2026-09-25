"""R468 — Routes de contact qualifié Pro / Développeur / Organisation.

Endpoint : POST /api/v1/contact
Stockage  : data/contacts/contact_YYYYMMDD_HHMMSS_{uuid}.json (local, non on-chain)
Aucune donnée personnelle n'est transmise sur la blockchain.
"""
from __future__ import annotations

MODULE_VERSION = "1.0.1"  # R468

import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

logger = logging.getLogger("artcb.api.contact")

DEBUG_MODE = True  # PROTOCOLE ARTCB — mode DEBUG obligatoire

router = APIRouter(prefix="/api/v1", tags=["contact"])

CONTACTS_DIR = Path("data/contacts")


# ── Modèles ────────────────────────────────────────────────────────────────────

class ContactRequest(BaseModel):
    """Demande de contact qualifié.

    contact_type détermine le tunnel d'origine (pro / developer / organization).
    Tous les champs sauf contact_type et email sont optionnels.
    """
    contact_type: Literal["pro", "developer", "organization"]

    # Champs communs
    name: Optional[str] = Field(default=None, max_length=200)
    email: str = Field(min_length=3, max_length=320)
    phone: Optional[str] = Field(default=None, max_length=50)
    linkedin: Optional[str] = Field(default=None, max_length=500)

    # PRO
    goal: Optional[str] = Field(default=None, max_length=100)
    sector: Optional[str] = Field(default=None, max_length=100)
    knowledge_level: Optional[str] = Field(default=None, max_length=100)

    # DEV
    integration_goal: Optional[str] = Field(default=None, max_length=100)
    stack: Optional[str] = Field(default=None, max_length=100)
    env: Optional[str] = Field(default=None, max_length=100)
    github: Optional[str] = Field(default=None, max_length=500)

    # ORG
    intent: Optional[str] = Field(default=None, max_length=100)
    org_type: Optional[str] = Field(default=None, max_length=100)
    size: Optional[str] = Field(default=None, max_length=50)
    topic: Optional[str] = Field(default=None, max_length=100)
    org_name: Optional[str] = Field(default=None, max_length=300)
    role: Optional[str] = Field(default=None, max_length=200)


class ContactResponse(BaseModel):
    status: str
    contact_id: str
    message: str


# ── Route ──────────────────────────────────────────────────────────────────────

@router.post("/contact", response_model=ContactResponse)
async def submit_contact(body: ContactRequest) -> ContactResponse:
    """Enregistre une demande de contact qualifié.

    Les données sont stockées localement dans data/contacts/.
    Aucune information personnelle n'est inscrite sur la blockchain.
    """
    contact_id = str(uuid.uuid4())
    ts = datetime.now(timezone.utc).isoformat()

    record = {
        "contact_id": contact_id,
        "received_at": ts,
        "contact_type": body.contact_type,
        "name": body.name,
        "email": body.email,
        "phone": body.phone,
        "linkedin": body.linkedin,
    }

    # Champs spécifiques selon le type
    if body.contact_type == "pro":
        record.update({
            "goal": body.goal,
            "sector": body.sector,
            "knowledge_level": body.knowledge_level,
        })
    elif body.contact_type == "developer":
        record.update({
            "integration_goal": body.integration_goal,
            "stack": body.stack,
            "env": body.env,
            "github": body.github,
        })
    elif body.contact_type == "organization":
        record.update({
            "intent": body.intent,
            "org_type": body.org_type,
            "size": body.size,
            "topic": body.topic,
            "org_name": body.org_name,
            "role": body.role,
        })

    # Stockage local
    try:
        CONTACTS_DIR.mkdir(parents=True, exist_ok=True)
        safe_ts = ts[:19].replace(":", "").replace("-", "").replace("T", "_")
        filename = CONTACTS_DIR / f"contact_{safe_ts}_{contact_id[:8]}.json"
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(record, f, ensure_ascii=False, indent=2)
        if DEBUG_MODE:
            logger.debug("[R468][DEBUG] Contact enregistré → %s", filename)
    except Exception as exc:
        logger.error("[R468][ERROR] Échec écriture contact %s : %s", contact_id, exc)
        # fail-open : on retourne quand même un succès pour ne pas exposer l'erreur interne
        # mais on logue l'erreur pour investigation

    logger.info(
        "[R468][INFO] Contact reçu — id=%s type=%s email=%s",
        contact_id, body.contact_type, body.email,
    )

    return ContactResponse(
        status="ok",
        contact_id=contact_id,
        message="Votre demande a bien été reçue. Nous vous répondrons dans les meilleurs délais.",
    )
