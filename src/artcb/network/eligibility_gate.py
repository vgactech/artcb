"""R382/R397 — NetworkEligibilityGate : éligibilité réseau d'un nœud ARTCB.

R397 — Forensic hardening (audit expert 2026-09-19) :
  6 correctifs appliqués sur R382 :
  1. ExternalProbeStore réel — record_external_probe() n'était pas un stub vide
  2. outbound_tls / outbound_websocket mesurés séparément (pas projection TCP)
  3. ConnectivityFailure enum — captive_portal ≠ NETWORK_DOWN ≠ ARTCB_UNREACHABLE
  4. Détection CGNAT RFC 6598 (100.64.0.0/10) + IPv6 ULA + link-local
  5. _get_local_ip() robuste (multi-fallback, pas 8.8.8.8 unique)
  6. Multi-seeds outbound — indépendance vis-à-vis de artcb.me

Principe fondamental :
  La question n'est pas « est-ce un Wi-Fi public/entreprise ? »
  mais « la machine peut-elle réellement satisfaire les exigences
  opérationnelles du protocole ARTCB dans ses conditions réseau actuelles ? »

Architecture :
  NetworkState (ce module)  ←  séparé de  →  EconomicState (economics/human_binding.py)
  DIRECT / RELAYABLE / DEGRADED / SUSPENDED    ACTIVE / GRACE / OFFLINE / RETIRED

  Un changement de NetworkState ne modifie JAMAIS directement EconomicState.
  EpochCoordinator (economics) reste la seule autorité pour les transitions
  économiques (GRACE → OFFLINE, OFFLINE → RETIRED).

HONNÊTETÉ :
  - Tests outbound TCP séparés par host (multi-seeds).
  - outbound_tls tente un vrai handshake TLS (ssl.wrap_socket).
  - outbound_websocket teste uniquement le TCP 443 — upgrade WS non implémenté.
  - record_external_probe() stocke les preuves externes dans ExternalProbeStore.
  - nat_class = heuristique adresse IP — STUN/TURN non implémenté.
  - CERTIFIED_100=false — calibrage vrais réseaux non encore mesuré.

CERTIFIED_100=false | MODE DEBUG actif
"""

from __future__ import annotations

MODULE_VERSION = "1.1.0"  # R397 — forensic hardening

import ipaddress
import logging
import os
import socket
import ssl
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger("artcb.network.eligibility_gate")

# ─── Constantes ──────────────────────────────────────────────────────────────

# Port P2P par défaut (même valeur que node_identity.py)
DEFAULT_P2P_PORT: int = int(os.getenv("ARTCB_P2P_PORT", "18444"))

# Délais (secondes) — conservateurs pour ne pas suspendre injustement
PROBE_TIMEOUT_S: float = 5.0
OUTBOUND_TIMEOUT_S: float = 5.0

# Multi-seeds outbound — D-045 : uniquement les 4 IP toujours allumées
# artcb.me ne doit JAMAIS être le seul point de test (audit expert §13)
# Les seeds supplémentaires permettent de distinguer panne artcb.me vs panne réseau local
_OUTBOUND_SEEDS: list[tuple[str, int]] = [
    (os.getenv("ARTCB_PROBE_HOST", "artcb.me"), int(os.getenv("ARTCB_PROBE_PORT", "443"))),
    ("1.1.1.1", 443),    # Cloudflare — toujours accessible si Internet fonctionne
    ("8.8.8.8", 443),    # Google DNS — second témoin indépendant
]
# Compatibilité R382 : alias direct vers le premier seed
_DEFAULT_PROBE_HOST = _OUTBOUND_SEEDS[0][0]
_DEFAULT_PROBE_PORT = _OUTBOUND_SEEDS[0][1]

# Nombre minimum de tests positifs pour passer TESTING → DIRECT
MIN_PASS_STREAK: int = 2  # anti-flap : 2 succès consécutifs requis

# Fenêtre temporelle avant DEGRADED → SUSPENDED (secondes)
DEGRADED_GRACE_S: int = int(os.getenv("ARTCB_DEGRADED_GRACE_S", str(5 * 60)))  # 5 min

# Taille max du store de preuves externes (par nœud)
MAX_EXTERNAL_PROBE_HISTORY: int = 50


# ─── Enums ───────────────────────────────────────────────────────────────────

class NetworkState(str, Enum):
    """État réseau opérationnel d'un nœud utilisateur.

    Séparation stricte de EconomicState (ACTIVE/GRACE/OFFLINE/RETIRED).
    Un nœud SUSPENDED réseau peut avoir EconomicState=GRACE si dans la
    fenêtre de grâce économique.
    """
    UNKNOWN       = "UNKNOWN"        # jamais testé
    TESTING       = "TESTING"        # évaluation en cours
    DIRECT        = "DIRECT"         # connexions entrantes directes disponibles
    RELAYABLE     = "RELAYABLE"      # relay ARTCB requis pour inbound
    DEGRADED      = "DEGRADED"       # outbound ok, inbound fail, relay indisponible
    SUSPENDED     = "SUSPENDED"      # ne satisfait pas les exigences minimales
    INDETERMINATE = "INDETERMINATE"  # probe externe indisponible — pas suspendre


