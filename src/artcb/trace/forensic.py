"""R451 — FORENSIC-01 : Forensic Observability & Evidence Layer ARTCB.

Ce module implémente le **Forensic Event Ledger transversal** décisionné lors de
la session R451. Il couvre TOUTES les couches ARTCB :

    appareil → authenticator → identité biométrique → anti-Sybil → wallet
    → langage → raisonnement → Knowledge → PoL → KnowledgeWork → bloc → économie

Architecture :
    ForensicEventType   — enum de tous les types d'événements par couche
    AttemptOutcome      — résultats distincts (SUCCESS/REJECTED/STORE_UNAVAILABLE/…)
    EvaluationContext   — contexte d'évaluation biométrique/identité
    ForensicEvent       — dataclass immuable (frozen) avec hash chain
    ForensicLedger      — gestionnaire de fichier JSONL + hash chain + Merkle root
    emit_forensic()     — helper de haut niveau (jamais bloquant — fail-open sur I/O)

Propriétés garanties :
    INTÉGRITÉ      : chaque événement contient previous_event_hash + event_hash
                     (hash chain détectable si altéré)
    CORRÉLATION    : correlation_id + trace_id + request_id + session_id
    TRAÇABILITÉ    : git_sha, module_version, protocol_version sur chaque événement
    CONFIDENTIALITÉ: JAMAIS de secret, clé privée, PIN, empreinte brute, template raw
    FAIL-OPEN I/O  : une exception d'écriture n'interrompt JAMAIS l'opération métier
    CERTIFIED_100  : False — invariant

Données JAMAIS enregistrées :
    - clé privée / seed / PIN / secret authenticator
    - template biométrique brut / image brute
    - challenge WebAuthn en clair (uniquement hash)
    - blinding_hex biométrique

Données TOUJOURS enregistrées (métadonnées forensic) :
    - event_id (UUID v4)
    - event_type (ForensicEventType)
    - attempt_outcome (AttemptOutcome)
    - evaluation_context (EvaluationContext)
    - correlation_id / trace_id / session_id
    - git_sha / module_version / protocol_version
    - timestamps wall_ns + mono_ns
    - état before/after résumé (jamais secrets)
    - hash_prev + event_hash (intégrité chaîne)

PROTOCOLE ARTCB — mode DEBUG actif — CERTIFIED_100=false.
"""
from __future__ import annotations
MODULE_VERSION = '1.0.1'  # R451 — FORENSIC-01 Forensic Event Ledger

import fcntl
import hashlib
import json
import logging
import os
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger("artcb.trace.forensic")

# ─── Fichier JSONL du ledger ──────────────────────────────────────────────────

FORENSIC_LEDGER_FILENAME = "forensic_ledger.jsonl"

# ─── Valeur sentinel hash genesis (premier événement) ────────────────────────

GENESIS_HASH = "0000000000000000000000000000000000000000000000000000000000000000"


# ═════════════════════════════════════════════════════════════════════════════
# TYPES — EventType
# ═════════════════════════════════════════════════════════════════════════════

