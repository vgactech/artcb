"""R430 — G16 Cross-Language ConceptID Equivalence — 14 langues complètes.

Objectif (G16 étendu) : démontrer que des expressions équivalentes dans les
14 langues officielles ARTCB produisent le MÊME ConceptID ARTCB, sans
traduction intermédiaire.

Architecture :
  <LANG>_text → IREncoder → ConceptID
  Assertion : intersection des ConceptID non vide OU ∇ documenté honnêtement.

Langues couvertes (14) :
  FR EN ES PT IT RU ZH      ← couverture R321 (partielle→complète)
  AR DE ID JA KO PL TR      ← nouvelles langues R430

Concepts testés par langue :
  V1  — verify/check
  C2  — vehicle/car
  E3  — energy
  N1  — server/node
  S2  — signature
  U1  — consume/use
  B1  — block
  M2  — memory
  M1  — world
  P1  — problem

Honnêteté :
  - Un ∇ (non-couvert) est documenté explicitement, jamais ignoré.
  - unique_human_proven=False invariant dans tous les chemins.
  - CERTIFIED_100=false.

PROTOCOLE ARTCB — mode DEBUG — jamais de stub.
"""
from __future__ import annotations

import pytest

from src.artcb.ir.concept import concept_id_from_node
from src.artcb.ir.encoder import IREncoder


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def enc() -> IREncoder:
    return IREncoder()


def _syms(encoder: IREncoder, text: str) -> set[str]:
    g = encoder.encode(text)
    return {n.sym for n in g.nodes if n.sym}


def _cids(encoder: IREncoder, text: str) -> set[str]:
    g = encoder.encode(text)
    return {concept_id_from_node(n) for n in g.nodes}


def assert_sym_convergence(encoder: IREncoder, texts: dict[str, str], sym: str) -> None:
    """Assert that all provided texts produce a node whose sym CONTAINS the given ARTCB code.

    The IREncoder builds composite symbols (e.g. 'V1N1S2') from multiple matched codes.
    We check whether sym is a substring of any node's sym, or an exact match.
    """
    failures: list[str] = []
    for lang, text in texts.items():
        s = _syms(encoder, text)
        # Match: sym exact match OR sym is a sub-code inside a composite sym
        found = any(sym in node_sym for node_sym in s)
        if not found:
            failures.append(f"{lang.upper()}: '{text}' → {s} (expected code '{sym}' in sym)")
    if failures:
        pytest.fail(f"G16 code '{sym}' NOT FOUND in:\n" + "\n".join(failures))


# ─────────────────────────────────────────────────────────────────────────────
# G16-R430-T01 — Verify (V1) — 14 langues
# ─────────────────────────────────────────────────────────────────────────────

class TestG16VerifyAllLanguages:
    """Concept V1 (verify) doit être reconnu dans les 14 langues officielles."""

    TEXTS: dict[str, str] = {
        "fr": "Le serveur doit vérifier la signature.",
        "en": "The server must verify the signature.",
        "es": "El servidor debe verificar la firma.",
        "pt": "O servidor deve verificar a assinatura.",
        "it": "Il server deve verificare la firma.",
        "ru": "Сервер должен проверить подпись.",
        "zh": "服务器必须验证签名。",
        "ar": "يجب على الخادم أن يتحقق من التوقيع",
        "de": "Der Server muss die Signatur überprüfen.",
        "id": "Server harus memverifikasi tanda tangan.",
        "ja": "サーバーは署名を検証する必要があります。",
        "ko": "서버는 서명을 검증해야 합니다.",
        "pl": "Serwer musi zweryfikować podpis.",
        "tr": "Sunucu imzayı doğrulamak zorundadır.",
    }

    def test_verify_v1_all_languages(self, enc: IREncoder) -> None:
        """V1 reconnu dans les 14 langues — aucun ∇ attendu."""
        assert_sym_convergence(enc, self.TEXTS, "V1")

    def test_concept_ids_not_empty(self, enc: IREncoder) -> None:
        """Chaque texte produit au moins un ConceptID non vide."""
        for lang, text in self.TEXTS.items():
            cids = _cids(enc, text)
            assert cids, f"G16 FAIL — no ConceptID for {lang.upper()}: '{text}'"


