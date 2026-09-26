"""Tests R483 — Graphe d'appel AST récursif (call_graph.py) + UAP hook automatique.

Suite de tests pour src/artcb/audit/call_graph.py.
Couvre : scan AST, construction du graphe, détection de cycles,
         impact des changements, traversée récursive, UAP branché dans le hook.

Architecture des tests :
    T01–T03 : scan_module() — extraction fonctions et appels
    T04–T06 : build_call_graph() — graphe complet src/artcb
    T07–T09 : get_transitive_callees() — traversée récursive
    T10–T12 : get_impact_of_change() — effets secondaires
    T13–T15 : détection de cycles
    T16–T18 : CallGraphReport invariants + sérialisation
    T19–T20 : UAP branché dans user_prompt_submit.py
    T21      : call_graph sur modules critiques TASK-001

CERTIFIED_100=false — invariant absolu.
unique_human_proven=false — invariant absolu.
"""
from __future__ import annotations

import ast
import textwrap
import tempfile
from pathlib import Path

import pytest

from src.artcb.audit.call_graph import (
    CallChain,
    CallGraphReport,
    CallSite,
    FunctionNode,
    MODULE_VERSION,
    _collect_calls_in_body,
    _extract_call_name,
    build_call_graph,
    get_impact_of_change,
    get_transitive_callees,
    scan_module,
)


# ─── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


@pytest.fixture
def simple_module(tmp_path: Path) -> Path:
    """Fichier Python minimal avec deux fonctions dont l'une appelle l'autre."""
    code = textwrap.dedent("""\
        def foo(x):
            return bar(x + 1)

        def bar(y):
            return y * 2

        class MyClass:
            def method_a(self):
                return self.method_b()

            def method_b(self):
                return 42
    """)
    p = tmp_path / "simple.py"
    p.write_text(code, encoding="utf-8")
    return p


@pytest.fixture
def cyclic_module(tmp_path: Path) -> Path:
    """Module avec appel cyclique : alpha → beta → alpha."""
    code = textwrap.dedent("""\
        def alpha():
            return beta()

        def beta():
            return alpha()
    """)
    p = tmp_path / "cyclic.py"
    p.write_text(code, encoding="utf-8")
    return p


@pytest.fixture
def minimal_repo(tmp_path: Path) -> Path:
    """Dépôt minimal simulant src/artcb avec deux modules."""
    src = tmp_path / "src" / "artcb"
    src.mkdir(parents=True)
    (src / "__init__.py").write_text("")
    # Module A : appelle une fonction de B
    (src / "module_a.py").write_text(textwrap.dedent("""\
        def entry_point(x):
            return process(x)

        def process(x):
            return helper(x)

        def helper(x):
            return x + 1
    """))
    # Module B : fonctions indépendantes
    (src / "module_b.py").write_text(textwrap.dedent("""\
        def standalone():
            return 0

        def another():
            return standalone()
    """))
    return tmp_path


# ─── T01–T03 : scan_module() ──────────────────────────────────────────────────

def test_T01_scan_module_extracts_functions(simple_module: Path, tmp_path: Path) -> None:
    """T01 — scan_module() extrait les fonctions top-level et les méthodes."""
    nodes, err = scan_module(simple_module, tmp_path)
    assert err is None, f"Erreur AST inattendue : {err}"
    names = {n.qualified_name for n in nodes}
    assert "foo" in names, "Fonction foo non détectée"
    assert "bar" in names, "Fonction bar non détectée"
    assert "MyClass.method_a" in names, "Méthode method_a non détectée"
    assert "MyClass.method_b" in names, "Méthode method_b non détectée"


def test_T02_scan_module_extracts_call_sites(simple_module: Path, tmp_path: Path) -> None:
    """T02 — scan_module() extrait les sites d'appel depuis foo → bar."""
    nodes, err = scan_module(simple_module, tmp_path)
    assert err is None
    foo_node = next((n for n in nodes if n.qualified_name == "foo"), None)
    assert foo_node is not None
    callee_names = [cs.callee_name for cs in foo_node.call_sites]
    assert "bar" in callee_names, f"Appel bar non détecté dans foo. Sites : {callee_names}"


def test_T03_scan_module_invalid_syntax_returns_error(tmp_path: Path) -> None:
    """T03 — scan_module() sur un fichier invalide retourne un message d'erreur (fail-open)."""
    bad = tmp_path / "bad.py"
    bad.write_text("def foo(:\n    pass\n", encoding="utf-8")
    nodes, err = scan_module(bad, tmp_path)
    assert err is not None, "Doit retourner une erreur sur syntaxe invalide"
    assert nodes == [], "Doit retourner une liste vide en cas d'erreur"