class ForensicEventType(str, Enum):
    """Types d'événements forensic par couche ARTCB.

    Nomenclature : COUCHE_ACTION
    Les suffixes _OK / _FAIL / _BLOCKED / _ERROR distinguent les issues.
    """
    # ── Couche biométrique ────────────────────────────────────────────────
    BIO_ENROLL_OK          = "BIO_ENROLL_OK"
    BIO_ENROLL_FAIL        = "BIO_ENROLL_FAIL"
    BIO_ENROLL_BLOCKED     = "BIO_ENROLL_BLOCKED"
    BIO_VERIFY_OK          = "BIO_VERIFY_OK"
    BIO_VERIFY_FAIL        = "BIO_VERIFY_FAIL"
    BIO_UNIQUENESS_OK      = "BIO_UNIQUENESS_OK"
    BIO_UNIQUENESS_FAIL    = "BIO_UNIQUENESS_FAIL"
    BIO_FUZZY_REPRODUCE_OK = "BIO_FUZZY_REPRODUCE_OK"
    BIO_FUZZY_REPRODUCE_FAIL = "BIO_FUZZY_REPRODUCE_FAIL"
    BIO_HAMMING_CHECK_OK   = "BIO_HAMMING_CHECK_OK"
    BIO_HAMMING_CHECK_FAIL = "BIO_HAMMING_CHECK_FAIL"

    # ── Couche authenticator / WebAuthn ───────────────────────────────────
    WEBAUTHN_REGISTER_OK   = "WEBAUTHN_REGISTER_OK"
    WEBAUTHN_REGISTER_FAIL = "WEBAUTHN_REGISTER_FAIL"
    WEBAUTHN_AUTH_OK       = "WEBAUTHN_AUTH_OK"
    WEBAUTHN_AUTH_FAIL     = "WEBAUTHN_AUTH_FAIL"
    WEBAUTHN_UV_CLAIMED    = "WEBAUTHN_UV_CLAIMED"   # UV=true déclaré (≠ bio prouvée)

    # ── Couche anti-Sybil / identité humaine ──────────────────────────────
    SYBIL_CHECK_OK         = "SYBIL_CHECK_OK"
    SYBIL_CHECK_BLOCKED    = "SYBIL_CHECK_BLOCKED"
    SYBIL_STORE_UNAVAILABLE= "SYBIL_STORE_UNAVAILABLE"
    SYBIL_STORE_EMPTY      = "SYBIL_STORE_EMPTY"
    HUMAN_ID_LINKED        = "HUMAN_ID_LINKED"
    HUMAN_ID_LINK_FAIL     = "HUMAN_ID_LINK_FAIL"
    WALLET_LIMIT_EXCEEDED  = "WALLET_LIMIT_EXCEEDED"

    # ── Couche wallet / device binding ────────────────────────────────────
    WALLET_CREATE_OK       = "WALLET_CREATE_OK"
    WALLET_CREATE_FAIL     = "WALLET_CREATE_FAIL"
    WALLET_CREATE_BLOCKED  = "WALLET_CREATE_BLOCKED"
    WALLET_LINK_OK         = "WALLET_LINK_OK"
    WALLET_LINK_FAIL       = "WALLET_LINK_FAIL"
    WALLET_REVOKE_OK       = "WALLET_REVOKE_OK"
    WALLET_REVOKE_FAIL     = "WALLET_REVOKE_FAIL"
    WALLET_PURGE_OK        = "WALLET_PURGE_OK"
    WALLET_PURGE_FAIL      = "WALLET_PURGE_FAIL"
    BINDING_CHECK_OK       = "BINDING_CHECK_OK"
    BINDING_CHECK_FAIL     = "BINDING_CHECK_FAIL"
    BINDING_CHECK_BLOCKED  = "BINDING_CHECK_BLOCKED"

    # ── Couche raisonnement IA / pipeline G4 ──────────────────────────────
    REASONING_PIPELINE_OK  = "REASONING_PIPELINE_OK"
    REASONING_PIPELINE_FAIL= "REASONING_PIPELINE_FAIL"
    IR_ENCODE_OK           = "IR_ENCODE_OK"
    IR_ENCODE_FAIL         = "IR_ENCODE_FAIL"
    CANONICAL_OK           = "CANONICAL_OK"
    CANONICAL_FAIL         = "CANONICAL_FAIL"
    KNOWLEDGE_CREATE_OK    = "KNOWLEDGE_CREATE_OK"
    KNOWLEDGE_CREATE_FAIL  = "KNOWLEDGE_CREATE_FAIL"
    USAGE_RECORD_OK        = "USAGE_RECORD_OK"
    USAGE_RECORD_FAIL      = "USAGE_RECORD_FAIL"
    POL_SCORE_OK           = "POL_SCORE_OK"
    POL_SCORE_FAIL         = "POL_SCORE_FAIL"
    KNOWLEDGE_WORK_OK      = "KNOWLEDGE_WORK_OK"
    KNOWLEDGE_WORK_FAIL    = "KNOWLEDGE_WORK_FAIL"

    # ── Couche multilingue ────────────────────────────────────────────────
    LANG_LOOKUP_HIT        = "LANG_LOOKUP_HIT"
    LANG_LOOKUP_MISS       = "LANG_LOOKUP_MISS"
    CONCEPT_ID_RESOLVED    = "CONCEPT_ID_RESOLVED"
    CONCEPT_ID_DIVERGED    = "CONCEPT_ID_DIVERGED"

    # ── Couche blockchain ─────────────────────────────────────────────────
    BLOCK_ACCEPTED         = "BLOCK_ACCEPTED"
    BLOCK_REJECTED         = "BLOCK_REJECTED"
    WORK_RECORD_SEALED     = "WORK_RECORD_SEALED"
    WORK_RECORD_PENDING    = "WORK_RECORD_PENDING"
    CONSENSUS_ROUND_OK     = "CONSENSUS_ROUND_OK"
    CONSENSUS_ROUND_FAIL   = "CONSENSUS_ROUND_FAIL"

    # ── Couche économique ─────────────────────────────────────────────────
    REWARD_ESTIMATED       = "REWARD_ESTIMATED"
    REWARD_PENDING         = "REWARD_PENDING"
    REWARD_SETTLED         = "REWARD_SETTLED"
    REWARD_REVOKED         = "REWARD_REVOKED"
    ECONOMIC_EVENT         = "ECONOMIC_EVENT"

    # ── Couche sécurité générale ──────────────────────────────────────────
    SECURITY_BLOCK         = "SECURITY_BLOCK"
    POLICY_BLOCK           = "POLICY_BLOCK"
    RATE_LIMIT             = "RATE_LIMIT"
    INTERNAL_ERROR         = "INTERNAL_ERROR"

    # ── Audit du forensic lui-même ────────────────────────────────────────
    FORENSIC_ACCESS        = "FORENSIC_ACCESS"
    FORENSIC_MERKLE_ROOT   = "FORENSIC_MERKLE_ROOT"