# ─────────────────────────────────────────────────────────────────────────────
# G16-R430-T02 — Vehicle (C2) — 14 langues
# ─────────────────────────────────────────────────────────────────────────────

class TestG16VehicleAllLanguages:
    """Concept C2 (vehicle/car) doit converger dans les 14 langues."""

    TEXTS: dict[str, str] = {
        "fr": "La voiture consomme de l'énergie.",
        "en": "The car consumes energy.",
        "es": "El coche consume energía.",
        "pt": "O carro consome energia.",
        "it": "La vettura consuma energia.",
        "ru": "Автомобиль потребляет энергию.",
        "zh": "汽车消耗能源。",
        "ar": "السيارة تستهلك الطاقة.",
        "de": "Das Fahrzeug verbraucht Energie.",
        "id": "Mobil mengonsumsi energi.",
        "ja": "車はエネルギーを消費します。",
        "ko": "자동차는 에너지를 소비합니다.",
        "pl": "Samochód zużywa energię.",
        "tr": "Araba enerji tüketir.",
    }

    def test_vehicle_c2_all_languages(self, enc: IREncoder) -> None:
        assert_sym_convergence(enc, self.TEXTS, "C2")

    def test_energy_e3_all_languages(self, enc: IREncoder) -> None:
        assert_sym_convergence(enc, self.TEXTS, "E3")

    def test_consume_u1_all_languages(self, enc: IREncoder) -> None:
        assert_sym_convergence(enc, self.TEXTS, "U1")

    def test_concept_ids_intersect_fr_en(self, enc: IREncoder) -> None:
        """FR et EN convergent vers les mêmes ConceptIDs pour C2+E3+U1."""
        fr_cids = _cids(enc, self.TEXTS["fr"])
        en_cids = _cids(enc, self.TEXTS["en"])
        common = fr_cids & en_cids
        assert common, f"G16 FAIL — FR/EN C2 ConceptID divergence: FR={fr_cids} EN={en_cids}"


# ─────────────────────────────────────────────────────────────────────────────
# G16-R430-T03 — Server/Node (N1) — 14 langues
# ─────────────────────────────────────────────────────────────────────────────

class TestG16ServerAllLanguages:
    """Concept N1 (server/node) dans les 14 langues."""

    TEXTS: dict[str, str] = {
        "fr": "Le serveur traite les données.",
        "en": "The server processes data.",
        "es": "El servidor procesa datos.",
        "pt": "O servidor processa dados.",
        "it": "Il server elabora dati.",
        "ru": "Сервер обрабатывает данные.",
        "zh": "服务器处理数据。",
        "ar": "الخادم يعالج البيانات.",
        "de": "Der Server verarbeitet Daten.",
        "id": "Server memproses data.",
        "ja": "サーバーはデータを処理します。",
        "ko": "서버는 데이터를 처리합니다.",
        "pl": "Serwer przetwarza dane.",
        "tr": "Sunucu verileri işler.",
    }

    def test_server_n1_all_languages(self, enc: IREncoder) -> None:
        assert_sym_convergence(enc, self.TEXTS, "N1")


# ─────────────────────────────────────────────────────────────────────────────
# G16-R430-T04 — Signature (S2) — 14 langues
# ─────────────────────────────────────────────────────────────────────────────

class TestG16SignatureAllLanguages:
    """Concept S2 (signature) dans les 14 langues."""

    TEXTS: dict[str, str] = {
        "fr": "La signature est valide.",
        "en": "The signature is valid.",
        "es": "La firma es válida.",
        "pt": "A assinatura é válida.",
        "it": "La firma è valida.",
        "ru": "Подпись действительна.",
        "zh": "签名有效。",
        "ar": "التوقيع صالح.",
        "de": "Die Signatur ist gültig.",
        "id": "Tanda tangan valid.",
        "ja": "署名は有効です。",
        "ko": "서명이 유효합니다.",
        "pl": "Podpis jest ważny.",
        "tr": "İmza geçerlidir.",
    }

    def test_signature_s2_all_languages(self, enc: IREncoder) -> None:
        assert_sym_convergence(enc, self.TEXTS, "S2")


