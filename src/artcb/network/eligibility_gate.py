"""R382 — NetworkEligibilityGate : éligibilité réseau d'un nœud ARTCB.

Principe fondamental (rapport expert 2026-09-19) :
  La question n'est pas « est-ce un Wi-Fi public/entreprise ? »
  mais « la machine peut-elle réellement satisfaire les exigences
  opérationnelles du protocole ARTCB dans ses conditions réseau actuelles ? »

Architecture :
  NetworkState (ce module)  ←  séparé de  →  EconomicState (economics/human_binding.py)
  DIRECT / RELAYABLE / DEGRADED / SUSPENDED    ACTIVE / GRACE / OFFLINE / RETIRED

  Un changement de NetworkState ne modifie JAMAIS directement EconomicState.
  EpochCoordinator (economics) reste la seule autorité pour les transitions
  économiques (GRACE → OFFLINE, OFFLINE → RETIRED).

Cycle complet :
  DISCOVERY → TESTING → DIRECT | RELAYABLE | DEGRADED | SUSPENDED
       ↑                              ↓
  NETWORK_CHANGE ←── REASSESSMENT ←──┘

Scénarios couverts (tableau expert §32) :
  S01 Wi-Fi domestique plein   → DIRECT
  S02 Wi-Fi public outbound    → RELAYABLE (si relay dispo) ou DEGRADED
  S03 Wi-Fi entreprise strict  → SUSPENDED
  S04 CGNAT / hotspot 4G       → RELAYABLE ou DEGRADED
  S05 Double NAT               → RELAYABLE ou DEGRADED
  S06 Captive portal (non auth)→ SUSPENDED
  S07 VPN actif                → REASSESS (nouveau test)
  S08 Changement réseau        → REASSESS
  S09 Sleep/Wake               → REASSESS
  S10 Probe node indisponible  → ne pas suspendre injustement (INDETERMINATE)

HONNÊTETÉ :
  - Les tests outbound sont réels (socket TCP).
  - Le test inbound simule une probe externe : en local, il teste l'écoute
    sur le port P2P configuré. En production, une probe externe ARTCB
    doit valider external_reachable=True.
  - CERTIFIED_100=false — calibrage sur vrais réseaux non encore mesuré.

CERTIFIED_100=false | MODE DEBUG actif
"""

from __future__ import annotations

MODULE_VERSION = "1.0.0"  # R382

import logging
import os
import socket
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

# Endpoints externes pour tests outbound (pas de fallback hardcodé secret —
# uniquement les nœuds seeds ARTCB publics déclarés D-045)
_DEFAULT_PROBE_HOST = os.getenv("ARTCB_PROBE_HOST", "artcb.me")
_DEFAULT_PROBE_PORT = int(os.getenv("ARTCB_PROBE_PORT", "443"))

# Nombre minimum de tests positifs pour passer TESTING → DIRECT
MIN_PASS_STREAK: int = 2  # anti-flap : 2 succès consécutifs requis

# Fenêtre temporelle avant DEGRADED → SUSPENDED (secondes)
DEGRADED_GRACE_S: int = int(os.getenv("ARTCB_DEGRADED_GRACE_S", str(5 * 60)))  # 5 min


# ─── Enums ───────────────────────────────────────────────────────────────────

class NetworkState(str, Enum):
    """État réseau opérationnel d'un nœud utilisateur.

    Séparation stricte de EconomicState (ACTIVE/GRACE/OFFLINE/RETIRED).
    Un nœud SUSPENDED réseau peut avoir EconomicState=GRACE si dans la
    fenêtre de grâce économique.
    """
    UNKNOWN      = "UNKNOWN"       # jamais testé
    TESTING      = "TESTING"       # évaluation en cours
    DIRECT       = "DIRECT"        # connexions entrantes directes disponibles
    RELAYABLE    = "RELAYABLE"     # relay ARTCB requis pour inbound
    DEGRADED     = "DEGRADED"      # outbound ok, inbound fail, relay indisponible
    SUSPENDED    = "SUSPENDED"     # ne satisfait pas les exigences minimales
    INDETERMINATE = "INDETERMINATE" # probe externe indisponible — pas suspendre