# ═════════════════════════════════════════════════════════════════════════════
# TYPES — AttemptOutcome
# ═════════════════════════════════════════════════════════════════════════════

class AttemptOutcome(str, Enum):
    """Résultat détaillé d'une tentative — distingue les causes d'échec."""
    SUCCESS              = "SUCCESS"
    REJECTED             = "REJECTED"           # rejeté par logique métier normale
    TIMEOUT              = "TIMEOUT"
    CANCELLED            = "CANCELLED"          # annulé par l'utilisateur
    ABORTED              = "ABORTED"
    STORE_UNAVAILABLE    = "STORE_UNAVAILABLE"  # R447 — store inaccessible → 503
    STORE_EMPTY          = "STORE_EMPTY"        # store vide = légal
    STORE_MISSING        = "STORE_MISSING"      # fichier absent = légal
    DEVICE_UNAVAILABLE   = "DEVICE_UNAVAILABLE"
    AUTHENTICATOR_ERROR  = "AUTHENTICATOR_ERROR"
    POLICY_BLOCKED       = "POLICY_BLOCKED"
    SYBIL_BLOCKED        = "SYBIL_BLOCKED"
    RATE_LIMITED         = "RATE_LIMITED"
    INTERNAL_ERROR       = "INTERNAL_ERROR"
    UNKNOWN              = "UNKNOWN"


# ═════════════════════════════════════════════════════════════════════════════
# TYPES — EvaluationContext
# ═════════════════════════════════════════════════════════════════════════════