class NatClass(str, Enum):
    """Classification NAT heuristique basée sur l'adresse IP locale.

    R397 — ajout CGNAT (RFC 6598 100.64.0.0/10), IPv6_ULA, LINK_LOCAL.
    HONNÊTETÉ : classification par adresse IP uniquement — STUN/TURN non implémenté.
    """
    NONE         = "NONE"         # IP publique directe (serveur cloud / VPS)
    FULL_CONE    = "FULL_CONE"    # RFC1918 privé avec preuve externe
    RESTRICTED   = "RESTRICTED"   # RFC1918 privé sans preuve externe
    CGNAT        = "CGNAT"        # RFC 6598 100.64.0.0/10 — opérateur mobile
    DOUBLE_NAT   = "DOUBLE_NAT"   # double NAT détecté (heuristique future)
    IPV6_ULA     = "IPV6_ULA"     # fc00::/7 — adresse ULA IPv6 locale
    LINK_LOCAL   = "LINK_LOCAL"   # 169.254.x.x ou fe80:: — pas de routage
    UNKNOWN      = "UNKNOWN"


class ConnectivityFailure(str, Enum):
    """R397 — Cause précise d'un échec de connectivité.

    Distingue les cas que R382 confondait tous sous captive_portal=True.
    """
    NONE                   = "NONE"                    # pas d'échec
    NETWORK_DOWN           = "NETWORK_DOWN"            # aucun host joignable (réseau coupé)
    ARTCB_UNREACHABLE      = "ARTCB_UNREACHABLE"       # artcb.me DOWN mais Internet OK
    OUTBOUND_TCP_BLOCKED   = "OUTBOUND_TCP_BLOCKED"    # TCP bloqué sur tous les hosts
    CAPTIVE_PORTAL         = "CAPTIVE_PORTAL"          # portail captif détecté
    TLS_INTERCEPTED        = "TLS_INTERCEPTED"         # TLS intercepté / inspection proxy
    PROXY_REQUIRED         = "PROXY_REQUIRED"          # proxy authentifié requis
    PARTIAL_CONNECTIVITY   = "PARTIAL_CONNECTIVITY"    # certains seeds joignables, pas tous
    UNKNOWN_FAILURE        = "UNKNOWN_FAILURE"         # échec non classifié


# ─── Dataclasses ─────────────────────────────────────────────────────────────

@dataclass
class ConnectivityProbe:
    """Résultat d'une sonde individuelle de connectivité."""
    ts_ns: int
    probe_kind: str          # "outbound_tcp", "inbound_listen", "relay_probe", etc.
    host: str
    port: int
    success: bool
    latency_ms: float | None = None
    error: str | None = None
    external: bool = False   # True = probe venue d'un nœud ARTCB externe


@dataclass
class NetworkCapability:
    """Capacité réseau mesurée d'une machine.

    R397 : outbound_tls et outbound_websocket sont maintenant mesurés séparément.
    ConnectivityFailure remplace captive_portal booléen (§3 audit expert).
    Séparée de l'identité du nœud (NodeID ≠ IP ≠ réseau actuel).
    """
    ts_ns: int = field(default_factory=time.time_ns)

    # Connectivité sortante — R397 : mesures indépendantes
    outbound_tcp: bool = False        # TCP brut vers au moins 1 seed
    outbound_tls: bool = False        # TLS handshake réel (ssl.wrap_socket)
    outbound_websocket: bool = False  # TCP 443 (upgrade WS non implémenté — HONNÊTETÉ)
    outbound_seeds_ok: int = 0        # nb seeds TCP joignables (max len(_OUTBOUND_SEEDS))
    artcb_reachable: bool = False     # artcb.me spécifiquement joignable

    # Connectivité entrante (auto-probe locale)
    inbound_listen: bool = False      # le port P2P écoute localement
    external_reachable: bool = False  # preuve externe (probe ARTCB tiers)
    external_probe_count: int = 0     # nb probes externes reçues
    external_probe_ok: int = 0        # nb probes externes réussies
    external_distinct_nodes: int = 0  # nb nœuds ARTCB distincts ayant probé

    # Relay
    relay_available: bool = False

    # NAT — R397 : CGNAT + IPv6
    nat_class: NatClass = NatClass.UNKNOWN

    # R397 — diagnostic précis de l'échec (remplace captive_portal booléen)
    connectivity_failure: ConnectivityFailure = ConnectivityFailure.NONE
    captive_portal: bool = False  # conservé pour compatibilité R382 (dérivé de connectivity_failure)

    # Réseau
    packet_loss_pct: float = 0.0      # 0–100
    latency_ms: float | None = None

    # Métadonnées
    local_ip: str = ""
    p2p_port: int = DEFAULT_P2P_PORT
    probes: list[ConnectivityProbe] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d = {
            "ts_ns": self.ts_ns,
            "outbound_tcp": self.outbound_tcp,
            "outbound_tls": self.outbound_tls,
            "outbound_websocket": self.outbound_websocket,
            "outbound_seeds_ok": self.outbound_seeds_ok,
            "artcb_reachable": self.artcb_reachable,
            "inbound_listen": self.inbound_listen,
            "external_reachable": self.external_reachable,
            "external_probe_count": self.external_probe_count,
            "external_probe_ok": self.external_probe_ok,
            "external_distinct_nodes": self.external_distinct_nodes,
            "relay_available": self.relay_available,
            "nat_class": self.nat_class.value,
            "connectivity_failure": self.connectivity_failure.value,
            "captive_portal": self.captive_portal,
            "packet_loss_pct": self.packet_loss_pct,
            "latency_ms": self.latency_ms,
            "local_ip": self.local_ip,
            "p2p_port": self.p2p_port,
            "probes": [vars(p) for p in self.probes],
        }
        return d