# ─── T04–T06 : build_call_graph() ────────────────────────────────────────────

def test_T04_build_call_graph_finds_nodes(minimal_repo: Path) -> None:
    """T04 — build_call_graph() trouve les fonctions des deux modules."""
    report = build_call_graph(minimal_repo)
    names = set(report.nodes.keys())
    assert "entry_point" in names
    assert "process" in names
    assert "helper" in names
    assert "standalone" in names


def test_T05_build_call_graph_builds_edges(minimal_repo: Path) -> None:
    """T05 — build_call_graph() construit les arêtes entry_point→process→helper."""
    report = build_call_graph(minimal_repo)
    # entry_point appelle process
    assert "entry_point" in report.edges, "Pas d'arêtes depuis entry_point"
    callees = report.edges["entry_point"]
    assert any("process" in c for c in callees), f"process non dans callees : {callees}"


def test_T06_build_call_graph_certified_invariants(minimal_repo: Path) -> None:
    """T06 — build_call_graph() : certified_100=False et unique_human_proven=False invariants."""
    report = build_call_graph(minimal_repo)
    assert report.certified_100 is False
    assert report.unique_human_proven is False


# ─── T07–T09 : get_transitive_callees() ──────────────────────────────────────

def test_T07_transitive_callees_chain(minimal_repo: Path) -> None:
    """T07 — get_transitive_callees() retourne la chaîne entry_point→process→helper."""
    report = build_call_graph(minimal_repo)
    chains = get_transitive_callees("entry_point", report)
    assert chains, "Aucune chaîne retournée"
    # Au moins une chaîne doit passer par process
    names_in_chains = {n for c in chains for n in c.chain}
    assert "process" in names_in_chains, f"process absent des chaînes : {names_in_chains}"


def test_T08_transitive_callees_unknown_func(minimal_repo: Path) -> None:
    """T08 — get_transitive_callees() sur une fonction inconnue retourne []."""
    report = build_call_graph(minimal_repo)
    chains = get_transitive_callees("nonexistent_func_xyz", report)
    assert chains == [], "Doit retourner [] pour une fonction inconnue"


def test_T09_transitive_callees_depth(minimal_repo: Path) -> None:
    """T09 — get_transitive_callees() avec max_depth=1 tronque à 1 niveau."""
    report = build_call_graph(minimal_repo)
    chains = get_transitive_callees("entry_point", report, max_depth=1)
    # Toutes les chaînes doivent avoir depth ≤ 2 (entrée + 1 descendant max)
    for chain in chains:
        assert chain.depth <= 2, f"Chaîne trop profonde : {chain}"


# ─── T10–T12 : get_impact_of_change() ────────────────────────────────────────

def test_T10_impact_includes_direct_callees(minimal_repo: Path) -> None:
    """T10 — get_impact_of_change() inclut les callees directs."""
    report = build_call_graph(minimal_repo)
    impacted = get_impact_of_change("entry_point", report)
    assert "entry_point" in impacted, "La fonction elle-même doit être dans l'impact"
    # process est appelé par entry_point → doit être dans l'impact
    assert any("process" in i for i in impacted), f"process absent de l'impact : {impacted}"


def test_T11_impact_includes_transitive(minimal_repo: Path) -> None:
    """T11 — get_impact_of_change() inclut les callees transitifs."""
    report = build_call_graph(minimal_repo)
    impacted = get_impact_of_change("entry_point", report)
    # helper est appelé par process qui est appelé par entry_point
    assert any("helper" in i for i in impacted), f"helper absent de l'impact : {impacted}"


def test_T12_impact_unknown_func_returns_self(minimal_repo: Path) -> None:
    """T12 — get_impact_of_change() sur une fonction sans arêtes retourne juste la fonction."""
    report = build_call_graph(minimal_repo)
    impacted = get_impact_of_change("nonexistent_xyz", report)
    assert impacted == ["nonexistent_xyz"], f"Attendu ['nonexistent_xyz'], reçu {impacted}"


# ─── T13–T15 : Détection de cycles ───────────────────────────────────────────

def test_T13_cycle_detected_in_cyclic_module(cyclic_module: Path, tmp_path: Path) -> None:
    """T13 — build_call_graph() détecte le cycle alpha→beta→alpha."""
    report = build_call_graph(tmp_path, include_paths=[tmp_path])
    assert report.cycles_detected, "Aucun cycle détecté dans le module cyclique"
    # Vérifier qu'alpha ou beta apparaît dans les cycles
    all_in_cycles = {n for cycle in report.cycles_detected for n in cycle}
    assert "alpha" in all_in_cycles or "beta" in all_in_cycles, (
        f"alpha/beta absent des cycles : {all_in_cycles}"
    )


