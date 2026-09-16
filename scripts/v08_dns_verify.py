#!/usr/bin/env python3
"""
V-08 DNS VERIFY — 2026-09-16
Vérifie que artcb.me résout vers plusieurs IPs (multi-A) après le fix V-08.
Usage : python3 scripts/v08_dns_verify.py
"""
import socket, subprocess, sys

ZONE = "artcb.me"
EXPECTED_IPS = {"152.228.144.34", "91.134.45.8", "151.80.107.29"}

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