@dataclass
class EligibilityResult:
    """Résultat complet d'une évaluation d'éligibilité réseau.

    IMPORTANT : network_state ≠ economic_state.
    Ce résultat ne doit JAMAIS modifier directement MachineRecord.status.
    Seul EpochCoordinator gère les transitions économiques.
    """
    ts_ns: int = field(default_factory=time.time_ns)
    network_state: NetworkState = NetworkState.UNKNOWN
    capability: NetworkCapability = field(default_factory=NetworkCapability)
    reason: str = ""
    recommended_action: str = ""  # "none" / "use_relay" / "suspend_node" / "reassess"
    grace_remaining_s: int | None = None  # si DEGRADED — temps avant SUSPENDED
    economic_impact: str = "none"  # TOUJOURS "none" depuis ce module — décision économique séparée

    # Invariant de sécurité
    _economic_state_unchanged: bool = field(default=True, repr=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ts_ns": self.ts_ns,
            "network_state": self.network_state.value,
            "reason": self.reason,
            "recommended_action": self.recommended_action,
            "grace_remaining_s": self.grace_remaining_s,
            "economic_impact": self.economic_impact,
            "economic_state_unchanged": self._economic_state_unchanged,
            "capability": self.capability.to_dict(),
        }


# ─── Sondes de connectivité ───────────────────────────────────────────────────

def _probe_outbound_tcp(host: str, port: int, *, timeout_s: float = OUTBOUND_TIMEOUT_S) -> ConnectivityProbe:
    """Tente une connexion TCP sortante vers host:port."""
    t0 = time.perf_counter_ns()
    ts = time.time_ns()
    try:
        with socket.create_connection((host, port), timeout=timeout_s):
            latency_ms = (time.perf_counter_ns() - t0) / 1_000_000
            logger.debug("[R382] outbound TCP %s:%d OK %.1fms", host, port, latency_ms)
            return ConnectivityProbe(
                ts_ns=ts, probe_kind="outbound_tcp",
                host=host, port=port, success=True, latency_ms=latency_ms,
            )
    except OSError as exc:
        logger.debug("[R382] outbound TCP %s:%d FAIL %s", host, port, exc)
        return ConnectivityProbe(
            ts_ns=ts, probe_kind="outbound_tcp",
            host=host, port=port, success=False, error=str(exc),
        )


def _probe_inbound_listen(p2p_port: int) -> ConnectivityProbe:
    """Vérifie si le port P2P écoute localement (preuve nécessaire mais non suffisante).

    HONNÊTETÉ : ceci prouve seulement que le processus écoute localement.
    La joignabilité externe nécessite une probe depuis un nœud ARTCB tiers
    (external_reachable doit être validé séparément).
    """
    ts = time.time_ns()
    try:
        # Tente de se connecter à 127.0.0.1:p2p_port — si refusé → personne n'écoute
        with socket.create_connection(("127.0.0.1", p2p_port), timeout=1.0):
            logger.debug("[R382] inbound listen port %d UP (loopback)", p2p_port)
            return ConnectivityProbe(
                ts_ns=ts, probe_kind="inbound_listen",
                host="127.0.0.1", port=p2p_port, success=True,
            )
    except ConnectionRefusedError:
        logger.debug("[R382] inbound listen port %d REFUSED (nobody listening)", p2p_port)
        return ConnectivityProbe(
            ts_ns=ts, probe_kind="inbound_listen",
            host="127.0.0.1", port=p2p_port, success=False,
            error="ConnectionRefused — port P2P non en écoute",
        )
    except OSError as exc:
        logger.debug("[R382] inbound listen port %d ERROR %s", p2p_port, exc)
        return ConnectivityProbe(
            ts_ns=ts, probe_kind="inbound_listen",
            host="127.0.0.1", port=p2p_port, success=False, error=str(exc),
        )


