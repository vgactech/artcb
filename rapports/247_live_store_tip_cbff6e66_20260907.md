# Rapport 247 — Le livre a été écrit (append keep-book, pas un wipe)

**Date :** 2026-09-07  
**GO opérateur :** « JUSTEMENT ! JE VEUX QUE TU TOUCHE LE LIVRE »  
**Pas de wipe.** `install.sh` / genesis / init-node / rescue : **non**.  
**GO-E produce :** non.  
**Contact :** `official@artcb.space`

---

## 0. Ce qui a été gravé (mesuré, pas inventé)

Livre **avant** les écritures de cette session (4 officiels, post-deploy `c1d8027`) : height **5**, tip `273500247292233c91535cc6a7bdbd86d1f5dde4fc862f4cefc2b7fd13056764`.

Puis **trois** `append_block` publics sur OVH1 HTTPS `:8443` Bearer (clé jamais affichée) :

| Quand | Route | HTTP | `block_index` | `hash` | `graph_id` | `pol_score` | `block_reward` |
|---|---|---|---|---|---|---|---|
| 19:45:21Z | `POST /api/v1/store` public | 200 | **5** | `cbff6e66eb2ff78beed3049406448ce099a7c5d57aa803e83408f210a1654d48` | `g_7ef5885adcef` | 0.6 | 5791666667 |
| 19:47:32Z | `POST /api/v1/store` public | 200 | **6** | `a9e411c3109e924347eca16d642e2f3060e35a4ab2301dadcc253861c8b4c1cc` | `g_9019ae2af91f` | 0.6 | 5791666667 |
| 19:47:34Z | `POST /api/v1/ir/learn` public | 200 | **7** | `f646c510db980a843b55efa9ab93d1f64406a5147305a74d60b4424fbcc467ed` | `g_8cc3f57d516b` | 0.6 | 5791666667 |

**Tip OVH1 maintenant :** height **8**, `last_index` **7**, `last_hash` `f646c510db980a843b55efa9ab93d1f64406a5147305a74d60b4424fbcc467ed`.  
`chain_valid` : **true**. SHA code live : `c1d8027da4c9ae79d0cd96974e492747034b5479` = `origin/main`.

SSH OVH1 `wc -l` `/home/ubuntu/artcb/data/chain/blocks.jsonl` = **8**. Les 5 hashes d’origine sont **toujours** là. C’est un append.

---

## 1. Livre disque OVH1 (8 lignes, ordre)

| idx | hash | visibility | graph_id | pol | timestamp |
|---|---|---|---|---|---|
| 0 | `b8a7d5ef50052790a0a243481981769d66710155088b0ed952860eeda282bfce` | public | `g_29b131e92c84` | 0.6 | 2026-09-01T18:34:30Z |
| 1 | `5c952df62b0cc2c80bfdb55be526da3dd33b9466d1a5c64797bdd5d04f2d9a70` | public | `commit:org:domain_28d714f7a39a` | 0.0 | 2026-09-05T13:24:46Z |
| 2 | `93eab711365a59c32f88df51dda0556a13f8de70cd8b9e2621006d50b02b8799` | public | `xfer:organization:org_a4497b4d756b:xfer_d729e48baa664d87` | 0.0 | 2026-09-05T13:24:49Z |
| 3 | `5e4dbb406d34e7f32a4c9c770d4d50afe4ddc42e0968ee9d542f4038acf74e0a` | public | `commit:org:domain_352b306fc7b8` | 0.0 | 2026-09-05T13:36:24Z |
| 4 | `273500247292233c91535cc6a7bdbd86d1f5dde4fc862f4cefc2b7fd13056764` | public | `xfer:organization:org_36432821c4fc:xfer_0798002f2d44488b` | 0.0 | 2026-09-05T13:36:29Z |
| 5 | `cbff6e66eb2ff78beed3049406448ce099a7c5d57aa803e83408f210a1654d48` | public | `g_7ef5885adcef` | 0.6 | 2026-09-07T19:45:21Z |
| 6 | `a9e411c3109e924347eca16d642e2f3060e35a4ab2301dadcc253861c8b4c1cc` | public | `g_9019ae2af91f` | 0.6 | 2026-09-07T19:47:32Z |
| 7 | `f646c510db980a843b55efa9ab93d1f64406a5147305a74d60b4424fbcc467ed` | public | `g_8cc3f57d516b` | 0.6 | 2026-09-07T19:47:34Z |

---

## 2. Écritures refusées (mesurées aussi)

| Route | HTTP | Détail |
|---|---|---|
| `POST /store` (3ᵉ tentative, après index 6) | **500** | `Internal Server Error` (corps générique) |
| même `/store` retry | **500** | idem |
| `POST /ir/learn` 41.9 s après index 7 | **422** | `Contributor operator_go2... too fast: 41.9s < 60s` |

Le 422 est le throttle 60 s. Le 500 n’a pas de corps utile ; `/store` ne wrappe pas `ValueError` comme `/ir/learn`. **Pas investigué plus loin ici** (pas de D-0xx, pas de patch dans ce rapport).

---

## 3. Les 3 autres nœuds n’ont **pas** ce tip

Mesuré `/api/v1/chain/status` + `/health` **après** les 3 appends :

| Nœud | SHA | height | `last_hash` | `chain_valid` |
|---|---|---|---|---|
| OVH1 `152.228.144.34` | `c1d8027` | **8** | `f646c510…` | true |
| OVH2 `151.80.107.29` | `c1d8027` | **5** | `27350024…` | true |
| AWS3 `51.44.222.232` | `c1d8027` | **5** | `27350024…` | true |
| OVH4 `91.134.45.8` | `c1d8027` | **5** | `27350024…` | true |

Règle 222 : `decide_public_import` n’étend le tip que pour `DOMAIN_COMMITMENT` / `ORG_CONTROL_TRANSFER`. Un `/store` ou `/ir/learn` public **ordinaire** n’est pas un nouveau tip canonique chez les pairs. Ce n’est **pas** un wipe des autres. C’est la règle d’import.

GO-E produce toujours off (`will_append_blocks=false`).

---

## 4. Deploy keep-book (contexte, déjà fait)

`ARTCB_FOLLOW_MODE=official bash scripts/artcb_follow_main.sh` ×4 **avant** le premier store. Livre resté à 5 lignes sur les 4 disques jusqu’aux POST de ce rapport.

| Nœud | HEAD après follow-main | book après follow-main |
|---|---|---|
| OVH1–4 | `c1d8027` | 5 |

---

## 5. Matrice

| Règle | Décidée | Simulée | Codée | Testée | Live |
|---|---|---|---|---|---|
| Keep-book follow-main | FOLLOW_MAIN | 199+ | `artcb_follow_main.sh` | SSH ×4 | SHA `c1d8027` ×4 |
| `/store` + `/ir/learn` append | CDC store | — | `routes.store` / `ir_learn` | **ce live** | idx 5–7 sur OVH1 |
| Import P2P n’étend pas un store arbitraire | 222 | T-E48 K | `decide_public_import` | live 247 | 2/3/4 restent `27350024` |
| Wipe interdit | D-043 | — | — | SSH 8 lignes, idx 0–4 intacts | oui |
| Throttle 60 s contributeur | mining | — | chain reject | `/ir/learn` 422 | 41.9 s < 60 s |

Pas de D-0xx nouvelle. Packet ConceptID inter-nœuds : **toujours pas** une route (nouvelle lettre).