# ─────────────────────────────────────────────────────────────────────────────
# G16-R430-T05 — Block (B1) — 14 langues
# ─────────────────────────────────────────────────────────────────────────────

class TestG16BlockAllLanguages:
    """Concept B1 (blockchain block) dans les 14 langues."""

    TEXTS: dict[str, str] = {
        "fr": "Le bloc est validé.",
        "en": "The block is validated.",
        "es": "El bloque es válido.",
        "pt": "O bloco é válido.",
        "it": "Il blocco è valido.",
        "ru": "Блок проверен.",
        "zh": "区块有效。",
        "ar": "الكتلة صالحة.",
        "de": "Der Block ist gültig.",
        "id": "Blok sudah valid.",
        "ja": "ブロックは検証済みです。",
        "ko": "블록이 검증되었습니다.",
        "pl": "Blok jest zweryfikowany.",
        "tr": "Blok doğrulandı.",
    }

    def test_block_b1_all_languages(self, enc: IREncoder) -> None:
        assert_sym_convergence(enc, self.TEXTS, "B1")


# ─────────────────────────────────────────────────────────────────────────────
# G16-R430-T06 — Memory (M2) — 14 langues
# ─────────────────────────────────────────────────────────────────────────────

class TestG16MemoryAllLanguages:
    """Concept M2 (memory) dans les 14 langues."""

    TEXTS: dict[str, str] = {
        "fr": "La mémoire est insuffisante.",
        "en": "Memory is insufficient.",
        "es": "La memoria es insuficiente.",
        "pt": "A memória é insuficiente.",
        "it": "La memoria è insufficiente.",
        "ru": "Памяти недостаточно.",
        "zh": "内存不足。",
        "ar": "الذاكرة غير كافية.",
        "de": "Der Speicher ist unzureichend.",
        "id": "Memori tidak cukup.",
        "ja": "メモリが不足しています。",
        "ko": "메모리가 부족합니다.",
        "pl": "Pamięć jest niewystarczająca.",
        "tr": "Bellek yetersiz.",
    }

    def test_memory_m2_all_languages(self, enc: IREncoder) -> None:
        assert_sym_convergence(enc, self.TEXTS, "M2")


# ─────────────────────────────────────────────────────────────────────────────
# G16-R430-T07 — World (M1) — 14 langues
# ─────────────────────────────────────────────────────────────────────────────

class TestG16WorldAllLanguages:
    """Concept M1 (world) dans les 14 langues."""

    TEXTS: dict[str, str] = {
        "fr": "Le monde est décentralisé.",
        "en": "The world is decentralized.",
        "es": "El mundo es descentralizado.",
        "pt": "O mundo é descentralizado.",
        "it": "Il mondo è decentralizzato.",
        "ru": "Мир децентрализован.",
        "zh": "世界是去中心化的。",
        "ar": "العالم غير مركزي.",
        "de": "Die Welt ist dezentral.",
        "id": "Dunia terdesentralisasi.",
        "ja": "世界は分散化されています。",
        "ko": "세계는 분산되어 있습니다.",
        "pl": "Świat jest zdecentralizowany.",
        "tr": "Dünya merkeziyetsizdir.",
    }

    def test_world_m1_all_languages(self, enc: IREncoder) -> None:
        assert_sym_convergence(enc, self.TEXTS, "M1")


# ─────────────────────────────────────────────────────────────────────────────
# G16-R430-T08 — Problem (P1) — 14 langues
# ─────────────────────────────────────────────────────────────────────────────

class TestG16ProblemAllLanguages:
    """Concept P1 (problem) dans les 14 langues."""

    TEXTS: dict[str, str] = {
        "fr": "Le problème est résolu.",
        "en": "The problem is solved.",
        "es": "El problema está resuelto.",
        "pt": "O problema está resolvido.",
        "it": "Il problema è risolto.",
        "ru": "Проблема решена.",
        "zh": "问题已解决。",
        "ar": "المشكلة محلولة.",
        "de": "Das Problem ist gelöst.",
        "id": "Masalah sudah diselesaikan.",
        "ja": "問題は解決されました。",
        "ko": "문제가 해결되었습니다.",
        "pl": "Problem jest rozwiązany.",
        "tr": "Sorun çözüldü.",
    }

    def test_problem_p1_all_languages(self, enc: IREncoder) -> None:
        assert_sym_convergence(enc, self.TEXTS, "P1")


