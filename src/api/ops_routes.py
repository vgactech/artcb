"""R336 — HTTPS operator ops (no SSH :22).

Ports measured from LAN 2026-09-13: only :80/:443 OPEN on seeds.
:22/:8000/:8443/:2222 CLOSED. Admin actions that need process restart
must therefore travel on the existing HTTPS surface, not a fantasy free port.

~~Do not add a raw shell/exec endpoint.~~ Restart = exit so systemd
``Restart=always`` re-runs ``doppler run`` and refreshes secrets.

Two auth paths:
1. Local ``require_write_actor`` (node's own env key) — ``/self-restart``
2. Official replica signature (like concept peer-ingest) — ``/peer-restart``
   so ovh-node-1 can bounce n2/n3/n4 over :443 without their API keys.

V-PQC-2 — ML-DSA-65 challenge/verify (R351):
  POST /ops/pqc-challenge  → nonce 32 octets (usage unique, TTL 5 min)
  POST /ops/pqc-verify     → signe le nonce avec la clé PQC privée du nœud,
                             vérifie immédiatement → preuve de contrôle PQC
"""

from __future__ import annotations
MODULE_VERSION = '1.0.0'  # R390 — auto-versioning

import hashlib
import os
import secrets
import threading
import time
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field

from src.api.api_keys_routes import require_write_actor
from src.artcb.trace.ns import now_mono_ns, now_wall_ns

router = APIRouter(prefix="/api/v1/ops", tags=["ops"])

PEER_RESTART_PROTOCOL = "ops-peer-restart-v1"
_MAX_SKEW_NS = 120_000_000_000  # 120s
_LAST_RESTART_MONO = 0.0
_MIN_RESTART_GAP_S = 30.0

# V-PQC-2 — challenges ML-DSA en attente de vérification
# nonce_hex → expires_at (timestamp float)
_PQC_CHALLENGES: dict[str, float] = {}
_PQC_CHALLENGE_TTL = 300  # 5 minutes
_PQC_CHALLENGE_MAX = 500  # cap mémoire anti-DoS
# Rate-limit par IP : ip → [timestamps]
_PQC_RATE_WINDOW_S = 60
_PQC_RATE_MAX = 10
_PQC_RATE: dict[str, list[float]] = {}


class PqcVerifyRequest(BaseModel):
    challenge: str = Field(min_length=64, max_length=64, description="Nonce hex 32 octets reçu via /ops/pqc-challenge")
    wallet_name: str = Field(default="default", description="Nom du wallet local dont on prouve le contrôle PQC")
    user_password: str | None = Field(default=None, description="Mot de passe wallet si nécessaire")


def _key_fingerprint() -> dict[str, Any]:
    raw = (os.environ.get("ARTCB_API_KEY") or "").strip()
    if len(raw) < 16:
        return {"present": False, "sha256_16": None, "len": len(raw)}
    return {
        "present": True,
        "sha256_16": hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16],
        "len": len(raw),
    }


def peer_restart_message(*, from_replica_id: str, ts_ns: int, target_hint: str) -> str:
    return f"{PEER_RESTART_PROTOCOL}|{from_replica_id}|{ts_ns}|{target_hint}"


def _schedule_exit(delay_s: float = 1.5) -> None:
    def _exit_later() -> None:
        time.sleep(delay_s)
        os._exit(42)

    threading.Thread(target=_exit_later, name="artcb-ops-self-restart", daemon=True).start()


def _rate_limit_or_429() -> None:
    global _LAST_RESTART_MONO
    now = time.monotonic()
    if now - _LAST_RESTART_MONO < _MIN_RESTART_GAP_S:
        raise HTTPException(status_code=429, detail="ops_restart_rate_limited")
    _LAST_RESTART_MONO = now


