# Rapport 220 — Ancrage public du hash + autorité transférable ORG/GROUP/sous-groupe (5 septembre 2026)

**Source :** `rapports/219 rapport chat et simulation.md` (rang 6).  
**Décision :** aucune D-0xx. Consensus / supply / PoL **inchangés**. Pas de wipe. Certification **non retouchée**.  
**Règle utilisateur réutilisée :** session humaine, pas le JSON ; agent plafonné ; `unique_human_proven` jamais impliqué pour une ORG.

---

## 0. Avant / après

### 0.1 Hash du domaine

**Avant :** `commitments.jsonl` local. `commitment_anchored_on_chain=false`. Les 3 autres nœuds ne voyaient même pas le hash.

**Après :** à la création (ORG / GROUP / sous-groupe) et à l’acceptation d’un transfert, un bloc `visibility=public` `block_reward=0` est ajouté. `public_symbols` = `{artcb_event, kind, domain_id, content_hash, parent_id, issuer}` uniquement.

C’est-à-dire : le réseau **peut** transporter l’empreinte. Il **ne** transporte **pas** le Genesis, les membres, ni un document.

### 0.2 Propriété / autorité

**Avant :** `founder_address` = seul maître. Pas de vente, pas de changement de directeur, le Genesis était traité comme la propriété.

**Après :**

| Concept | Rôle | Change ? |
|---|---|---|
| `founder_address` | constitution historique | **non** |
| `ORG_ID` / `group_id` | identité permanente | **non** |
| `LEGAL_OWNER` | propriétaire juridique technique | oui si `SALE` |
| `AUTHORIZED_CONTROLLER` | qui administre (export, transfert) | oui après propose+accept |

C’est-à-dire : on ne recrée pas l’ORG. On change l’autorité. Comme un utilisateur : **session humaine obligatoire**. Un agent ne peut pas créer ni transférer.

### 0.3 Certification utilisateur adaptée

Même règles qu’un wallet :

* identité = session / clé liée, jamais `actor_address` du body ;
* agent ≠ humain (`403 agent_cannot_admin_org_or_group`) ;
* `unique_human_proven=false` sur l’ORG (une entreprise n’est pas un humain unique) ;
* DENY > ALLOW et plafond agent inchangés pour les documents.

---

## 1. Ce que le rapport 219 demandait, et ce qui est fait

| Demande 219 | État 220 |
|---|---|
| Ancrage `blocks.jsonl` (P-218-2) | **Codé** `anchor.py` + test + à mesurer live |
| LEGAL_OWNER ≠ CONTROLLER | **Codé** |
| ORG_CONTROL_TRANSFER propose/accept | **Codé** `SALE` / `DIRECTOR_CHANGE` / `SUCCESSION` / `KEY_ROTATION` |
| ORG_ID inchangé | **Testé** |
| Ancien contrôleur révoqué (plus d’export) | **Testé** |
| Groupe / sous-groupe sans transférer l’ORG | **Codé + testé** |
| Session humaine, pas agent | **Codé + testé** |
| Multisig 3-of-5 | **Non** (`threshold=1`, champ prêt) |
| Délai de contestation | **Non** (finalisation à l’acceptation) |
| Fusion / scission / freeze / close | **Non** |
| Preuve juridique externe (tribunal) | **Non** — la crypto prouve la clé, pas le RCS |
| Chiffrement au repos | **Non** (P-218-1) |
| Réplication auto du corps | **Non** (P-218-3) |

---

## 2. Oublié de préciser (ajouté quand même)

