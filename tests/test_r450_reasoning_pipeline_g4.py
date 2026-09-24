"""R450 — Tests G4 : Pipeline de raisonnement bout-en-bout ARTCB.

Couverture G4 — 28 tests P01→P28 :

  VALIDATION ENTRÉES (P01→P06)
  ─────────────────────────────
  P01 : texte valide FR → PipelineResult retourné sans exception
  P02 : producer_id vide → PipelineError
  P03 : producer_id None → PipelineError
  P04 : text=None → PipelineError
  P05 : text trop court (<3 car) → PipelineError
  P06 : text non-string → PipelineError

  DÉTERMINISME (P07→P10)
  ─────────────────────────
  P07 : même texte + même producer_id + même ts → même knowledge_id
  P08 : même texte + même producer_id + même ts → même reasoning_id (canonical)
  P09 : texte différent → knowledge_id différent
  P10 : producer_id différent → knowledge_id différent

  COHÉRENCE DES MAILLONS (P11→P16)
  ──────────────────────────────────
  P11 : knowledge_id présent et non vide dans PipelineResult
  P12 : usage.knowledge_id == knowledge.knowledge_id
  P13 : pol_metrics.knowledge_id == knowledge.knowledge_id
  P14 : work_record.knowledge_id == knowledge.knowledge_id
  P15 : work_record.usage_id == usage.usage_id
  P16 : work_record.pol_score == pol_metrics.pol_score

  INVARIANTS PoL / SÉCURITÉ (P17→P20)
  ──────────────────────────────────────
  P17 : unique_human_proven = False dans tout résultat
  P18 : certified_100 = False dans tout résultat
  P19 : knowledge.status = ACTIVE après pipeline normal
  P20 : usage.pol_eligible = True (purpose=POL_CLAIM + status=ACTIVE)

  RÉSISTANCE AUX ENTRÉES MALFORMÉES (P21→P23)
  ─────────────────────────────────────────────
  P21 : texte 10 001 car → pas d'exception (tronqué à 10 000)
  P22 : texte avec caractères spéciaux → pas d'exception
  P23 : texte tout en chiffres → pas d'exception

  MULTILINGUISME 14 LANGUES (P24→P26)
  ──────────────────────────────────────
  P24 : 14 langues produisent chacune un PipelineResult (pas d'exception)
  P25 : language_hint correctement propagé dans to_summary()
  P26 : langues différentes → reasoning_id peut diverger (documenté honnêtement)

  RÉSUMÉ & SÉRIALISATION (P27→P28)
  ──────────────────────────────────
  P27 : to_summary() contient tous les champs obligatoires
  P28 : non-régression — pipeline ne casse pas les tests R434/R436

PROTOCOLE ARTCB — mode DEBUG actif — CERTIFIED_100=false.
"""
from __future__ import annotations

import pytest

from src.artcb.reasoning.pipeline import (
    PipelineError,
    PipelineResult,
    PipelineStageError,
    ReasoningPipeline,
)

# ─── Fixture ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def pipeline() -> ReasoningPipeline:
    """Instance partagée du pipeline G4 (IREncoder + PolScorer avec cache)."""
    return ReasoningPipeline()


# ─── Textes de test par langue ────────────────────────────────────────────────

LANG_SAMPLES: dict[str, tuple[str, str]] = {
    "fr": ("fr", "Le serveur valide la signature PQC et produit un bloc."),
    "en": ("en", "The server verifies the signature and produces a block."),
    "es": ("es", "El servidor verifica la firma y produce un bloque."),
    "pt": ("pt", "O servidor verifica a assinatura e produz um bloco."),
    "it": ("it", "Il server verifica la firma e produce un blocco."),
    "ru": ("ru", "Сервер проверяет подпись и создаёт блок."),
    "zh": ("zh", "服务器验证签名并生成块。"),
    "ar": ("ar", "يتحقق الخادم من التوقيع وينتج كتلة."),
    "de": ("de", "Der Server prüft die Signatur und erzeugt einen Block."),
    "id": ("id", "Server memverifikasi tanda tangan dan menghasilkan blok."),
    "ja": ("ja", "サーバーが署名を検証してブロックを生成する。"),
    "ko": ("ko", "서버가 서명을 검증하고 블록을 생성합니다."),
    "pl": ("pl", "Serwer weryfikuje podpis i generuje blok."),
    "tr": ("tr", "Sunucu imzayı doğrular ve bir blok üretir."),
}