# ─────────────────────────────────────────────────────────────────────────────
# G16-R430-T09 — Tokenizer coverage — scripts non-Latin
# ─────────────────────────────────────────────────────────────────────────────

class TestTokenizerCoverage:
    """Vérifie que le tokenizer R430 tokenise correctement les scripts non-Latin."""

    def test_arabic_tokenized(self, enc: IREncoder) -> None:
        """L'arabe doit produire des tokens et des symboles."""
        g = enc.encode("السيارة تستهلك الطاقة")
        assert g.nodes, "G16 ∇ Arabic — aucun nœud encodé"

    def test_japanese_katakana_tokenized(self, enc: IREncoder) -> None:
        """Le Katakana japonais doit produire des tokens."""
        g = enc.encode("サーバーは署名を検証する")
        assert g.nodes, "G16 ∇ Japanese — aucun nœud encodé"

    def test_korean_hangul_tokenized(self, enc: IREncoder) -> None:
        """Le Hangul coréen doit produire des tokens."""
        g = enc.encode("서버는 서명을 검증해야 합니다")
        assert g.nodes, "G16 ∇ Korean — aucun nœud encodé"

    def test_german_umlauts_tokenized(self, enc: IREncoder) -> None:
        """Les umlauts allemands (ü ö ä) doivent être tokenisés.
        Le sym est composite (ex: 'U1C2E3') — on cherche 'C2' comme sous-code.
        """
        g = enc.encode("Das Fahrzeug verbraucht Energie")
        assert any("C2" in (n.sym or "") for n in g.nodes), \
            f"G16 ∇ German — Fahrzeug not mapped to C2 — syms: {[n.sym for n in g.nodes]}"

    def test_polish_diacritics_tokenized(self, enc: IREncoder) -> None:
        """Les diacritiques polonais (ą ę ś ć ż) doivent être tokenisés.
        Le sym est composite — on cherche 'C2' comme sous-code.
        """
        g = enc.encode("Samochód zużywa energię")
        assert any("C2" in (n.sym or "") for n in g.nodes), \
            f"G16 ∇ Polish — Samochód not mapped to C2 — syms: {[n.sym for n in g.nodes]}"

    def test_turkish_special_chars_tokenized(self, enc: IREncoder) -> None:
        """Les caractères turcs (ğ ı ş ç ü ö) doivent être tokenisés.
        Le sym est composite — on cherche 'C2' comme sous-code.
        """
        g = enc.encode("Araba enerji tüketir")
        assert any("C2" in (n.sym or "") for n in g.nodes), \
            f"G16 ∇ Turkish — Araba not mapped to C2 — syms: {[n.sym for n in g.nodes]}"


# ─────────────────────────────────────────────────────────────────────────────
# G16-R430-T10 — Invariant unique_human_proven=False dans tous les chemins
# ─────────────────────────────────────────────────────────────────────────────

class TestInvariantUniqueHumanProven:
    """Le système IR ne prouve jamais l'unicité humaine — invariant ARTCB."""

    ALL_TEXTS: list[str] = [
        "السيارة تستهلك الطاقة",
        "Das Fahrzeug verbraucht Energie",
        "Mobil mengonsumsi energi",
        "車はエネルギーを消費します",
        "자동차는 에너지를 소비합니다",
        "Samochód zużywa energię",
        "Araba enerji tüketir",
    ]

    def test_encoder_does_not_set_unique_human(self, enc: IREncoder) -> None:
        """IREncoder ne produit pas d'attribut unique_human_proven=True."""
        for text in self.ALL_TEXTS:
            g = enc.encode(text)
            for node in g.nodes:
                attrs = vars(node) if hasattr(node, "__dict__") else {}
                assert not attrs.get("unique_human_proven", False), (
                    f"INVARIANT VIOLATED: unique_human_proven=True in node {node}"
                )