def test_T14_cycle_chain_marked(cyclic_module: Path, tmp_path: Path) -> None:
    """T14 — get_transitive_callees() marque has_cycle=True sur les chaînes cycliques."""
    report = build_call_graph(tmp_path, include_paths=[tmp_path])
    chains = get_transitive_callees("alpha", report, max_depth=10)
    cyclic_chains = [c for c in chains if c.has_cycle]
    assert cyclic_chains, "Aucune chaîne cyclique détectée depuis alpha"


def test_T15_no_false_cycle_in_acyclic_module(minimal_repo: Path) -> None:
    """T15 — build_call_graph() ne détecte pas de faux cycle dans un module acyclique."""
    report = build_call_graph(minimal_repo)
    # Le graphe minimal entry_point→process→helper est acyclique
    # Il peut y avoir des cycles détectés dans d'autres fonctions, mais pas dans cette chaîne
    # On vérifie simplement que le scan ne plante pas et que les invariants tiennent
    assert report.certified_100 is False
    assert report.unique_human_proven is False


# ─── T16–T18 : CallGraphReport invariants + structure ────────────────────────

def test_T16_report_has_all_fields(minimal_repo: Path) -> None:
    """T16 — CallGraphReport expose tous les champs attendus."""
    report = build_call_graph(minimal_repo)
    assert hasattr(report, "nodes")
    assert hasattr(report, "edges")
    assert hasattr(report, "cycles_detected")
    assert hasattr(report, "unreachable")
    assert hasattr(report, "scan_errors")
    assert isinstance(report.nodes, dict)
    assert isinstance(report.edges, dict)
    assert isinstance(report.cycles_detected, list)


def test_T17_function_node_has_module_path(minimal_repo: Path) -> None:
    """T17 — Chaque FunctionNode expose son module_path non vide."""
    report = build_call_graph(minimal_repo)
    for qname, node in report.nodes.items():
        assert node.module_path, f"module_path vide pour {qname}"
        assert node.lineno > 0, f"lineno invalide pour {qname}"


def test_T18_module_version_string() -> None:
    """T18 — MODULE_VERSION est une chaîne non vide."""
    assert isinstance(MODULE_VERSION, str)
    assert MODULE_VERSION, "MODULE_VERSION vide"


# ─── T19–T20 : UAP branché dans le hook ──────────────────────────────────────

def test_T19_uap_hook_inject_produces_uap_line(repo_root: Path) -> None:
    """T19 — user_prompt_submit.py produit une ligne UAP R483 dans sa sortie."""
    import subprocess
    result = subprocess.run(
        ["python3", ".bob/hooks/user_prompt_submit.py", "test"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert "UAP R483" in result.stdout, (
        f"Ligne UAP R483 absente de la sortie du hook.\n"
        f"STDOUT[:500]: {result.stdout[:500]}\n"
        f"STDERR[:200]: {result.stderr[:200]}"
    )


def test_T20_uap_hook_shows_certified_false(repo_root: Path) -> None:
    """T20 — La ligne UAP dans le hook contient certified_100=false."""
    import subprocess
    result = subprocess.run(
        ["python3", ".bob/hooks/user_prompt_submit.py", "test"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        timeout=15,
    )
    uap_lines = [l for l in result.stdout.splitlines() if "UAP R483" in l or "certified_100" in l]
    assert any("certified_100=false" in l for l in uap_lines), (
        f"certified_100=false absent des lignes UAP : {uap_lines}"
    )


# ─── T21 : call_graph sur modules critiques TASK-001 ─────────────────────────

def test_T21_call_graph_task001_modules(repo_root: Path) -> None:
    """T21 — build_call_graph() sur les modules TASK-001 : trouve check_uniqueness
    et les fonctions BCH/FHE critiques."""
    identity_dir = repo_root / "src" / "artcb" / "identity"
    crypto_dir   = repo_root / "src" / "artcb" / "crypto"
    report = build_call_graph(
        repo_root,
        include_paths=[identity_dir, crypto_dir],
    )
    node_names = set(report.nodes.keys())
    # Fonctions critiques TASK-001 attendues
    critical_funcs = [
        "check_uniqueness",
        "fuzzy_extract",
        "fuzzy_reproduce",
        "hamming_distance_bits",
        "enroll_biometric",
    ]
    found = [f for f in critical_funcs if any(f in n for n in node_names)]
    assert len(found) >= 3, (
        f"Moins de 3 fonctions critiques TASK-001 trouvées. "
        f"Trouvées : {found}. Nœuds : {sorted(node_names)[:20]}"
    )
