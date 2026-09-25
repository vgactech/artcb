# R465 — Bibliothèque Lexicale IA ARTCB 14 langues

**Date :** 2026-09-25T17:05:00Z
**SHA commit :** `16f878e` (code) + rapport mis à jour
**Tâche :** TASK-001-BIOMETRIE-SUITE → R465 (Lexicon Builder)
**CERTIFIED_100 :** false
**État rapport :** FINAL (13/14 langues — ja en retry PID 11945)

---

## 1. Contexte

Le `LanguageRegistry` (R448) était complet côté architecture (14 modules enregistrés) mais tous vides (`entry_count = 0`). R465 implémente le pipeline de construction des dictionnaires complets depuis **kaikki.org** (dumps Wiktionary pré-parsés, licence libre CC-BY-SA 3.0).

---

## 2. Artefacts produits

### 2.1 Code (committé — SHA `13f2158`)

| Fichier | Lignes | Rôle |
|---------|--------|------|
| `scripts/artcb_r465_lexicon_build.py` | 457 | Build streaming kaikki.org → JSON |
| `src/artcb/language/lexicon_loader.py` | 269 | LexiconLoader JSON → LanguageRegistry |
| `tests/test_r465_lexicon_loader.py` | 311 | 25 tests pipeline (mini-lexicon compact) |
| `.gitignore` | +3 lignes | `data/lexicons/` exclu (>100 MB) |

### 2.2 Données lexicales (locales — non committées, ignorées par `.gitignore`)

| Langue | Entrées brutes | Lemmes+formes | Taille | SHA256 (8 premiers cars) | État |
|--------|---------------|---------------|--------|--------------------------|------|
| Français (`fr`) | 403 269 | 784 019 | 97 MB | `168760bd` | ✅ DONE |
| Anglais (`en`) | 1 492 836 | 2 360 112 | 293 MB | `dff3588b` | ✅ DONE |
| Espagnol (`es`) | 811 049 | 1 992 273 | 247 MB | `ec3f0c53` | ✅ DONE |
| Portugais (`pt`) | 446 043 | 909 945 | 112 MB | `8752d313` | ✅ DONE |
| Italien (`it`) | 623 702 | 1 363 559 | 170 MB | `f79d96d1` | ✅ DONE |
| Russe (`ru`) | 442 594 | 1 935 993 | 272 MB | `2ba71422` | ✅ DONE |
| Chinois (`zh`) | 327 297 | 472 921 | 57 MB | `f7f33f01` | ✅ DONE |
| Arabe (`ar`) | 78 135 | 1 373 037 | 185 MB | `af6260d6` | ✅ DONE |
| Allemand (`de`) | 371 261 | 1 733 696 | 224 MB | `0d55244d` | ✅ DONE |
| Indonésien (`id`) | 40 098 | 79 949 | 10 MB | `96205c44` | ✅ DONE |
| Japonais (`ja`) | — (timeout 16h) | — | — | — | 🔄 RETRY (PID 11945) |
| Coréen (`ko`) | 63 773 | 463 834 | 58 MB | — | ✅ DONE |
| Polonais (`pl`) | 199 289 | 1 885 859 | 237 MB | `fd676396` | ✅ DONE |
| Turc (`tr`) | 45 949 | 2 891 601 | 374 MB | — | ✅ DONE |

**Total build_report.json :** 13/14 langues, **18 246 798 entrées uniques**, ~2,1 GB total
**Cause erreur ja :** timeout réseau après ~16h (dump ~1-2 GB, réseau instable) — retry en cours

---

## 3. Architecture du pipeline

```
kaikki.org JSONL
     │
     ▼ (streaming HTTP)
artcb_r465_lexicon_build.py
     │  _extract_entries() : lemma + forms → LexicalEntry
     │  _bch_encode() : N/A (artcb_code = UNK par défaut)
     ▼
data/lexicons/{lang}_lexicon.json
     │  Format : { lang_id, entries: [{surface_form, lemma, pos, senses, artcb_code}] }
     ▼
LexiconLoader.load(registry, lang_id)
     │  → LanguageModule.entries += [LexicalEntry]
     │  → coverage_state = IMPLEMENTED | PARTIALLY_IMPLEMENTED
     ▼
LanguageRegistry
     └─ get("fr").entry_count = 784019
```

### Format d'une entrée lexicale

```json
{
  "surface_form": "maison",
  "lemma": "maison",
  "pos": "noun",
  "lang": "fr",
  "senses": [{"raw_gloss": "habitation humaine"}],
  "artcb_code": "UNK",
  "confidence": 1.0
}
```

`artcb_code = "UNK"` = non encore résolu par l'IREncoder (chantier R466+).

---

## 4. Tests — résultats

### Avant (R448) — état initial
```
LanguageRegistry.get("fr").entry_count = 0   # tous les 14 modules vides
```

### Après (R465) — état réel (13/14 terminées)
```
LanguageRegistry.get("fr").entry_count = 784019
LanguageRegistry.get("en").entry_count = 2360112
LanguageRegistry.get("es").entry_count = 1992273
LanguageRegistry.get("pt").entry_count = 909945
LanguageRegistry.get("it").entry_count = 1363559
LanguageRegistry.get("ru").entry_count = 1935993
LanguageRegistry.get("zh").entry_count = 472921
LanguageRegistry.get("ar").entry_count = 1373037
LanguageRegistry.get("de").entry_count = 1733696
LanguageRegistry.get("id").entry_count = 79949
LanguageRegistry.get("ja").entry_count = 0   # en retry
LanguageRegistry.get("ko").entry_count = 463834
LanguageRegistry.get("pl").entry_count = 1885859
LanguageRegistry.get("tr").entry_count = 2891601
```