@router.get("/key-fingerprint", summary="Empreinte sha256_16 de ARTCB_API_KEY env (jamais la valeur)")
def key_fingerprint(
    actor: Annotated[dict | None, Depends(require_write_actor)] = None,
) -> dict[str, Any]:
    if actor is None:
        raise HTTPException(status_code=401, detail="ops_requires_bearer")
    return {
        "node_id": os.environ.get("ARTCB_NODE_ID") or None,
        "doppler_project": os.environ.get("DOPPLER_PROJECT") or None,
        "doppler_config": os.environ.get("DOPPLER_CONFIG") or None,
        "key": _key_fingerprint(),
        "ts_ns": now_wall_ns(),
        "note": "compare sha256_16 to local ~/.artcb/nodes/*.env without shipping secrets",
    }


@router.post(
    "/self-restart",
    summary="Quitte le process (Bearer local) pour systemd + doppler run",
)
async def self_restart(
    actor: Annotated[dict | None, Depends(require_write_actor)] = None,
) -> dict[str, Any]:
    t0 = now_mono_ns()
    if actor is None:
        raise HTTPException(status_code=401, detail="ops_requires_bearer")
    source = str(actor.get("source") or "")
    if source not in {"operator", "env", "api_key"}:
        scopes = actor.get("scopes") or []
        if "admin" not in scopes and "write" not in scopes:
            raise HTTPException(status_code=403, detail="ops_restart_forbidden")
    _rate_limit_or_429()
    delay_s = 1.5
    _schedule_exit(delay_s)
    return {
        "accepted": True,
        "action": "self_restart",
        "delay_s": delay_s,
        "node_id": os.environ.get("ARTCB_NODE_ID") or None,
        "key_before": _key_fingerprint(),
        "doppler_project": os.environ.get("DOPPLER_PROJECT") or None,
        "doppler_config": os.environ.get("DOPPLER_CONFIG") or None,
        "auth": source or actor.get("kind"),
        "ts_ns": now_wall_ns(),
        "dur_ns": now_mono_ns() - t0,
        "note": "systemd Restart=always expected; CERTIFIED_100 unchanged",
    }


@router.post(
    "/peer-restart",
    summary="Redémarrage demandé par une replica officielle (signature, pas API key étrangère)",
)
async def peer_restart(
    request: Request,
    x_artcb_replica_id: Annotated[str | None, Header()] = None,
    x_artcb_replica_sig: Annotated[str | None, Header()] = None,
    x_artcb_producer_ed25519: Annotated[str | None, Header()] = None,
    x_artcb_ops_ts_ns: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """R336 — same trust model as ``/concepts/peer-ingest``."""
    t0 = now_mono_ns()
    replica_id = (x_artcb_replica_id or "").strip()
    signature = (x_artcb_replica_sig or "").strip()
    ed_b64 = (x_artcb_producer_ed25519 or "").strip()
    try:
        ts_ns = int((x_artcb_ops_ts_ns or "0").strip())
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="ops_peer_ts_invalid") from exc

    if not replica_id or not signature or not ed_b64:
        raise HTTPException(status_code=401, detail="ops_peer_restart_requires_replica_signature")
    now = now_wall_ns()
    if ts_ns <= 0 or abs(now - ts_ns) > _MAX_SKEW_NS:
        raise HTTPException(status_code=401, detail="ops_peer_ts_stale_or_missing")

    host = (request.headers.get("host") or "").split(":")[0].lower()
    message = peer_restart_message(from_replica_id=replica_id, ts_ns=ts_ns, target_hint=host)

    from src.artcb.consensus.replica_identity import (
        expected_binding,
        official_pbft_replica_ids,
        verify_bound_signature,
    )

    if replica_id not in set(official_pbft_replica_ids()):
        raise HTTPException(status_code=403, detail="ops_peer_replica_not_official")
    expected = expected_binding(replica_id)
    if expected is None or expected.revoked:
        raise HTTPException(status_code=403, detail="ops_peer_replica_unregistered")
    ed_use = (expected.ed25519_b64 or ed_b64 or "").strip()
    ok, reason = verify_bound_signature(
        replica_id=replica_id,
        message=message,
        signature=signature,
        producer_ed25519_b64=ed_use,
        producer_pqc_b64="",
    )
    if not ok:
        raise HTTPException(status_code=403, detail=f"ops_peer_rejected:{reason}")

    _rate_limit_or_429()
    delay_s = 1.5
    _schedule_exit(delay_s)
    return {
        "accepted": True,
        "action": "peer_restart",
        "delay_s": delay_s,
        "from_replica_id": replica_id,
        "target_host": host,
        "protocol": PEER_RESTART_PROTOCOL,
        "key_before": _key_fingerprint(),
        "doppler_project": os.environ.get("DOPPLER_PROJECT") or None,
        "doppler_config": os.environ.get("DOPPLER_CONFIG") or None,
        "node_id": os.environ.get("ARTCB_NODE_ID") or None,
        "ts_ns": now_wall_ns(),
        "dur_ns": now_mono_ns() - t0,
        "note": "replica-signed restart over :443; not SSH; CERTIFIED_100 unchanged",
    }


