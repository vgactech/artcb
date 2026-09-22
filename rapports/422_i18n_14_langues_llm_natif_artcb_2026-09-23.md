# Rapport R422 — Internationalisation ARTCB + nouveau chantier LLM natif

Date : 2026-09-23
Dépôt : vgactech/artcb / main
Type : audit documentaire et plan d'implementation. Aucun code applicatif modifié.

## Expertises mobilisées

- audit GitHub et architecture logicielle
- i18n/l10n frontend et Unicode
- NLP multilingue
- architecture Transformer/LLM
- tokenisation et datasets
- apprentissage auto-supervisé, continued pretraining et instruction tuning
- évaluation LLM et tests de regression
- représentation sémantique, ConceptID, ExpressionID, KnowledgeID
- agents IA et communication agent-agent
- PoL, blockchain, provenance et versionnement
- systèmes distribués et calcul GPU
- confidentialité des données d'apprentissage

## 1. Audit internationalisation

Le fichier frontend/src/i18n/translations.ts actuellement présent dans main déclare 7 langues : fr, en, zh, es, pt, it, ru.

La cible demandée est de 14 langues :

1. ar — arabe
2. de — allemand
3. en — anglais
4. es — espagnol
5. fr — français
6. id — Bahasa Indonesia
7. it — italien
8. ja — japonais
9. ko — coréen
10. pl — polonais
11. pt — portugais
12. tr — turc
13. zh-Hans — chinois simplifié
14. zh-Hant — chinois traditionnel

Ecart minimal à traiter : ar, de, id, ja, ko, pl, tr et zh-Hant. La langue ru existe actuellement mais n'est pas dans la liste cible de cette demande ; elle peut rester en compatibilité tant qu'une décision explicite ne demande pas sa suppression.

Le code actuel utilise zh comme identifiant générique. Pour éviter une ambiguïté entre chinois simplifié et traditionnel, la cible doit utiliser zh-Hans/zh-Hant, ou zh-CN/zh-TW avec une table canonique interne.

## 2. Processus i18n complet

Le problème n'est pas seulement de traduire translations.ts. Il faut auditer toutes les vues et tous les modules frontend : dashboard, agents, chain, PoL, wallets, mining, system, logs, console, integrations, governance, groups, register, biométrie et tous les composants partagés.

Chaque chaîne doit avoir : clé stable, traduction, fallback, test d'absence et test d'affichage.

Il faut aussi tester les messages d'erreur venant de l'API, les notifications, les modales, les états vides, les tableaux, les formulaires et les textes dynamiques.

Pour l'arabe, ajouter une vraie gestion RTL. Les hashes, adresses, IDs, seed, ConceptID et autres identifiants techniques doivent rester lisibles et ne pas être réordonnés par le rendu RTL.

Pour le chinois, la séparation zh-Hans/zh-Hant doit être explicite.

## 3. Lien avec le langage IA ARTCB

Le dépôt possède déjà une base réelle : LANGAGE_SYMBOLES_ARTCB documente trois couches de symboles, un registre persistant, des symboles originaux proposés par l'IA et une synchronisation P2P des symboles.

Le R421 fourni dans le contexte établit aussi des résultats sur ConceptID, codec, KnowledgeID et certains niveaux L1-L10, tout en laissant plusieurs niveaux partiels et plusieurs exigences ouvertes.

Il faut donc maintenant distinguer trois couches :

A. langues humaines : arabe, allemand, anglais, espagnol, français, indonésien, italien, japonais, coréen, polonais, portugais, turc, chinois simplifié et chinois traditionnel ;

B. représentation sémantique ARTCB : ConceptID, ExpressionID, KnowledgeID, symboles, IR et codec ;

C. LLM natif : modèle capable de comprendre les langues humaines, manipuler directement la représentation ARTCB, produire cette représentation et la soumettre à un validateur externe.

## 4. Nouveau chantier : LLM natif ARTCB

Le LLM natif ne doit pas être défini comme un simple modèle qui parle une nouvelle langue. Il doit comprendre la relation :

langue humaine -> concept -> représentation ARTCB -> connaissance -> raisonnement -> sortie vérifiable.

L'architecture cible proposée est :

Langues humaines
        ↓
Tokenizer multilingue + tokens ARTCB
        ↓
LLM ARTCB
        ↓
ARTCB Expression
        ↓
Validator
        ↓
Concept/Knowledge/Expression Registry
        ↓
provenance + éventuellement PoL

Le LLM propose ; le validateur protocolaire décide si la sortie est syntaxiquement et sémantiquement acceptable. Il ne faut pas transformer directement une sortie probabiliste en vérité blockchain.

## 5. Processus de création LLM à suivre

Phase 1 — spécification du langage : grammaire, types, symboles, ConceptID, ExpressionID, KnowledgeID, opérateurs et règles de compatibilité.

Phase 2 — tokenizer : tokenizer multilingue pouvant représenter les textes humains et les tokens structurés ARTCB. Les outils Hugging Face permettent déjà d'entraîner un tokenizer personnalisé et d'adapter le vocabulaire à un domaine ou à une langue. Voir sources officielles citées dans le rapport de réponse.

Phase 3 — dataset : corpus des 14 langues, équivalences sémantiques, exemples langue -> ConceptID, ConceptID -> texte, ARTCB IR, raisonnements, preuves, contre-exemples et données synthétiques contrôlées.

Phase 4 — provenance : chaque entrée doit avoir DatasetEntryID, source, langue, ConceptID éventuel, version, licence, classe de confidentialité et hash de provenance.