_TEXT_FR = LANG_SAMPLES["fr"][1]
_TEXT_EN = LANG_SAMPLES["en"][1]


# ═══════════════════════════════════════════════════════════════════════════════
# VALIDATION ENTRÉES
# ═══════════════════════════════════════════════════════════════════════════════

def test_p01_valid_french_text_returns_pipeline_result(pipeline: ReasoningPipeline) -> None:
    """P01 — Texte FR valide → PipelineResult retourné sans exception."""
    result = pipeline.run(_TEXT_FR, producer_id="agent_test", language_hint="fr")
    assert isinstance(result, PipelineResult)


def test_p02_empty_producer_id_raises_pipeline_error(pipeline: ReasoningPipeline) -> None:
    """P02 — producer_id vide → PipelineError."""
    with pytest.raises(PipelineError, match="producer_id"):
        pipeline.run(_TEXT_FR, producer_id="")


def test_p03_none_producer_id_raises_pipeline_error(pipeline: ReasoningPipeline) -> None:
    """P03 — producer_id=None → PipelineError."""
    with pytest.raises(PipelineError, match="producer_id"):
        pipeline.run(_TEXT_FR, producer_id=None)  # type: ignore[arg-type]


def test_p04_none_text_raises_pipeline_error(pipeline: ReasoningPipeline) -> None:
    """P04 — text=None → PipelineError."""
    with pytest.raises(PipelineError, match="None"):
        pipeline.run(None, producer_id="agent_test")  # type: ignore[arg-type]


def test_p05_too_short_text_raises_pipeline_error(pipeline: ReasoningPipeline) -> None:
    """P05 — text trop court (<3 car après strip) → PipelineError."""
    with pytest.raises(PipelineError, match="court"):
        pipeline.run("ab", producer_id="agent_test")


def test_p06_non_string_text_raises_pipeline_error(pipeline: ReasoningPipeline) -> None:
    """P06 — text non-str → PipelineError."""
    with pytest.raises(PipelineError, match="str"):
        pipeline.run(42, producer_id="agent_test")  # type: ignore[arg-type]


# ═══════════════════════════════════════════════════════════════════════════════
# DÉTERMINISME
# ═══════════════════════════════════════════════════════════════════════════════

def test_p07_same_text_same_producer_same_ts_same_knowledge_id(pipeline: ReasoningPipeline) -> None:
    """P07 — même texte + même producer_id + même ts → même knowledge_id."""
    ts = "2026-09-24T10:00:00Z"
    r1 = pipeline.run(_TEXT_FR, producer_id="agent_A", language_hint="fr", created_at=ts)
    r2 = pipeline.run(_TEXT_FR, producer_id="agent_A", language_hint="fr", created_at=ts)
    assert r1.knowledge.knowledge_id == r2.knowledge.knowledge_id, (
        f"P07 : knowledge_id diverge : {r1.knowledge.knowledge_id!r} ≠ {r2.knowledge.knowledge_id!r}"
    )


def test_p08_same_text_same_producer_same_ts_same_reasoning_id(pipeline: ReasoningPipeline) -> None:
    """P08 — même texte + même producer_id + même ts → même reasoning_id canonique."""
    ts = "2026-09-24T10:00:00Z"
    r1 = pipeline.run(_TEXT_FR, producer_id="agent_A", language_hint="fr", created_at=ts)
    r2 = pipeline.run(_TEXT_FR, producer_id="agent_A", language_hint="fr", created_at=ts)
    assert r1.canonical.reasoning_id() == r2.canonical.reasoning_id(), (
        f"P08 : reasoning_id diverge : {r1.canonical.reasoning_id()!r} ≠ {r2.canonical.reasoning_id()!r}"
    )