class NatClass(str, Enum):
    """Classification NAT mesurée."""
    NONE         = "NONE"         # IP publique directe (serveur cloud)
    FULL_CONE    = "FULL_CONE"    # NAT domestique classique
    RESTRICTED   = "RESTRICTED"   # NAT avec restriction de port
    SYMMETRIC    = "SYMMETRIC"    # NAT symétrique (CGNAT)
    DOUBLE_NAT   = "DOUBLE_NAT"   # double NAT détecté
    UNKNOWN      = "UNKNOWN"


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

    Séparée de l'identité du nœud (NodeID ≠ IP ≠ réseau actuel).
    """
    ts_ns: int = field(default_factory=time.time_ns)

    # Connectivité sortante
    outbound_tcp: bool = False
    outbound_tls: bool = False
    outbound_websocket: bool = False  # testé via TCP 443 (proxy-safe)

    # Connectivité entrante (auto-probe locale)
    inbound_listen: bool = False      # le port P2P écoute localement
    external_reachable: bool = False  # preuve externe (probe ARTCB tiers)
    external_probe_count: int = 0     # nb probes externes reçues
    external_probe_ok: int = 0        # nb probes externes réussies

    # Relay
    relay_available: bool = False

    # NAT
    nat_class: NatClass = NatClass.UNKNOWN

    # Réseau
    packet_loss_pct: float = 0.0      # 0–100
    latency_ms: float | None = None
    captive_portal: bool = False       # captive portal détecté

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
            "inbound_listen": self.inbound_listen,
            "external_reachable": self.external_reachable,
            "external_probe_count": self.external_probe_count,
            "external_probe_ok": self.external_probe_ok,
            "relay_available": self.relay_available,
            "nat_class": self.nat_class.value,
            "packet_loss_pct": self.packet_loss_pct,
            "latency_ms": self.latency_ms,
            "captive_portal": self.captive_portal,
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


def _detect_captive_portal(probe_host: str, probe_port: int) -> bool:
    """Détecte un captive portal : connexion TCP acceptée mais HTTP redirige.

    Approche légère : on vérifie si le TCP 443 vers le probe_host est joignable.
    Un captive portal bloquera typiquement cette connexion ou redirigera HTTP→captive.
    Honnêteté : détection partielle (TCP uniquement — pas de validation TLS/SNI).
    """
    try:
        with socket.create_connection((probe_host, probe_port), timeout=3.0):
            return False  # connexion directe réussie → probablement pas de captive portal
    except OSError:
        # Impossible de joindre → potentiel captive portal ou réseau coupé
        return True


def _get_local_ip() -> str:
    """Détecte l'IP locale principale (non loopback)."""
    try:
        with socket.create_connection(("8.8.8.8", 80), timeout=2.0) as s:
            return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"


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
    _force_outbound: bool | None = None,    # injection de test uniquement
    _force_inbound: bool | None = None,     # injection de test uniquement
) -> NetworkCapability:
    """Mesure la capacité réseau réelle de la machine courante.

    Args :
        p2p_port           : port P2P ARTCB configuré
        probe_host         : hôte de référence pour tests outbound (artcb.me par défaut)
        probe_port         : port de référence (443)
        relay_available    : un relay ARTCB tiers a confirmé sa disponibilité
        external_reachable : preuve externe (True/False) ou None si non testée
        external_probe_count / external_probe_ok : résultats des probes externes reçues
        _force_outbound    : injection pour tests (ne PAS utiliser en production)
        _force_inbound     : injection pour tests (ne PAS utiliser en production)
    """
    logger.debug("[R382] assess_network_capability — p2p_port=%d probe=%s:%d",
                 p2p_port, probe_host, probe_port)

    cap = NetworkCapability(p2p_port=p2p_port)
    cap.local_ip = _get_local_ip()

    # --- Connectivité sortante ---
    if _force_outbound is not None:
        outbound_probe = ConnectivityProbe(
            ts_ns=time.time_ns(), probe_kind="outbound_tcp",
            host=probe_host, port=probe_port,
            success=_force_outbound,
        )
        cap.outbound_tcp = _force_outbound
        cap.outbound_tls = _force_outbound
        cap.outbound_websocket = _force_outbound
    else:
        outbound_probe = _probe_outbound_tcp(probe_host, probe_port)
        cap.outbound_tcp = outbound_probe.success
        cap.outbound_tls = outbound_probe.success   # même chemin TCP 443
        cap.outbound_websocket = outbound_probe.success  # WS sur 443 même test
        cap.latency_ms = outbound_probe.latency_ms

    cap.probes.append(outbound_probe)

    # --- Captive portal ---
    if not cap.outbound_tcp:
        cap.captive_portal = True   # si même TCP 443 échoue → fort indice de portail
        logger.debug("[R382] captive_portal=True (outbound TCP fail)")
    else:
        cap.captive_portal = False

    # --- Connectivité entrante ---
    if _force_inbound is not None:
        inbound_probe = ConnectivityProbe(
            ts_ns=time.time_ns(), probe_kind="inbound_listen",
            host="127.0.0.1", port=p2p_port,
            success=_force_inbound,
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
        # Pas de probe externe fournie → on ne présume pas
        cap.external_reachable = False
        logger.debug("[R382] external_reachable=None — conservateur: False")

    cap.external_probe_count = external_probe_count
    cap.external_probe_ok = external_probe_ok

    # --- Relay ---
    cap.relay_available = relay_available

    # --- NAT (heuristique légère) ---
    if cap.local_ip.startswith("10.") or cap.local_ip.startswith("172.") or cap.local_ip.startswith("192.168."):
        if not cap.external_reachable and cap.outbound_tcp:
            cap.nat_class = NatClass.RESTRICTED  # heuristique — IP privée sans preuve externe
        else:
            cap.nat_class = NatClass.FULL_CONE   # IP privée mais preuve externe présente
    else:
        cap.nat_class = NatClass.NONE  # IP publique directe (ex. VPS cloud)

    logger.debug("[R382] capability: outbound=%s inbound=%s external=%s relay=%s nat=%s",
                 cap.outbound_tcp, cap.inbound_listen, cap.external_reachable,
                 cap.relay_available, cap.nat_class.value)
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

        logger.debug("[R382] NetworkEligibilityGate init node_id=%s port=%d",
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
        """Lance une évaluation complète et met à jour l'état interne.

        Args supplémentaires injectés par les probes externes ARTCB :
            relay_available      : un relay tiers a confirmé sa dispo
            external_reachable   : preuve externe de joignabilité
            external_probe_count : nb probes reçues depuis nœuds tiers
            external_probe_ok    : nb probes réussies
        """
        prev_state = self._current_state
        self._current_state = NetworkState.TESTING
        logger.info("[R382] assess() node_id=%s (prev_state=%s)",
                    self.node_id, prev_state.value)

        cap = assess_network_capability(
            p2p_port=self.p2p_port,
            probe_host=self.probe_host,
            probe_port=self.probe_port,
            relay_available=relay_available,
            external_reachable=external_reachable,
            external_probe_count=external_probe_count,
            external_probe_ok=external_probe_ok,
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
        logger.info("[R382] on_network_change(%s) — réévaluation", reason)
        self._degraded_since_ts_ns = None   # réinitialise la fenêtre de grâce
        self._pass_streak = 0
        self._current_state = NetworkState.TESTING
        return self.assess()

    def record_external_probe(
        self,
        *,
        success: bool,
        probe_node_id: str = "unknown",
    ) -> None:
        """Enregistre une probe externe reçue d'un nœud ARTCB tiers.

        Ce mécanisme (équivalent AutoNAT libp2p) permet de valider
        external_reachable depuis plusieurs points du réseau ARTCB.
        """
        logger.debug("[R382] external_probe from=%s success=%s", probe_node_id, success)
        # La prochaine assess() utilisera ces données si passées explicitement

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
        }