@router.post(
    "/fanout-restart",
    summary="Depuis ce nœud, demande peer-restart signé vers les seeds (Bearer local)",
)
async def fanout_restart(
    request: Request,
    actor: Annotated[dict | None, Depends(require_write_actor)] = None,
) -> dict[str, Any]:
    """Publisher (usually ovh1) bounces peers over HTTPS with replica sig."""
    import urllib.error
    import urllib.request

    t0 = now_mono_ns()
    if actor is None:
        raise HTTPException(status_code=401, detail="ops_requires_bearer")

    from src.artcb.consensus.replica_identity import official_consensus_node_id
    from src.artcb.consensus.tip_attest import producer_key_b64, sign_message
    from src.api.concept_routes import DEFAULT_SEED_PEERS

    state = request.app.state.artcb
    chain = state.chain
    replica_id = official_consensus_node_id()
    if not replica_id:
        raise HTTPException(status_code=503, detail="local_replica_id_unknown")

    ts_ns = now_wall_ns()
    ed_b64, _pqc = producer_key_b64(chain)
    host = (request.headers.get("host") or "").split(":")[0].lower()
    peers_env = (os.getenv("ARTCB_OPS_RESTART_PEERS") or "").strip()
    peers = [p.strip() for p in peers_env.split(",") if p.strip()] or list(DEFAULT_SEED_PEERS)

    peer_rows: dict[str, Any] = {}
    ok_peers = 0
    for peer in peers:
        peer_host = peer.split("//", 1)[-1].split("/")[0].lower()
        if host and host == peer_host:
            peer_rows[peer] = {"skipped": "self"}
            continue
        message = peer_restart_message(from_replica_id=replica_id, ts_ns=ts_ns, target_hint=peer_host)
        signature = sign_message(chain, message)
        url = f"{peer.rstrip('/')}/api/v1/ops/peer-restart"
        req = urllib.request.Request(
            url,
            data=b"{}",
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "X-ARTCB-Replica-Id": replica_id,
                "X-ARTCB-Replica-Sig": signature,
                "X-ARTCB-Producer-Ed25519": ed_b64,
                "X-ARTCB-Ops-Ts-Ns": str(ts_ns),
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=45) as resp:
                body = resp.read().decode()
                peer_rows[peer] = {"http": int(resp.status), "ok": True, "body_preview": body[:240]}
                ok_peers += 1
        except urllib.error.HTTPError as exc:
            err_body = ""
            try:
                err_body = exc.read().decode()[:300]
            except Exception:  # noqa: BLE001
                pass
            peer_rows[peer] = {"http": int(exc.code), "ok": False, "body": err_body}
        except Exception as exc:  # noqa: BLE001
            peer_rows[peer] = {"http": 0, "ok": False, "error": type(exc).__name__, "detail": str(exc)[:160]}

    return {
        "from_replica_id": replica_id,
        "protocol": PEER_RESTART_PROTOCOL,
        "peers": peer_rows,
        "peers_ok": ok_peers,
        "fanout_restart_pass": ok_peers >= 3,
        "ts_ns": now_wall_ns(),
        "dur_ns": now_mono_ns() - t0,
        "published_by": actor.get("kind") or actor.get("source"),
        "note": "HTTPS :443 peer restart; keys reload only if doppler run injects ARTCB_API_KEY",
    }