class EvaluationContext(str, Enum):
    """Contexte dans lequel une opération biométrique / identité a été produite.

    Nécessaire pour segmenter FAR/FRR par contexte (enrollment ≠ authentication).
    """
    ENROLLMENT          = "ENROLLMENT"
    AUTHENTICATION      = "AUTHENTICATION"
    RECOVERY            = "RECOVERY"
    WALLET_CREATION     = "WALLET_CREATION"
    WALLET_LINK         = "WALLET_LINK"
    UNIQUENESS_CHECK    = "UNIQUENESS_CHECK"
    SYBIL_CHECK         = "SYBIL_CHECK"
    REASONING_PIPELINE  = "REASONING_PIPELINE"
    BLOCKCHAIN          = "BLOCKCHAIN"
    ECONOMIC            = "ECONOMIC"
    ADMIN               = "ADMIN"
    UNKNOWN             = "UNKNOWN"


# ═════════════════════════════════════════════════════════════════════════════
# ForensicEvent — événement immuable
# ═════════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class ForensicEvent:
    """Événement forensic immuable ARTCB — toutes couches.

    Identifiants de corrélation :
        event_id         : UUID v4 unique par événement
        correlation_id   : relie plusieurs événements d'une même opération
        trace_id         : relie la chaîne complète (ex: enroll → sybil → wallet)
        request_id       : identifiant de la requête HTTP ou job (optionnel)
        session_id       : identifiant de session utilisateur (optionnel)

    Provenance protocolaire :
        git_sha          : SHA git du code ayant produit l'événement
        module_version   : MODULE_VERSION du module émetteur
        protocol_version : version du protocole ARTCB
        schema_version   : version de ce schéma ForensicEvent

    Timestamps :
        ts_wall_ns       : timestamp mur en nanosecondes (time.time_ns())
        ts_mono_ns       : timestamp monotone en nanosecondes (time.perf_counter_ns())
        created_at       : timestamp ISO UTC lisible

    Données métier (jamais de secret) :
        event_type       : ForensicEventType
        outcome          : AttemptOutcome
        evaluation_context : EvaluationContext
        layer            : couche ARTCB ('biometric', 'wallet', 'reasoning', …)
        actor_ref        : référence de l'acteur (wallet_name ou agent_id, jamais clé privée)
        subject_ref      : référence du sujet (human_id, work_id, …)
        algorithm_version: version de l'algorithme utilisé
        state_before     : résumé état avant (sans secrets)
        state_after      : résumé état après (sans secrets)
        extra            : champs libres additionnels (sans secrets)

    Intégrité hash chain :
        previous_event_hash : event_hash de l'événement précédent (GENESIS_HASH si premier)
        event_hash          : sha256(JSON canonique de tous les champs sauf event_hash)

    Invariants :
        unique_human_proven : TOUJOURS False
        certified_100       : TOUJOURS False
    """
    # ── Identifiants ─────────────────────────────────────────────────────
    event_id:           str
    event_type:         ForensicEventType
    outcome:            AttemptOutcome
    evaluation_context: EvaluationContext

    # ── Timestamps ───────────────────────────────────────────────────────
    ts_wall_ns:  int
    ts_mono_ns:  int
    created_at:  str

    # ── Corrélation ──────────────────────────────────────────────────────
    correlation_id:  str = ""
    trace_id:        str = ""
    request_id:      str = ""
    session_id:      str = ""

    # ── Provenance protocolaire ───────────────────────────────────────────
    git_sha:          str = ""
    module_version:   str = ""
    protocol_version: str = "artcb-mainnet-1"
    schema_version:   str = "forensic-v1"
    node_id:          str = ""
    environment:      str = "dev"

    # ── Données métier ────────────────────────────────────────────────────
    layer:              str = ""        # 'biometric', 'wallet', 'reasoning', etc.
    actor_ref:          str = ""        # wallet_name, agent_id — jamais clé privée
    subject_ref:        str = ""        # human_id, knowledge_id, work_id, …
    algorithm_version:  str = ""        # version de l'algorithme impliqué
    attempt_number:     int = 1
    failure_reason_code: str = ""

    # ── Résumés état (sans secrets) ────────────────────────────────────────
    state_before:  dict = field(default_factory=dict)
    state_after:   dict = field(default_factory=dict)
    extra:         dict = field(default_factory=dict)

    # ── Hash chain (intégrité) ─────────────────────────────────────────────
    previous_event_hash: str = GENESIS_HASH
    event_hash:          str = ""        # calculé par ForensicLedger.append()

    # ── Invariants ────────────────────────────────────────────────────────
    unique_human_proven: bool = False
    certified_100:       bool = False

    def to_dict(self) -> dict[str, Any]:
        """Sérialisation complète. Les enums sont converties en str."""
        d = asdict(self)
        # Convertir les enums en str pour JSON
        for key in ("event_type", "outcome", "evaluation_context"):
            if isinstance(d.get(key), Enum):
                d[key] = d[key].value
            elif hasattr(d.get(key), "value"):
                d[key] = d[key]
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ForensicEvent":
        """Désérialisation depuis dict JSON."""
        d2 = dict(d)
        # Convertir str → enum
        if isinstance(d2.get("event_type"), str):
            d2["event_type"] = ForensicEventType(d2["event_type"])
        if isinstance(d2.get("outcome"), str):
            d2["outcome"] = AttemptOutcome(d2["outcome"])
        if isinstance(d2.get("evaluation_context"), str):
            d2["evaluation_context"] = EvaluationContext(d2["evaluation_context"])
        return cls(**d2)

    def compute_hash(self) -> str:
        """Calcule le hash SHA-256 de cet événement (sans le champ event_hash lui-même)."""
        d = self.to_dict()
        d.pop("event_hash", None)          # exclure event_hash du calcul
        raw = json.dumps(d, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()


# ═════════════════════════════════════════════════════════════════════════════
# ForensicLedger — gestionnaire hash-chain + JSONL
# ═════════════════════════════════════════════════════════════════════════════

class ForensicLedger:
    """Ledger forensic ARTCB : JSONL append-only avec hash-chain et Merkle root périodique.

    Architecture :
        data_dir/forensic/forensic_ledger.jsonl
            → chaque ligne = ForensicEvent JSON compact
            → hash_prev[n] == event_hash[n-1] (invariant de chaîne)

    Usage :
        ledger = ForensicLedger(data_dir=Path("data"))
        event = ledger.build(
            event_type=ForensicEventType.BIO_ENROLL_OK,
            outcome=AttemptOutcome.SUCCESS,
            evaluation_context=EvaluationContext.ENROLLMENT,
            correlation_id="corr-xyz",
            layer="biometric",
            subject_ref="human_id_abc",
        )
        ledger.append(event)
    """

    FORENSIC_DIR = "forensic"

    def __init__(self, data_dir: Path | str) -> None:
        self._dir = Path(data_dir) / self.FORENSIC_DIR
        self._ledger_path = self._dir / FORENSIC_LEDGER_FILENAME
        self._dir.mkdir(parents=True, exist_ok=True)

    # ── Lecture du dernier hash ────────────────────────────────────────────

    def _last_event_hash(self) -> str:
        """Retourne le event_hash du dernier événement dans le JSONL, ou GENESIS_HASH."""
        if not self._ledger_path.is_file():
            return GENESIS_HASH
        last_line = ""
        try:
            with self._ledger_path.open("rb") as fh:
                # Lecture efficace du dernier enregistrement non vide
                fh.seek(0, 2)  # fin du fichier
                size = fh.tell()
                if size == 0:
                    return GENESIS_HASH
                # Lire les 4 Ko finaux pour trouver la dernière ligne
                chunk_size = min(4096, size)
                fh.seek(max(0, size - chunk_size))
                tail = fh.read().decode("utf-8", errors="replace")
                lines = [l.strip() for l in tail.splitlines() if l.strip()]
                last_line = lines[-1] if lines else ""
        except Exception as exc:  # noqa: BLE001
            logger.warning("[forensic] _last_event_hash failed: %s", exc)
            return GENESIS_HASH

        if not last_line:
            return GENESIS_HASH
        try:
            parsed = json.loads(last_line)
            return parsed.get("event_hash", GENESIS_HASH)
        except Exception:  # noqa: BLE001
            return GENESIS_HASH

    # ── Construction d'un événement ────────────────────────────────────────

    def build(
        self,
        *,
        event_type: ForensicEventType,
        outcome: AttemptOutcome,
        evaluation_context: EvaluationContext = EvaluationContext.UNKNOWN,
        correlation_id: str = "",
        trace_id: str = "",
        request_id: str = "",
        session_id: str = "",
        git_sha: str = "",
        module_version: str = "",
        protocol_version: str = "artcb-mainnet-1",
        node_id: str = "",
        environment: str = "dev",
        layer: str = "",
        actor_ref: str = "",
        subject_ref: str = "",
        algorithm_version: str = "",
        attempt_number: int = 1,
        failure_reason_code: str = "",
        state_before: dict | None = None,
        state_after: dict | None = None,
        extra: dict | None = None,
    ) -> ForensicEvent:
        """Construit un ForensicEvent SANS l'ajouter au ledger (hash non calculé).

        Utiliser append() pour calculer le hash et écrire.
        """
        ts_wall = time.time_ns()
        ts_mono = time.perf_counter_ns()
        ts_iso  = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        eid     = str(uuid.uuid4())

        return ForensicEvent(
            event_id=eid,
            event_type=event_type,
            outcome=outcome,
            evaluation_context=evaluation_context,
            ts_wall_ns=ts_wall,
            ts_mono_ns=ts_mono,
            created_at=ts_iso,
            correlation_id=correlation_id,
            trace_id=trace_id,
            request_id=request_id,
            session_id=session_id,
            git_sha=git_sha,
            module_version=module_version,
            protocol_version=protocol_version,
            schema_version="forensic-v1",
            node_id=node_id,
            environment=environment,
            layer=layer,
            actor_ref=actor_ref,
            subject_ref=subject_ref,
            algorithm_version=algorithm_version,
            attempt_number=attempt_number,
            failure_reason_code=failure_reason_code,
            state_before=dict(state_before or {}),
            state_after=dict(state_after or {}),
            extra=dict(extra or {}),
            previous_event_hash=GENESIS_HASH,   # corrigé par append()
            event_hash="",                       # calculé par append()
            unique_human_proven=False,
            certified_100=False,
        )

    # ── Ajout au ledger (avec hash chain) ─────────────────────────────────

    def append(self, event: ForensicEvent) -> ForensicEvent:
        """Ajoute un événement au ledger JSONL avec hash chain.

        1. Récupère le previous_event_hash depuis la dernière ligne du JSONL.
        2. Crée une nouvelle instance avec previous_event_hash correct.
        3. Calcule event_hash sur tous les champs (sauf event_hash lui-même).
        4. Écrit en mode append (fcntl LOCK_EX sur les systèmes POSIX).
        5. Retourne l'événement enrichi avec ses hashs.

        En cas d'erreur d'écriture : logue WARNING et retourne l'événement non écrit.
        Ne lève JAMAIS d'exception (fail-open I/O).
        """
        prev_hash = self._last_event_hash()

        # Recréer avec previous_event_hash correct (frozen → objet.replace())
        import dataclasses
        event_with_prev = dataclasses.replace(event, previous_event_hash=prev_hash)
        computed_hash = event_with_prev.compute_hash()
        sealed = dataclasses.replace(event_with_prev, event_hash=computed_hash)

        try:
            line = json.dumps(sealed.to_dict(), ensure_ascii=False, separators=(",", ":")) + "\n"
            with self._ledger_path.open("a", encoding="utf-8") as fh:
                # Lock exclusif POSIX (non-bloquant sur macOS/Linux)
                try:
                    fcntl.flock(fh, fcntl.LOCK_EX)
                except Exception:  # noqa: BLE001
                    pass  # Si flock non disponible, continuer sans lock
                fh.write(line)
                try:
                    fcntl.flock(fh, fcntl.LOCK_UN)
                except Exception:  # noqa: BLE001
                    pass
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "[forensic] WARN — écriture ledger échouée (fail-open): %s", exc
            )

        return sealed

    # ── Lecture ────────────────────────────────────────────────────────────

    def list_events(
        self,
        *,
        limit: int = 500,
        event_type: ForensicEventType | None = None,
        correlation_id: str | None = None,
        outcome: AttemptOutcome | None = None,
    ) -> list[ForensicEvent]:
        """Retourne les N derniers événements du ledger avec filtres optionnels."""
        if not self._ledger_path.is_file():
            return []

        results: list[ForensicEvent] = []
        try:
            with self._ledger_path.open(encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        parsed = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    # Filtres
                    if event_type and parsed.get("event_type") != event_type.value:
                        continue
                    if correlation_id and parsed.get("correlation_id") != correlation_id:
                        continue
                    if outcome and parsed.get("outcome") != outcome.value:
                        continue
                    try:
                        results.append(ForensicEvent.from_dict(parsed))
                    except Exception:  # noqa: BLE001
                        continue
        except Exception as exc:  # noqa: BLE001
            logger.warning("[forensic] list_events error: %s", exc)
            return []

        cap = max(1, min(limit, 10_000))
        return results[-cap:]

    # ── Vérification de la chaîne ──────────────────────────────────────────

    def verify_chain(self) -> dict[str, Any]:
        """Vérifie l'intégrité de la hash-chain du ledger.

        Retourne :
            ok         : True si la chaîne est intègre
            checked    : nombre d'événements vérifiés
            broken_at  : index du premier événement brisé (None si ok)
            detail     : description de la rupture
        """
        events = self.list_events(limit=10_000)
        if not events:
            return {"ok": True, "checked": 0, "broken_at": None, "detail": "ledger vide"}

        for i, ev in enumerate(events):
            # Recalculer le hash attendu
            import dataclasses
            ev_no_hash = dataclasses.replace(ev, event_hash="")
            computed = ev_no_hash.compute_hash()
            if ev.event_hash != computed:
                return {
                    "ok": False, "checked": i + 1, "broken_at": i,
                    "detail": f"event_hash incorrect à index {i}: attendu={computed[:16]}… reçu={ev.event_hash[:16]}…",
                }
            # Vérifier hash_prev sauf pour le premier
            if i > 0 and ev.previous_event_hash != events[i - 1].event_hash:
                return {
                    "ok": False, "checked": i + 1, "broken_at": i,
                    "detail": (
                        f"hash_prev rompu à index {i}: "
                        f"attendu={events[i-1].event_hash[:16]}… "
                        f"reçu={ev.previous_event_hash[:16]}…"
                    ),
                }

        return {"ok": True, "checked": len(events), "broken_at": None, "detail": "chaîne intègre"}

    # ── Merkle root ────────────────────────────────────────────────────────

    def compute_merkle_root(self, *, limit: int = 10_000) -> str:
        """Calcule un Merkle root SHA-256 des event_hash des N derniers événements.

        Algorithme : paires SHA-256(hash_gauche || hash_droite) jusqu'à racine unique.
        Si nombre impair : dernier élément dupliqué.
        Retourne GENESIS_HASH si ledger vide.
        """
        events = self.list_events(limit=limit)
        leaves = [ev.event_hash for ev in events if ev.event_hash]
        if not leaves:
            return GENESIS_HASH

        def _merkle(hashes: list[str]) -> str:
            if len(hashes) == 1:
                return hashes[0]
            if len(hashes) % 2 == 1:
                hashes = hashes + [hashes[-1]]  # dupliquer le dernier si impair
            parents = []
            for i in range(0, len(hashes), 2):
                combined = (hashes[i] + hashes[i + 1]).encode("utf-8")
                parents.append(hashlib.sha256(combined).hexdigest())
            return _merkle(parents)

        return _merkle(leaves)

    def emit_merkle_checkpoint(self) -> ForensicEvent | None:
        """Émet un événement FORENSIC_MERKLE_ROOT et l'ajoute au ledger.

        Cela ancre périodiquement l'intégrité du ledger dans la chaîne elle-même.
        """
        root = self.compute_merkle_root()
        ev = self.build(
            event_type=ForensicEventType.FORENSIC_MERKLE_ROOT,
            outcome=AttemptOutcome.SUCCESS,
            evaluation_context=EvaluationContext.ADMIN,
            layer="forensic",
            extra={"merkle_root": root},
        )
        return self.append(ev)


# ═════════════════════════════════════════════════════════════════════════════
# Helper de haut niveau — emit_forensic()
# ═════════════════════════════════════════════════════════════════════════════

def emit_forensic(
    ledger: ForensicLedger | None,
    *,
    event_type: ForensicEventType,
    outcome: AttemptOutcome,
    evaluation_context: EvaluationContext = EvaluationContext.UNKNOWN,
    correlation_id: str = "",
    trace_id: str = "",
    session_id: str = "",
    layer: str = "",
    actor_ref: str = "",
    subject_ref: str = "",
    algorithm_version: str = "",
    git_sha: str = "",
    module_version: str = "",
    state_before: dict | None = None,
    state_after: dict | None = None,
    failure_reason_code: str = "",
    extra: dict | None = None,
) -> ForensicEvent | None:
    """Helper FAIL-OPEN : émet un événement forensic sans jamais bloquer l'opération métier.

    Si ledger=None : construit l'événement sans l'écrire (utile pour les tests).
    Si une exception survient : logue WARNING et retourne None.

    Règle ARTCB : ne JAMAIS passer de secret, clé privée, PIN, template brut dans
    state_before, state_after ou extra.
    """
    try:
        if ledger is None:
            # Mode sans persistence — construire l'événement pour tests
            tmp_ledger = ForensicLedger.__new__(ForensicLedger)
            tmp_ledger._dir = Path("/tmp")
            tmp_ledger._ledger_path = Path("/tmp/__forensic_no_write.jsonl")
            ev = tmp_ledger.build(
                event_type=event_type,
                outcome=outcome,
                evaluation_context=evaluation_context,
                correlation_id=correlation_id,
                trace_id=trace_id,
                session_id=session_id,
                layer=layer,
                actor_ref=actor_ref,
                subject_ref=subject_ref,
                algorithm_version=algorithm_version,
                git_sha=git_sha,
                module_version=module_version,
                state_before=state_before,
                state_after=state_after,
                failure_reason_code=failure_reason_code,
                extra=extra,
            )
            import dataclasses
            hash_val = ev.compute_hash()
            return dataclasses.replace(ev, previous_event_hash=GENESIS_HASH, event_hash=hash_val)

        ev = ledger.build(
            event_type=event_type,
            outcome=outcome,
            evaluation_context=evaluation_context,
            correlation_id=correlation_id,
            trace_id=trace_id,
            session_id=session_id,
            layer=layer,
            actor_ref=actor_ref,
            subject_ref=subject_ref,
            algorithm_version=algorithm_version,
            git_sha=git_sha,
            module_version=module_version,
            state_before=state_before,
            state_after=state_after,
            failure_reason_code=failure_reason_code,
            extra=extra,
        )
        return ledger.append(ev)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[forensic] emit_forensic failed (fail-open): %s", exc)
        return None
