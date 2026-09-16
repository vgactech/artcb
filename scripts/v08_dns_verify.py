#!/usr/bin/env python3
"""
V-08 DNS VERIFY — révision 2 (2026-09-16)
Vérifie que artcb.me résout vers les IPs multi-A après le fix V-08.

IPs dans le DNS apex (enregistrements A OVH) :
  152.228.144.34 — OVH1 (apex historique, bloqué en test)
  91.134.45.8    — N4 OVH (ACTIVE, cert wildcard artcb.me)
  151.80.107.29  — N2 OVH (ACTIVE, cert n2.artcb.me — wildcard à déployer)

Note : N3 (13.38.209.25) n'est PAS dans le DNS apex multi-A —
  il sert artcb.me par backend mais ne reçoit pas directement le trafic DNS.
  Si on souhaite l'y ajouter : POST OVH API avec subDomain="" target=13.38.209.25.

Usage : python3 scripts/v08_dns_verify.py
"""
import socket, subprocess, sys

ZONE = "artcb.me"
# IPs effectivement déclarées dans les enregistrements A apex (OVH DNS, IDs 5432477544/5435561713/5435561715)
EXPECTED_IPS = {"152.228.144.34", "91.134.45.8", "151.80.107.29"}
# N3 capable de servir artcb.me mais non dans le DNS apex
CAPABLE_NOT_IN_DNS = {"13.38.209.25"}

print(f"=== V-08 DNS Verify — {ZONE} ===\n")

# Résolution DNS standard
try:
    results = socket.getaddrinfo(ZONE, None, socket.AF_INET)
    resolved = {r[4][0] for r in results}
    print(f"Résolution DNS locale : {sorted(resolved)}")
except Exception as e:
    resolved = set()
    print(f"DNS ERROR: {e}")

# Résolution via dig si disponible
try:
    r = subprocess.run(
        ["dig", "+short", "A", ZONE, "@8.8.8.8"],
        capture_output=True, text=True, timeout=5
    )
    dig_ips = set(r.stdout.strip().split()) if r.returncode == 0 else set()
    print(f"dig @8.8.8.8 : {sorted(dig_ips)}")
except Exception:
    dig_ips = set()

all_resolved = resolved | dig_ips

# Vérification
missing = EXPECTED_IPS - all_resolved
extra   = all_resolved - EXPECTED_IPS

print(f"\nIPs attendues  : {sorted(EXPECTED_IPS)}")
print(f"IPs résolues   : {sorted(all_resolved)}")
print(f"Manquantes     : {sorted(missing)}")
print(f"Supplémentaires: {sorted(extra)}")

if not missing:
    print("\n✅ V-08 DNS PASS — apex multi-A confirmé")
    sys.exit(0)
elif len(all_resolved) > 1:
    print(f"\n⚠️  V-08 DNS PARTIAL — {len(all_resolved)} IPs résolues (propagation en cours TTL=60s)")
    sys.exit(0)
else:
    print(f"\n❌ V-08 DNS FAIL — apex pointe vers 1 seule IP ({all_resolved}), SPOF non résolu")
    sys.exit(1)
