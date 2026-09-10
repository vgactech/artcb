# R309 — Explications claires + SSH diagnostiqué + CI déclenchée

**UTC :** 2026-09-10T16:40:00Z  
**CERTIFIED_100 :** `false`  
**SHA ×5 :** `32a0ab0…` = `origin/main` (rattrapé)

## 1. « Ingestion aux blocs 1135 / 1136 » — en français simple

Quand tu m’envoies un message, le protocole copie ton texte dans un **mémo** et le grave dans la blockchain ARTCB.

- **Bloc** = une page du livre (numéro d’ordre).
- **1135** puis **1136** = numéros de pages où ces mémos ont été écrits.
- Ce n’est **pas** du thinking. C’est le **texte de ton prompt**.
- Preuve : HTTP 200, `includes_thinking=false`.

## 2. Langage IA ConceptID — pourquoi « pas finalisé »

Il existe du **code IR** (`src/artcb/ir/concept.py`) qui calcule des `ConceptID` (K…) à partir de symboles.

Ce qui **n’est pas** terminé (rapports 252–256) :

- un vrai langage natif agent↔agent bout-en-bout prouvé live ;
- convergence multi-langues humaine → même ConceptID mesurée en production ;
- remplacement du langage humain dans le consensus.

**i18n 7 langues UI ≠ langage IA ConceptID.**  
Finaliser ça = chantier produit, pas un bouton. Je ne peux pas le déclarer « fini » sans mentir.

## 3. Blocage SSH — de quoi je parle (mesuré)

| Chemin | Résultat |
|--------|----------|
| `https://artcb.me` / `n2` / `n3` / `n4` | **OK** (souvent Cloudflare) |
| IP publique `:22` / `:8000` / `:8443` depuis **ce Mac** | **Connection refused** ×4 (OVH1/2/4 + AWS3) |
| Sur AWS3 **depuis l’intérieur** (SSM) | `sshd` écoute `0.0.0.0:22`, `pub22_ok` |

Donc : **les serveurs AWS ne sont pas « SSH cassé »**.  
Le refus vient du trajet **Mac/LAN → IP publique**. Même symptôme sur les 4 IPv4.

J’ai pu ouvrir **SSM sur AWS3** (profil IAM créé + associé + reboot). Via SSM : firewall hôte OK, UFW inactive, SG/NACL ouverts.

### Pourquoi je ne « règle » pas tout seul

Sans un chemin réseau Mac→IP:22, je ne peux pas SSH vers OVH1/2/4 pour y retirer d’éventuelles règles. AWS : gérable via SSM maintenant. OVH : **besoin de toi** (console) si le filtre n’est pas côté Mac.

### Ce que tu peux faire pour m’aider (priorité)

1. **Test hotspot téléphone** : depuis le Mac en 4G, `nc -vz 13.38.209.25 22` et `nc -vz 152.228.144.34 22`.  
   - Si **ça passe** → filtre box/Wi‑Fi.  
   - Si **ça refuse encore** → firewall Mac (Little Snitch / Lulu / pf).
2. Désactive temporairement le pare-feu applicatif Mac, reteste.
3. OVH (si besoin côté serveur) : console VNC Manager → une seule commande de diagnostic :
   `sudo ss -lntp | grep :22 ; sudo iptables -L INPUT -n | head`
4. **Ne wipe rien.** Ne touche pas `blocks.jsonl`.

## 4. CI « statuses vides » — expliqué

Le workflow `tests.yml` est **volontairement** `workflow_dispatch` only (commentaire dans le fichier) : **jamais** de CI auto sur push.  
D’où `total_count=0` / `statuses=[]` sur chaque commit — ce n’était pas « cassé », c’était **désactivé**.

Action ce tour : dispatch manuel run **34503344277** sur SHA `32a0ab0…` (queued puis suivi).

## 5. Follow-main OVH en retard

**Résolu** au moment de la mesure R309 : SHA `32a0ab0…` ×5 (OVH1/2/4 + AWS3 + Mac).

## 6. Ce qui reste bloqué sans toi

| Item | Bloqué par |
|------|------------|
| SSH Mac → IPv4 seeds | Réseau/pare-feu **côté Mac/LAN** (preuve AWS interne OK) |
| Tunnel Mac PBFT public | Token/tunnel **à démarrer sur le Mac** |
| ConceptID « langage final » | Conception + preuves live longues |
| CERTIFIED_100 | Toujours false (N04, chaos, Mac tip, etc.) |

Je continue le possible (SSM AWS, CI dispatch, mesures). Je ne invente pas un PASS SSH.

## 7. CI run 34503344277

`workflow_dispatch` lancé sur `32a0ab0…` → **failure** : `pytest --timeout=120` sans plugin `pytest-timeout`.
Correctif : ajout `pytest-timeout>=2.3.1` dans `requirements.txt`, redispatch.

