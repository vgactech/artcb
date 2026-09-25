# R465-ext — Extension linguistique 14→16 profils (Latin + Português Brasileiro)

**Date :** 2026-09-25T17:45:00Z  
**SHA commit :** `71861d5` (main)  
**CERTIFIED_100 :** false  
**État :** ✅ FINAL — 16/16 profils buildés et validés

---

## 1. Contexte

Le rapport R465 (SHA `96c7f2c`) déclarait 14/14 langues construites. Audit expert a identifié deux profils manquants dans le référentiel linguistique ARTCB :

- **Latin (`la`)** — profil distinct de l'italien (≠ `it`), langue source de nombreux concepts ARTCB
- **Português Brasileiro (`pt-BR`)** — variante régionale distincte de `pt` (portugais neutre commun)

Total corrigé : **14 + 2 = 16 profils**.

---

## 2. Diagnostic sources — résultats réels

### 2.1 kaikki.org et pt-BR

**Constat (vérifié par inspection du dump)** : kaikki.org ne fournit **pas** de dump `pt-BR` séparé.  
Les marqueurs `Brazil` / `Portugal` sont dans `sounds[].tags` (phonologie), **pas** dans `lang_code`. Le champ `lang` est uniformément `"Portuguese"` pour toutes les entrées.

```
# Exemple entrée kaikki.org Portuguese :
{"word": "pie", "lang": "Portuguese", "lang_code": "pt",
 "sounds": [{"tags": ["Brazil"], "ipa": "/ˈpi.i/"},
             {"tags": ["Portugal"], "ipa": "/ˈpi.ɨ/"}]}
```

**Conclusion** : extraction pt-BR depuis kaikki.org impossible sans perdre la majorité du vocabulaire commun. Source alternative requise.

### 2.2 Source pt-BR retenue : fserb/pt-br

- **Dépôt** : `github.com/fserb/pt-br` (Licence MIT)
- **Fichier** : `lexico` (plain text, un mot par ligne, UTF-8)
- **URL** : `https://raw.githubusercontent.com/fserb/pt-br/master/lexico`
- **⚠️ Erreur initiale** : URL tentée = `.../wordlist.txt` → HTTP 404. Correction : le fichier s'appelle `lexico` (sans extension). Leçon L-056 (candidat).

### 2.3 Source Latin : kaikki.org (DEPRECATED)

