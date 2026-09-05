# Rapport 221 — Convergence publique du commitment et du transfert (5 septembre 2026)

**Source :** audit critique du rapport 220 (chat).  
**Décision :** aucune D-0xx. Pas de wipe. Certification **non retouchée**.  
**Contact officiel :** `official@artcb.space` (remplace `contact@artcb.io` dans les docs vivantes).

---

## 0. Avant / après

**Avant (220 mesuré) :** OVH1 avait `DOMAIN_COMMITMENT` + `ORG_CONTROL_TRANSFER`. OVH2 / AWS3 / OVH4 gardaient l’ancien tip. `import_public_blocks` n’étendait le tip que si `protocol_compatible`. `POST /p2p/blocks/receive` n’étendait jamais.

**Après :** un bloc public `reward=0` dont `artcb_event` ∈ {`DOMAIN_COMMITMENT`, `ORG_CONTROL_TRANSFER`} **étend le tip** dès que `prev_hash` + index sont valides. L’annonce P2P part après ancrage (best-effort).

C’est-à-dire : la preuve publique peut quitter le nœud créateur. Le corps Genesis reste sur les nœuds de domaine.

---

## 1. Confidentialité (oublis 220 traités)

| Sujet | Décision 221 |
|---|---|
| Adresses dans `ORG_CONTROL_TRANSFER` | **Plus dans le bloc public.** Bindings `SHA-256(artcb_authority_v1:adresse)` |
| `issuer` du commitment | Même binding |
| Hash Genesis prévisible | `commitment_salt` 32 octets dans le corps local, **absent** de `/chain` et de la réponse HTTP create |
| Hash ≠ chiffrement | Rappel : le sel empêche le dictionnaire, il ne chiffre pas |
| SALE = vente juridique | **Non.** La crypto prouve une clé autorisée, pas le RCS |

Multisig 3-of-5 et timelock : **toujours hors périmètre** (threshold=1). Un second `propose` pendant qu’un transfert est `proposed` est rejeté (`transfer_already_proposed`) — un seul état canonique.

---

## 2. Scénarios

| ID | Attendu | Test |
|---|---|---|
| A propagation | même `last_hash` / digest après import | T-E47 local ; live à mesurer |
| B créateur tombé | la destination garde le tip | T-E47 (chaîne A oubliée) — **OVH1 n’est pas arrêté** |
| C transfert puis lecture ailleurs | bindings publics + autorité locale | live |
| D double propose | 422 `transfer_already_proposed` | T-E47 |
| E ancien contrôleur | 403, pas de nouveau bloc valide | T-E47 |
| F agent | 403 (220) | T-E46 |

---

## 3. Preuve 220 versionnée

Le JSON brut `logs/220_live_20260905T132431Z.json` n’était pas sur GitHub. Copie d’évidence (aucun token) :

`rapports/evidence/220_live_20260905T132431Z.json`

---

## 4. Contact

Docs vivantes (README, licence, gouvernance, charte, FAQ contact) : **official@artcb.space**.  
Dépôt : https://github.com/vgactech/artcb  
API / frontend **locaux** : `http://localhost:8000/docs` et `http://localhost:5173`.  
`security@artcb.io` inchangé (canal sécurité distinct).

---

## 5. Live (mesuré 2026-09-05T13:36:14Z, pas inventé)

`origin/main` au moment du parcours = `32a378d32a991b48829b0c86e2728b3436c48cdc`.  
JSON brut versionné : `rapports/evidence/221_live_20260905T133614Z.json` (aucun token).

### Avant le parcours 221

| Nœud | SHA | certified | blocs | tip (préfixe) |
|---|---|---|---|---|
| OVH1 | `32a378d` | true | 3 | `93eab711…` (déjà +2 blocs 220) |
| OVH2 / AWS3 / OVH4 | `32a378d` | true | 1 | `b8a7d5ef…` (même genesis, pas encore le tip 220) |

### Après create + SALE + annonce P2P depuis OVH1

| Nœud | blocs | `DOMAIN_COMMITMENT` | `ORG_CONTROL_TRANSFER` | `last_hash` | `public_state_digest` |
|---|---|---|---|---|---|
| OVH1 | 5 | 2 | 2 | `273500247292233c…` | `b5f93d3f420f03dc…` |
| OVH2 | 5 | 2 | 2 | **identique** | **identique** |
| AWS3 | 5 | 2 | 2 | **identique** | **identique** |
| OVH4 | 5 | 2 | 2 | **identique** | **identique** |

`four_same_last_hash=true`. `four_same_digest=true`. `certified=true` ×4. Keep-book (OVH1 est passé de 3 à 5 lignes, les autres de 1 à 5 par **import de tip**, pas un wipe).

Parcours humain HTTPS `:8443` : create 200, sel absent de la réponse HTTP, propose 200, accept 200.

### Nuances mesurées (ne pas les cacher)

1. **Blocs 220 historiques** (index 1–2) portent encore `old_controller` / `issuer` en clair. Ils ont aussi convergé. Les blocs **221** (index 3–4) n’ont **pas** `artcb1` dans les symboles : bindings seulement.
2. `POST /p2p/sync` opérateur : **200** sur OVH1 (6/7 pairs OK). **401** sur OVH2/AWS3/OVH4 — clé nœud 1 isolée (D-029). La convergence s’est faite par **push depuis OVH1**, pas par sync opérateur croisé.
3. Second propose Aline→Aline = **422** `invalid_new_controller` (le script a réutilisé la même adresse). T-E47 E (Aline→Carol après SALE) reste **403** en test local.
4. OVH1 n’a **pas** été arrêté (scénario B simulé localement seulement).
5. Multisig / timelock / preuve RCS : toujours non.

**V-01 :** démontré sur ce parcours — 4/4 même tip public après un commitment + un transfert.
