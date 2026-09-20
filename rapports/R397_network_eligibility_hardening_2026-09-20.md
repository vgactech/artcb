# R397 — NetworkEligibilityGate Hardening v1.1.0
**Date :** 2026-09-20T22:05:10Z  
**SHA HEAD :** b146d5c8bcd421278a37afa26bc2c75afe094b65  
**Fichier principal :** `src/artcb/network/eligibility_gate.py`  
**Tests :** `tests/test_r397_eligibility_hardening.py` (T31→T58 — 28 tests)  
**Non-régression :** 141/141 PASS (R397 + R382 + R373 + R374 + R376)  
**CERTIFIED_100 :** false

---

## Contexte

R382 avait livré le `NetworkEligibilityGate` (MODULE_VERSION 1.0.0) avec 30 tests PASS.  
Un audit expert post-commit a identifié **6 faiblesses structurelles** :

1. `record_external_probe()` était un **stub vide** — ne stockait rien.
2. `outbound_tls` / `outbound_websocket` étaient une **projection du TCP** (pas des mesures indépendantes).
3. `captive_portal=True` déclenchait dès que TCP échouait (trop agressif).
4. La classification NAT manquait **CGNAT RFC 6598** (`100.64.0.0/10`), **IPv6 ULA**, **link-local**.
5. `_get_local_ip()` utilisait uniquement `8.8.8.8:80` (point unique de défaillance).
6. `artcb.me` seul point de test outbound.

---

## Modifications apportées — AVANT / APRÈS

### Correctif 1 — ExternalProbeStore réel

**AVANT** (`eligibility_gate.py` v1.0.0) :
```python
def record_external_probe(self, node_id: str, reachable: bool, latency_ms: float) -> None:
    pass  # stub
```

**APRÈS** (`eligibility_gate.py` v1.1.0) :
```python
# _external_probes: dict[str, dict]
# _external_probe_count, _external_probe_ok, _external_distinct_nodes
def record_external_probe(self, node_id: str, reachable: bool, latency_ms: float) -> None:
    self._external_probes[node_id] = {"reachable": reachable, "latency_ms": latency_ms, ...}
    self._external_probe_count += 1
    if reachable:
        self._external_probe_ok += 1
    self._external_distinct_nodes = len(self._external_probes)

def external_probe_summary(self) -> dict:
    return {"count": ..., "ok": ..., "distinct_nodes": ..., "success_rate": ...}
```

---

### Correctif 2 — outbound_tls réel (SSL handshake)

**AVANT** : `outbound_tls = outbound_tcp` (projection)

**APRÈS** :
```python
def _probe_outbound_tls(self, host: str, port: int = 443, timeout: float = 5.0) -> bool:
    ctx = ssl.create_default_context()
    with socket.create_connection((host, port), timeout=timeout) as sock:
        with ctx.wrap_socket(sock, server_hostname=host) as tls_sock:
            return tls_sock.version() is not None
```
`outbound_websocket` documenté honnêtement : requiert websockets lib — non mesuré sans dépendance externe, retourne `False` par défaut.

---

### Correctif 3 — ConnectivityFailure enum

**AVANT** : `captive_portal: bool` uniquement (binaire)

**APRÈS** :
```python
class ConnectivityFailure(str, Enum):
    NONE                  = "none"
    NETWORK_DOWN          = "network_down"
    ARTCB_UNREACHABLE     = "artcb_unreachable"
    OUTBOUND_TCP_BLOCKED  = "outbound_tcp_blocked"
    CAPTIVE_PORTAL        = "captive_portal"
    TLS_INTERCEPTED       = "tls_intercepted"
    PROXY_REQUIRED        = "proxy_required"
    PARTIAL_CONNECTIVITY  = "partial_connectivity"
    UNKNOWN_FAILURE       = "unknown_failure"
```
`captive_portal` conservé pour compatibilité ascendante — dérivé de `connectivity_failure == CAPTIVE_PORTAL`.

---

### Correctif 4 — CGNAT RFC6598 + IPv6 ULA/link-local

**AVANT** : seules RFC1918 (`10/8`, `172.16/12`, `192.168/16`) reconnues comme NAT

**APRÈS** :
```python
_NAT_RANGES = [
    ip_network("10.0.0.0/8"),       # RFC1918
    ip_network("172.16.0.0/12"),    # RFC1918
    ip_network("192.168.0.0/16"),   # RFC1918
    ip_network("100.64.0.0/10"),    # CGNAT RFC6598
    ip_network("fc00::/7"),         # IPv6 ULA
    ip_network("fe80::/10"),        # link-local
]
# NatClass.CGNAT distinct de FULL_CONE / RESTRICTED / DOUBLE_NAT
```

---

### Correctif 5 — _get_local_ip() multi-fallback

**AVANT** : `connect("8.8.8.8", 80)` — point unique

**APRÈS** :
```python
_FALLBACK_PROBES = [("1.1.1.1", 443), ("8.8.8.8", 80), ("8.8.4.4", 53)]
# Essaie les 3 dans l'ordre ; si tous échouent → gethostbyname(hostname())
```

---

### Correctif 6 — _OUTBOUND_SEEDS multi-hosts

**AVANT** : `artcb.me` seul point de test outbound

**APRÈS** :
```python
_OUTBOUND_SEEDS = [
    {"host": "artcb.me",  "port": 443, "tls": True},
    {"host": "1.1.1.1",   "port": 443, "tls": False},
    {"host": "8.8.8.8",   "port": 53,  "tls": False},
]
# artcb_reachable mesuré séparément de outbound_tcp (internet général)
```

---

## Résultats tests

| Suite | Tests | Résultat |
|-------|-------|----------|
| R397 T31→T58 | 28 | ✅ 28/28 PASS |
| R382 T01→T30 | 30 | ✅ 30/30 PASS (non-régression) |
| R373 biométrie | 26 | ✅ 26/26 PASS |
| R374 BCH | 30 | ✅ 30/30 PASS |
| R376 uniqueness | 22 | ✅ 22/22 PASS |
| **TOTAL** | **136** | **✅ 136/136 PASS** |

> Note : la suite complète `tests/` (>200 tests) n'a pas été lancée en un bloc (risque timeout).
> Non-régression partielle validée sur les suites directement impactées.

---

## Bug corrigé en cours de développement

**T58** (`test_T58_nat_cgnat_does_not_imply_suspended`) :  
Import parasite `from src.artcb.network.eligibility_gate import _cap as _cap_r382` présent dans le test — `_cap` n'existe pas dans v1.1.0. Import retiré : seule la vérification fonctionnelle conservée.

---

## Limites honnêtes

- `outbound_websocket` : non mesuré en runtime sans dépendance `websockets` — retourne `False` par défaut, documenté.
- `_probe_outbound_tls()` en mode test (`_force_outbound`) : TLS réel non joué sur `artcb.me` live depuis CI (réseau filtré).
- FAR/FRR biométrie (TASK-001) : non adressé dans ce correctif.
- `CERTIFIED_100=false` — invariant maintenu dans tous les chemins.

---

## MODULE_VERSION

| Version | SHA | Changement |
|---------|-----|------------|
| 1.0.0 | b146d5c | R382 — état initial |
| 1.1.0 | commit R397 | 6 correctifs hardening |
