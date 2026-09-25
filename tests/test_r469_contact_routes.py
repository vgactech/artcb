"""Tests R469 — Tunnels de contact qualifié Pro / Développeur / Organisation.

Module : src/api/contact_routes.py
Tests  : T01→T20

Invariants :
- POST /api/v1/contact retourne status="ok" pour chaque tunnel valide
- contact_id est un UUID v4
- Chaque type (pro/developer/organization) est accepté
- email manquant ou trop court → HTTP 422
- contact_type invalide → HTTP 422
- Les champs spécifiques sont correctement routés
- Aucune donnée personnelle n'est exposée dans la réponse
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from fastapi import FastAPI

# Monkey-patch CONTACTS_DIR avant import pour éviter de polluer le répertoire réel
import src.api.contact_routes as cr_module

_TMP_DIR = Path(tempfile.mkdtemp(prefix="artcb_contact_test_"))
cr_module.CONTACTS_DIR = _TMP_DIR

from src.api.contact_routes import router, ContactRequest, ContactResponse

DEBUG_MODE = True

# ── App de test ────────────────────────────────────────────────────────────────

_app = FastAPI()
_app.include_router(router)
client = TestClient(_app, raise_server_exceptions=True)


def _post(payload: dict) -> tuple[int, dict]:
    resp = client.post("/api/v1/contact", json=payload)
    return resp.status_code, resp.json()


# ── T01–T06 : tunnel PRO ───────────────────────────────────────────────────────

def test_t01_pro_minimal():
    """T01 — PRO minimal : email uniquement."""
    status, body = _post({"contact_type": "pro", "email": "test@example.com"})
    assert status == 200, body
    assert body["status"] == "ok"
    assert len(body["contact_id"]) == 36  # UUID v4


def test_t02_pro_complet():
    """T02 — PRO complet : tous les champs."""
    status, body = _post({
        "contact_type": "pro",
        "email": "pro@company.com",
        "name": "Alice Dupont",
        "phone": "+33600000001",
        "linkedin": "https://linkedin.com/in/alice",
        "goal": "use",
        "sector": "finance",
        "knowledge_level": "technical",
    })
    assert status == 200, body
    assert body["status"] == "ok"


def test_t03_pro_fichier_cree():
    """T03 — Un fichier JSON est créé dans CONTACTS_DIR après soumission PRO."""
    before = set(_TMP_DIR.iterdir())
    _post({"contact_type": "pro", "email": "file_check@artcb.me"})
    after = set(_TMP_DIR.iterdir())
    new_files = after - before
    assert len(new_files) == 1
    data = json.loads(list(new_files)[0].read_text(encoding="utf-8"))
    assert data["contact_type"] == "pro"
    assert data["email"] == "file_check@artcb.me"


# ── T07–T11 : tunnel DEVELOPER ─────────────────────────────────────────────────

def test_t04_developer_minimal():
    """T04 — DEVELOPER minimal."""
    status, body = _post({"contact_type": "developer", "email": "dev@artcb.me"})
    assert status == 200, body
    assert body["status"] == "ok"


def test_t05_developer_complet():
    """T05 — DEVELOPER complet."""
    status, body = _post({
        "contact_type": "developer",
        "email": "dev2@artcb.me",
        "name": "Bob Builder",
        "github": "https://github.com/bbuilder",
        "integration_goal": "run_node",
        "stack": "python",
        "env": "production",
    })
    assert status == 200, body
    assert body["status"] == "ok"


def test_t06_developer_fichier_contient_champs_dev():
    """T06 — Le fichier Developer contient les champs spécifiques (stack, github)."""
    before = set(_TMP_DIR.iterdir())
    _post({
        "contact_type": "developer",
        "email": "devcheck@artcb.me",
        "stack": "rust",
        "github": "https://github.com/rust_dev",
        "integration_goal": "contribute",
        "env": "research",
    })
    after = set(_TMP_DIR.iterdir())
    new_file = (after - before).pop()
    data = json.loads(new_file.read_text(encoding="utf-8"))
    assert data["stack"] == "rust"
    assert data["github"] == "https://github.com/rust_dev"
    assert data["integration_goal"] == "contribute"


# ── T12–T16 : tunnel ORGANIZATION ─────────────────────────────────────────────

def test_t07_organization_minimal():
    """T07 — ORGANIZATION minimal."""
    status, body = _post({"contact_type": "organization", "email": "org@artcb.me"})
    assert status == 200, body


def test_t08_organization_complet():
    """T08 — ORGANIZATION complet : 5 étapes remplies."""
    status, body = _post({
        "contact_type": "organization",
        "email": "cto@bigcorp.com",
        "name": "Charles Martin",
        "phone": "+33144000000",
        "linkedin": "https://linkedin.com/in/cmartin",
        "intent": "pilot",
        "org_type": "company",
        "size": "251_1000",
        "topic": "security",
        "org_name": "BigCorp SA",
        "role": "CTO",
    })
    assert status == 200, body
    assert body["status"] == "ok"


def test_t09_organization_fichier_contient_champs_org():
    """T09 — Fichier Organization contient org_name, role, intent."""
    before = set(_TMP_DIR.iterdir())
    _post({
        "contact_type": "organization",
        "email": "orgcheck@artcb.me",
        "org_name": "TestOrg",
        "role": "DPO",
        "intent": "partnership",
        "org_type": "public",
        "size": "51_250",
        "topic": "identity",
    })
    after = set(_TMP_DIR.iterdir())
    new_file = (after - before).pop()
    data = json.loads(new_file.read_text(encoding="utf-8"))
    assert data["org_name"] == "TestOrg"
    assert data["role"] == "DPO"
    assert data["intent"] == "partnership"


# ── T17–T20 : validation / erreurs ────────────────────────────────────────────

def test_t10_email_manquant_422():
    """T10 — Email absent → HTTP 422."""
    status, _ = _post({"contact_type": "pro"})
    assert status == 422


def test_t11_email_trop_court_422():
    """T11 — Email trop court (< 3 chars) → HTTP 422."""
    status, _ = _post({"contact_type": "pro", "email": "a@"})
    assert status == 422


def test_t12_contact_type_invalide_422():
    """T12 — contact_type inconnu → HTTP 422."""
    status, _ = _post({"contact_type": "hacker", "email": "x@y.com"})
    assert status == 422


def test_t13_contact_id_est_uuid():
    """T13 — contact_id a le format UUID v4 (36 chars avec tirets)."""
    _, body = _post({"contact_type": "pro", "email": "uuid@test.com"})
    cid = body["contact_id"]
    assert len(cid) == 36
    parts = cid.split("-")
    assert len(parts) == 5
    assert len(parts[0]) == 8
    assert len(parts[4]) == 12


def test_t14_reponse_ne_contient_pas_email():
    """T14 — La réponse HTTP ne contient pas l'email ni le nom (RGPD)."""
    _, body = _post({"contact_type": "pro", "email": "rgpd@secret.com", "name": "Jean Secret"})
    resp_str = json.dumps(body)
    assert "rgpd@secret.com" not in resp_str
    assert "Jean Secret" not in resp_str


