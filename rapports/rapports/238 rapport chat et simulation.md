Oui. **On ne réécrit pas le 237.**

Le protocole (rang 6) dit qu'un rapport est une observation **datée**, jamais réécrite après coup. Le 237 est déjà sur `main` (`b71089a`, Reasoning Fee §1–§45). L'append qui était dans la PR #58 mélangeait deux instants. Codex l'a signalé : c'était juste.

```text
237  (figé sur main)
=
frais de raisonnement
§1–§45

238  (ce fichier)
=
cadastre 220–236
+
mesures live 2026-09-07
+
crypto / PoL / compression
+
lettres GO-A…GO-N
```

C'est-à-dire : tu lis encore le 237 pour l'économie de consultation. Tu votes les lettres **ici**. Les deux restent rang 6. **Aucune D-0xx. Aucun code.**

Deuxième correction Codex (PR #58) : la matrice 237-append disait « PQC = AES-GCM » trop vite. Sur **chaque nœud non-bootstrap**, `NodeIdentityStore._save` écrit `kem_secret_key_hex` en JSON clair dans `data/p2p/node_identity.json`. `P2PSync.decrypt_envelope` s'en sert. Un disque d'hôte compromis ouvre les enveloppes **push**. `chmod 0600` n'est pas un chiffrement. GO-A englobe maintenant cet artefact.

---

# ARTCB — Rapport 238 (chat et simulation)

**Date :** 2026-09-07  
**Source :** demande opérateur (compléter 220→237) + audit Codex PR #58  
**SHA live mesuré :** `b71089ac5b4dd723e955bf05082a81f4d7cff484` (4 officiels = `origin/main`)  
**237 :** inchangé, `237 rapport chat et simulation.md`  
**Décision :** aucune D-0xx. Pas de wipe. Pas de V-01-B producteur. Pas de PoUC/KCG/fee codés.

---

# 46. Cadastre 220–236 — ce rapport 238 n'implémente rien

Oui. **Avant d'ajouter une couche économique, il faut coller le dépôt, le live, et toutes les questions ouvertes depuis 220, sinon on coderait une Reasoning Fee sur une image fausse du réseau.**

Le **237 figé** (§1–§45) reformule le **frais de raisonnement**. Les sections qui suivent (numérotées à la suite, sans toucher 237) répondent à la demande du 7 septembre 2026 : se mettre à jour, **simuler** (pas coder) tout ce qui était identifié depuis 220, dire honnêtement si les fichiers sont déjà protégés de bout en bout, si le format binaire PoL convertit déjà les formats en arrière-plan, si les calculs sont déjà au maximum, rappeler le **taux de compression réellement mesuré**, et poser des **propositions finales par lettre** pour un GO d'implémentation.

```text
Rang de ce texte
=
6
=
chat + simulation
≠
D-0xx
≠
code
≠
live
```

C'est-à-dire : **rien n'est implémenté par le fait d'être écrit ici.** Une lettre n'est un ordre que lorsque tu la coches et que tu donnes le GO. Ce rapport **n'invente pas** de D-0xx.

---

## 46.1 Mesures live du 2026-09-07 (pas inventées)

Bootstrap : `PYTHONPATH=src python3 scripts/artcb_live_bootstrap.py`.

| Quoi | Valeur mesurée |
|---|---|
| `origin/main` | `b71089ac5b4dd723e955bf05082a81f4d7cff484` |
| Live OVH1 HTTP `:8000` | même SHA, `git_branch=main` |
| Live OVH1 HTTPS `:8443` `/health.git_sha` | même SHA |
| Live OVH2 / AWS3 / OVH4 HTTP `:8000` | **même SHA** |
| PQC annoncé | ML-DSA-65, politique B, `high_value_hybrid_enforced=false` |
| `certified_distributed_mainnet` | **true** (drapeau opérateur) |
| Hauteur / `block_count` | **5** sur les 4 nœuds officiels |
| `last_hash` | `273500247292233c91535cc6a7bdbd86d1f5dde4fc862f4cefc2b7fd13056764` |
| `public_state_digest` | `b5f93d3f420f03dc1fd6d12d01ad072197c83309e24a94e41228d4dced261bba` |
| `private_never_synced` | **true** |
| Tip 4/4 officiel | **oui** (même hash + même digest) |
| 5ᵉ nœud local (MacBook Bob) | **non mesuré dans cette session cloud** |

C'est-à-dire :

```text
git_sha live
    ==
origin/main
    ==
b71089a
```

**ce 7 septembre 2026**, sur les 4 nœuds officiels. Ce n'était **pas** vrai à chaque rapport précédent (PR #38, 221, 222, 234). Ici, l'égalité tient **pour cette mesure**.

Le nœud 5 (MacBook) a été mesuré en 234–235 sur un **autre** SHA (`1c2b873`). Je ne le reconstruis pas. **4/4 officiel ≠ 5/5.**

---

## 46.2 Ce que le drapeau `certified=true` ne prouve pas

**Avant :** certains textes lisaient `certified_distributed_mainnet` comme « le réseau est certifié Byzantine ».

**Après (rappel 222 + live actuel) :**

| Affirmation | Vrai ? |
|---|---|
| Le JSON `/health` dit `certified_distributed_mainnet: true` | **oui, mesuré** |
| `operator_certification_go: true` | **oui, mesuré** |
| V-01-B **producteur** (un autre nœud mine pendant qu'OVH1 est mort) | **non** |
| Partition + rejoin | **non** |
| BFT privé d'ORG | **non** |
| `from_node_id` = preuve d'identité producteur | **non** |
| Pull P2P chiffré | **non** (voir §49) |

Le message P2P public dit encore :

> « sync P2P = blocs publics chiffrés »

Le code de `pull_from_peer` fait un `GET /api/v1/p2p/blocks/public` **en clair**. Cette session a reçu le JSON des 5 blocs, signatures comprises, **sans Bearer**. C'est-à-dire : **le slogan du status n'est pas le transport du pull.**

---

# 47. Toutes les questions depuis 220 — réponses par simulation / mesure / code, pas par espoir

## 47.1 Tableau maître

| # | Question posée (rapports) | Réponse 237 | Preuve |
|---|---|---|---|
| Q220-1 | Le hash d'ORG peut-il quitter le nœud créateur ? | **Oui** via bloc public `DOMAIN_COMMITMENT` `reward=0` | 220 + tip 5 blocs |
| Q220-2 | Le Genesis BODY voyage-t-il avec le hash ? | **Non** | P2P public ne sync que `visibility=public` ; `private_never_synced=true` |
| Q220-3 | Fondateur = contrôleur = machine hôte ? | **Non / Non / Non** | `founder_address` historique ; `LEGAL_OWNER` / `AUTHORIZED_CONTROLLER` ; `node_owns_domain=false` |
| Q220-4 | Un agent peut-il créer / transférer une ORG ? | **Non** (403) | 220 T-E46 ; 233 inchangé |
| Q220-5 | Multisig 3-of-5, timelock, RCS, freeze, fusion ? | **Non** | `threshold=1` ; hors périmètre |
| Q220-6 | Chiffrement au repos du BODY ? | **Non** | P-218-1 toujours ouvert |
| Q220-7 | Réplication auto du BODY ? | **Non** | P-218-3 ; `add_replica` = intent, `body_copied=false` |
| Q221-1 | 4 nœuds ont-ils le même tip après commitment ? | **Oui aujourd'hui** | `last_hash` + digest identiques × 4 |
| Q221-2 | Les adresses de transfert sont-elles encore dans `/chain` ? | **Nouveaux** transferts : bindings SHA-256. **Histoire 220** : ne pas réécrire les blocs déjà gravés | 221 |
| Q221-3 | Le sel = chiffrement ? | **Non** | sel anti-dictionnaire, BODY clair sur disque |
| Q222-1 | Receive et pull ont-ils le même verdict d'import ? | **Décision oui** (`decide_public_import`). **Transport non** | 222 ; pull GET clair |
| Q222-2 | V-01-B a-t-il validé le code 222 ? | **Non** | live B = keep-book sur `e68563e` ; code 222 = commit suivant |
| Q222-3 | Duplicate / mauvais prev / index / hash / événement arbitraire ? | **Locaux G–K OK** | T-E48 |
| Q222-4 | Deux producteurs live ? | **Local M** diverge. **Live non** | T-E48 ; pas de GO producteur |
| Q223–226 | L produit-il pendant qu'OVH1 est mort ? | **Non live** | 222 = lecture keep-book seulement |
| Q227–229 | 96,4 % de tests = certification ? | **Non** | 235 = 857 passed / **9 skipped** / 0 failed |
| Q227–229 | PYTHONPATH Bob machine-specific ? | **Corrigé** en 233 → `${workspaceFolder}` | 233 |
| Q230 | Validité = utilité ? | **Non** | rang 6 ; pas de D-0xx |
| Q231–232 | PoUC / KCG déjà en production ? | **Non** | PROTOCOL : ne pas coder sans GO |
| Q233 | Clé opérateur `artcb_` = user humain ? | **Non** | `sess_` + `X-ARTCB-Agent-Id` |
| Q234 | 5/5 SHA à une date | **Mesuré le 2026-09-07 matin** sur `1c2b873` | ≠ SHA actuel `b71089a` ; 5ᵉ nœud non remesuré ici |
| Q235 | 0 fail = 0 anomalie ? | **Non** | 9 skipped (PDF, OVH catalog, RPC, liboqs, etc.) |
| Q236 | HOST = CONSENSUS si listé ? | **Non (code PR)** | PR #57 ouverte, **pas mergée**, **pas live** `b71089a` |
| Q237 | Payer une vue YouTube ? | **Non** | VIEW < CONSULT < USE < VALIDATE < UTILITY ; §1–§45 |

---

## 47.2 Simulations **déjà identifiées** — statut

Ce ne sont pas de nouvelles attaques live. C'est le cadastre.

| ID | Scénario | Où | Live ? |
|---|---|---|---|
| 221-A | Propagation même `last_hash` / digest | T-E47 + live 221 + **remeasure 237** | **oui** (4/4 actuel) |
| 221-B | Créateur tombé, destination garde le tip | V-01-B keep-book | **oui lecture** ; **non production** |
| 221-C | Transfert puis lecture ailleurs | 221 | bindings publics |
| 221-D | Double propose | T-E47 | 422 |
| 221-E | Ancien contrôleur | T-E47 | 403 |
| 221-F | Agent admin ORG | T-E46 | 403 |
| 222-G | Duplicate | T-E48 | pas de 2ᵉ append |
| 222-H | Mauvais `prev_hash` | T-E48 | refus |
| 222-I | Mauvais index | T-E48 | refus |
| 222-J | Hash forgé | T-E48 | `hash_mismatch` |
| 222-K | Événement public arbitraire | T-E48 | `archive_only` |
| 222-M | Deux producteurs | T-E48 local | tips divergent ; pas de fusion silencieuse |
| 222-N | Partition + rejoin | identifié | **non démontré** |
| 225-L | Producteur de secours live | identifié, GO distinct | **non exécuté** |
| 236-T | Liste CONSENSUS sans certificat | T-E50 sur branche 236 | `can_produce=false` **local** ; pas live |
| 237-R | Boucle Reasoning Fee (Sybil / collusion / inutilité) | **cette section** | simulation papier, **pas** de mint live |

---

## 47.3 Simulation économique de la boucle (§45) — unités **SIM**, pas un solde live

Aucun chiffre ci-dessous n'est un solde, un bloc ou un Settlement du mainnet. Plafond 21 M **inchangé**. La fee est un **transfert**, pas une émission.

Hiérarchie figée :

```text
VIEW
  <
CONSULT          (UsageID signé wallet humain)
  <
USE              (le graphe entre dans un nouveau raisonnement)
  <
TRANSFORM        (dérivation, pas copie)
  <
VALIDATE         (résultat mesuré)
  <
UTILITY          (PoUC / Evidence)
  <
REPRODUCED       (indépendant)
```

### SIM-R1 — 1 000 agents « vues » vs 50 consultations humaines

Hypothèse : 1 000 agents cliquent. 50 humains signent `CONSULT`.

| Règle de paiement | Revenu producteur (SIM-u) | Sybil gagne ? |
|---|---|---|
| YouTube-like : 0,001 × 1 000 vues | 1,000 | **oui** |
| BaseAccessFee seulement sur CONSULT : 0,001 × 50 | 0,050 | **non** (agent sans session humaine) |
| Base + UsageVerified (USE) : 50 consult + 10 USE × 0,01 | 0,150 | **non** si USE exige un graphe descendant |

C'est-à-dire : **si tu paies VIEW, tu finances l'attaque.** Si tu paies CONSULT+USE, le volume d'agents n'est plus le PIB.

### SIM-R2 — lettres de **prix** du §44 (A–E) — distinctes des lettres **GO** du §56

| Lettre prix | Barème | Pression spam CONSULT | Adoption | Concentration |
|---|---|---|---|---|
| A | 0,0001 / accès | haute | haute | producteur médiocre survit |
| B | 0,001 / accès | moyenne | moyenne | compromis |
| C | 0,01 / accès | basse | plus basse | bon producteur plus visible |
| D | dynamique | dépend du score | imprévisible sans KCG | risque de feedback loop |
| E | accès 0 + reward sur USE validé | spam d'accès **gratuit** ; attaque se déplace sur fausses USE | lecture large | le plus proche de PoUC |

**Je ne choisis toujours pas A–E comme prix définitif.** Le §45 reste l'architecture à tester :

```text
ReasoningFee
=
BaseAccessFee
+
UsageVerifiedComponent
```

en **transfert**. E (prix) est compatible avec cette architecture si BaseAccessFee=0. Ce n'est **pas** GO-E (producteur live).

### SIM-R3 — mint vs transfer (plafond 21 M)

| Mécanisme | Supply | Attaque |
|---|---|---|
| Mint à chaque vue | explose / ou casse D-024 | YouTube on-chain |
| Transfer consulteur → producteur | **21 M inchangé** | il faut des jetons déjà émis |
| Reward PoL de bloc `reward=0` sur commitment | **n'émet pas** | déjà le cas 220 |

C'est-à-dire : la Reasoning Fee **ne doit pas** devenir une deuxième émission.

### SIM-R4 — royalties infinies sur connaissances dérivées

| Politique | Effet |
|---|---|
| 100 % au producteur originel à chaque descendant | le graphe se fige ; personne n'améliore |
| 0 % au parent | pillage ; KCG inutile |
| Part plafonnée + décroissance + cap de profondeur (ex. 3) | **à spécifier dans GO-F/G**, pas à inventer ici en D-0xx |

### SIM-R5 — l'utilisateur paie et n'obtient aucune utilité

Sans PoUC, la fee d'accès est un loyer. Avec PoUC, une partie peut être **escrow** jusqu'à un résultat mesuré (GO-H). **Non codé.**

### SIM-R6 — collusion A↔B (je consulte tes graphes, tu consultes les miens)

CONSULT signé ne suffit pas. Il faut : identité humaine, plafond agent, anti-Sybil déjà présents **en partie**, plus une **réputation de connaissance** (232) qui n'existe pas encore en rang 3.

---

# 48. 236 n'est pas sur `main`

PR ouverte : https://github.com/vgactech/artcb/pull/57  
Branche : `cursor/org-node-roles-236-568e`  
Commit : `4ba0196`  
État : **OPEN**, pas mergée. Live `b71089a` **ne contient pas** `node_roles.py` / `node_cert.py`.

```text
déclaré dans authorized_nodes
        ≠
certifié par signature fondateur
        ≠
BODY copié
        ≠
droit de produire
        ≠
droit de vendre l'ORG
```

`TRANSFER_OWNERSHIP` = **humain seulement**. Lister Frankfurt en `CONSENSUS` sans certificat → `can_produce=false` (T-E50 **local**).

C'est-à-dire : **on ne doit pas parler de 236 comme s'il tournait déjà sur OVH1.**

---

# 49. Les fichiers générés sont-ils déjà protégés cryptographiquement de bout en bout, à tous les niveaux ?

**Non.**

Hash ≠ chiffrement. Sel ≠ chiffrement. Signature de bloc ≠ confidentialité au repos. HTTPS sur `:8443` (OVH1) ≠ les 3 autres nœuds en HTTP `:8000`. Push chiffré ≠ pull clair.

## 49.1 Matrice — ce qui existe vraiment

| Artefact généré | Au repos (disque hôte) | En transit | Intégrité | Identité producteur / auteur |
|---|---|---|---|---|
| `blocks.jsonl` (lignes publiques) | **clair** | pull **GET clair** ; push **ML-KEM-768 + AES-GCM** | hash bloc + sig hybride Ed25519\|ML-DSA-65 | `from_node_id` **n'est pas** une preuve |
| BODY Genesis ORG `orgs.json` | **clair** (P-218-1) | **pas** gossip public | `canonical_hash` | session fondateur / contrôleur |
| export / import bundle | **clair** | API (HTTP ou HTTPS selon nœud) | hash | session |
| `commitments.jsonl` local | **clair** | non gossipé comme BODY | hash + `commitment_salt` local | — |
| graphe IR (JSON) | **clair** | HTTP `/encode` | `sha256` du `source_text` et des `txt` | aucune clé IR |
| mémos auto-dev | `visibility=private` | **pas** sync P2P public | hash bloc | `sess_` (+ agent id) |
| seed wallet / blob PQC | **AES-256-GCM** (scrypt, magic `ARTCBENC1`) **si** passphrase présente | n/a | AEAD | passphrase env |
| `data/p2p/node_identity.json` (`kem_secret_key_hex`) | **clair** (JSON, chmod 0600 seulement) | n/a (clé locale) | aucun AEAD | `P2PSync.decrypt_envelope` lit cette clé |
| seed Ed25519 chaîne (création sans passphrase) | **peut rester clair** (`chain/manager.py` fallback) | n/a | hash/sig des blocs | nœud |
| pool chunks opt-in | — | ML-KEM-768 | AEAD | worker KEM |
| certificats nœud 236 | n/a live | n/a live | Ed25519 fondateur **sur PR #57 seulement** | possession de `node_public_key` **PR seulement** |

## 49.2 Niveaux qui **ne** sont **pas** fermés

```text
1. Disque hôte ORG / IR / blocks.jsonl     → clair
2. Pull P2P public                         → clair
3. HTTP :8000 nœuds 2/3/4                  → Bearer interdit en clair (SDK) ; health public
4. High-value hybrid AND                   → fonction câblée, enforcement false
5. Handshake P2P                           → historique : Ed25519 seule encore acceptée (fenêtre D-032)
6. Identité nœud OVH1                      → placeholder `artcb1_REMPLACER_PAR_VOTRE_ADRESSE`
7. advertised_base_url                     → OVH1 = `http://172.16.0.67:8000` (RFC1918)
                                              OVH2/AWS3/OVH4 = `http://localhost:8000`
8. kem_secret_key_hex (node_identity.json) → JSON clair — pas AES-GCM
9. seed Ed25519 chaîne (fallback)          → peut être clair si passphrase absente
```

Donc : **seuls les blobs wallet/PQC passés par `encrypt_secret_blob` / `encrypt_private_key` sont chiffrés au repos.** La clé privée **P2P ML-KEM** (`kem_secret_key_hex` dans `node_identity.json`) est du JSON clair. Un compromis disque de l'hôte ouvre les enveloppes push. `chmod 0600` n'est pas un chiffrement. Le reste (livre, ORG, IR, export) est clair comme déjà dit.

Codex (PR #58) : grouping « PQC = AES-GCM » sans cette ligne **était faux**. Corrigé ici, pas dans le 237.

---

# 50. Le format binaire PoL convertit-il déjà tous les formats en arrière-plan ?

**Non.**

Ce qui existe :

```text
texte humain UTF-8
   →
IREncoder (règles + option LLM)
   →
IRGraph JSON v0.1
   = source_text COMPLET
   + nodes (t, sym, txt, checksum, spans)
   + edges
   + macros
   →
option GraphCompressor
   = gzip niveau 6 du JSON
```

Ce qui **n'existe pas** :

- codec binaire natif PoL (pas de msgpack / CBOR / protobuf / IR packed) ;
- conversion universelle PDF/DOCX/audio/image → IR en arrière-plan « déjà » ;
- un langage **uniquement** IA sans phrase humaine : chaque nœud garde `txt` (phrase) ;
- SIMD / mmap d'IR ; GPU encode.

Le PDF Wailly a un loader (`parallel=False` depuis 235). Ce n'est pas « tous les formats ».  
`libartcb_chain.so` calcule des **SHA-256 de blocs**, pas un packing IR.

La réversibilité vient de `source_text` + spans (`encoder.py` / `decoder.py`). C'est volontaire. C'est aussi **pourquoi il n'y a pas de compression nette** : on **duplique** le texte dans le JSON.

« Langage adapté à l'IA » aujourd'hui = **interlangue hybride** :

| Couche | Pour qui | Exemple |
|---|---|---|
| `t` | agent | `F` `E` `R` `H` `D` `G` `P` `C` `M` |
| `sym` / ACTION_CODES | agent | `O1` `C1` `K1` `V1`… |
| `rel` | agent | `→` `⇒` `⊃` `⊥` `⊢` `≡` |
| `txt` | humain **et** agent | phrase française |
| `source_text` | humain / audit | texte original entier |
| droits ORG / policies | JSON clés humaines | pas de l-IR des droits |

C'est-à-dire : **ce n'est ni du Python, ni un langage IA pur, ni déjà le format binaire PoL complet.** Les droits (GRANT, TRANSFER, HOST) restent des documents JSON, pas des nœuds IR.

---

# 51. Taux de compression **réellement** mesuré (2026-09-07, cet environnement)

Commande : `IREncoder` + `GraphCompressor.compress_graph` + gzip/zstd/brotli/lzma sur les **mêmes** octets UTF-8.  
`zstandard` et `brotli` **ne sont pas** des dépendances runtime ARTCB ; ils ont été installés **seulement pour comparer**. Le produit, lui, gzip-6.

Formule code `IREncoder.compression_ratio` :

```text
1 - len(IR JSON) / len(source_text)
```

Comme le JSON **contient** `source_text` **plus** les nœuds, cette formule est **souvent négative**. Ce n'est pas un taux de compression. C'est un taux d'**expansion** déguisé.

`GraphCompressor.estimate_compression_ratio` ≈ **0,69** sur tous les échantillons (heuristique unique_chars). **Ce n'est pas une mesure.** Les tests `test_compression_ratio_positive` vérifient seulement `isinstance(ratio, float)`, pas un ratio > 0.

La doc API (`docs/API_REFERENCE_ARTCB.md`) montre `"compression_ratio": 0.68`. **Cet exemple n'est pas reproductible** sur les textes mesurés ici.

## 51.1 Octets mesurés

| Échantillon | UTF-8 | gzip-6 | zstd-3 | zstd-19 | brotli-5 | lzma-6 | IR JSON | gzip(IR) | formule encoder |
|---|---|---|---|---|---|---|---|---|---|
| PROTOCOL 8k chars | 4239 | 2217 | 2310 | 2219 | 2224 | 2268 | **21545** | 6333 | **-4,1439** |
| AUTO_PROMPT 8k chars | 8225 | 4034 | 4192 | 3994 | 4094 | 3980 | **28524** | 8829 | **-2,4695** |
| phrase Reasoning Fee | 280 | 231 | 221 | 225 | 213 | 292 | **7844** | 3954 | **-26,3394** |
| « Observer… » ×40 | 2600 | 102 | 79 | 76 | 73 | 144 | **43055** | 6606 | **-15,9246** |

Round-trip `GraphCompressor` : **OK** (texte identique, checksums OK). `GraphCompressor` **= gzip du JSON**, pas un codec PoL.

## 51.2 Ratio réel = taille_sortie / taille_utf8 (plus petit = mieux)

| Échantillon | gzip texte | zstd-19 texte | IR JSON | gzip(IR) |
|---|---|---|---|---|
| PROTOCOL | **0,523** (~1,91×) | 0,523 | **5,08× plus gros** | 1,49× plus gros que l'original |
| AUTO_PROMPT | **0,490** (~2,04×) | 0,486 | **3,47×** | 1,07× plus gros |
| phrase courte | 0,825 (~1,21×) | 0,804 | **28,0×** | **14,1×** |
| répétitif | **0,039** (~25,5×) | 0,029 (~34×) | **16,6×** | 2,54× plus gros que l'original |

Même **sans** `source_text`, le JSON des nœuds gzippé restait **plus gros** que l'UTF-8 d'origine sur ces 4 textes (mesure parallèle : 6157 / 8618 / 3911 / 6503 octets gzip sans source).

## 51.3 Comparaison aux processus **standards connus**

| Procédé | Rôle | Sur texte ARTCB (cette mesure) | Point fort | Point faible |
|---|---|---|---|---|
| gzip / DEFLATE (LZ77+Huffman) | standard HTTP, git, PNG IDAT | ~2× sur spec/prompt ; ~25× si très répétitif ; ~1,2× si court | universel, streamable | pas sémantique ; fenêtre 32 Ko |
| zstd | Facebook/Meta, moderne | voisin de gzip ici ; **meilleur** sur répétitif (79 vs 102) | plus rapide que xz en général | **absent du runtime IR** |
| brotli | HTTPS web | voisin gzip ; **meilleur** répétitif (73) | dense sur texte web | **absent du runtime IR** ; plus lent à haute qualité |
| lzma/xz | archives | voisin gzip sur spec ; **pire** que brut sur 280 octets (292>280) | max densité parfois | lent ; overhead court |
| bzip2 | (non mesuré ici) | typiquement entre gzip et xz | — | — |
| JSON pretty/compact | sérialisation | IR utilise compact `indent=None` pour gzip | lisible debug | verbeux (`"source_text"`, `"checksum"`) |
| IR ARTCB + gzip | « compression » produit | **expansion 1,07× à 14×** vs UTF-8 | structure agent + réversibilité | **perd** contre gzip du texte |
| Macros IR (7 sur répétitif) | dédup sémantique | n'empêche pas 16× JSON | intention PoL | JSON reste énorme |
| Tokenizers LLM (BPE) | contexte modèle | **pas** une compression fichier | dense pour l'IA | irréversible ; pas le livre |
| PNG/JPEG/WebP | images | **hors sujet** texte/IR | — | — |
| SHA-256 C (`libartcb_chain`) | intégrité bloc | n'économise aucun octet IR | consensus | pas un codec |

Ordres de grandeur **classiques** (littérature, pas cette run) : gzip texte ~2–3× ; zstd similaire ou un peu mieux ; xz un peu mieux sur gros corpus ; brotli-11 souvent le plus dense en HTTP. **Aucun de ces standards n'est battu par l'IR actuel**, parce que l'IR n'est pas un compresseur : c'est un **graphe d'audit qui embarque encore le texte.**

## 51.4 Points forts / points faibles — IR PoL actuel

**Forts**

- réversible (spans + `source_text`) ;
- checksums `sha256:` par nœud et par graphe ;
- types / symboles pour un agent ;
- cache d'encode par hash de texte ;
- gzip round-trip testé.

**Faibles**

- duplication `source_text` + `txt` ;
- formule et doc annoncent une compression qui n'existe pas ;
- heuristique ~69 % trompeuse ;
- gzip-6 seulement, pas zstd ;
- pas de binaire natif ;
- petits textes = catastrophe d'expansion (28×) ;
- « Optimisation #6 » = gzip JSON, pas un algorithme PoL.

---

# 52. Les calculs sont-ils déjà optimisés au maximum ?

**Non.**

| Déjà là | Pas au maximum |
|---|---|
| cache `IREncoder._cache` par `sha256_text` | pas de cache disque IR, pas de mmap |
| gzip niveau 6 | pas 9, pas zstd, pas dictionary training |
| SHA-256 C pour le **bloc** | IR reste Python + JSON |
| `pol_score` 0–1, anti-Sybil préfiltre | pas SIMD graphe, pas GPU |
| `decide_public_import` unique | pull encore clair (coût réseau + fuite) |

C'est-à-dire : on a des **raccourcis honnêtes**, pas un IR saturé machine. Le goulot mesuré n'est même pas le CPU d'encode : c'est **la taille JSON**.

---

# 53. Ce que tu n'avais pas précisé — rattrapé ici (protocole + AUTO_PROMPT)

1. **Un rapport ne crée pas une D-0xx.** Lettres = propositions. GO opérateur ensuite.
2. **SHA tests ≠ SHA docs ≠ SHA live ≠ SHA de la PR 236.** 237 mesure `b71089a`. 236 = `4ba0196` hors main. V-01-B = `e68563e`.
3. **9 skipped ≠ 0 anomalie.** PDF Wailly, catalog OVH, RPC bridges, liboqs, fichiers founders.
4. **`certified=true` ≠ BFT ≠ failover producteur ≠ ORG privée certifiée.**
5. **Ne pas réécrire l'histoire du bloc 220** (adresses éventuellement encore dans d'anciens `public_symbols`).
6. **Ne pas mélanger Doppler** (D-029). Clé OVH1 ≠ `artcb-2` ≠ `artcb3`.
7. **Ne pas déployer `main` sur OVH1** sans ordre — les 4 officiels **exécutent déjà** `b71089a` ; ce rapport ne redéploie pas.
8. **Ne pas lancer V-01-B producteur** sans GO dédié (fork).
9. **Ne pas coder PoUC/KCG/Reasoning Fee** tant que tu n'as pas choisi une lettre GO.
10. **P-218-7** : `node_id` OVH1 toujours placeholder ; `ARTCB_NODE_PUBLIC_URL` manquant sur 2/3/4 (localhost) ; OVH1 annonce une IP privée `172.16.0.67`.
11. **Le slogan P2P « blocs publics chiffrés » est faux pour le pull.**
12. **L'exemple API `compression_ratio: 0.68` est faux** comme fait général.
13. **Contact** `official@artcb.space`. Halving **interdit** (D-024) — pas dans ce menu.
14. **Agents** : plafond, pas d'ORG, mémos private. Reasoning Fee future = wallet **humain**.
15. **Lettres prix §44 A–E ≠ lettres GO §56 GO-A…** Coller l'étiquette évite de « choisir E » en croyant parler du producteur live.
16. **`node_identity.json` n'est pas un blob wallet.** `NodeIdentityStore._save` écrit `kem_secret_key_hex` en clair. `chmod 0600` ≠ AES-GCM. GO-A doit le couvrir. Ne pas dire « les secrets PQC sont chiffrés » sans distinguer **signing wallet** et **KEM P2P**.
17. **Un rapport déjà sur `main` n'est pas un fichier de travail.** Suite = numéro suivant (238), pas un append sur 237.

---

# 54. Architecture préférée (rappel §45) — toujours valable, toujours non codée

$$
\boxed{
ReasoningFee = BaseAccessFee + UsageVerifiedComponent
}
$$

- transfert, pas mint ;
- VIEW non payé ;
- CONSULT = événement signé ;
- USE / VALIDATE / UTILITY montent la part variable ;
- 21 M intact ;
- KCG = graphe, pas compteur de vues.

La prochaine étape **si tu veux l'économie** n'est pas 0,001 vs 0,01. C'est **GO-F puis GO-G** (ou le paquet **GO-L**).

---

# 55. Autres paquets que le §45 n'avait pas mis en lettres

Le frais de raisonnement **ne ferme pas** :

- P-218-1 chiffrement BODY ;
- pull clair ;
- certificats nœud 236 ;
- replica automatique ;
- V-01-B producteur ;
- IR binaire.

Si tu donnes GO seulement sur la fee, ces trous restent.

---

# 56. Propositions **finales par lettre** — à cocher pour GO d'implémentation bout en bout

Ces lettres sont des **paquets de code complets**, pas des idées.  
**Aucune n'est commencée par ce rapport.**

Légende : **prérequis** = autre lettre d'abord. **Risque fork** = essai live dangereux. **Ops** = config, pas protocole.

| Lettre | Paquet bout en bout | Prérequis | Risque | Ce que ça n'est pas |
|---|---|---|---|---|
| **GO-A** | Chiffrement au repos : BODY / `orgs.json` / export (P-218-1) **et** `kem_secret_key_hex` dans `node_identity.json` (même famille AES-256-GCM que le wallet) + seed chaîne si encore clair + tests + rotation | — | moyen (tous les nœuds doivent relire l'identité) | pas du transport pull |
| **GO-B** | Pull P2P = même crypto que push (ML-KEM-768+AES-GCM) ; `from_node_id` lié à la clé ; slogan status aligné | — | moyen (compat pairs) | pas BFT |
| **GO-C** | Merger PR #57 + poser `ARTCB_NODE_ID` / certificats live HOST≠CONSENSUS | merge #57 | moyen | pas auto-copie BODY |
| **GO-D** | Réplication privée automatique du BODY vers hôtes certifiés (P-218-3) | **C** (+ **A** fortement) | élevé (fuite si mauvais hôte) | pas chaîne privée BFT |
| **GO-E** | V-01-B **producteur** live (un nœud mine, OVH1 down, 5 nœuds) | GO **dédié** écrit | **fork** | pas keep-book 222 |
| **GO-F** | Modèle d'événements KCG rang 3 : UsageID, lineage, CONSULT/USE/TRANSFORM **sans** fee | — | faible | pas de token |
| **GO-G** | Reasoning Fee complète = formule §45, transfert, anti-VIEW, tests éco, **pas** de mint | **F** | moyen (tokenomics) | pas PoUC escrow |
| **GO-H** | PoUC Challenge / Stake / Evidence / escrow « payé sans utilité » | **F** (idéal **G**) | moyen | pas YouTube |
| **GO-I** | IR binaire natif PoL : plus de duplication `source_text` dans le wire format ; zstd ; mesures avant/après ; droits aussi en nœuds IR si tu veux le « langage IA » | — | moyen (réversibilité) | pas une D-0xx supply |
| **GO-J** | Ops seulement : `ARTCB_NODE_PUBLIC_URL` OVH2/AWS3/OVH4 (+ corriger OVH1 172.16) | — | faible | pas du protocole économique |
| **GO-K** | Gel : **aucun** code. Rang 6 freeze. | — | nul | — |
| **GO-L** | Paquet **économie connaissance** : F+G+H d'un seul GO | — | moyen/élevé | n'inclut pas A–E réseau |
| **GO-M** | Paquet **domaine durci** : A+B+C+D | — | élevé | n'inclut pas la fee |
| **GO-N** | Doc/runtime honesty only : corriger API `0.68`, message P2P « chiffré », formule `compression_ratio` pour qu'elle ne mente plus | — | nul | pas une feature |

## 56.1 Combinaisons autorisées (pour ne pas tout mélanger)

Tu peux cocher **une** lettre, ou une combinaison **écrite** :

```text
Exemple 1 : GO-J + GO-N          (ops + honnêteté, zéro économie)
Exemple 2 : GO-C                 (finir 236 sur main, puis live certs)
Exemple 3 : GO-F puis plus tard GO-G
Exemple 4 : GO-L                 (économie complète KCG+fee+PoUC)
Exemple 5 : GO-M                 (ORG réellement privée sur hôtes)
Exemple 6 : GO-I                 (vrai format PoL binaire)
```

**Interdit d'inférer :** GO-G n'autorise pas GO-E. GO-C n'autorise pas GO-D. GO-L n'autorise pas le chiffrement au repos. Un GO « implémente tout » sans lettre = **refusé par ce rapport**.

## 56.2 Recommandation (ce n'est pas un GO)

Si **un seul** GO économique : **GO-L** (c'est le §45 + 230–232, bout en bout).  
Si **un seul** GO « j'ai oublié la confidentialité » : **GO-M**.  
Si **tu ne veux encore rien coder** : **GO-K**.  
Si **tu veux d'abord que les docs cessent de mentir** (compression, pull) : **GO-N**, puis le reste.

Ordre technique le plus sûr **si tu enchaînes plus tard** :

```text
GO-N  (ne plus mentir)
  →
GO-J  (URL publiques)
  →
GO-C  (236 live)
  →
GO-A + GO-B  (disque + pull)
  →
GO-D  (copie BODY, seulement après A+C)
  →
GO-F → GO-G → GO-H   ou d'un coup GO-L
  →
GO-I  (binaire IR, peut être parallèle à F)
```

**GO-E** reste **hors séquence**, GO manuscrit, jour dédié, 5 nœuds, keep-book vérifié **avant**.

---

# 57. Feuille de vote opérateur (à recopier)

```text
Date GO :
Lettre(s) choisie(s) :
Combinaison autorisée explicitement :
GO-E producteur live : oui / non (défaut non)
Nouvelle D-0xx : aucune depuis ce rapport, sauf si tu l'écris dans DECISIONS_UTILISATEUR_ARTCB
Contact : official@artcb.space
```

---

# Conclusion 238 (suite du 237 figé)

Le **Reasoning Fee** reste cohérent avec PoUC/KCG **à condition** de ne pas payer les vues.

Le réseau live **aujourd'hui** : 4 officiels sur `b71089a`, tip `27350024…`, digest `b5f93d3f…`, 5 blocs. PR 236 **ouverte**. PoUC/KCG/fee **non codés**. Fichiers ORG/IR/livre **non** chiffrés au repos. Pull **clair**. IR **JSON+gzip**, pas binaire PoL. Compression IR **négative** (expansion 3× à 28×) alors que gzip du texte fait ~2×.

Tu n'as plus à choisir « 0,001 ou 0,01 ». Tu as à **cocher une lettre GO** ici, pas dans le 237. Tant que la feuille §57 est vide, l'agent suivant **ne code pas**.
