# R467 — Filtrage POS + Traçage Collisions + fix A-03
**Date :** 2026-09-25  
**HEAD avant :** `5cf5524` (R468 — cahier des charges financement)  
**Commit R467 :** à venir  
**CERTIFIED_100=false**

---

## Contexte — décisions de l'audit forensic R466b

L'audit forensic `rapports/R466b_audit_forensic_exhaustif_2026-09-25.md` a identifié 3 anomalies
bloquantes à corriger avant tout enrichissement du lexique :

| ID | Sévérité | Anomalie |
|---|---|---|
| A-01 | CRITICAL | Bug sémantique POS-aveugle : `car` pos=`conj` (FR) → C2 (véhicule) |
| A-02 | HIGH | 18 collisions inter-tables OBJECT/MODIFIER silencieuses |
| A-03 | HIGH | Divergence `resolve()` vs `resolve_batch()` non documentée |

---

## Corrections implémentées

### CORR-01 — Filtrage POS (résout A-01)

**Fichier :** [`src/artcb/language/lexicon_mapper.py`](../src/artcb/language/lexicon_mapper.py)

#### AVANT (R466, lignes 134–155)

```python
sf_lower = surface_form.lower().strip()
lm_lower = lemma.lower().strip()

# 1. Correspondance exacte sur surface_form
for table, _keys, name in self._tables_with_names():
    if sf_lower in table:
        code = table[sf_lower]
        ...
        return MappingResult(..., match_method="exact_surface", ...)
```

Résultat : `resolve('car', 'car', 'conj')` → `C2` (véhicule — FAUX)

#### APRÈS (R467)

```python
pos_lower = (pos or "").lower().strip()

# 0. CORR-01 R467 — Filtre POS
if pos_lower in GRAMMATICAL_POS:
    return MappingResult(..., artcb_code="UNK", match_method="pos_filtered",
                         pos_filtered=True)
```

Résultat : `resolve('car', 'car', 'conj')` → `UNK` ✅  
Résultat : `resolve('car', 'car', 'noun')` → `C2` ✅ (inchangé)

**`GRAMMATICAL_POS`** (frozenset exporté) :
```
conj, prep, art, pron, punct, intj, det, part, num,
aux, cop, mark, cc, cs, rel, adp, sconj, cconj
```

---

### CORR-02 — Traçage des collisions inter-tables (résout A-02)

#### AVANT (R466)

18 clés présentes dans `OBJECT_ALIASES` (C2) ET `MODIFIER_ALIASES` (PL) :
`cars`, `voitures`, `automobiles`, `automóviles`… — OBJECT écrasait MODIFIER
**silencieusement**. `match_method="exact_surface"` ne distinguait pas les cas normaux
des cas de collision.

#### APRÈS (R467)

```python
_COLLISION_OBJECT_OVER_MODIFIER: frozenset[str] = frozenset(
    k for k in OBJECT_ALIASES if k in MODIFIER_ALIASES
)
# → 18 clés calculées automatiquement au chargement du module
```

Lors d'un match sur une clé de collision :
```python
method = "collision_object_over_modifier" if sf_l in _COLLISION_OBJECT_OVER_MODIFIER \
         else "exact_surface"
```

`MappingResult.collision = True` + `match_method = "collision_object_over_modifier"`.  
`MapperStats.summary()["collision_count"]` compte les entrées concernées.

---

### A-03 fix — Divergence `resolve()` vs `resolve_batch()` documentée

#### AVANT (R466)

La divergence existait implicitement. `resolve_batch()` ne faisait pas de préfixe.
Aucun paramètre ne permettait de l'activer. `T06` testait `resolve()` et donnait
une fausse impression de couverture.

#### APRÈS (R467)

```python
def resolve_batch(self, entries, *, allow_prefix_in_batch: bool = False):
```

- `allow_prefix_in_batch=False` (défaut) → comportement identique à R466
- `allow_prefix_in_batch=True` → préfixe activé (O(N×K), faux positifs possibles)
- La divergence est maintenant **documentée, testée et contrôlable**

---

## Résultats sur corpus FR (784 019 entrées)

| Métrique | R466 | R467 | Delta |
|---|---|---|---|
| resolved | 448 | **446** | −2 (car/conj corrigés) |
| pos_filtered | 0 | **2 620** | +2620 (POS grammaticaux filtrés) |
| collisions tracées | 0 | **18** | +18 (collision_object_over_modifier) |
| car/conj → C2 (faux positif) | 1 | **0** | ✅ résolu |
| car/noun → C2 | 1 | **1** | ✅ inchangé |

---

## Tests

| Suite | Avant R467 | Après R467 |
|---|---|---|
| `test_r466_lexicon_mapper.py` | 31/31 | **42/42** |
| `test_task001_r37*.py` | 106/106 | **106/106** |

**Tests ajoutés T26–T36 :**

| Test | Vérification |
|---|---|
| T26 | `car` pos=`conj` → UNK (A-01 résolu) |
| T27 | `car` pos=`noun` → C2 (non-régression) |
| T28 | `can` pos=`aux` → UNK |
| T29 | `can` pos=`noun` → MOD (non-régression) |
| T30 | `resolve_batch` filtre pos=conj : 1 UNK + 1 C2 |
| T31 | `voitures` pos=noun → C2 + `collision=True` |
| T32 | `cars` en batch → `collision_object_over_modifier` |
| T33 | `resolve_batch` sans préfixe par défaut → UNK (A-03) |
| T34 | `resolve_batch(allow_prefix_in_batch=True)` → V1 |
| T35 | `by_method_unresolved` tracke `pos_filtered` séparément |
| T36 | `GRAMMATICAL_POS` exporté et complet |

---

## Limitations connues (CERTIFIED_100=false)

- CORR-02 traçage : les 18 clés reçoivent toujours C2 (OBJECT prime sur MODIFIER).
  La résolution sémantiquement correcte nécessiterait un POS-aware pour distinguer
  "voitures" (nom pluriel → C2 ou PL selon le contexte). Tracé comme collision pour
  l'instant — résolution contextuelle = chantier R468+.
- Taux de résolution FR passe de 0.057% → 0.057% (−2 sur 784 019).
  Les 2 620 pos_filtered représentent des POS grammaticaux qui ne devaient pas être
  mappés : leur exclusion améliore la précision sémantique sans réduire le recall.
- 15 profils non re-exécutés dans cette session (seul FR vérifié).

**`CERTIFIED_100=false`** — maintenu.
