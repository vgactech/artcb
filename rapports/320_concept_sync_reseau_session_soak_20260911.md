# R320 — Sync ConceptStore réseau (C2-D) + durcissement session (2026-09-11)

`CERTIFIED_100=false`. Ce rapport sépare : **faits mesurés**, **comportement du code**,
**hypothèses**, **limites**, **solutions possibles**. Aucune valeur live n'est inventée.

---

## 1. Le problème que R319 laissait ouvert

R319 mesurait C2-D en `PARTIAL`. C'est-à-dire : un agent A apprend une phrase,
fabrique un paquet binaire `ACPT` qui ne contient **que des ConceptID**
(des identifiants du type `K3e7dc01c5cf83cd8`, jamais de texte humain), et
l'envoie à un agent B.

Or un ConceptID est **une référence, pas une définition**. C'est-à-dire : c'est
l'équivalent d'un numéro de fiche. Si B ne possède pas la fiche — le graphe
binaire `.arcb` correspondant dans son propre `ConceptStore` — il ne peut rien
reconstruire. R319 contournait cela avec `shutil.copytree`, c'est-à-dire une
copie de répertoire sur le même disque. **Copier un dossier n'est pas une preuve
réseau.**

## 2. Ce que R320 ajoute (comportement du code)

### 2.1 Un format binaire de bundle : `ACBN`

Nouveau fichier <ref_file file="/home/ubuntu/repos/artcb/src/artcb/memory/concept_sync.py" />.

```text
magic(4)="ACBN" | version(2) | graph_count(4)
puis graph_count × : graph_id_len(2) | graph_id | blob_len(4) | blob(.arcb)
```

C'est-à-dire : une enveloppe qui transporte un ou plusieurs graphes `.arcb`
**tels quels**, sans JSON, sans texte lisible par un humain. Le décodeur rejette
un magic inconnu, une version inconnue, une longueur incohérente ou un message
tronqué — il ne « devine » jamais.

### 2.2 Deux routes réseau

Nouveau routeur <ref_file file="/home/ubuntu/repos/artcb/src/api/concept_routes.py" /> :

| Route | Rôle | Auth |
|---|---|---|
| `POST /api/v1/concepts/publish` | ingérer un bundle `ACBN` (≤ 8 MiB) | Bearer **obligatoire** |
| `GET /api/v1/concepts/resolve?ids=…` | renvoyer le bundle binaire couvrant ces ConceptID | lecture |
| `GET /api/v1/concepts/stats` | vue humaine du store | lecture |
| `GET /api/v1/concepts/{concept_id}` | métadonnées d'un concept | lecture |

`resolve` déclare honnêtement les concepts qu'il **ne** connaît pas dans l'en-tête
`X-ARTCB-Concept-Missing`, et publie le SHA-256 du bundle dans
`X-ARTCB-Bundle-Sha256`. Traces `ts_ns` / `dur_ns` sur les deux chemins.

### 2.3 Un agent qui va chercher ce qui lui manque

<ref_file file="/home/ubuntu/repos/artcb/src/artcb/memory/agent_channel.py" /> :
`receive_packet(packet, resolver=…)` cherche d'abord localement, liste les
ConceptID manquants, appelle le résolveur **uniquement pour ceux-là**, ingère le
bundle, puis retente. Sans résolveur, le comportement d'avant est inchangé.

## 3. Faits mesurés

### 3.1 Batterie C2 relancée (script <ref_file file="/home/ubuntu/repos/artcb/scripts/artcb_c2_langage_e2e.py" />)

| Niveau | R319 | R320 |
|---|---|---|
| C2-A lexique + adversaire | PASS | PASS |
| C2-B phrases FR/EN/ES | PASS | PASS |
| C2-C raisonnement sans texte | PASS | PASS |
| C2-D chemin réseau | **PARTIAL** | **PASS** (portée §5) |

Mesures C2-D du run :

```text
b_missing_before_network : ["K9638f146df59253d", "K05336c50b14ee52d"]   ← B froid échoue
bundle_bytes             : 554
bundle_sha256            : a6fb891c300dd8f7fe6732f941d98123a42821872419cdd446b880e4f41d942b
bundle_has_no_human_text : true
publish                  : 1 graphe, 2 ConceptID, HTTP OK
resolve_http_status      : 200
graphs_ingested_from_network : 1
b_missing_after_network  : []                                           ← B comprend
b_persists_without_network : true                                       ← B a vraiment appris
```