# ---------------------------------------------------------------------------
# V-08 — déploiement TLS wildcard artcb.me (2026-09-16)
# ---------------------------------------------------------------------------

@router.post(
    "/deploy-tls",
    summary="V-08 : déployer le certificat TLS wildcard depuis les variables Doppler",
)
def deploy_tls(
    actor: Annotated[dict | None, Depends(require_write_actor)] = None,
) -> dict[str, Any]:
    """Lit ARTCB_TLS_CERT_WILDCARD + ARTCB_TLS_KEY_WILDCARD depuis l'environnement
    (injectés par doppler run) et configure nginx avec le certificat wildcard
    artcb.me + *.artcb.me.

    Auth : Bearer ARTCB_API_KEY (env/operator).
    Sécurité : ne log jamais la clé privée ; path fixe /etc/nginx/certs/artcb-wildcard.
    Idempotent : peut être rappelé sans danger.
    """
    import stat
    import subprocess as _sub

    t0 = now_mono_ns()
    if actor is None:
        raise HTTPException(status_code=401, detail="ops_requires_bearer")
    src = str(actor.get("source") or "")
    if src not in {"operator", "env", "api_key"}:
        scopes = actor.get("scopes") or []
        if "admin" not in scopes and "write" not in scopes:
            raise HTTPException(status_code=403, detail="ops_deploy_tls_forbidden")

    cert = os.environ.get("ARTCB_TLS_CERT_WILDCARD", "").strip()
    key  = os.environ.get("ARTCB_TLS_KEY_WILDCARD", "").strip()

    if not cert or not key:
        raise HTTPException(
            status_code=424,
            detail="deploy_tls_env_missing:ARTCB_TLS_CERT_WILDCARD or ARTCB_TLS_KEY_WILDCARD absent — inject via doppler run",
        )
    if "BEGIN CERTIFICATE" not in cert:
        raise HTTPException(status_code=422, detail="deploy_tls_cert_invalid:not a PEM certificate")
    if "BEGIN" not in key or "PRIVATE KEY" not in key:
        raise HTTPException(status_code=422, detail="deploy_tls_key_invalid:not a PEM private key")

    # Chemin : /etc/nginx/certs si root, sinon via sudo ou ~/.artcb/certs
    # nginx doit avoir accès en lecture aux fichiers de cert
    node_id   = os.environ.get("ARTCB_NODE_ID", "unknown")
    domain    = "artcb.me"

    # Détecter si sudo est disponible sans mot de passe (NOPASSWD sudoers)
    sudo_ok = _sub.run(["sudo", "-n", "true"], capture_output=True).returncode == 0
    is_root = os.geteuid() == 0

    if is_root or sudo_ok:
        cert_dir   = "/etc/nginx/certs/artcb-wildcard"
        nginx_conf = "/etc/nginx/conf.d/artcb-tls-wildcard.conf"
    else:
        # Pas de sudo disponible — écrire dans ARTCB_DATA_DIR, configurer via include nginx
        data_dir   = os.environ.get("ARTCB_DATA_DIR", os.path.expanduser("~"))
        cert_dir   = os.path.join(data_dir, ".artcb-certs", "artcb-wildcard")
        nginx_conf = None  # ne peut pas écrire dans /etc/nginx sans droits

    cert_file = f"{cert_dir}/fullchain.pem"
    key_file  = f"{cert_dir}/privkey.pem"

    steps: list[dict] = []

    def run_cmd(cmd: list[str]) -> tuple[int, str, str]:
        """Exécute une commande, préfixe sudo si nécessaire et pas root."""
        if not is_root and sudo_ok and cmd[0] != "sudo":
            cmd = ["sudo", "-n"] + cmd
        r = _sub.run(cmd, capture_output=True, text=True, timeout=15)
        return r.returncode, r.stdout, r.stderr

    # ── Écrire les fichiers de cert ──────────────────────────────────────────
    try:
        rc, _, err = run_cmd(["mkdir", "-p", cert_dir])
        if rc != 0:
            raise PermissionError(f"mkdir failed: {err}")
        # Écrire via fichier temp puis mv atomique
        import tempfile
        for fname, content, mode in [
            (cert_file, cert, "644"),
            (key_file,  key,  "600"),
        ]:
            with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".tmp") as tf:
                tf.write(content)
                tmp_path = tf.name
            run_cmd(["mv", tmp_path, fname])
            run_cmd(["chmod", mode, fname])
        steps.append({"step": "write_certs", "ok": True, "cert_dir": cert_dir})
    except Exception as exc:
        steps.append({"step": "write_certs", "ok": False, "error": str(exc)[:200]})
        raise HTTPException(status_code=500, detail=f"deploy_tls_write_failed:{exc}") from exc

    # ── Écrire la config nginx ────────────────────────────────────────────────
    if nginx_conf:
        nginx_conf_content = (
            f"# ARTCB wildcard TLS — généré par /ops/deploy-tls le "
            f"{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}\n"
            f"# node={node_id} domain={domain}\n"
            f"server {{\n"
            f"    listen 443 ssl;\n"
            f"    listen [::]:443 ssl;\n"
            f"    server_name {domain} www.{domain} n1.{domain} n2.{domain} "
            f"n3.{domain} n4.{domain} node.{domain} _;\n"
            f"    ssl_certificate     {cert_file};\n"
            f"    ssl_certificate_key {key_file};\n"
            f"    ssl_protocols       TLSv1.2 TLSv1.3;\n"
            f"    ssl_ciphers         HIGH:!aNULL:!MD5;\n"
            f"    ssl_prefer_server_ciphers on;\n"
            f"    ssl_session_cache   shared:SSL:10m;\n"
            f"    add_header Strict-Transport-Security "
            f'"max-age=15768000; includeSubDomains" always;\n'
            f"    location / {{\n"
            f"        proxy_pass http://127.0.0.1:8000;\n"
            f"        proxy_http_version 1.1;\n"
            f"        proxy_set_header Host $host;\n"
            f"        proxy_set_header X-Real-IP $remote_addr;\n"
            f"        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;\n"
            f"        proxy_set_header X-Forwarded-Proto https;\n"
            f"        proxy_set_header Authorization $http_authorization;\n"
            f"        proxy_pass_header Authorization;\n"
            f"        proxy_set_header Upgrade $http_upgrade;\n"
            f'        proxy_set_header Connection "upgrade";\n'
            f"        proxy_read_timeout 120s;\n"
            f"    }}\n"
            f"}}\n"
        )
        try:
            import tempfile
            with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".tmp") as tf:
                tf.write(nginx_conf_content)
                tmp_conf = tf.name
            run_cmd(["mv", tmp_conf, nginx_conf])
            steps.append({"step": "write_nginx_conf", "ok": True, "path": nginx_conf})
        except Exception as exc:
            steps.append({"step": "write_nginx_conf", "ok": False, "error": str(exc)[:200]})
            raise HTTPException(status_code=500, detail=f"deploy_tls_nginx_conf_failed:{exc}") from exc

        # ── Désactiver l'ancien fichier TLS sous-domaine (conflit server_name) ──
        # nginx charge les fichiers par ordre alpha — artcb-tls.conf < artcb-tls-wildcard.conf
        # → le wildcard est ignoré. On le renomme en 00-artcb-tls-wildcard.conf pour passer premier.
        new_nginx_conf = "/etc/nginx/conf.d/00-artcb-tls-wildcard.conf"
        old_conflicts = [
            "/etc/nginx/conf.d/artcb-tls.conf",
            "/etc/nginx/conf.d/artcb-tls-wildcard.conf",  # ancien nom de ce script
        ]
        # Déplacer vers le nom prioritaire si différent
        if nginx_conf != new_nginx_conf:
            run_cmd(["mv", nginx_conf, new_nginx_conf])
            nginx_conf = new_nginx_conf
            steps.append({"step": "rename_conf_priority", "ok": True, "path": nginx_conf})

        # Sauvegarder les anciens fichiers conflictuels
        for old in old_conflicts:
            if old != nginx_conf:
                bak = old + f".bak-v08-{time.strftime('%Y%m%d')}"
                rc2, _, _ = run_cmd(["test", "-f", old])
                if rc2 == 0:
                    run_cmd(["mv", old, bak])
                    steps.append({"step": "backup_old_conf", "ok": True, "old": old, "bak": bak})
    else:
        steps.append({
            "step": "write_nginx_conf", "ok": False,
            "error": "no_sudo_no_root — nginx_conf non écrit; configurer sudo NOPASSWD pour ubuntu",
        })

    # ── nginx -t ─────────────────────────────────────────────────────────────
    try:
        rc, stdout, stderr = run_cmd(["nginx", "-t"])
        ok = rc == 0
        steps.append({"step": "nginx_test", "ok": ok, "stderr": stderr[:300]})
        if not ok:
            raise HTTPException(status_code=500, detail=f"deploy_tls_nginx_test_failed:{stderr[:200]}")
    except FileNotFoundError:
        steps.append({"step": "nginx_test", "ok": False, "error": "nginx not found"})

    # ── systemctl reload nginx ───────────────────────────────────────────────
    reloaded = False
    for cmd in [["systemctl", "reload", "nginx"], ["nginx", "-s", "reload"]]:
        try:
            rc, _, err = run_cmd(cmd)
            if rc == 0:
                steps.append({"step": "nginx_reload", "ok": True, "cmd": cmd[0]})
                reloaded = True
                break
            steps.append({"step": "nginx_reload", "ok": False, "cmd": cmd[0], "stderr": err[:200]})
        except FileNotFoundError:
            continue
    if not reloaded:
        steps.append({"step": "nginx_reload", "ok": False, "error": "no reload method worked"})

    all_ok = all(s.get("ok", False) for s in steps)
    return {
        "deploy_tls_ok": all_ok,
        "node_id": node_id,
        "domain": domain,
        "cert_dir": cert_dir,
        "nginx_conf": nginx_conf,
        "cert_domains": os.environ.get("ARTCB_TLS_CERT_DOMAIN", "?"),
        "cert_expiry": os.environ.get("ARTCB_TLS_CERT_EXPIRY", "?"),
        "steps": steps,
        "ts_ns": now_wall_ns(),
        "dur_ns": now_mono_ns() - t0,
        "note": "Certificat wildcard déployé depuis ARTCB_TLS_CERT_WILDCARD (Doppler). Ne log pas la clé.",
        "certified_100": False,
    }