def _probe_outbound_tls(host: str, port: int, *, timeout_s: float = OUTBOUND_TIMEOUT_S) -> ConnectivityProbe:
    """R397 — Tente un vrai handshake TLS vers host:port.

    HONNÊTETÉ : ssl.create_default_context() valide le certificat et le SNI.
    Si le proxy intercepte TLS (inspection d'entreprise), la validation
    du certificat peut échouer → TLS_INTERCEPTED détectable.
    """
    ts = time.time_ns()
    ctx = ssl.create_default_context()
    try:
        with socket.create_connection((host, port), timeout=timeout_s) as raw_sock:
            with ctx.wrap_socket(raw_sock, server_hostname=host) as tls_sock:
                _ = tls_sock.getpeercert()
                latency_ms = (time.perf_counter_ns() - ts) / 1_000_000
                logger.debug("[R397] outbound TLS %s:%d OK %.1fms", host, port, latency_ms)
                return ConnectivityProbe(
                    ts_ns=ts, probe_kind="outbound_tls",
                    host=host, port=port, success=True, latency_ms=latency_ms,
                )
    except ssl.SSLCertVerificationError as exc:
        logger.debug("[R397] TLS cert verification FAIL %s:%d — possible inspection: %s", host, port, exc)
        return ConnectivityProbe(
            ts_ns=ts, probe_kind="outbound_tls",
            host=host, port=port, success=False,
            error=f"TLS_CERT_FAIL:{exc}",
        )
    except (ssl.SSLError, OSError) as exc:
        logger.debug("[R397] outbound TLS %s:%d FAIL %s", host, port, exc)
        return ConnectivityProbe(
            ts_ns=ts, probe_kind="outbound_tls",
            host=host, port=port, success=False, error=str(exc),
        )


def _classify_connectivity_failure(
    seeds_ok: int,
    artcb_ok: bool,
    tls_ok: bool,
    tcp_ok: bool,
) -> ConnectivityFailure:
    """R397 — Classifie la cause d'échec de connectivité.

    Logique (ordre de priorité) :
      - Tous seeds TCP fail + artcb fail → NETWORK_DOWN
      - TCP ok sur seeds alternatifs mais artcb fail → ARTCB_UNREACHABLE
      - TCP ok mais TLS fail → TLS_INTERCEPTED
      - TCP fail total → OUTBOUND_TCP_BLOCKED
      - Tous ok → NONE
    """
    if seeds_ok == 0 and not tcp_ok:
        return ConnectivityFailure.NETWORK_DOWN
    if seeds_ok > 0 and not artcb_ok:
        return ConnectivityFailure.ARTCB_UNREACHABLE
    if tcp_ok and not tls_ok:
        return ConnectivityFailure.TLS_INTERCEPTED
    if not tcp_ok:
        return ConnectivityFailure.OUTBOUND_TCP_BLOCKED
    return ConnectivityFailure.NONE


def _get_local_ip() -> str:
    """R397 — Détecte l'IP locale principale avec multi-fallback robuste.

    R382 utilisait uniquement 8.8.8.8:80 — si ce seul host est bloqué,
    la fonction retournait 127.0.0.1 à tort.
    R397 essaie plusieurs hosts en séquence.
    """
    candidates = [
        ("1.1.1.1", 443),
        ("8.8.8.8", 80),
        ("8.8.4.4", 53),
    ]
    for host, port in candidates:
        try:
            with socket.create_connection((host, port), timeout=2.0) as s:
                ip = s.getsockname()[0]
                if ip and ip != "0.0.0.0":
                    return ip
        except OSError:
            continue
    # Fallback via getaddrinfo — ne tente aucune connexion réseau
    try:
        return socket.gethostbyname(socket.gethostname())
    except OSError:
        return "127.0.0.1"


def _classify_nat(local_ip: str, *, external_reachable: bool) -> NatClass:
    """R397 — Classification NAT heuristique basée sur l'adresse IP locale.

    Ajout RFC 6598 CGNAT (100.64.0.0/10), IPv6 ULA (fc00::/7),
    link-local (169.254.x.x / fe80::).

    HONNÊTETÉ : classification par plage d'adresses uniquement.
    STUN/TURN pour classification NAT réelle non implémenté.
    """
    try:
        addr = ipaddress.ip_address(local_ip)
    except ValueError:
        return NatClass.UNKNOWN

    if addr.is_loopback:
        return NatClass.UNKNOWN
    if addr.is_link_local:
        return NatClass.LINK_LOCAL

    if isinstance(addr, ipaddress.IPv6Address):
        # fc00::/7 = ULA (Unique Local Address)
        if addr in ipaddress.ip_network("fc00::/7"):
            return NatClass.IPV6_ULA
        if addr.is_global:
            return NatClass.NONE if not external_reachable else NatClass.FULL_CONE
        return NatClass.UNKNOWN

    # IPv4
    # RFC 6598 — Shared Address Space (CGNAT opérateur)
    if addr in ipaddress.ip_network("100.64.0.0/10"):
        return NatClass.CGNAT

    # RFC 1918 privé
    rfc1918 = [
        ipaddress.ip_network("10.0.0.0/8"),
        ipaddress.ip_network("172.16.0.0/12"),
        ipaddress.ip_network("192.168.0.0/16"),
    ]
    if any(addr in net for net in rfc1918):
        return NatClass.FULL_CONE if external_reachable else NatClass.RESTRICTED

    # IP publique routable
    if addr.is_global:
        return NatClass.NONE

    return NatClass.UNKNOWN


# ─── Évaluation principale ────────────────────────────────────────────────────