La dernière ligne est importante : après coupure du nœud, B **re-résout le même
paquet sans réseau**. C'est-à-dire que la connaissance est entrée dans son store,
ce n'est pas un cache de requête.

### 3.2 Tests

`28 passed` — 17 tests réseau concepts + 11 tests soak session
(<ref_file file="/home/ubuntu/repos/artcb/tests/test_e2e320_concept_sync_network.py" />,
<ref_file file="/home/ubuntu/repos/artcb/tests/test_e2e320_session_soak.py" />).

### 3.3 Session (durcissement demandé)

<ref_file file="/home/ubuntu/repos/artcb/src/api/auth_routes.py" /> :

- TTL absolu conservé : **1800 s**.
- Nouveau TTL d'inactivité : **900 s** (`ARTCB_SESSION_IDLE_TTL`) → `401 session_idle_timeout`.
- Liaison d'appareil (empreinte hachée de `User-Agent` + `X-ARTCB-Device-Id`) →
  un token rejoué depuis un autre appareil donne `401 session_device_mismatch`.
- `GET /auth/sessions` (jamais de token ni de hash complet), `POST /auth/revoke`
  (par `session_id`, propriétaire seul), `POST /auth/logout-all`.

### 3.4 Nœud live (bootstrap du tour)

| Mesure | Valeur |
|---|---|
| health | `200` |
| `git_sha` live | `99cb1d7ff5722c85efd0724ec7705341f955039b` = `origin/main` |
| hauteur | `1526`, dernier index `1525` |
| `last_hash` | `c113bf70df30f2d16cdd21ee7449de2559bb8decd0a8609531d184153f40b55b` |
| `chain_valid` | `true` |
| clé API dans cet environnement | **absente** → ingestion mémo `ingest_skipped=true` |

Sonde des nouvelles routes sur le nœud live : `GET /api/v1/concepts/resolve` → **404**.
C'est-à-dire : le code R320 **n'est pas encore déployé**. Aucun PASS live n'est revendiqué.

## 4. Hypothèses (non prouvées ici)

- Le `404` live est attribué à l'absence de déploiement, pas à un blocage réseau :
  cohérent avec `git_sha` live = R319, mais non prouvé tant que R320 n'est pas suivi ×4.
- L'ancre mémo du `packet_sha256` n'a pas pu être relue dans ce tour faute de clé
  API dans cet environnement ; le code de relecture (`_get_memo`) existe et sera
  mesuré au prochain tour disposant de la clé.

## 5. Limites — à lire avant de crier victoire

1. **Portée du PASS C2-D** : la preuve est une vraie requête HTTP sur socket TCP
   (`127.0.0.1`, uvicorn, corps binaire), entre **deux ConceptStore séparés**.
   Ce n'est pas encore une preuve **multi-hôte** entre OVH/AWS. Le champ
   `network_proof_scope` du JSON le dit explicitement.
2. **Pas de propagation P2P** : `publish` écrit sur le nœud contacté. Aucune
   diffusion PBFT des blobs `.arcb` n'est implémentée.
3. **Sessions en mémoire** : `_sessions` est un dict de processus. Un redémarrage
   révoque tout, et deux workers ne partagent pas l'état.
4. **`automobile` ≠ C2** reste un trou lexical honnête (R319, non refermé).
5. Trois tests de `tests/test_e2e216_authz_privacy.py` échouent — préexistants à
   R320, non investigués jusqu'à la cause racine.
6. Tâches héritées toujours ouvertes : catch-up après 716, `swtpm` macOS 12,
   matrice multi-wallet, langage IA natif **NON CERTIFIÉ**.

## 6. Solutions possibles (par coût croissant)

- **Déployer R320 ×4 puis re-sonder** `/api/v1/concepts/resolve` : transforme le
  PASS local en PASS multi-hôte. Coût : un follow-main.
- **Ancrer le bundle SHA en mémo PBFT** à chaque `publish` : le bundle devient
  vérifiable contre la chaîne, pas seulement contre son propre hash.
- **Sessions persistées** (fichier chiffré ou table) : supprime la limite 3.
- **Diffusion `ACBN` dans le gossip** : un concept publié sur un nœud devient
  résoluble sur les quatre sans requête dirigée.

---

Append-only : ce rapport n'efface aucun rapport antérieur. R319 reste valide sur
son propre périmètre ; seul le statut C2-D évolue, avec sa portée explicitée.