# ---------------------------------------------------------------------------
# V-PQC-2 — Preuve de contrôle ML-DSA-65 (R351)
# ---------------------------------------------------------------------------

@router.post(
    "/pqc-challenge",
    summary="V-PQC-2 : émettre un challenge ML-DSA-65 (nonce 32 octets, TTL 5 min)",
)
def pqc_challenge(request: Request) -> dict[str, Any]:
    """Étape 1/2 de V-PQC-2 : le serveur émet un nonce anti-rejeu.

    Le client doit ensuite appeler POST /ops/pqc-verify avec ce nonce pour
    prouver qu'il détient la clé privée ML-DSA-65 correspondant au wallet.
    Chaque nonce est à usage unique et expire dans 5 minutes.
    Rate-limit : 10 requêtes/minute/IP. Cap mémoire : 500 challenges actifs max.
    """
    now = time.time()

    # Rate-limit par IP
    client_ip = (request.client.host if request.client else "unknown")
    hits = _PQC_RATE.get(client_ip, [])
    hits = [t for t in hits if now - t < _PQC_RATE_WINDOW_S]
    if len(hits) >= _PQC_RATE_MAX:
        raise HTTPException(status_code=429, detail="pqc_challenge_rate_limited")
    hits.append(now)
    _PQC_RATE[client_ip] = hits

    # Purge des challenges expirés
    expired = [k for k, exp in list(_PQC_CHALLENGES.items()) if now > exp]
    for k in expired:
        _PQC_CHALLENGES.pop(k, None)

    # Cap mémoire anti-DoS
    if len(_PQC_CHALLENGES) >= _PQC_CHALLENGE_MAX:
        raise HTTPException(status_code=503, detail="pqc_challenge_capacity_exceeded")

    nonce = secrets.token_hex(32)  # 32 octets = 64 chars hex
    _PQC_CHALLENGES[nonce] = now + _PQC_CHALLENGE_TTL
    return {
        "challenge": nonce,
        "algorithm": "ML-DSA-65",
        "expires_in": _PQC_CHALLENGE_TTL,
        "instructions": (
            "Signez ce challenge (bytes.fromhex(challenge)) avec votre clé privée ML-DSA-65, "
            "puis POST /api/v1/ops/pqc-verify avec {challenge, wallet_name, [user_password]}."
        ),
        "ts_ns": now_wall_ns(),
    }


