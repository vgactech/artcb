# LICENCE ARTCB — Politique ARTCB (privé / groupe / public)

**Titulaire :** ARTCB (Société)  
**Contact :** official@artcb.space  
**Horodatage :** 2026-07-08T22:00:00Z  
**Décision :** ordre utilisateur — , passage licences fermées  
**Autorité licence :** **ARTCB uniquement**, par décision écrite  
**Autorité code :** ARTCB modifie à tout moment — **rollback si majorité rejette** une MAJ majeure (voir `GOUVERNANCE_ARTCB.md`)

---

## 1. Résumé en langage simple

| Réseau | Exemple | Licence du **logiciel** | Les autres peuvent copier/modifier ? |
|--------|---------|-------------------------|--------------------------------------|
| **PRIVÉ** | Ma mémoire perso sur mon wallet | **Propriétaire** | **Non** (sans accord ARTCB) |
| **GROUPE** | Projet d'équipe, join-request, ACL | **Propriétaire** | **Non** (sans accord ARTCB) |
| **PUBLIC** | Blocs `visibility=public` sur la chaîne | **BSL 1.1** (SSPL possible si ARTCB le décide) | **Limité** — voir LICENSE-PUBLIC-BSL.md |

**Le dépôt GitHub entier** est **propriétaire par défaut** (`LICENSE`).  
Seul le volet **réseau public** a une licence plus permissive (BSL) pour consultation et R&D non-production.

---

## 2. Fichiers de licence

| Fichier | Rôle |
|---------|------|
| `LICENSE` | Licence **défaut** — propriétaire ARTCB (tout le dépôt) |
| `LICENSE-PROPRIETAIRE.md` | Détail réseaux **privé** et **groupe** |
| `LICENSE-PUBLIC-BSL.md` | Réseau **public** — Business Source License 1.1 |
| `LICENCE_ARTCB.md` | Ce document — politique globale |
| `GOUVERNANCE_ARTCB.md` | Modifications code + vote majorité + rollback |
| `NOTICE` | Copyright et marques |

---

## 3. Qui peut changer les licences ? Qui peut changer le code ?

### Licences (copier, utiliser, vendre le logiciel)

**Uniquement ARTCB** — pas un vote des utilisateurs. Voir sections 1–2 et `LICENSE-*.md`.

### Code (mises à jour du programme)

| Règle | Détail |
|-------|--------|
| ARTCB modifie le code | **À tout moment**, sans vote préalable |
| Engagement rollback | Si **majorité des utilisateurs votants** **rejette** une mise à jour **majeure**, ARTCB **corrige** (revient en arrière ou publie un correctif) |
| Vote automatique | **Pas encore codé** — règle actée dans `GOUVERNANCE_ARTCB.md` |
| Contact | official@artcb.space |

Les utilisateurs :
- gardent le contrôle de **leurs données** (wallet, clés privées) ;
- **ne décident pas** de la licence ;
- **peuvent voter** pour valider ou **rejeter** une mise à jour majeure (quand le mécanisme sera en place).

---

## 4. Annexe A — Composants réseau PUBLIC (BSL 1.1)

| Composant | Chemin indicatif |
|-----------|------------------|
| Filtre chaîne `visibility=public` | `src/artcb/chain/manager.py` (lecture public) |
| Store `visibility=public` | `src/api/routes.py` |
| API `GET /chain?visibility=public` | `src/api/routes.py` |
| Documentation protocole public | `GROUPES_RESEAUX_ARTCB.md` § réseau public |

Tout le reste (groupes, join-request, wallets privés, dashboard interne, tokenomics, anti-sybil, etc.) = **LICENSE-PROPRIETAIRE.md**.

---

## 5. Annexe B — Composants PRIVÉ et GROUPE (propriétaire)

| Composant | Chemin indicatif |
|-----------|------------------|
| Groupes & ACL | `src/artcb/groups/` |
| Join-request Solution 2 | `src/artcb/groups/join_requests.py`, `signing.py` |
| Wallets locaux | `src/artcb/wallet/` |
| Chaîne privée / groupe scoped | `data/chain/`, store `group_id` |
| Dashboard V1–V10 | `frontend/` |
| Tokenomics & rewards | `src/artcb/tokenomics.py` |

---

## 6. SSPL (alternative future)

Si ARTCB publie un **service en ligne** (SaaS) basé sur le réseau public, la **SSPL v1** pourra s'appliquer à ce service sur décision écrite, en complément ou remplacement du BSL pour la partie hébergée.

Tant qu'aucun fichier `LICENSE-PUBLIC-SSPL.md` n'est publié, **BSL seul** régit le public.

---

## 7. Historique

| Date | Événement |
|------|-----------|
| 2026-07-04 | CDC NF-09 : intention « open source » (hackathon) |
| 2026-07-08 | Hackathon terminé — ARTCB : **propriétaire** (privé+groupe) + **BSL** (public) |
| 2026-07-08 | Gouvernance : modif code libre + rollback si majorité rejette — `GOUVERNANCE_ARTCB.md` |

---

**© 2026 ARTCB — official@artcb.space**