Phase 5 — petit modèle expérimental : commencer par un modèle de recherche de taille modeste afin de démontrer la stabilité sémantique avant d'investir dans un très grand modèle.

Phase 6 — continued pretraining : adapter un modèle de base avec le corpus ARTCB. Cette voie permet de conserver des capacités générales tout en spécialisant le modèle.

Phase 7 — instruction tuning : apprendre les tâches ARTCB : traduire vers l'IR, lire l'IR, expliquer une Expression, comparer deux connaissances, construire une réponse avec provenance et refuser une représentation invalide.

Phase 8 — alignement/évaluation : comparer les sorties selon exactitude sémantique, validité ARTCB, provenance, reproductibilité et absence d'hallucination. DPO/RLHF ou une autre méthode restent à choisir après benchmark.

Phase 9 — validator externe : validation de schéma, Concept Registry, Expression Registry, provenance cryptographique et règles de compatibilité.

Phase 10 — intégration PoL : Job -> LLM -> raisonnement -> validation -> KnowledgeID -> preuve -> règlement. Une simple inference ne doit jamais être automatiquement considérée comme un travail utile rémunérable.

Phase 11 — distribution : commencer en mono-GPU puis utiliser les primitives distribuées nécessaires. PyTorch documente DDP, FSDP et tensor parallelism ; Megatron Core documente data, tensor, pipeline, context et expert parallelism pour les très grands modèles.

Phase 12 — registry : ModelID, ParentModelID, DatasetVersion, TokenizerVersion, TrainingConfigHash, WeightsHash, EvaluationHash et ReleaseID.

## 6. Dataset ARTCB à construire

D1 : corpus multilingue 14 langues.
D2 : phrases parallèles et reformulations sémantiquement équivalentes.
D3 : mapping texte -> ConceptID.
D4 : mapping ConceptID -> expressions ARTCB.
D5 : KnowledgeID/ExpressionID et provenance.
D6 : raisonnements avec hypothèse, étapes, conclusion et preuve.
D7 : contre-exemples et collisions sémantiques.
D8 : tâches de traduction ARTCB -> humain et humain -> ARTCB.
D9 : données adversariales et hallucination.
D10 : exemples de confidentialité : les données privées ne deviennent pas automatiquement des données globales d'entraînement.

## 7. Fonction de perte à étudier

Proposition de recherche, non implémentée :

L_total = λ1 L_language + λ2 L_concept + λ3 L_expression + λ4 L_reconstruction + λ5 L_consistency + λ6 L_provenance

C'est-à-dire : apprendre la langue, le bon ConceptID, la bonne structure ARTCB, la reconstruction, la stabilité sémantique et la traçabilité.

Cette équation doit rester une hypothèse expérimentale jusqu'à validation sur les benchmarks.

## 8. Tests fondamentaux

Test multilingue :

FR -> ARTCB -> EN -> ARTCB -> JA -> ARTCB -> FR

Le ConceptID doit rester identique lorsque le concept est réellement identique.

Tests inverses :

ARTCB -> français
ARTCB -> anglais
ARTCB -> arabe
ARTCB -> japonais
ARTCB -> chinois simplifié
ARTCB -> chinois traditionnel

Tests de collision : deux concepts différents ne doivent pas converger artificiellement vers le même ConceptID.

Tests de falsification : un raisonnement plausible mais faux ne doit pas devenir une connaissance validée uniquement parce que le LLM le formule avec assurance.

## 9. Intégration blockchain

Les poids du modèle ne doivent pas être stockés directement dans la blockchain. La chaîne doit plutôt enregistrer les commitments et métadonnées nécessaires : ModelID, version, hash des poids, version du tokenizer, version du dataset, configuration d'entraînement, résultats d'évaluation et provenance.

Les poids peuvent rester dans une couche de stockage adaptée.

## 10. Exigences du nouveau chantier

LLM-01 spécification formelle du langage.
LLM-02 tokenizer ARTCB.
LLM-03 vocabulaire spécial.
LLM-04 grammaire et validator.
LLM-05 dataset 14 langues.
LLM-06 dataset ConceptID.
LLM-07 dataset ExpressionID.
LLM-08 dataset raisonnement/provenance.
LLM-09 petit modèle baseline.
LLM-10 architecture hybride humain + ARTCB.
LLM-11 continued pretraining.
LLM-12 instruction tuning.
LLM-13 alignment/evaluation.
LLM-14 validator externe.
LLM-15 tests hallucination/sémantique.
LLM-16 reproductibilité.
LLM-17 provenance cryptographique.
LLM-18 Model Registry.
LLM-19 Knowledge/Expression settlement.
LLM-20 PoL end-to-end.

## 11. Critère de réussite

Le chantier ne pourra pas être déclaré terminé parce qu'un modèle génère correctement du texte.

La preuve recherchée est :

14 langues -> même concept -> même ConceptID -> Expression ARTCB valide -> validation externe -> provenance -> KnowledgeID -> travail PoL vérifiable.

## 12. Conclusion

Internationalisation : l'état actuel frontend est inférieur à la cible de 14 langues ; huit ajouts sont nécessaires et le chinois doit être séparé en simplifié/traditionnel.

Langage IA : la base symbolique ARTCB existe déjà, mais le LLM natif n'est pas démontré comme système complet.

Nouveau chantier : LLM-001 doit commencer par la spécification, le tokenizer, le dataset et les benchmarks, puis seulement par l'entraînement. Le premier objectif n'est pas la taille du modèle mais la preuve que la sémantique ARTCB est apprise et conservée entre les 14 langues.

Statut : chantier spécifié, implémentation LLM native non certifiée.
CERTIFIED_100 = false.
