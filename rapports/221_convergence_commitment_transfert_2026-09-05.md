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

## 5. Live

Rempli après push `main` + follow-main + `scripts/run_live221_commitment_convergence.py`.