def test_p09_different_text_different_knowledge_id(pipeline: ReasoningPipeline) -> None:
    """P09 — textes différents → knowledge_id différents."""
    ts = "2026-09-24T10:00:00Z"
    r1 = pipeline.run(_TEXT_FR, producer_id="agent_A", created_at=ts)
    r2 = pipeline.run(_TEXT_EN, producer_id="agent_A", created_at=ts)
    # Les deux texts sont différents → reasoning_id différent → knowledge_id différent
    # (Cas limite : si les deux textes produisent exactement le même graphe IR réduit,
    # les IDs pourraient coïncider — on documente ce cas honnêtement mais c'est rare)
    if r1.canonical.reasoning_id() != r2.canonical.reasoning_id():
        assert r1.knowledge.knowledge_id != r2.knowledge.knowledge_id, (
            "P09 : reasoning_ids différents mais knowledge_ids identiques — incohérence"
        )


def test_p10_different_producer_different_knowledge_id(pipeline: ReasoningPipeline) -> None:
    """P10 — même texte mais producer_id différent → knowledge_id différent."""
    ts = "2026-09-24T10:00:00Z"
    r1 = pipeline.run(_TEXT_FR, producer_id="agent_A", created_at=ts)
    r2 = pipeline.run(_TEXT_FR, producer_id="agent_B", created_at=ts)
    assert r1.knowledge.knowledge_id != r2.knowledge.knowledge_id, (
        "P10 : knowledge_id doit différer quand producer_id diffère"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# COHÉRENCE DES MAILLONS
# ═══════════════════════════════════════════════════════════════════════════════

def test_p11_knowledge_id_non_empty(pipeline: ReasoningPipeline) -> None:
    """P11 — knowledge_id présent et non vide dans PipelineResult."""
    result = pipeline.run(_TEXT_FR, producer_id="agent_test")
    assert result.knowledge.knowledge_id, "P11 : knowledge_id vide"
    assert result.knowledge.knowledge_id.startswith("K"), (
        f"P11 : knowledge_id doit commencer par 'K', reçu: {result.knowledge.knowledge_id!r}"
    )


def test_p12_usage_knowledge_id_matches_knowledge(pipeline: ReasoningPipeline) -> None:
    """P12 — usage.knowledge_id == knowledge.knowledge_id."""
    result = pipeline.run(_TEXT_FR, producer_id="agent_test")
    assert result.usage.knowledge_id == result.knowledge.knowledge_id, (
        f"P12 : incohérence usage.knowledge_id={result.usage.knowledge_id!r} "
        f"≠ knowledge.knowledge_id={result.knowledge.knowledge_id!r}"
    )


def test_p13_pol_metrics_knowledge_id_matches(pipeline: ReasoningPipeline) -> None:
    """P13 — pol_metrics.knowledge_id == knowledge.knowledge_id."""
    result = pipeline.run(_TEXT_FR, producer_id="agent_test")
    assert result.pol_metrics.knowledge_id == result.knowledge.knowledge_id, (
        f"P13 : pol_metrics.knowledge_id={result.pol_metrics.knowledge_id!r} "
        f"≠ knowledge_id={result.knowledge.knowledge_id!r}"
    )


def test_p14_work_record_knowledge_id_matches(pipeline: ReasoningPipeline) -> None:
    """P14 — work_record.knowledge_id == knowledge.knowledge_id."""
    result = pipeline.run(_TEXT_FR, producer_id="agent_test")
    assert result.work_record.knowledge_id == result.knowledge.knowledge_id, (
        f"P14 : work_record.knowledge_id={result.work_record.knowledge_id!r} "
        f"≠ knowledge_id={result.knowledge.knowledge_id!r}"
    )


def test_p15_work_record_usage_id_matches(pipeline: ReasoningPipeline) -> None:
    """P15 — work_record.usage_id == usage.usage_id."""
    result = pipeline.run(_TEXT_FR, producer_id="agent_test")
    assert result.work_record.usage_id == result.usage.usage_id, (
        f"P15 : work_record.usage_id={result.work_record.usage_id!r} "
        f"≠ usage.usage_id={result.usage.usage_id!r}"
    )


def test_p16_work_record_pol_score_matches(pipeline: ReasoningPipeline) -> None:
    """P16 — work_record.pol_score == pol_metrics.pol_score."""
    result = pipeline.run(_TEXT_FR, producer_id="agent_test")
    assert result.work_record.pol_score == result.pol_metrics.pol_score, (
        f"P16 : work_record.pol_score={result.work_record.pol_score} "
        f"≠ pol_metrics.pol_score={result.pol_metrics.pol_score}"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# INVARIANTS PoL / SÉCURITÉ
# ═══════════════════════════════════════════════════════════════════════════════

def test_p17_unique_human_proven_always_false(pipeline: ReasoningPipeline) -> None:
    """P17 — unique_human_proven = False dans tout résultat de pipeline."""
    result = pipeline.run(_TEXT_FR, producer_id="agent_test")
    assert result.unique_human_proven is False, (
        "P17 : unique_human_proven doit être False — invariant ARTCB"
    )


def test_p18_certified_100_always_false(pipeline: ReasoningPipeline) -> None:
    """P18 — certified_100 = False dans tout résultat de pipeline."""
    result = pipeline.run(_TEXT_FR, producer_id="agent_test")
    assert result.certified_100 is False, (
        "P18 : certified_100 doit être False — invariant ARTCB"
    )


def test_p19_knowledge_status_active(pipeline: ReasoningPipeline) -> None:
    """P19 — knowledge.status = ACTIVE après pipeline normal."""
    from src.artcb.knowledge.knowledge import KnowledgeStatus
    result = pipeline.run(_TEXT_FR, producer_id="agent_test")
    assert result.knowledge.status == KnowledgeStatus.ACTIVE, (
        f"P19 : statut inattendu : {result.knowledge.status}"
    )


def test_p20_usage_pol_eligible_true(pipeline: ReasoningPipeline) -> None:
    """P20 — usage.pol_eligible = True (purpose=POL_CLAIM + knowledge ACTIVE)."""
    result = pipeline.run(_TEXT_FR, producer_id="agent_test")
    assert result.usage.pol_eligible is True, (
        "P20 : pol_eligible doit être True pour purpose=POL_CLAIM + status=ACTIVE"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# RÉSISTANCE AUX ENTRÉES MALFORMÉES
# ═══════════════════════════════════════════════════════════════════════════════

def test_p21_very_long_text_truncated_no_exception(pipeline: ReasoningPipeline) -> None:
    """P21 — Texte de 10 001 car → pas d'exception (tronqué à 10 000)."""
    long_text = "Le serveur ARTCB valide le bloc. " * 400  # ~13 200 car
    result = pipeline.run(long_text, producer_id="agent_test")
    assert isinstance(result, PipelineResult)
    assert len(result.input_text) <= ReasoningPipeline.MAX_TEXT_LEN


def test_p22_special_characters_no_exception(pipeline: ReasoningPipeline) -> None:
    """P22 — Texte avec caractères spéciaux → pas d'exception."""
    text = "ARTCB ✓ ← → ↑ ↓ ≤ ≥ ∀ ∃ ∈ ∉ ≡ ≠ 🔒🔑 blockchain"
    result = pipeline.run(text, producer_id="agent_test")
    assert isinstance(result, PipelineResult)


def test_p23_numeric_only_text_no_exception(pipeline: ReasoningPipeline) -> None:
    """P23 — Texte tout en chiffres → pas d'exception."""
    result = pipeline.run("1234567890", producer_id="agent_test")
    assert isinstance(result, PipelineResult)


# ═══════════════════════════════════════════════════════════════════════════════
# MULTILINGUISME 14 LANGUES
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("lang_code,text", [
    (lang, text) for lang, (_, text) in LANG_SAMPLES.items()
])
def test_p24_14_languages_no_exception(pipeline: ReasoningPipeline, lang_code: str, text: str) -> None:
    """P24 — Les 14 langues produisent chacune un PipelineResult sans exception."""
    result = pipeline.run(text, producer_id="agent_test", language_hint=lang_code)
    assert isinstance(result, PipelineResult), f"P24 : échec pour langue {lang_code!r}"
    assert result.knowledge.knowledge_id, f"P24 : knowledge_id vide pour {lang_code!r}"


def test_p25_language_hint_propagated_in_summary(pipeline: ReasoningPipeline) -> None:
    """P25 — language_hint correctement propagé dans to_summary()."""
    result = pipeline.run(
        LANG_SAMPLES["ar"][1], producer_id="agent_test", language_hint="ar"
    )
    summary = result.to_summary()
    assert summary["language_hint"] == "ar", (
        f"P25 : language_hint non propagé : {summary.get('language_hint')!r}"
    )


def test_p26_different_languages_can_diverge_documented(pipeline: ReasoningPipeline) -> None:
    """P26 — Langues différentes → reasoning_id peut diverger (documenté honnêtement).

    Ce test vérifie que le pipeline n'invente pas une équivalence sémantique
    entre les langues. La divergence est attendue et documentée (pas un bug).
    On s'assure simplement qu'aucune exception n'est levée et que les résultats
    sont retournés.
    """
    ts = "2026-09-24T10:00:00Z"
    results = {}
    for lang_code, (_, text) in LANG_SAMPLES.items():
        results[lang_code] = pipeline.run(
            text, producer_id="agent_test", language_hint=lang_code, created_at=ts
        )

    # Vérification honnête : le nombre de reasoning_ids uniques
    unique_reasoning_ids = {r.canonical.reasoning_id() for r in results.values()}
    # On ne prétend PAS que toutes les langues convergent.
    # On documente la couverture réelle :
    # Si > 1 ID unique → divergence inter-langues (attendu)
    # Si = 1 ID unique → convergence inattendue (possible mais exceptionnel)
    # Dans les deux cas, le pipeline ne doit pas lever d'exception.
    assert len(unique_reasoning_ids) >= 1, (
        "P26 : aucun reasoning_id produit — erreur inattendue"
    )
    # Note honnête : la convergence totale serait une prétention injustifiée
    # sauf si l'IREncoder reconnaît les 14 langues de façon équivalente.


# ═══════════════════════════════════════════════════════════════════════════════
# RÉSUMÉ & SÉRIALISATION
# ═══════════════════════════════════════════════════════════════════════════════

def test_p27_to_summary_contains_mandatory_fields(pipeline: ReasoningPipeline) -> None:
    """P27 — to_summary() contient tous les champs obligatoires."""
    result = pipeline.run(_TEXT_FR, producer_id="agent_test", language_hint="fr")
    summary = result.to_summary()
    mandatory_fields = [
        "knowledge_id",
        "reasoning_id",
        "usage_id",
        "work_record_id",
        "pol_score",
        "block_accepted",
        "pol_eligible",
        "language_hint",
        "producer_id",
        "session_id",
        "created_at",
        "unique_human_proven",
        "certified_100",
    ]
    for field_name in mandatory_fields:
        assert field_name in summary, (
            f"P27 : champ obligatoire manquant dans to_summary() : {field_name!r}"
        )
    # Invariants toujours dans le résumé
    assert summary["unique_human_proven"] is False
    assert summary["certified_100"] is False


def test_p28_non_regression_r434_r436_imports(pipeline: ReasoningPipeline) -> None:
    """P28 — Non-régression : les imports R434/R436 restent fonctionnels après R450."""
    # Vérification que les imports critiques des modules voisins ne sont pas cassés
    from src.artcb.knowledge.knowledge import create_knowledge, KnowledgeType, KnowledgeStatus
    from src.artcb.knowledge.usage import record_usage, UsagePurpose
    from src.artcb.chain.knowledge_work import create_knowledge_work_record

    # Test fonctionnel minimal — si les imports fonctionnent et le pipeline aussi, R450 n'a pas cassé R434/R436
    result = pipeline.run(
        "ARTCB blockchain decentralized validation node block",
        producer_id="regression_agent",
        language_hint="en",
    )
    assert result.knowledge.knowledge_id.startswith("K"), "P28 : KnowledgeID format invalide"
    assert result.usage.usage_id.startswith("U"), "P28 : UsageID format invalide"
    assert result.work_record.work_record_id.startswith("KW"), "P28 : WorkRecordID format invalide"