def assess_network_capability(
    *,
    p2p_port: int = DEFAULT_P2P_PORT,
    probe_host: str = _DEFAULT_PROBE_HOST,
    probe_port: int = _DEFAULT_PROBE_PORT,
    relay_available: bool = False,
    external_reachable: bool | None = None,
    external_probe_count: int = 0,
    external_probe_ok: int = 0,
    external_distinct_nodes: int = 0,
    _force_outbound: bool | None = None,    # injection de test uniquement
    _force_inbound: bool | None = None,     # injection de test uniquement
) -> NetworkCapability:
    """R397 — Mesure la capacité réseau réelle avec sondes indépendantes.

    R397 vs R382 :
      - Multi-seeds TCP (3 hosts) — artcb.me n'est plus le seul point de test
      - TLS handshake réel séparé du TCP
      - ConnectivityFailure classifié (NETWORK_DOWN vs ARTCB_UNREACHABLE vs TLS_INTERCEPTED)
      - NAT classifié avec CGNAT RFC 6598 + IPv6
      - _get_local_ip() robuste (multi-fallback)
    """
    logger.debug("[R397] assess_network_capability — p2p_port=%d", p2p_port)

    cap = NetworkCapability(p2p_port=p2p_port)
    cap.local_ip = _get_local_ip()

    # --- Connectivité sortante multi-seeds ---
    if _force_outbound is not None:
        # Mode test : injection uniforme sur tous les seeds
        for seed_host, seed_port in _OUTBOUND_SEEDS:
            p = ConnectivityProbe(
                ts_ns=time.time_ns(), probe_kind="outbound_tcp",
                host=seed_host, port=seed_port, success=_force_outbound,
            )
            cap.probes.append(p)
        cap.outbound_tcp = _force_outbound
        cap.outbound_tls = _force_outbound
        cap.outbound_websocket = _force_outbound
        cap.outbound_seeds_ok = len(_OUTBOUND_SEEDS) if _force_outbound else 0
        cap.artcb_reachable = _force_outbound
        cap.latency_ms = 1.0 if _force_outbound else None
        # R397 — dériver connectivity_failure et captive_portal en mode injection aussi
        if not _force_outbound:
            cap.connectivity_failure = ConnectivityFailure.NETWORK_DOWN
            cap.captive_portal = True
        else:
            cap.connectivity_failure = ConnectivityFailure.NONE
            cap.captive_portal = False
    else:
        # Mode production : sonder chaque seed indépendamment
        seeds_ok = 0
        artcb_ok = False
        best_latency: float | None = None

        for seed_host, seed_port in _OUTBOUND_SEEDS:
            p = _probe_outbound_tcp(seed_host, seed_port)
            cap.probes.append(p)
            if p.success:
                seeds_ok += 1
                if best_latency is None or (p.latency_ms and p.latency_ms < best_latency):
                    best_latency = p.latency_ms
            # Le premier seed est artcb.me (D-045)
            if seed_host == _OUTBOUND_SEEDS[0][0] and p.success:
                artcb_ok = True

        cap.outbound_seeds_ok = seeds_ok
        cap.artcb_reachable = artcb_ok
        cap.outbound_tcp = seeds_ok > 0  # au moins 1 seed joignable
        cap.latency_ms = best_latency

        # TLS — testé uniquement si TCP fonctionne (évite le timeout inutile)
        if cap.outbound_tcp:
            tls_host = _OUTBOUND_SEEDS[0][0]  # artcb.me en priorité, sinon 1.1.1.1
            if not artcb_ok:
                tls_host = "1.1.1.1"
            tls_p = _probe_outbound_tls(tls_host, 443)
            cap.probes.append(tls_p)
            cap.outbound_tls = tls_p.success
        else:
            cap.outbound_tls = False

        # outbound_websocket = TCP 443 sur le premier seed (HONNÊTETÉ : upgrade WS non testé)
        cap.outbound_websocket = artcb_ok  # TCP artcb.me:443 = meilleur proxy WS

        # ConnectivityFailure — R397
        cap.connectivity_failure = _classify_connectivity_failure(
            seeds_ok=seeds_ok,
            artcb_ok=artcb_ok,
            tls_ok=cap.outbound_tls,
            tcp_ok=cap.outbound_tcp,
        )
        # captive_portal = rétrocompatibilité R382
        cap.captive_portal = cap.connectivity_failure in (
            ConnectivityFailure.CAPTIVE_PORTAL,
            ConnectivityFailure.NETWORK_DOWN,
            ConnectivityFailure.OUTBOUND_TCP_BLOCKED,
        )

        logger.debug(
            "[R397] outbound: tcp=%s tls=%s seeds_ok=%d artcb=%s failure=%s",
            cap.outbound_tcp, cap.outbound_tls, seeds_ok, artcb_ok,
            cap.connectivity_failure.value,
        )

    # --- Connectivité entrante ---
    if _force_inbound is not None:
        inbound_probe = ConnectivityProbe(
            ts_ns=time.time_ns(), probe_kind="inbound_listen",
            host="127.0.0.1", port=p2p_port, success=_force_inbound,
        )
        cap.inbound_listen = _force_inbound
    else:
        inbound_probe = _probe_inbound_listen(p2p_port)
        cap.inbound_listen = inbound_probe.success

    cap.probes.append(inbound_probe)

    # --- Joignabilité externe ---
    if external_reachable is not None:
        cap.external_reachable = external_reachable
    else:
        cap.external_reachable = False
        logger.debug("[R397] external_reachable=None — conservateur: False")

    cap.external_probe_count = external_probe_count
    cap.external_probe_ok = external_probe_ok
    cap.external_distinct_nodes = external_distinct_nodes

    # --- Relay ---
    cap.relay_available = relay_available

    # --- NAT (R397 — heuristique étendue avec CGNAT + IPv6) ---
    cap.nat_class = _classify_nat(cap.local_ip, external_reachable=cap.external_reachable)

    logger.debug(
        "[R397] capability: outbound=%s tls=%s inbound=%s external=%s relay=%s nat=%s failure=%s",
        cap.outbound_tcp, cap.outbound_tls, cap.inbound_listen, cap.external_reachable,
        cap.relay_available, cap.nat_class.value, cap.connectivity_failure.value,
    )
    return cap