@router.post(
    "/pqc-verify",
    summary="V-PQC-2 : signer + vérifier le challenge ML-DSA-65 (preuve de contrôle PQC)",
)
def pqc_verify(body: PqcVerifyRequest, request: Request) -> dict[str, Any]:
    """Étape 2/2 de V-PQC-2 : le nœud signe le challenge avec sa clé PQC privée
    puis vérifie immédiatement la signature avec la clé publique.

    Prouve que ce nœud détient la clé privée ML-DSA-65 dont l'empreinte
    est enregistrée dans le wallet (pqc_public_key_hex).

    Résultat persisté dans le log debug — CERTIFIED_100 reste false tant que
    cette preuve n'est pas validée sur les 4 nœuds.
    """
    import logging as _logging
    _logger = _logging.getLogger("artcb.ops.vpqc2")

    t0 = now_mono_ns()

    # 1. Vérifier que le challenge est connu et non expiré
    exp = _PQC_CHALLENGES.get(body.challenge)
    if not exp:
        raise HTTPException(status_code=400, detail="vpqc2_challenge_unknown_or_already_used")
    if time.time() > exp:
        _PQC_CHALLENGES.pop(body.challenge, None)
        raise HTTPException(status_code=400, detail="vpqc2_challenge_expired")

    # 2. Vérifier que PQC est disponible sur ce nœud
    from src.artcb.crypto.pqc import pqc_available, sign_message as pqc_sign, verify_message as pqc_verify_msg
    if not pqc_available():
        raise HTTPException(
            status_code=503,
            detail="vpqc2_pqc_unavailable: liboqs ML-DSA-65 absent sur ce nœud — installer liboqs",
        )

    # 3. Charger le wallet (clé PQC privée chiffrée localement)
    from src.artcb.wallet.manager import WalletManager
    wm = WalletManager()
    try:
        wallet = wm.load_wallet(name=body.wallet_name, user_password=body.user_password)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"vpqc2_wallet_not_found: {body.wallet_name}")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"vpqc2_wallet_load_error: {exc}")

    # 4. Vérifier que ce wallet a une clé PQC
    if not wallet.pqc_secret_key or not wallet.pqc_public_key:
        raise HTTPException(
            status_code=422,
            detail="vpqc2_no_pqc_key: ce wallet n'a pas de clé ML-DSA-65 — recréer avec liboqs",
        )

    # 5. Signer le challenge avec la clé PQC privée
    challenge_bytes = bytes.fromhex(body.challenge)
    try:
        pqc_signature = pqc_sign(challenge_bytes, wallet.pqc_secret_key)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"vpqc2_sign_error: {exc}")

    # 6. Vérifier immédiatement la signature (preuve complète)
    try:
        verified = pqc_verify_msg(challenge_bytes, pqc_signature, wallet.pqc_public_key)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"vpqc2_verify_error: {exc}")

    # 7. Challenge consommé (usage unique)
    _PQC_CHALLENGES.pop(body.challenge, None)

    # 8. Résultat
    node_id = os.environ.get("ARTCB_NODE_ID") or "unknown"
    pqc_pub_hex = wallet.pqc_public_key.hex()
    sig_hex = pqc_signature.hex()
    dur_ns = now_mono_ns() - t0

    result: dict[str, Any] = {
        "vpqc2_pass": verified,
        "node_id": node_id,
        "wallet_name": body.wallet_name,
        "wallet_address": wallet.address,
        "wallet_address_v2": wallet.address_v2,
        "algorithm": "ML-DSA-65",
        "challenge": body.challenge,
        "pqc_public_key_hex": pqc_pub_hex,
        "pqc_public_key_len": len(wallet.pqc_public_key),
        "signature_hex": sig_hex[:64] + "...(truncated)",
        "signature_len": len(pqc_signature),
        "verified": verified,
        "ts_ns": now_wall_ns(),
        "dur_ns": dur_ns,
        "dur_ms": round(dur_ns / 1_000_000, 2),
        "note": (
            "V-PQC-2 PASS: contrôle clé privée ML-DSA-65 prouvé sur ce nœud. "
            "CERTIFIED_100 reste false jusqu'à validation sur les 4 nœuds."
        ) if verified else "V-PQC-2 FAIL: signature ML-DSA invalide",
    }

    if verified:
        _logger.info(
            "[V-PQC-2] PASS node=%s wallet=%s address=%s pqc_pub=%s... dur_ms=%.1f",
            node_id, body.wallet_name, wallet.address, pqc_pub_hex[:16], dur_ns / 1_000_000,
        )
    else:
        _logger.error("[V-PQC-2] FAIL node=%s wallet=%s", node_id, body.wallet_name)
        raise HTTPException(status_code=500, detail="vpqc2_signature_verification_failed")

    return result


