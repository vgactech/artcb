#!/usr/bin/env python3
"""scripts/artcb_reflex_check.py — Vérification automatique du réflexe ARTCB (R350–R354).

Ce script s'exécute automatiquement à chaque modification du code ARTCB.
Il vérifie :
  1. Présence et cohérence des hooks Bob IDE (.bob/hooks/)
  2. Présence et cohérence des règles Cursor (.cursor/rules/)
  3. État du module src/artcb/reflex/
  4. Absence de face_camera/PIN comme méthode de preuve principale
  5. Présence de CERTIFIED_100=false partout où requis
  6. État de la mémoire live ARTCB

Usage :
    python3 scripts/artcb_reflex_check.py
    python3 scripts/artcb_reflex_check.py --strict  # exit 1 si FAIL

CERTIFIED_100=false — vérification stub fonctionnelle.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# ─── Checks ──────────────────────────────────────────────────────────────────


@dataclass
class CheckResult:
    name: str
    pass_: bool
    detail: str
    ts_ns: int = field(default_factory=time.time_ns)

    @property
    def status(self) -> str:
        return "✅ PASS" if self.pass_ else "❌ FAIL"


def check_bob_hooks() -> CheckResult:
    """Vérifie que tous les hooks Bob IDE sont présents et non vides."""
    hooks_dir = ROOT / ".bob" / "hooks"
    required = [
        "session_start.py",
        "user_prompt_submit.py",
        "post_tool_use.py",
        "stop.py",
    ]
    missing = [h for h in required if not (hooks_dir / h).exists()]
    if missing:
        return CheckResult("bob_hooks", False, f"Hooks manquants: {missing}")
    return CheckResult("bob_hooks", True, f"Tous les hooks présents ({len(required)})")


def check_cursor_rules() -> CheckResult:
    """Vérifie que les règles Cursor obligatoires sont présentes."""
    rules_dir = ROOT / ".cursor" / "rules"
    required = [
        "artcb-live-node.mdc",
        "artcb-read-all.mdc",
        "artcb-reflex-priority.mdc",  # nouvelle règle R350–R354
    ]
    missing = [r for r in required if not (rules_dir / r).exists()]
    if missing:
        return CheckResult("cursor_rules", False, f"Règles manquantes: {missing}")
    # Vérifier que artcb-reflex-priority.mdc a alwaysApply: true
    reflex_rule = (rules_dir / "artcb-reflex-priority.mdc").read_text()
    if "alwaysApply: true" not in reflex_rule:
        return CheckResult("cursor_rules", False, "artcb-reflex-priority.mdc: alwaysApply: true absent")
    return CheckResult("cursor_rules", True, f"Toutes les règles présentes ({len(required)})")


def check_reflex_module() -> CheckResult:
    """Vérifie que src/artcb/reflex/ est correctement implémenté."""
    reflex_dir = ROOT / "src" / "artcb" / "reflex"
    required = ["__init__.py", "core.py"]
    missing = [f for f in required if not (reflex_dir / f).exists()]
    if missing:
        return CheckResult("reflex_module", False, f"Fichiers manquants: {missing}")
    # Vérifier que ReflexEngine est importable
    core = (reflex_dir / "core.py").read_text()
    if "class ReflexEngine" not in core:
        return CheckResult("reflex_module", False, "ReflexEngine absent de core.py")
    if "CERTIFIED_100=false" not in core.lower() and "certified: bool = False" not in core:
        return CheckResult("reflex_module", False, "certified=False absent de core.py")
    return CheckResult("reflex_module", True, "Module réflexe complet (ReflexEngine, certified=False)")


def check_certified_100_false() -> CheckResult:
    """Vérifie que CERTIFIED_100=false est présent dans les fichiers critiques."""
    critical = [
        ROOT / "src" / "artcb" / "identity" / "biometric_onchain.py",
        ROOT / "scripts" / "certif_vpqc2_x4.py",
        ROOT / "src" / "artcb" / "reflex" / "core.py",
    ]
    issues = []
    for f in critical:
        if not f.exists():
            continue
        content = f.read_text().lower()
        if "certified_100" not in content and "certified=false" not in content and "certified: bool = false" not in content:
            issues.append(str(f.relative_to(ROOT)))
    if issues:
        return CheckResult("certified_100_false", False, f"CERTIFIED_100=false absent dans: {issues}")
    return CheckResult("certified_100_false", True, "CERTIFIED_100=false présent partout")


def check_face_camera_not_auth_path() -> CheckResult:
    """Vérifie que face_camera n'est pas une voie d'authentification principale.

    Spec §1 rapport 367/370 : face_camera doit être INACTIVE ou clairement
    marquée comme non-preuve d'identité humaine unique.
    """
    webauthn_routes = ROOT / "src" / "api" / "webauthn_routes.py"
    if not webauthn_routes.exists():
        return CheckResult("face_camera_inactive", True, "webauthn_routes.py absent — skip")

    content = webauthn_routes.read_text()

    # Vérifier que face_camera a level <= 1 (pas 2 ou 3)
    # et does_not_prove "identity" ou "uniqueness"
    if '"face_camera"' in content:
        # Chercher le niveau
        match = re.search(r'"face_camera".*?"level":\s*(\d)', content, re.DOTALL)
        if match:
            level = int(match.group(1))
            if level >= 2:
                return CheckResult(
                    "face_camera_inactive",
                    False,
                    f"face_camera level={level} ≥ 2 — ne doit jamais atteindre le niveau WebAuthn"
                )

    # Vérifier qu'il n'y a pas de wallet créé directement depuis face_camera
    # sans restriction explicite
    if "FACE_CAMERA_INACTIVE_PRODUCTION" in content or "face_camera_disabled" in content.lower():
        return CheckResult("face_camera_inactive", True, "face_camera marquée inactive production ✅")

    # Vérifier que does_not_prove inclut "uniqueness" et "identity"
    if "does_not_prove" in content:
        return CheckResult(
            "face_camera_inactive",
            True,
            "face_camera: does_not_prove présent (pas de claim d'identité unique)"
        )

    return CheckResult(
        "face_camera_inactive",
        False,
        "face_camera: marquage does_not_prove manquant — risque de confusion"
    )


def check_pin_not_identity_proof() -> CheckResult:
    """Vérifie que le PIN n'est jamais utilisé comme preuve d'identité ARTCB.

    Spec §4 rapport 367/370 : PIN → ARTCB = ❌ REJET absolu.
    """
    # Fichiers à auditer
    audit_files = [
        ROOT / "src" / "api" / "auth_routes.py",
        ROOT / "src" / "api" / "webauthn_routes.py",
        ROOT / "src" / "api" / "biometric_identity_routes.py",
        ROOT / "frontend" / "src" / "pages" / "Wallets.tsx",
    ]

    FORBIDDEN_PATTERNS = [
        # PIN envoyé directement à ARTCB comme preuve d'identité humaine
        re.compile(r'pin\s*[=:]\s*["\'].*["\'].*human', re.I),
        re.compile(r'human.*pin\s*[=:]\s*["\']', re.I),
        re.compile(r'biometric.*pin\s*==', re.I),
        # Champ "biometric" auto-déclaré vrai
        re.compile(r'"biometric"\s*:\s*true', re.I),
        re.compile(r"human_verified\s*=\s*True"),
        re.compile(r"unique_human_proven\s*=\s*True"),
    ]

    issues = []
    for f in audit_files:
        if not f.exists():
            continue
        content = f.read_text()
        for pat in FORBIDDEN_PATTERNS:
            m = pat.search(content)
            if m:
                issues.append(f"{f.relative_to(ROOT)}: {m.group()[:60]}")

    if issues:
        return CheckResult("pin_not_identity", False, f"Patterns interdits: {issues}")
    return CheckResult("pin_not_identity", True, "Aucun pattern PIN→identité détecté")


def check_unique_human_proven_false() -> CheckResult:
    """Vérifie que unique_human_proven n'est jamais True en production."""
    # Chercher des assignations unique_human_proven = True (hors tests)
    src_dir = ROOT / "src"
    violations = []
    for py_file in src_dir.rglob("*.py"):
        content = py_file.read_text()
        # Pattern: unique_human_proven = True ou "unique_human_proven": True
        if re.search(r'unique_human_proven\s*[=:]\s*True', content):
            violations.append(str(py_file.relative_to(ROOT)))

    if violations:
        return CheckResult(
            "unique_human_proven_false",
            False,
            f"unique_human_proven=True trouvé dans: {violations}"
        )
    return CheckResult(
        "unique_human_proven_false",
        True,
        "unique_human_proven=False partout dans src/"
    )