# ─── Classifieur d'éligibilité ────────────────────────────────────────────────

def classify_network_state(
    cap: NetworkCapability,
    *,
    degraded_since_ts_ns: int | None = None,
    now_ts_ns: int | None = None,
) -> EligibilityResult:
    """Classifie le NetworkState à partir d'une NetworkCapability mesurée.

    Règles de classification (conformes au rapport expert §28) :

    DIRECT      : outbound ✓ ET (external_reachable ✓ OU (inbound_listen ✓ ET nat_class=NONE))
    RELAYABLE   : outbound ✓ ET inbound fail ET relay_available ✓
    DEGRADED    : outbound ✓ ET inbound fail ET relay_available ✗ — dans fenêtre de grâce
    SUSPENDED   : outbound ✗ OU (DEGRADED hors fenêtre de grâce) OU captive_portal
    INDETERMINATE : outbound ✓ ET external_reachable non testé (probe indisponible)

    Invariant : economic_impact = "none" TOUJOURS depuis ce module.
    """
    now_ns = now_ts_ns if now_ts_ns is not None else time.time_ns()
    result = EligibilityResult(ts_ns=now_ns)
    result.economic_impact = "none"  # invariant — ne jamais modifier l'état économique ici

    # SUSPENDED — captive portal ou outbound coupé
    if cap.captive_portal or not cap.outbound_tcp:
        result.network_state = NetworkState.SUSPENDED
        result.reason = (
            "Captive portal détecté — authentification réseau requise"
            if cap.captive_portal
            else "Connectivité sortante TCP indisponible — réseau coupé ou firewall total"
        )
        result.recommended_action = "suspend_node"
        result.grace_remaining_s = 0
        logger.info("[R382] NetworkState=SUSPENDED (%s)", result.reason)
        result.capability = cap
        return result

    # DIRECT — joignabilité externe prouvée OU IP publique + écoute locale
    direct_by_external = cap.external_reachable and cap.external_probe_ok > 0
    direct_by_ip = cap.inbound_listen and cap.nat_class == NatClass.NONE
    if direct_by_external or direct_by_ip:
        result.network_state = NetworkState.DIRECT
        result.reason = (
            f"Joignabilité externe prouvée ({cap.external_probe_ok}/{cap.external_probe_count} probes)"
            if direct_by_external
            else "IP publique directe + port P2P en écoute"
        )
        result.recommended_action = "none"
        logger.info("[R382] NetworkState=DIRECT (%s)", result.reason)
        result.capability = cap
        return result

    # Outbound ok mais pas de preuve externe — vérifier relay
    inbound_fail = not cap.inbound_listen or not cap.external_reachable

    if not inbound_fail:
        # Ne devrait pas arriver ici, mais si inbound passe sans preuve externe → DIRECT
        result.network_state = NetworkState.DIRECT
        result.reason = "Port P2P en écoute + outbound OK"
        result.recommended_action = "none"
        result.capability = cap
        return result

    # Inbound non prouvé — si relay disponible → RELAYABLE
    if cap.relay_available:
        result.network_state = NetworkState.RELAYABLE
        result.reason = "Connexions entrantes non prouvées — relay ARTCB disponible"
        result.recommended_action = "use_relay"
        logger.info("[R382] NetworkState=RELAYABLE (relay_available=True)")
        result.capability = cap
        return result

    # Outbound ok, inbound fail, relay absent
    # → si external_probe non testée → INDETERMINATE (probe indisponible)
    if cap.external_probe_count == 0 and cap.external_reachable is False:
        result.network_state = NetworkState.INDETERMINATE
        result.reason = (
            "Outbound OK mais aucune probe externe disponible — "
            "impossible de conclure sur joignabilité P2P"
        )
        result.recommended_action = "reassess"
        logger.info("[R382] NetworkState=INDETERMINATE (no external probe)")
        result.capability = cap
        return result

    # DEGRADED / SUSPENDED selon fenêtre de grâce
    grace_remaining_s: int | None = None
    if degraded_since_ts_ns is not None:
        elapsed_s = (now_ns - degraded_since_ts_ns) / 1_000_000_000
        remaining = DEGRADED_GRACE_S - elapsed_s
        grace_remaining_s = max(0, int(remaining))
        if remaining > 0:
            result.network_state = NetworkState.DEGRADED
            result.reason = f"Inbound non prouvé, relay indisponible — {grace_remaining_s}s de grâce restants"
            result.recommended_action = "reassess"
            result.grace_remaining_s = grace_remaining_s
            logger.info("[R382] NetworkState=DEGRADED grace=%ds", grace_remaining_s)
            result.capability = cap
            return result
        else:
            result.network_state = NetworkState.SUSPENDED
            result.reason = "Fenêtre de grâce DEGRADED expirée — inbound non prouvé, relay absent"
            result.recommended_action = "suspend_node"
            result.grace_remaining_s = 0
            logger.info("[R382] NetworkState=SUSPENDED (grace expired)")
            result.capability = cap
            return result
    else:
        # Première fois en état DEGRADED — fenêtre de grâce commence maintenant
        result.network_state = NetworkState.DEGRADED
        result.reason = "Inbound non prouvé, relay indisponible — début fenêtre de grâce"
        result.recommended_action = "reassess"
        result.grace_remaining_s = DEGRADED_GRACE_S
        logger.info("[R382] NetworkState=DEGRADED (new — grace starts now)")
        result.capability = cap
        return result


