# FAQ ARTCB — Questions de Non-Experts

**Date :** 2026-07-05  
**Version :** 1.0  
**Public cible :** Personnes sans connaissance technique blockchain/IA

---

## 📚 Table des Matières

1. [Qu'est-ce qu'ARTCB ?](#1-quest-ce-quartcb)
2. [Comment ça marche ?](#2-comment-ça-marche)
3. [Minage d'apprentissage](#3-minage-dapprentissage)
4. [Argent et économie](#4-argent-et-économie)
5. [Sécurité et confiance](#5-sécurité-et-confiance)
6. [Utilisation pratique](#6-utilisation-pratique)
7. [Comparaison avec autres systèmes](#7-comparaison-avec-autres-systèmes)
8. [Questions avancées](#8-questions-avancées)

---

## 1. Qu'est-ce qu'ARTCB ?

### Q1.1 : C'est quoi ARTCB en une phrase ?

**R :** ARTCB est un système qui **récompense les gens qui aident des intelligences artificielles à apprendre**, comme Bitcoin récompense ceux qui sécurisent le réseau, mais ici le travail est **utile** (compression de connaissance) au lieu d'être du calcul pur.

### Q1.2 : C'est une cryptomonnaie comme Bitcoin ?

**R :** **Pas exactement.** ARTCB a une unité de compte (le "coin" ARTCB) pour récompenser le travail, mais son objectif principal est de **tracer et valider l'apprentissage des IA**, pas d'être une monnaie d'échange comme Bitcoin.

**Différences clés :**
- **Bitcoin** : Monnaie décentralisée, réserve de valeur
- **ARTCB** : Mémoire IA + traçabilité + récompense apprentissage

### Q1.3 : Pourquoi "Proof-of-Learning" ?

**R :** C'est le nom du mécanisme qui **prouve qu'un apprentissage a eu lieu**. Au lieu de prouver qu'on a fait du calcul (Proof-of-Work Bitcoin), on prouve qu'on a :
1. **Compressé** de l'information (réduction de taille)
2. **Validé** la cohérence (vérification qualité)
3. **Reconstruit** le texte original (réversibilité 100%)

### Q1.4 : C'est pour qui ?

**R :** Trois publics :
1. **Développeurs IA** — Mémoire persistante pour agents
2. **Chercheurs** — Audit causal des raisonnements
3. **Mineurs d'apprentissage** — Gagner des ARTCB en compressant des livres/documents

---

## 2. Comment ça marche ?

### Q2.1 : Comment on "mine" de l'apprentissage ?

**R :** En 6 étapes simples :

```
1. Charger un livre PDF (ex: "Le Roi de l'Inconnu")
2. Le système le décompose en "nœuds" (concepts)
3. Il compresse l'information (réduction de taille)
4. Il valide la cohérence (pas d'erreurs)
5. Il reconstruit le texte original (test réversibilité)
6. Si tout est OK → vous gagnez des ARTCB
```

**Exemple concret :**
- Livre : 654,767 caractères
- Compression : 6,407 nœuds
- Réversibilité : 100% (texte identique)
- Récompense : 1 ARTCB (genesis, puis halving)

### Q2.2 : Qu'est-ce qu'un "nœud" ?

**R :** Un **nœud** est un morceau de connaissance (concept, phrase, idée) extrait du texte. Imaginez découper un livre en post-it intelligents qui se connectent entre eux.

**Exemple :**
```
Texte : "Le roi était sage et juste."
Nœuds :
  - Nœud 1 : "roi" (entité)
  - Nœud 2 : "sage" (attribut)
  - Nœud 3 : "juste" (attribut)
  - Lien : Nœud 1 → Nœud 2, Nœud 1 → Nœud 3
```

### Q2.3 : C'est quoi la "blockchain" ARTCB ?

**R :** Une **liste de blocs** (comme un registre comptable) où chaque bloc contient :
- Un graphe de connaissance (nœuds + liens)
- Un score PoL (qualité de l'apprentissage)
- Une signature cryptographique (preuve d'authenticité)
- Les récompenses distribuées

**Analogie :** Comme un cahier où chaque page est signée et référence la page précédente — impossible de tricher.

### Q2.4 : Pourquoi c'est "réversible" ?

**R :** **Réversibilité = reconstruction exacte du texte original.**

**Exemple :**
```
Texte original : "Le roi était sage."
Compression → Nœuds IR
Décompression → "Le roi était sage." (identique à 100%)
```

**Pourquoi c'est important ?**
- Prouve qu'aucune information n'est perdue
- Garantit la qualité de la compression
- Permet de vérifier le travail des mineurs

---

## 3. Minage d'apprentissage

### Q3.1 : Combien je gagne en minant ?

**R :** Ça dépend de votre **score PoL** (Proof-of-Learning) :

| Score PoL | Qualité | Reward (bloc 1 ARTCB) |
|-----------|---------|------------------------|
| 0.8 | Excellent | ~40 ARTCB (80%) |
| 0.6 | Bon (seuil) | ~30 ARTCB (60%) |
| 0.4 | Faible | 0 ARTCB (rejeté) |

**Formule :**
```
Votre reward = Block reward × (Votre PoL / Total PoL de tous)
```

### Q3.2 : Qu'est-ce qui fait un bon score PoL ?

**R :** Trois critères (pondérés) :

1. **Compression** (40%) — Réduire la taille sans perdre d'info
   - Bon : 50% de réduction
   - Excellent : 70%+ de réduction

2. **Validation** (30%) — Cohérence des nœuds
   - Bon : 80% des nœuds validés
   - Excellent : 95%+

3. **Récupération** (30%) — Reconstruction exacte
   - Bon : 90% de similarité
   - Excellent : 100% (identique)

**Seuil minimum :** PoL ≥ 0.6 pour être payé

### Q3.3 : Combien de temps ça prend ?

**R :** Exemples réels (PC standard) :

| Livre | Taille | Temps | Vitesse |
|-------|--------|-------|---------|
| Wailly (Le Roi de l'Inconnu) | 654,767 chars | 25.85s | 25,328 char/s |
| Quintus (La Fin de l'Iliade) | 548,843 chars | 13.07s | 42,007 char/s |

**Moyenne :** ~30 secondes par livre de 600,000 caractères

### Q3.4 : Je peux miner avec mon ordinateur portable ?

**R :** **Oui !** ARTCB ne nécessite pas de GPU puissant comme Bitcoin.

**Configuration minimale :**
- CPU : 2 cœurs (Intel i3 / AMD Ryzen 3)
- RAM : 4 GB
- Disque : 10 GB
- OS : Linux, macOS, Windows (WSL)

**Pas besoin de :**
- Carte graphique gaming
- Serveur dédié
- Connexion internet ultra-rapide

### Q3.5 : C'est rentable ?

**R :** **Ça dépend du prix de l'ARTCB** (qui n'existe pas encore sur les marchés).

**Calcul théorique :**
```
Hypothèse : 1 ARTCB = 1 USD (arbitraire)
Minage : 1 livre/minute = 50 ARTCB/minute = 50 USD/minute
Coût électricité : ~0.10 USD/minute (PC 100W)
Profit net : ~49.90 USD/minute
```

**Réalité :** Le prix de l'ARTCB sera déterminé par l'offre/demande si un marché se crée.

---

## 4. Argent et économie

### Q4.1 : Combien y a-t-il d'ARTCB au total ?

**R :** **21 millions d'ARTCB maximum** (comme Bitcoin).

**Répartition :**
- **89%** — Minage PoL (block rewards)
- **5%** — Founders (équipe fondatrice)
- **5%** — Réserve protocole
- **1%** — Partenaires / communauté

### Q4.2 : C'est quoi le "halving" ?

**R :** Le **halving** = division par 2 du reward tous les 210,000 blocs.

**Séquence :**
```
Blocs 0-209,999      : 1 ARTCB/bloc
Blocs 210,000-419,999: 25 ARTCB/bloc
Blocs 420,000-629,999: 12.5 ARTCB/bloc
...
Bloc ~6,930,000      : 0.00000001 ARTCB/bloc (dernier satoshi)
```

**Durée :** ~130 ans pour émettre les 21 millions (comme Bitcoin)

### Q4.3 : Qui sont les "founders" ?

**R :** Les **5 personnes** qui ont créé ARTCB. Chacun reçoit **1% de la supply** (210,000 ARTCB) au lancement.

**Pourquoi ?**
- Récompenser le travail de développement initial
- Aligner les intérêts (si ARTCB réussit, ils gagnent)
- Financer le développement futur

**Transparence :** Toutes les transactions founders sont publiques sur la blockchain.

### Q4.4 : Les founders peuvent tricher ?

**R :** **Non**, grâce à 3 mécanismes :

1. **Blockchain publique** — Toutes les transactions sont visibles
2. **Anti-Sybil** — Détection des comportements suspects
3. **Slashing** — Pénalités si tentative de fraude

**Exemple :** Si un founder essaie de créer 1000 faux comptes pour miner, le système détecte et bloque.

### Q4.5 : Je peux acheter/vendre des ARTCB ?

**R :** **Pas encore.** ARTCB est en phase de développement (hackathon 2026).

**Futur possible :**
- Échanges peer-to-peer (personne à personne)
- Listing sur exchanges crypto (Binance, Coinbase, etc.)
- Utilisation comme "gas" pour services IA

**Attention :** Aucune promesse de valeur — c'est un projet expérimental.

---

## 5. Sécurité et confiance

### Q5.1 : Mes données sont-elles privées ?

**R :** **Oui**, par défaut. Vous choisissez la visibilité :

| Mode | Qui voit quoi ? |
|------|-----------------|
| **Private** | Seulement vous (chiffré local) |
| **Public** | Tout le monde (blockchain publique) |
| **Shared** | Groupe spécifique (permissions) |

**Exemple :** Miner un livre privé → seul vous pouvez le lire, mais le hash (empreinte) est public pour prouver l'existence.

### Q5.2 : Quelqu'un peut voler mes ARTCB ?

**R :** **Non**, si vous protégez votre **clé privée**.

**Analogie :** Votre clé privée = mot de passe de votre compte bancaire.

**Bonnes pratiques :**
- ✅ Sauvegarder la clé dans un coffre-fort chiffré
- ✅ Ne jamais la partager
- ✅ Utiliser un wallet hardware (Ledger, Trezor)
- ❌ Ne pas la stocker en clair sur votre PC
- ❌ Ne pas l'envoyer par email/Slack

### Q5.3 : C'est quoi "Anti-Sybil" ?

**R :** Un système qui **détecte les tricheurs** qui créent plein de faux comptes.

**Exemple de triche :**
```
Alice crée 1000 comptes → mine avec tous → prend 99% des rewards
```

**Anti-Sybil détecte :**
- Même adresse IP
- Patterns de comportement identiques
- Timing suspect (tous les comptes minant en même temps)

**Sanction :** Comptes bloqués + rewards confisqués

### Q5.4 : C'est quoi "Slashing" ?

**R :** Une **pénalité** si vous essayez de tricher.

**Exemples de comportements punis :**
- Soumettre des données invalides
- Créer des faux nœuds
- Signer plusieurs blocs contradictoires
- Attaque Sybil (faux comptes)

**Pénalités :**
- **Minor** : Perte de 10% des rewards
- **Major** : Perte de 50% + ban temporaire
- **Critical** : Perte de 100% + ban permanent

### Q5.5 : Qui contrôle ARTCB ?

**R :** **ARTCB** détient le logiciel (licence propriétaire pour privé/groupe).  
Le réseau **public** est en BSL 1.1 (voir `LICENCE_ARTCB.md`).  
Les **données** restent contrôlées par chaque détenteur de wallet.

**Gouvernance :**
- Code : **ARTCB** modifie à tout moment — voir `GOUVERNANCE_ARTCB.md`
- Rollback si **majorité rejette** une mise à jour majeure (vote à implémenter)
- Contact : official@artcb.space

---

## 6. Utilisation pratique

### Q6.1 : Comment je commence à miner ?

**R :** 5 étapes simples :

```bash
# 1. Cloner le projet
git clone https://github.com/vgac2025/lvx.git
cd lvx

# 2. Installer les dépendances
pip install -r requirements.txt

# 3. Compiler la blockchain C
make chain

# 4. Lancer le minage
python3 scripts/mine_learning_simple.py

# 5. Voir vos gains
cat logs/mining_results_*.json
```

**Temps total :** ~5 minutes

### Q6.2 : Quels livres je peux miner ?

**R :** **N'importe quel PDF** (domaine public recommandé).

**Exemples fournis :**
- "Le Roi de l'Inconnu" (Wailly)
- "La Fin de l'Iliade" (Quintus de Smyrne)

**Où trouver des livres ?**
- Project Gutenberg (70,000+ livres gratuits)
- Archive.org (millions de documents)
- Wikisource (textes libres)

**Attention :** Respecter les droits d'auteur (domaine public ou licence libre).

### Q6.3 : Je peux miner en équipe ?

**R :** **Oui !** C'est même encouragé (distribution collective).

**Exemple :**
```
Équipe de 3 personnes mine un livre :
- Alice : PoL 0.8 → 40% du reward (20 ARTCB)
- Bob : PoL 0.7 → 35% du reward (17.5 ARTCB)
- Carol : PoL 0.5 → 25% du reward (12.5 ARTCB)
Total : 1 ARTCB distribué proportionnellement
```

**Avantage :** Partage du travail + validation croisée

### Q6.4 : Ça consomme beaucoup d'électricité ?

**R :** **Non**, ~100x moins que Bitcoin.

**Comparaison :**
| Système | Consommation | Équivalent |
|---------|--------------|------------|
| **Bitcoin** | ~150 TWh/an | Pays-Bas entier |
| **ARTCB** | ~1.5 TWh/an (estimé) | Ville moyenne |

**Raison :** Pas de compétition de hash (Proof-of-Work), juste compression + validation.

### Q6.5 : Je peux utiliser ARTCB pour autre chose que miner ?

**R :** **Oui**, plusieurs cas d'usage :

1. **Mémoire IA** — Stocker les raisonnements d'agents
2. **Audit causal** — Tracer les décisions d'IA
3. **Recherche** — Analyser des corpus de textes
4. **Éducation** — Apprendre la compression de données
5. **Archivage** — Stocker des documents de manière vérifiable

---

## 7. Comparaison avec autres systèmes

### Q7.1 : ARTCB vs Bitcoin ?

| Aspect | Bitcoin | ARTCB |
|--------|---------|-------|
| **Objectif** | Monnaie décentralisée | Mémoire IA + traçabilité |
| **Consensus** | Proof-of-Work (hash) | Proof-of-Learning (compression) |
| **Travail** | Calcul compétitif | Compression utile |
| **Reward** | 1 gagnant/bloc | Tous contributeurs PoL |
| **Gaspillage** | ~99% calcul perdu | Minimal (tout utile) |
| **Énergie** | 150 TWh/an | ~1.5 TWh/an (estimé) |

**Résumé :** ARTCB = Bitcoin mais avec travail utile + distribution collective

### Q7.2 : ARTCB vs Ethereum ?

| Aspect | Ethereum | ARTCB |
|--------|----------|-------|
| **Consensus** | Proof-of-Stake | Proof-of-Learning |
| **Smart contracts** | Oui (Solidity) | Non (focus mémoire IA) |
| **Validateurs** | Stake 32 ETH | Score PoL ≥ 0.6 |
| **Reward** | Validateurs sélectionnés | Tous contributeurs PoL |

**Résumé :** Ethereum = plateforme smart contracts, ARTCB = mémoire IA spécialisée

### Q7.3 : ARTCB vs Filecoin ?

| Aspect | Filecoin | ARTCB |
|--------|----------|-------|
| **Objectif** | Stockage décentralisé | Compression + apprentissage |
| **Consensus** | Proof-of-Spacetime | Proof-of-Learning |
| **Travail** | Prouver stockage | Prouver compression |
| **Reward** | Stockage prouvé | PoL validé |

**Résumé :** Filecoin = stockage brut, ARTCB = compression intelligente

### Q7.4 : ARTCB vs ChatGPT ?

**R :** **Pas comparable** — objectifs différents.

| Aspect | ChatGPT | ARTCB |
|--------|---------|-------|
| **Type** | Modèle de langage (LLM) | Blockchain mémoire IA |
| **Fonction** | Générer du texte | Tracer l'apprentissage |
| **Propriétaire** | OpenAI (centralisé) | Open source (décentralisé) |
| **Coût** | Abonnement 20$/mois | Gratuit (minage optionnel) |

**Complémentarité :** ChatGPT pourrait **utiliser** ARTCB pour tracer ses raisonnements.

---

## 8. Questions avancées

### Q8.1 : C'est quoi un "graphe IR" ?

**R :** **IR = Intermediate Representation** (représentation intermédiaire).

**Analogie :** Comme un plan d'architecte pour un bâtiment.

**Structure :**
```
Graphe IR = {
  Nœuds : [concept1, concept2, ...]
  Arêtes : [lien1, lien2, ...]
  Métadonnées : {source, timestamp, ...}
}
```

**Exemple :**
```
Texte : "Le roi sage gouverne justement."
Graphe IR :
  Nœud 1 : "roi" (entité)
  Nœud 2 : "sage" (attribut)
  Nœud 3 : "gouverne" (action)
  Nœud 4 : "justement" (manière)
  Arête 1 : Nœud 1 → Nœud 2 (a_attribut)
  Arête 2 : Nœud 1 → Nœud 3 (fait_action)
  Arête 3 : Nœud 3 → Nœud 4 (de_manière)
```

### Q8.2 : C'est quoi "RT-LEG" ?

**R :** **RT-LEG = Real-Time Learning Event Graph** (graphe d'événements d'apprentissage en temps réel).

**Fonction :** Tracer **qui a fait quoi, quand, pourquoi** dans le processus d'apprentissage.

**Exemple :**
```
Événement 1 : Explorer propose nœud "roi" (timestamp: 10:00:01)
Événement 2 : Critic valide nœud "roi" (timestamp: 10:00:02)
Événement 3 : Explorer propose nœud "sage" (timestamp: 10:00:03)
...
```

**Utilité :** Audit causal — comprendre comment une décision a été prise.

### Q8.3 : Pourquoi Ed25519 pour les signatures ?

**R :** **Ed25519** = algorithme de signature cryptographique moderne.

**Avantages :**
- **Rapide** : 10x plus rapide que RSA
- **Compact** : Clés de 32 bytes (vs 256 bytes RSA)
- **Sécurisé** : Résistant aux attaques quantiques (partiellement)
- **Déterministe** : Même message → même signature

**Utilisation ARTCB :** Signer les blocs blockchain + transactions

### Q8.4 : C'est quoi le "Merkle root" ?

**R :** Un **hash** (empreinte) qui résume tout le contenu d'un bloc.

**Analogie :** Comme un code-barres unique pour un livre.

**Propriété magique :** Si on change **un seul caractère** dans le bloc, le Merkle root change complètement.

**Utilité :** Détecter toute modification (intégrité garantie)

### Q8.5 : ARTCB est-il résistant aux ordinateurs quantiques ?

**R :** **Partiellement.**

**Vulnérabilités :**
- Ed25519 : Résistant aux attaques quantiques **actuelles**, mais pas aux futurs algorithmes de Shor
- SHA-256 : Résistant (algorithme de Grover réduit sécurité de 256 bits → 128 bits, toujours sûr)

**Plan de migration :**
- Surveiller les avancées quantiques
- Migrer vers signatures post-quantiques (CRYSTALS-Dilithium, etc.) si nécessaire
- Prévoir un hard fork (mise à jour majeure) avant que les ordinateurs quantiques soient une menace réelle

**Horizon :** ~10-20 ans avant que les ordinateurs quantiques soient une menace pratique

---

## 📞 Besoin d'aide ?

**Documentation complète :** [README.md](README.md)  
**Guide technique :** [PROTOCOLE_ARTCB](PROTOCOLE_ARTCB)  
**Support communauté :** GitHub Issues  
**Contact sécurité :** security@artcb.io (PGP requis)

---

**Dernière mise à jour :** 2026-07-05  
**Version :** 1.0  
**Licence :** CC BY-SA 4.0 (Creative Commons Attribution-ShareAlike)