- **URL** : `https://kaikki.org/dictionary/Latin/kaikki.org-dictionary-Latin.jsonl`
- **Taille** : 1.2 GB JSONL
- **Statut kaikki.org** : DEPRECATED (issue wiktextract #1178) — mais **accessible et fonctionnel** au moment du build
- **Avertissement** : ce dump peut être retiré prochainement. À surveiller.

---

## 3. Artefacts produits

### 3.1 Code (committés)

| SHA | Fichier modifié | Changement |
|-----|----------------|-----------|
| `e51d682` | `src/artcb/language/registry.py` | `EXTENDED_2_LANG_IDS`, `ALL_16_LANG_IDS`, `_register_extended_2()`, `missing_from_all_16()` |
| `e51d682` | `src/artcb/language/lexicon_loader.py` | `coverage_report()` → `ALL_16_LANG_IDS` |
| `e51d682` | `scripts/artcb_r465_lexicon_build.py` | `la` + `pt-BR` dans `LANG_CONFIG`, `_stream_plaintext_words()`, `build_lexicon_ptbr()`, `--all-16` |
| `e51d682` | `tests/test_r465_lexicon_loader.py` | T22 → 16 profils ; T26–T30 (la + pt-BR) |
| `e51d682` | `tests/test_r448_language_modules.py` | T13/T19 → 16 profils |
| `71861d5` | `scripts/artcb_r465_lexicon_build.py` | URL pt-BR corrigée (`lexico` ≠ `wordlist.txt`) |

### 3.2 Données lexicales — 16 profils complets (local, ignorés par `.gitignore`)

| Langue | Entrées | Taille | Source | SHA256 (8 cars) |
|--------|---------|--------|--------|----------------|
| 🇫🇷 fr | 784 019 | 97 MB | kaikki.org | `168760bd` |
| 🇬🇧 en | 2 360 112 | 293 MB | kaikki.org | `dff3588b` |
| 🇪🇸 es | 1 992 273 | 247 MB | kaikki.org | `ec3f0c53` |
| 🇵🇹 pt | 909 945 | 112 MB | kaikki.org | `8752d313` |
| 🇮🇹 it | 1 363 559 | 170 MB | kaikki.org | `f79d96d1` |
| 🇷🇺 ru | 1 935 993 | 272 MB | kaikki.org | `2ba71422` |
| 🇨🇳 zh | 472 921 | 57 MB | kaikki.org | `f7f33f01` |
| 🇸🇦 ar | 1 373 037 | 185 MB | kaikki.org | `af6260d6` |
| 🇩🇪 de | 1 733 696 | 224 MB | kaikki.org | `0d55244d` |
| 🇮🇩 id | 79 949 | 10 MB | kaikki.org | `96205c44` |
| 🇯🇵 ja | 1 048 878 | 132 MB | kaikki.org | — |
| 🇰🇷 ko | 463 834 | 58 MB | kaikki.org | — |
| 🇵🇱 pl | 1 885 859 | 237 MB | kaikki.org | `fd676396` |
| 🇹🇷 tr | 2 891 601 | 374 MB | kaikki.org | — |
| 🏛️ **la** | **2 042 686** | **253 MB** | **kaikki.org (DEPRECATED)** | `3142bf5a` |
| 🇧🇷 **pt-BR** | **145 744** | **18 MB** | **fserb/pt-br (MIT)** | — |

**TOTAL 16/16 : 21 484 106 entrées uniques | ~2.74 GB**

---

## 4. Avant / Après

### `src/artcb/language/registry.py`

**Avant (ligne 175–176) :**
```python
# Les 14 langues officielles initiales (ordre alphabétique ISO)
INITIAL_14_LANG_IDS = ("ar", "de", "en", "es", "fr", "id", "it", "ja", "ko", "pl", "pt", "ru", "tr", "zh")
```

**Après :**
```python
INITIAL_14_LANG_IDS = ("ar", "de", "en", "es", "fr", "id", "it", "ja", "ko", "pl", "pt", "ru", "tr", "zh")
EXTENDED_2_LANG_IDS = ("la", "pt-BR")
ALL_16_LANG_IDS = INITIAL_14_LANG_IDS + EXTENDED_2_LANG_IDS
# + _register_extended_2() + missing_from_all_16()
```

### `tests/test_r448_language_modules.py`

**Avant (T13, T19) :**
```python
assert len(reg.all_lang_ids()) == 14
assert len(report) == 14
```

**Après :**
```python
assert len(all_ids) == 16  # R465-ext : 14 + la + pt-BR
assert len(report) == 16
```

### `scripts/artcb_r465_lexicon_build.py`

**Avant :** 14 entrées dans `LANG_CONFIG`, pas de routing pt-BR, pas de `--all-16`.

**Après :**
- `LANG_CONFIG` : +`la` (kaikki.org Latin DEPRECATED) + `pt-BR` (fserb/pt-br)
- `_stream_plaintext_words()` : streaming plain-text pour pt-BR
- `build_lexicon_ptbr()` : builder dédié pt-BR
- routing `pt-BR` → `build_lexicon_ptbr()` vs kaikki.org pour les autres
- `--all-16` : build des 16 profils

---

## 5. Tests — résultats

```
tests/test_r465_lexicon_loader.py — 30/30 PASS (9.85s)
tests/test_r448_language_modules.py — 30/30 PASS
Gate DO-178C : 124/124 PASS (commits e51d682 + 71861d5)

T26 — Registry contient 16 profils ✅
T27 — Latin (la) distinct de Italian (it) ✅
T28 — pt-BR distinct de pt ✅
T29 — ALL_16_LANG_IDS = 14 + la + pt-BR ✅
T30 — la/pt-BR coverage_state=ABSENT avant build ✅
```

---

## 6. Incident L-056 (candidat) — URL corpus pt-BR incorrecte

**Contexte :** L'URL `https://raw.githubusercontent.com/fserb/pt-br/master/wordlist.txt` citée dans le README du projet avait été utilisée comme source pour pt-BR. Au moment du build, HTTP 404.

**Root cause :** Le fichier réel dans le dépôt fserb/pt-br est `lexico` (sans extension). Le README décrit le contenu mais ne cite pas le nom de fichier exact.

**Résolution :** URL corrigée → `master/lexico`. Build pt-BR : **145 744 entrées, 17.7 MB, PASS**.

**Leçon L-056 (à graver dans LEÇONS_APPRISES_ARTCB) :**  
Toujours vérifier l'arborescence réelle d'un dépôt (via API GitHub `trees`) avant d'intégrer une URL de corpus. Un README peut citer un nom conceptuel qui ne correspond pas au nom de fichier exact.

---

## 7. Limites honnêtes

1. **pt-BR sans POS** : le corpus fserb/pt-br ne contient que des lemmes bruts — `pos=unknown` pour toutes les 145 744 entrées. Pas de formes fléchies. Pour un pt-BR plus riche : LanguageTool `portuguese-pos-dict` (format complexe, non intégré).
2. **Latin DEPRECATED** : kaikki.org a annoncé le retrait du dump Latin (issue #1178). Le build actuel est valide, mais la reproductibilité future n'est pas garantie. Une alternative (Perseus Digital Library, LatinISE) devrait être évaluée avant R466.
3. **La ≠ it** : les 2 042 686 entrées latines ont `pos`, lemmes et formes fléchies (déclinaisons nominales, conjugaisons verbales) — traitement CJK non requis, script Latin standard.
4. **pt ≠ pt-BR** : les 909 945 entrées `pt` représentent le portugais neutre commun (kaikki.org). Les 145 744 entrées `pt-BR` sont complémentaires, pas redondantes (vocabulaire brésilien spécifique).
5. **Total 21 484 106 ≠ dédupliqué inter-langues** : ce comptage est par langue. Des mots identiques entre langues (ex: `"blockchain"` présent en fr, en, es…) ne sont pas dédupliqués au niveau global — c'est intentionnel (chaque profil est indépendant).

---

## 8. État final R465/R465-ext

| Étape | État |
|-------|------|
| Code R465 (14 langues) — SHA `13f2158` | ✅ DONE |
| Build 14 langues (R465) | ✅ DONE |
| Extension registry 14→16 — SHA `e51d682` | ✅ DONE |
| Fix URL pt-BR — SHA `71861d5` | ✅ DONE |
| Build Latin (`la`) — 2 042 686 entrées, 253 MB | ✅ DONE |
| Build pt-BR — 145 744 entrées, 17.7 MB | ✅ DONE |
| Tests 30/30 PASS (T01–T30) | ✅ DONE |
| Gate DO-178C 124/124 PASS | ✅ DONE |

**16/16 profils ✅ | 21 484 106 entrées totales | CERTIFIED_100=false**

---

## 9. Prochaine étape

**R466 — IREncoder mapping `artcb_code`** : résoudre les 21.5M entrées `artcb_code=UNK` en mappant lemme+POS → ConceptID ARTCB.  
**Périmètre final R466** : 16 profils (14 kaikki + la + pt-BR) — ne pas lancer R466 sur 14 profils seulement.

---

*Rapport R465-ext — 2026-09-25T17:45:00Z | SHA `71861d5`*  
*16/16 profils ✅ | 21 484 106 entrées | CERTIFIED_100=false | Mode DEBUG actif*