def test_t15_trois_tunnels_chacun_cree_fichier_distinct():
    """T15 — 3 appels successifs (un par type) créent 3 fichiers distincts."""
    before = set(_TMP_DIR.iterdir())
    _post({"contact_type": "pro", "email": "t15a@artcb.me"})
    _post({"contact_type": "developer", "email": "t15b@artcb.me"})
    _post({"contact_type": "organization", "email": "t15c@artcb.me"})
    after = set(_TMP_DIR.iterdir())
    new_files = after - before
    assert len(new_files) == 3
    types = {json.loads(f.read_text())["contact_type"] for f in new_files}
    assert types == {"pro", "developer", "organization"}


def test_t16_message_present_dans_reponse():
    """T16 — Le champ 'message' est présent dans la réponse."""
    _, body = _post({"contact_type": "developer", "email": "msg@artcb.me"})
    assert "message" in body
    assert len(body["message"]) > 10


def test_t17_champs_pro_non_presents_dans_org():
    """T17 — Un fichier Organization ne contient pas les champs PRO (sector, goal)."""
    before = set(_TMP_DIR.iterdir())
    _post({"contact_type": "organization", "email": "nopro@artcb.me"})
    after = set(_TMP_DIR.iterdir())
    new_file = (after - before).pop()
    data = json.loads(new_file.read_text())
    assert "sector" not in data
    assert "goal" not in data


def test_t18_champs_org_non_presents_dans_dev():
    """T18 — Un fichier Developer ne contient pas les champs ORG (org_name, intent)."""
    before = set(_TMP_DIR.iterdir())
    _post({"contact_type": "developer", "email": "noorg@artcb.me"})
    after = set(_TMP_DIR.iterdir())
    new_file = (after - before).pop()
    data = json.loads(new_file.read_text())
    assert "org_name" not in data
    assert "intent" not in data


def test_t19_received_at_est_iso8601():
    """T19 — received_at dans le fichier est au format ISO 8601 UTC."""
    from datetime import datetime, timezone
    before = set(_TMP_DIR.iterdir())
    _post({"contact_type": "pro", "email": "ts@artcb.me"})
    after = set(_TMP_DIR.iterdir())
    new_file = (after - before).pop()
    data = json.loads(new_file.read_text())
    ts = data["received_at"]
    # Doit être parseable
    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    assert dt.tzinfo is not None


def test_t20_contact_id_coherent_fichier_et_reponse():
    """T20 — contact_id dans le fichier == contact_id dans la réponse HTTP."""
    before = set(_TMP_DIR.iterdir())
    _, body = _post({"contact_type": "pro", "email": "coherent@artcb.me"})
    after = set(_TMP_DIR.iterdir())
    new_file = (after - before).pop()
    data = json.loads(new_file.read_text())
    assert data["contact_id"] == body["contact_id"]