1. Le **sous-groupe** n’enregistrait pas de Domain Manifest en 218 — corrigé.
2. `GET /chain` anonyme voit maintenant les blocs de commitment : ce n’est **pas** une fuite privée. Les tests 216 comptent les documents, pas ces blocs.
3. `ARTCB_NODE_ID` live n’est toujours pas posé (P-218-7).
4. Ancrer un bloc public **allonge la chaîne du nœud qui crée**. Tant que le P2P n’a pas étendu le tip, les hauteurs peuvent différer. Ce n’est pas un wipe.
5. Le double commitment `kind=org` + `kind=domain` du journal local **reste** ; le bloc public ancre le `domain_id` du manifeste.
6. L’UI n’exportait que si `founder_address === session` — après une SALE le nouveau contrôleur ne voyait plus le bouton. L’export est maintenant proposé à la session ; le serveur refuse l’ancien contrôleur.
7. Un rôle `founder` dans le groupe ne donne plus l’admin une fois le contrôle transféré (le fondateur reste historique).
8. À l’acceptation : révocation des GRANT tenus par l’ancien contrôleur **et** par ses agents sur ce sujet (219 §31.13/14). Les GRANT des autres humains restent.
9. Événement public distinct `ORG_CONTROL_TRANSFER` (pas un second hash Genesis). Annulation par le contrôleur, refus par le destinataire.
10. `SUCCESSION` et `KEY_ROTATION` ne changent pas le `LEGAL_OWNER` (comme `DIRECTOR_CHANGE`). Seule `SALE` le déplace.

---

## 3. Fichiers

`src/artcb/authz/anchor.py`, `governance.py`, routes `/authz/orgs/{id}/transfer`, `/transfers/accept`, `/orgs/{id}/authority`, UI `/groups`.  
Tests : `tests/test_e2e220_org_governance.py` **T-E46**.

---

## 4. Matrice

| Règle | Décidée | Simulée | Codée | Testée | Live |
|---|---|---|---|---|---|
| Hash = bloc public reward=0 | 219 / P-218-2 | audit 219 | `anchor.py` | T-E46 | à remplir après follow-main |
| Transfert autorité | 219 | Aline→Bob | `governance.py` | T-E46 | à mesurer |
| Agent interdit | règles user 216 | | routes | T-E46 | |
| unique_human_proven ORG | D-055 adapté | | toujours false | T-E46 | |
| Multisig / timelock / preuve légale | 219 reco | | non | — | non |

---

## 5. Live (mesuré 2026-09-05T13:24:31Z, pas inventé)

`origin/main` = `9a536689f38a25da147df7f1ea4f28ff1ab5d375`.

| Surface | `git_sha` | `certified_distributed_mainnet` | `blocks.jsonl` | domaines | `DOMAIN_COMMITMENT` | `ORG_CONTROL_TRANSFER` |
|---|---|---|---|---|---|---|
| OVH1 `:8000` + `:8443` | `9a53668` | `true` | 3 | 2 | 1 | 1 |
| OVH2 | `9a53668` | `true` | 1 | 0 | 0 | 0 |
| AWS3 | `9a53668` | `true` | 1 | 0 | 0 | 0 |
| OVH4 | `9a53668` | `true` | 1 | 0 | 0 | 0 |

Parcours humain réel (wallets jetables sur OVH1, session HTTPS `:8443`) :

* `POST /authz/orgs` anonyme = **401** ×4 ; transfert anonyme = **401** ×4
* agent header : create **403**, transfer **403**
* create org = **200**, `commitment_anchored_on_chain=true`, `unique_human_proven=false`, `node_owns_domain=false`
* hash du bloc public = hash du Genesis ; `block_reward=0`
* SALE Aline→Bob : propose **200**, accept **200**, `org_id_unchanged=true`, fondateur inchangé, contrôleur = Bob
* export ancien contrôleur **403** ; export Bob **200**
* corps / manifeste **absents** sur OVH2 / AWS3 / OVH4 (attendu : pas de copie auto, P-218-3)
* les 2 blocs publics nouveaux sont **sur OVH1 seulement**. Ce n’est pas un wipe. Le P2P n’a pas encore étendu le tip des 3 autres.

Livre : keep-book. `install.sh` / genesis / rescue : non exécutés. Certification non retouchée.

Script : `scripts/run_live220_org_governance.py` (journal `logs/220_live_20260905T132431Z.json`, aucun token imprimé).