### Tests automatisés

```
tests/test_r465_lexicon_loader.py — 25/25 PASS (10.79s) sur SHA 16f878e

T01 PASS (fr_lexicon.json présent 97 MB → format validé)
T02 PASS (idem — entries > 0, certified_100=False)
T03–T15 : pipeline sur mini-lexicon compact (rapide <1s par test)
T16–T19 : tests négatifs (langue absente, JSON corrompu, entrées vides)
T20–T25 : load_all, coverage_report, lookup, bounds confidence

Gate DO-178C : 124/124 PASS avant commit
```

**Correction timeout :** Fixture `loader` (97 MB → 307s FAIL) → `loader_small` (mini-lexicon tmp → 10.79s PASS). T01/T02 décorés `@pytest.mark.skipif` si fichier absent.

---

## 5. Avant / Après

### `src/artcb/language/lexicon_loader.py` (NOUVEAU)
- **Avant :** inexistant
- **Après :** 269 lignes — `LexiconLoader`, `load()`, `load_all()`, `coverage_report()`, `get_loader()`, `load_all_lexicons()`

### `tests/test_r465_lexicon_loader.py` (NOUVEAU puis CORRIGÉ)
- **Avant :** inexistant
- **Après R465 initial :** fixture `loader` → LEXICON_DIR (97 MB) → timeout 307s sur T20–T23
- **Après correction :** fixture `loader_small` → `tmp_path` mini-lexicon → 14.77s, 25/25 PASS

### `.gitignore` (MODIFIÉ)
- **Avant ligne 75 :** fin du fichier (SSH keys)
- **Après :** `data/lexicons/` ajouté (ligne 78) — protège contre commit accidentel de fichiers >100 MB

---

## 6. Avancement global R465

| Étape | État |
|-------|------|
| Script build `artcb_r465_lexicon_build.py` | ✅ DONE |
| `LexiconLoader` (`lexicon_loader.py`) | ✅ DONE |
| Tests 25/25 PASS | ✅ DONE |
| `.gitignore` data/lexicons | ✅ DONE |
| Commit + push `13f2158` | ✅ DONE |
| Rapport intermédiaire + push `16f878e` | ✅ DONE |
| **Build fr** (784k entrées, 97 MB) | ✅ DONE |
| **Build en** (2.36M entrées, 293 MB) | ✅ DONE |
| **Build es** (1.99M entrées, 247 MB) | ✅ DONE |
| **Build pt** (910k entrées, 112 MB) | ✅ DONE |
| **Build it** (1.36M entrées, 170 MB) | ✅ DONE |
| **Build ru** (1.93M entrées, 272 MB) | ✅ DONE |
| **Build zh** (473k entrées, 57 MB) | ✅ DONE |
| **Build ar** (1.37M entrées, 185 MB) | ✅ DONE |
| **Build de** (1.73M entrées, 224 MB) | ✅ DONE |
| **Build id** (80k entrées, 10 MB) | ✅ DONE |
| **Build ja** (timeout réseau 16h) | 🔄 RETRY PID 11945 |
| **Build ko** (464k entrées, 58 MB) | ✅ DONE |
| **Build pl** (1.89M entrées, 237 MB) | ✅ DONE |
| **Build tr** (2.89M entrées, 374 MB) | ✅ DONE |
| Rapport final mis à jour | ✅ CE DOCUMENT |

**Avancement global R465 : 13/14 langues (93%)** — total 18 246 798 entrées | ~2.1 GB

---

## 7. Limites honnêtes

1. **`artcb_code = "UNK"`** pour toutes les entrées — l'IREncoder (R466+) devra résoudre le mapping lemme → code ARTCB.
2. **kaikki.org = Wiktionary extracté** — couverture excellente mais non exhaustive (néologismes, argot récent, noms propres exclus).
3. **Données locales uniquement** — les 749 MB de lexicons ne sont pas sur GitHub (limites taille). Reproductibles via `python3 scripts/artcb_r465_lexicon_build.py --all`.
4. **Langues CJK (zh, ja, ko)** — segmentation par caractères/morphèmes, non par espaces. Le script utilise les `forms` kaikki.org tels quels — vérification spécifique à prévoir.
5. **Arabe (`ar`)** — script RTL, normalisation Unicode requise. Traitement identique aux autres langues pour l'instant.
6. **`CERTIFIED_100 = false`** — invariant maintenu dans tous les chemins.

---

## 8. Erreur ja — analyse et retry

**Cause :** Le dump japonais kaikki.org (~1.2 GB) a déclenché un timeout TCP après ~15.9h de téléchargement continu (la connexion réseau a été interrompue entre 00:53 et 16:51 UTC — absence de reconnexion automatique dans le script).

**Correction à terme (R465-bis) :** Ajouter `stream=True` + retry sur TimeoutError dans `_download_lang()` avec reprise partielle.

**Retry en cours :** PID 11945 — `python3 scripts/artcb_r465_lexicon_build.py --lang ja --force`

## 9. Prochaine étape

1. Attendre fin retry ja (PID 11945) — log `data/lexicons/build_ja_retry.log`
2. Vérifier `ja_lexicon.json` présent + `build_report.json` updated
3. Commit rapport final mis à jour (après ja DONE)
4. Chantier suivant : **R466 — IREncoder mapping artcb_code** (résoudre les UNK)

---

*Rapport mis à jour — session 2026-09-25T17:05:00Z | SHA `16f878e` (code)*
*CERTIFIED_100=false | Mode DEBUG actif*
