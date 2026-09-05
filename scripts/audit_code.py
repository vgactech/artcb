#!/usr/bin/env python3
"""Audit complet : smoke / hardcoding / placeholder / stub / mock dans src/ et tests/."""
import subprocess, re, sys, os
from pathlib import Path

ROOT = Path(__file__).parent.parent

def grep(pattern, path, flags=None, include="*.py"):
    cmd = ["grep", "-rn", f"--include={include}", pattern, str(path)]
    if flags:
        cmd = ["grep", "-rn", flags, f"--include={include}", pattern, str(path)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    return [l for l in r.stdout.splitlines() if "__pycache__" not in l and ".pyc" not in l]

print("=" * 70)
print("AUDIT ARTCB — smoke / hardcoding / placeholder / stub / mock")
print("=" * 70)

# ── 1. NotImplementedError (vraie implémentation manquante)
lines = grep("raise NotImplementedError", ROOT / "src")
print(f"\n[1] raise NotImplementedError dans src/ : {len(lines)}")
for l in lines: print("  ", l)

# ── 2. pass nu (corps de fonction vide réel)
lines = grep(r"^\s*pass\s*$", ROOT / "src", "-P")
# filtrer les pass légitimes après except/class/if vide
filtered = []
for l in lines:
    # On garde seulement les pass qui semblent être des corps de méthode vides
    if not any(k in l for k in ["except ", "if True", "else:", "elif "]):
        filtered.append(l)
print(f"\n[2] pass nu dans src/ (hors except) : {len(filtered)}")
for l in filtered[:30]: print("  ", l)

# ── 3. Commentaires TODO/FIXME/HACK dans src/
for marker in ["# TODO", "# FIXME", "# HACK", "# XXX", "# STUB", "# SMOKE"]:
    lines = grep(marker, ROOT / "src", "-i")
    if lines:
        print(f"\n[3] {marker} dans src/ : {len(lines)}")
        for l in lines: print("  ", l)

# ── 4. Placeholder/dummy/fake explicites dans src/
for pat, label in [
    ("placeholder", "placeholder explicite"),
    ("dummy", "dummy"),
    ("fake_", "fake_ préfixe"),
    ("stub", "stub"),
    ("smoke", "smoke"),
]:
    lines = grep(pat, ROOT / "src", "-i")
    lines = [l for l in lines if not l.strip().startswith("#!") and "__pycache__" not in l]
    if lines:
        print(f"\n[4] {label} dans src/ : {len(lines)}")
        for l in lines: print("  ", l)

# ── 5. Valeurs hardcodées dans la logique métier
hc_patterns = [
    ("artcb_test_token_", "token de test hardcodé"),
    ("\"test_key\"", "clé de test en dur"),
    ("'test_key'", "clé de test en dur"),
    ("contact@artcb.io", "ancien email officiel hardcodé dans code"),
    ("official@artcb.space", "email officiel hardcodé dans code"),
    ("vgac42@gmail.com", "email hardcodé dans code"),
    ("51.255.22.253", "IP serveur OVH hardcodée"),
]
for pat, label in hc_patterns:
    lines = grep(pat, ROOT / "src")
    if lines:
        print(f"\n[5] {label} dans src/ : {len(lines)}")
        for l in lines: print("  ", l)

# ── 6. Secrets/tokens hardcodés dans src/ (hors .env)
secret_patterns = [
    ("dp.st.", "token Doppler"),
    ("sk-[a-zA-Z0-9]", "clé OpenAI"),
    ("ghp_[a-zA-Z0-9]", "token GitHub"),
    ("ngrok_[a-zA-Z0-9]", "token ngrok"),
    ("artcb_prod_", "clé prod ARTCB"),
]
for pat, label in secret_patterns:
    lines = grep(pat, ROOT / "src", "-E")
    if lines:
        print(f"\n[6] SECRET: {label} dans src/ : {len(lines)}")
        for l in lines: print("  ", l)

# ── 7. Fonctions retournant toujours une constante (retour fake)
lines = grep(r"^\s*return True\s*$", ROOT / "src", "-P")
print(f"\n[7] return True nu dans src/ : {len(lines)}")
for l in lines[:15]: print("  ", l)

lines2 = grep(r"^\s*return \{\}\s*$", ROOT / "src", "-P")
print(f"\n[7b] return {{}} nu dans src/ : {len(lines2)}")
for l in lines2[:15]: print("  ", l)

# ── 8. Mocks dans les tests (normal MAIS à auditer si dans src/)
for pat, label in [
    ("MagicMock", "MagicMock"),
    ("AsyncMock", "AsyncMock"),
    ("unittest.mock", "unittest.mock"),
]:
    lines_src = grep(pat, ROOT / "src")
    lines_tests = grep(pat, ROOT / "tests")
    if lines_src:
        print(f"\n[8] {label} dans SRC/ (ANORMAL) : {len(lines_src)}")
        for l in lines_src: print("  ", l)
    else:
        print(f"\n[8] {label} dans tests/ : {len(lines_tests)} (normal)")

# ── 9. URLs et IPs hardcodées dans la logique métier (hors doc)
hard_urls = [
    ("0.0.0.0", "bind 0.0.0.0 (OK serveur)"),
    ("localhost:8000", "localhost hardcodé"),
    ("127.0.0.1", "loopback hardcodé"),
    ("18444", "port P2P hardcodé"),
]
for pat, label in hard_urls:
    lines = grep(pat, ROOT / "src")
    lines = [l for l in lines if '"""' not in l and "'''" not in l]
    if lines:
        print(f"\n[9] {label} : {len(lines)}")
        for l in lines: print("  ", l)

# ── 10. Commentaires laissés "à faire plus tard" dans tests/
for marker in ["# TODO", "# FIXME", "# skip", "pytest.skip", "pytest.mark.skip"]:
    lines = grep(marker, ROOT / "tests", "-i")
    if lines:
        print(f"\n[10] {marker} dans tests/ : {len(lines)}")
        for l in lines: print("  ", l)

print("\n" + "=" * 70)
print("FIN DE L'AUDIT")
print("=" * 70)