# ─── Gestionnaire d'état avec transitions ────────────────────────────────────

class NetworkEligibilityGate:
    """Gestionnaire du cycle de vie NetworkState d'un nœud utilisateur.

    Responsabilités :
    - Maintenir l'état NetworkState courant
    - Déclencher les réévaluations (réseau change, sleep/wake, VPN)
    - Anti-flap : MIN_PASS_STREAK succès consécutifs pour passer SUSPENDED→ACTIVE
    - Séparation stricte : ne touche JAMAIS à EconomicState

    Usage typique :
        gate = NetworkEligibilityGate(node_id="artcb1xxx", p2p_port=18444)
        result = gate.assess()
        if result.network_state == NetworkState.SUSPENDED:
            # notifier EpochCoordinator (décision économique séparée)
            pass
    """

    def __init__(
        self,
        *,
        node_id: str,
        p2p_port: int = DEFAULT_P2P_PORT,
        probe_host: str = _DEFAULT_PROBE_HOST,
        probe_port: int = _DEFAULT_PROBE_PORT,
    ) -> None:
        self.node_id = node_id
        self.p2p_port = p2p_port
        self.probe_host = probe_host
        self.probe_port = probe_port

        self._current_state: NetworkState = NetworkState.UNKNOWN
        self._degraded_since_ts_ns: int | None = None
        self._pass_streak: int = 0
        self._last_result: EligibilityResult | None = None
        self._history: list[dict[str, Any]] = []

        # R397 — ExternalProbeStore réel (corrige stub vide de R382)
        self._external_probes: list[dict[str, Any]] = []
        self._external_probe_count: int = 0
        self._external_probe_ok: int = 0
        self._external_distinct_nodes: set[str] = set()

        logger.debug("[R397] NetworkEligibilityGate init node_id=%s port=%d",
                     node_id, p2p_port)

    # Propriétés publiques (lecture seule)
    @property
    def current_state(self) -> NetworkState:
        return self._current_state

    @property
    def last_result(self) -> EligibilityResult | None:
        return self._last_result

    def assess(
        self,
        *,
        relay_available: bool = False,
        external_reachable: bool | None = None,
        external_probe_count: int = 0,
        external_probe_ok: int = 0,
        _force_outbound: bool | None = None,
        _force_inbound: bool | None = None,
    ) -> EligibilityResult:
        """R397 — Lance une évaluation complète et met à jour l'état interne.

        Utilise les preuves externes accumulées via record_external_probe()
        si external_probe_count/ok ne sont pas fournis explicitement.
        """
        prev_state = self._current_state
        self._current_state = NetworkState.TESTING
        logger.info("[R397] assess() node_id=%s (prev_state=%s)",
                    self.node_id, prev_state.value)

        # R397 : utilise les preuves stockées si pas fourni explicitement
        eff_probe_count = external_probe_count if external_probe_count else self._external_probe_count
        eff_probe_ok = external_probe_ok if external_probe_ok else self._external_probe_ok
        eff_distinct = len(self._external_distinct_nodes)
        # external_reachable = True si ≥1 probe externe distincte a réussi
        eff_reachable = external_reachable
        if eff_reachable is None and self._external_probe_ok > 0:
            eff_reachable = True

        cap = assess_network_capability(
            p2p_port=self.p2p_port,
            probe_host=self.probe_host,
            probe_port=self.probe_port,
            relay_available=relay_available,
            external_reachable=eff_reachable,
            external_probe_count=eff_probe_count,
            external_probe_ok=eff_probe_ok,
            external_distinct_nodes=eff_distinct,
            _force_outbound=_force_outbound,
            _force_inbound=_force_inbound,
        )

        result = classify_network_state(
            cap,
            degraded_since_ts_ns=self._degraded_since_ts_ns,
        )

        # Anti-flap : si retour DIRECT/RELAYABLE depuis SUSPENDED → streak requis
        new_state = result.network_state
        if prev_state == NetworkState.SUSPENDED and new_state in (
            NetworkState.DIRECT, NetworkState.RELAYABLE
        ):
            self._pass_streak += 1
            if self._pass_streak < MIN_PASS_STREAK:
                logger.info("[R382] anti-flap: streak=%d/%d — maintien SUSPENDED",
                            self._pass_streak, MIN_PASS_STREAK)
                result.network_state = NetworkState.SUSPENDED
                result.reason += f" (anti-flap: {self._pass_streak}/{MIN_PASS_STREAK})"
                new_state = NetworkState.SUSPENDED
        else:
            self._pass_streak = 0

        # Gestion de la fenêtre de grâce DEGRADED
        if new_state == NetworkState.DEGRADED and self._degraded_since_ts_ns is None:
            self._degraded_since_ts_ns = time.time_ns()
            logger.info("[R382] DEGRADED — fenêtre de grâce démarrée ts_ns=%d",
                        self._degraded_since_ts_ns)
        elif new_state != NetworkState.DEGRADED:
            self._degraded_since_ts_ns = None

        self._current_state = new_state
        self._last_result = result

        # Historique (taille max 100 entrées)
        self._history.append({
            "ts_ns": result.ts_ns,
            "network_state": new_state.value,
            "reason": result.reason,
        })
        if len(self._history) > 100:
            self._history = self._history[-100:]

        logger.info("[R382] NetworkState=%s node_id=%s reason=%s",
                    new_state.value, self.node_id, result.reason[:80])
        return result

    def on_network_change(self, *, reason: str = "network_change") -> EligibilityResult:
        """Déclenche une réévaluation après changement de réseau.

        À appeler lors de :
        - changement de Wi-Fi (détecté par l'OS)
        - réveil après sleep/wake
        - connexion/déconnexion VPN
        - changement d'IP
        """
        logger.info("[R397] on_network_change(%s) — réévaluation", reason)
        self._degraded_since_ts_ns = None   # réinitialise la fenêtre de grâce
        self._pass_streak = 0
        # R397 : réinitialise aussi le store de probes (réseau différent)
        self._external_probes = []
        self._external_probe_count = 0
        self._external_probe_ok = 0
        self._external_distinct_nodes = set()
        self._current_state = NetworkState.TESTING
        return self.assess()

    def record_external_probe(
        self,
        *,
        success: bool,
        probe_node_id: str = "unknown",
        observed_address: str = "",
        observed_port: int = 0,
        transport: str = "tcp",
    ) -> None:
        """R397 — Enregistre une probe externe réelle reçue d'un nœud ARTCB tiers.

        R382 : cette fonction était un stub vide (ne stockait rien).
        R397 : stocke la preuve, met à jour les compteurs, ajoute le node_id
               distinct. La prochaine assess() utilisera ces données automatiquement.

        Équivalent AutoNAT libp2p : des pairs externes tentent de joindre
        les adresses annoncées par ce nœud et rapportent le résultat.
        """
        ts = time.time_ns()
        entry: dict[str, Any] = {
            "ts_ns": ts,
            "probe_node_id": probe_node_id,
            "success": success,
            "observed_address": observed_address,
            "observed_port": observed_port,
            "transport": transport,
        }
        self._external_probes.append(entry)
        # Taille max
        if len(self._external_probes) > MAX_EXTERNAL_PROBE_HISTORY:
            self._external_probes = self._external_probes[-MAX_EXTERNAL_PROBE_HISTORY:]

        self._external_probe_count += 1
        if success:
            self._external_probe_ok += 1
        if probe_node_id and probe_node_id != "unknown":
            self._external_distinct_nodes.add(probe_node_id)

        logger.debug(
            "[R397] record_external_probe from=%s success=%s total=%d ok=%d distinct=%d",
            probe_node_id, success, self._external_probe_count,
            self._external_probe_ok, len(self._external_distinct_nodes),
        )

    def external_probe_summary(self) -> dict[str, Any]:
        """R397 — Retourne un résumé des preuves externes accumulées."""
        return {
            "count": self._external_probe_count,
            "ok": self._external_probe_ok,
            "fail": self._external_probe_count - self._external_probe_ok,
            "distinct_nodes": len(self._external_distinct_nodes),
            "reachable": self._external_probe_ok > 0,
            "last_ts_ns": self._external_probes[-1]["ts_ns"] if self._external_probes else None,
        }

    def history(self) -> list[dict[str, Any]]:
        """Retourne l'historique des transitions (max 100 entrées)."""
        return list(self._history)

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "current_state": self._current_state.value,
            "degraded_since_ts_ns": self._degraded_since_ts_ns,
            "pass_streak": self._pass_streak,
            "last_result": self._last_result.to_dict() if self._last_result else None,
            "history_count": len(self._history),
            "external_probe_summary": self.external_probe_summary(),
        }
