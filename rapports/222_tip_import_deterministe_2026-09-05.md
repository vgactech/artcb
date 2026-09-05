# Rapport 222 — Import P2P déterministe + V-01-B live (5 septembre 2026)

**Source :** audit critique du rapport 221.  
**Décision :** aucune D-0xx. Pas de wipe. Certification **non retouchée**.  
**Ce n’est pas** une certification complète du réseau.

---

## 0. Distinguer les SHA (comme l’audit 221 l’exige)

| Quoi | SHA |
|---|---|
| Code exécuté pendant V-01-B live | `e68563e8ea4b0fd402a145749d9f959b44e31acf` (221 documentaire, même livre 5 blocs) |
| Code 222 (décision d’import unique) | le commit qui ajoute ce rapport — **après** le B-live |

Le B-live prouve la **résilience du livre déjà convergé**. Il ne prouve pas encore que le code 222 tournait sur les nœuds.

---

## 1. Avant / après (chemins P2P)

**Avant :** `receive` appelait `import_public_blocks(extend_tip=False)`. `pull` passait `protocol_compatible`. Deux chemins, deux comportements possibles.

**Après :** une seule fonction `decide_public_import()`. `extend_tip` est **ignoré**. Receive et pull ont le même verdict.

Ordre figé :

```text
visibility → structure/hash → duplicate → événement convergent
→ symbols liés à graph_root → index → prev_hash → append
```

C’est-à-dire : un bloc `visibility=public` `reward=0` avec un `artcb_event` arbitraire **n’obtient pas** le privilège d’extension (scénario K).

---

## 2. Scénarios locaux T-E48

| ID | Résultat |
|---|---|
| G duplicate | pas de second append |
| H mauvais `prev_hash` (rehashé) | `wrong_prev_hash`, tip inchangé |
| I mauvais index | `wrong_index`, tip inchangé |
| J hash forgé | `hash_mismatch` |
| K événement arbitraire | `archive_only` |
| M deux producteurs | les tips divergent ; l’import adverse est rejeté (pas de fusion silencieuse) |
| receive = pull | même `ImportDecision` |

Partition réseau (N) et recovery/rejoin (H au sens audit) : **non démontrés en live**.

---

## 3. V-01-B live (OVH1 arrêté)

Mesure `20260905T134527Z`. JSON : `rapports/evidence/222_live_20260905T134527Z.json`.

| Phase | OVH1 | OVH2 / AWS3 / OVH4 |
|---|---|---|
| Avant | tip `27350024…` / 5 blocs / certified | identique |
| Pendant `systemctl stop artcb` | `/health` = **0** (injoignable) | tip **identique**, certified **true**, 5 blocs |
| Après `systemctl start artcb` | même tip restauré, keep-book 5 lignes | inchangé |

`others_kept_tip_while_ovh1_down=true`. `ovh1_book_restored=true`. **Pas de nouvelle ORG** pendant l’arrêt (cela aurait été le scénario M).

C’est-à-dire : la preuve **survit à la disparition temporaire du créateur**. Ce n’est **pas** encore « les autres produisent un nouveau bloc canonique pendant que OVH1 est mort ».

---

## 4. Ce qui reste hors certification

- Operator `/p2p/sync` 4/4 : 401 sur 2/3/4 (D-029, clés isolées). La convergence 221 était un **push OVH1**.
- Multisig, timelock, preuve RCS, chiffrement au repos.
- Partition + rejoin, producteurs concurrents **live**.
- Byzantine général.

**V-01** : parcours 221 + B-live lecture.  
**Réseau définitivement certifié** : **non**.