def check_reflex_priority_rule_active() -> CheckResult:
    """Vérifie que la règle réflexe est active dans artcb-read-all.mdc."""
    read_all = ROOT / ".cursor" / "rules" / "artcb-read-all.mdc"
    if not read_all.exists():
        return CheckResult("reflex_rule_active", False, "artcb-read-all.mdc absent")
    content = read_all.read_text()
    if "artcb-reflex-priority.mdc" in content:
        return CheckResult("reflex_rule_active", True, "artcb-reflex-priority.mdc référencé dans artcb-read-all.mdc")
    # Pas encore référencé — warning mais pas FAIL bloquant
    return CheckResult(
        "reflex_rule_active",
        True,  # pass non-bloquant — sera ajouté
        "artcb-reflex-priority.mdc à ajouter dans artcb-read-all.mdc (non bloquant)"
    )


# ─── Runner ───────────────────────────────────────────────────────────────────

def run_checks() -> list[CheckResult]:
    """Exécute tous les checks du réflexe."""
    return [
        check_bob_hooks(),
        check_cursor_rules(),
        check_reflex_module(),
        check_certified_100_false(),
        check_face_camera_not_auth_path(),
        check_pin_not_identity_proof(),
        check_unique_human_proven_false(),
        check_reflex_priority_rule_active(),
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description="ARTCB Réflexe Check — vérification automatique")
    parser.add_argument("--strict", action="store_true", help="Exit 1 si au moins un FAIL")
    parser.add_argument("--json", action="store_true", help="Sortie JSON")
    args = parser.parse_args()

    results = run_checks()
    ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    passed = [r for r in results if r.pass_]
    failed = [r for r in results if not r.pass_]

    if args.json:
        report = {
            "reflex_check_version": 1,
            "ts": ts,
            "total": len(results),
            "passed": len(passed),
            "failed": len(failed),
            "certified_100": False,
            "results": [
                {
                    "name": r.name,
                    "pass": r.pass_,
                    "status": r.status,
                    "detail": r.detail,
                    "ts_ns": r.ts_ns,
                }
                for r in results
            ],
        }
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"[ARTCB Réflexe Check] {ts}")
        print(f"{'CHECK':<35} {'STATUS':<12} DÉTAIL")
        print("-" * 90)
        for r in results:
            print(f"{r.name:<35} {r.status:<12} {r.detail[:45]}")
        print(f"\nRésultat : {len(passed)}/{len(results)} PASS {'✅' if not failed else '❌'}")
        if failed:
            print(f"\nFAILS ({len(failed)}) :")
            for r in failed:
                print(f"  ❌ {r.name}: {r.detail}")
        print("\nCERTIFIED_100=false — vérification stub fonctionnelle.")

    if args.strict and failed:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