# ── GO-E V-01-B : route de production failover ────────────────────────────────

@router.post(
    "/failover-produce",
    summary="GO-E V-01-B : tente de produire un bloc de secours (Bearer opérateur)",
)
def failover_produce(request: Request) -> dict[str, Any]:
    """Déclenche manuellement maybe_produce() du ProducerFailoverRuntime.

    Conditions : ARTCB_PRODUCER_FAILOVER_LIVE=true + ARTCB_PRODUCER_FAILOVER_PRODUCE=true
    + le producteur actif doit être mort (heartbeat_timeout dépassé).
    La grace period doit être expirée (30s par défaut après élection).
    """
    from src.api.api_keys_routes import require_write_actor

    actor: dict | None = None
    auth = request.headers.get("authorization", "")
    if auth:
        try:
            actor = require_write_actor(request, authorization=auth)
        except Exception:
            from fastapi import HTTPException
            raise HTTPException(status_code=401, detail="ops_requires_bearer")
    if actor is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=401, detail="ops_requires_bearer")
    source = str(actor.get("source") or "")
    if source not in {"operator", "env", "api_key"}:
        scopes = actor.get("scopes") or []
        if "admin" not in scopes and "write" not in scopes:
            from fastapi import HTTPException
            raise HTTPException(status_code=403, detail="ops_restart_forbidden")

    state = request.app.state.artcb
    runtime = getattr(state, "producer_failover", None)
    if runtime is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=503, detail="failover_runtime_unavailable")

    chain = getattr(state, "chain", None)
    result = runtime.maybe_produce(chain=chain)
    return {
        "ok": result.get("appended", False),
        "result": result,
        "node_id": getattr(state.p2p_identity, "node_id", "?") if state else "?",
        "ts_ns": now_wall_ns(),
    }


@router.get(
    "/failover-status",
    summary="GO-E V-01-B : état du ProducerFailoverRuntime",
)
def failover_status(request: Request) -> dict[str, Any]:
    """Retourne l'état du ProducerFailoverRuntime : monitor, last_produce_result, etc."""
    state = request.app.state.artcb
    runtime = getattr(state, "producer_failover", None)
    if runtime is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=503, detail="failover_runtime_unavailable")
    return {
        "ok": True,
        "status": runtime.status(),
        "node_id": getattr(state.p2p_identity, "node_id", "?") if state else "?",
        "ts_ns": now_wall_ns(),
    }
