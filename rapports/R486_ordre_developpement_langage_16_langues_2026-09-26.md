# R486 — ORDRE DE DÉVELOPPEMENT DU LANGAGE ARTCB — CONVERGENCE 16 LANGUES

**Date :** 2026-09-26  
**HEAD audité avant ordre :** `a36e5138654cb20793455553dd74c2f160b2fb51`  
**Objet :** donner à l'agent de développement un ordre d'intégration strict pour faire converger le langage ARTCB vers un langage sémantique natif utilisable par les agents, avec les 16 langues traitées en parallèle.

## 0. RÈGLE DE PÉRIMÈTRE

Ce rapport est un **ordre de développement**. Il ne modifie pas le code, les règles, les tests ou la configuration du protocole.

Seul le dossier `rapports/` est modifié par cet ordre. Toute implémentation doit être effectuée ensuite par l'agent de développement dans ses propres changements contrôlés.

**Invariant :** `CERTIFIED_100=false` reste inchangé tant que les preuves requises ne sont pas obtenues.

## 1. EXPERTISES MOBILISÉES

- ingénierie de langage et compilateurs ;
- tokenisation, normalisation et morphologie multilingue ;
- représentation sémantique / IR ;
- équivalence sémantique et ConceptID ;
- architecture de langages pour agents IA ;
- tests de conformité et property-based testing ;
- forensic lineage / provenance ;
- systèmes distribués et exécution déterministe ;
- benchmark, Monte Carlo et analyse statistique ;
- optimisation Pareto ;
- routage sémantique / graphes ;
- ingénierie logicielle, CI et non-régression ;
- audit spécification → code → tests → preuves.

## 2. ÉTAT DE DÉPART VÉRIFIÉ

Le commit `a36e513` livre R485 et établit désormais une source de vérité unique :

`rules/LANGUAGE_REGISTRY_CANONICAL.json`

et son API :

`src/artcb/language/canonical_registry.py`

Le registre déclare **16 langues** et impose l'utilisation du registre canonique pour les déclarations de couverture.

Les 16 voies à traiter en parallèle sont :

`fr, en, es, pt, pt-BR, it, ru, zh, ar, de, id, ja, ko, pl, tr, la`.

R485 confirme également que le système ne doit pas prétendre être certifié à 100 % : le taux R471 global est de **0,064136 %** de résolution sur 21 484 106 entrées, soit 13 779 résolutions.

La batterie `langage_battery.py` n'établit actuellement que des `PASS_LOCAL` pour T2 et T3 ; plusieurs fonctions fondamentales restent OPEN ou NOT_PROVEN_LIVE.

## 3. OBJECTIF RÉEL

L'objectif n'est pas de fabriquer 16 traducteurs indépendants.

L'objectif est :

**16 langues humaines → normalisation linguistique propre à chaque langue → représentation sémantique canonique ARTCB → ConceptID/IR déterministe → raisonnement, mémoire, outils et exécution sans dépendance obligatoire au texte humain.**

C'est-à-dire :

- chaque langue doit pouvoir exprimer le même concept ;
- le concept doit être représenté une seule fois au niveau sémantique ;
- les agents doivent pouvoir manipuler cette représentation directement ;
- la langue humaine devient une interface d'entrée/sortie, et non le format interne obligatoire de raisonnement ;
- aucune langue ne doit devenir une dépendance structurelle cachée des autres.

## 4. ORDRE D'INTÉGRATION OBLIGATOIRE

### R486-A — BATTERIE DE CONFORMITÉ 16 LANGUES

Créer le banc de référence qui exécute exactement les mêmes tests pour les 16 ISO.

Pour chaque langue, produire :

1. tokenizer ;
2. normalizer ;
3. lexical mapper ;
4. parse/IR mapping ;
5. ConceptID attendu ;
6. sortie canonique ;
7. erreurs et ambiguïtés ;
8. provenance de la résolution ;
9. métriques de couverture.

**Règle :** les 16 langues doivent utiliser la même interface de test. Une langue ne doit pas bénéficier d'un test plus faible parce que son script ou sa morphologie est différente.

### R486-B — CORPUS SÉMANTIQUE CANONIQUE

Construire un corpus de concepts indépendants de la langue.

Chaque entrée doit posséder au minimum :

- `ConceptID` ;
- catégorie sémantique ;
- forme canonique ;
- variantes ;
- contraintes de contexte ;
- relations avec d'autres concepts ;
- exemples positifs ;
- exemples négatifs ;
- ambiguïtés connues ;
- version du corpus ;
- hash du corpus.

Le corpus doit être versionné et hashé.

### R486-C — 16 PIPELINES EN PARALLÈLE

Créer une implémentation par langue, mais sous une même interface :

`LanguageAdapter`

Contrat minimal :

- `tokenize()`
- `normalize()`
- `morphology()`
- `map_to_concept()`
- `parse_to_ir()`
- `render_from_ir()`
- `explain_mapping()`

Les adapters ne doivent pas contenir leur propre définition de ConceptID.

Le ConceptID appartient au niveau sémantique commun.

### R486-D — NORMALISATION PAR FAMILLE LINGUISTIQUE

Traiter explicitement les problèmes réels déjà identifiés :

- arabe : RTL, racines/formes morphologiques ;
- allemand : mots composés + cas ;
- indonésien : affixes/agglutination ;
- japonais : segmentation + kanji/hiragana/katakana ;
- coréen : agglutination, particules, honorifiques ;
- polonais/russe : flexion casuelle ;
- turc : agglutination + harmonie vocalique ;
- chinois : segmentation des mots ;
- portugais/PT-BR : variantes régionales ;
- latin : flexion et déclinaisons ;
- langues latines restantes : variantes morphologiques et lexicales.

**Important :** ne pas corriger ces problèmes par ajout massif d'alias seulement. Les alias sont un filet de sécurité lexical ; ils ne remplacent pas une normalisation linguistique structurée.

### R486-E — ÉQUIVALENCE CROSS-LANGUAGE

Pour chaque concept du corpus, générer des expressions dans les 16 langues.

Tester :

`langue A → ConceptID`

puis :

`ConceptID → langue B → ConceptID`

pour les 16 × 16 chemins pertinents.

Le test doit détecter :

- collision ;
- perte d'information ;
- ambiguïté ;
- changement de sens ;
- dépendance à la langue source ;
- dépendance à l'ordre des tokens ;
- dérive de version.

Le résultat doit être une matrice d'équivalence 16×16, avec preuve reproductible.

### R486-F — ROUND-TRIP

Exigence :

`texte → IR → texte → IR`

doit conserver le sens canonique, même si la surface textuelle change.

Le test ne doit pas exiger que la phrase reconstruite soit identique mot pour mot.

Il doit exiger :

`ConceptID_{initial} = ConceptID_{final}`

et, pour les structures composées :

`SemanticGraph_{initial} equiv SemanticGraph_{final}`.

### R486-G — LANGAGE NATIF POUR AGENTS

Une fois l'équivalence prouvée, exposer l'IR comme interface native des agents.

Les fonctions minimales à fournir sont :

- création de concept ;
- composition ;
- décomposition ;
- comparaison ;
- unification ;
- substitution ;
- requête ;
- mémoire ;
- provenance ;
- raisonnement ;
- sérialisation ;
- désérialisation ;
- traduction surface ↔ IR ;
- validation ;
- versionnement.

**Principe :** l'agent ne doit pas avoir besoin de repasser par une langue humaine pour combiner deux concepts déjà représentés en IR.

## 5. ORDRE DES TRAVAUX APRÈS R486

### R487 — FORENSIC LINEAGE COUCHE PAR COUCHE

Tracer chaque ConceptID depuis :

`texte source → tokenizer → normalizer → mapper → IR → ConceptID → graphe → raisonnement → sortie`.

Chaque étape doit être identifiable et reproductible.

Une résolution sans provenance complète ne doit pas être comptée comme preuve forte.

### R488 — MONTE CARLO LINGUISTIQUE

Créer une simulation indépendante du Monte Carlo économique.

Variables :

- langue ;
- script ;
- longueur ;
- morphologie ;
- ambiguïté ;
- synonymie ;
- bruit typographique ;
- variation régionale ;
- ordre des mots ;
- combinaison de concepts.

Sorties :

- probabilité de résolution ;
- collision ;
- perte sémantique ;
- ambiguïté ;
- temps de traitement ;
- taille IR.

### R489 — PARETO RUNTIME

Mesurer les compromis :

- précision ;
- latence ;
- mémoire ;
- taille IR ;
- coût CPU ;
- coût réseau.

Ne pas optimiser une métrique isolément.

### R490 — PARETO INVERSÉ

Chercher les cas où l'optimisation d'une métrique dégrade une propriété sémantique importante.

Exemple :

`IR plus petit ≠ IR meilleur`

si la compression détruit une distinction sémantique.

### R491 — TSP / SEMANTIC ROUTING

Construire le routage sémantique comme problème de graphe :

- concepts = nœuds ;
- relations = arêtes ;
- coût = distance sémantique + coût d'exécution ;
- objectif = atteindre le concept cible avec le minimum de coût sous contrainte de fidélité.

Le routage doit fonctionner indépendamment de la langue de surface.

## 6. RÈGLE DE CONCURRENCE DES 16 LANGUES

Les 16 langues avancent **en parallèle**, mais les dépendances sont communes.

Le modèle de travail est :

`1 corpus canonique → 16 adapters → 1 IR commun → 1 batterie commune → 1 matrice d'équivalence`.

Il est interdit de créer :

`16 corpus + 16 IR + 16 règles de ConceptID`

car cela recréerait exactement la divergence que R485 vient de supprimer.

## 7. GATES DE VALIDATION

Aucun passage à l'étape suivante ne doit être déclaré DONE_VERIFIED sans :

1. tests automatisés ;
2. test des 16 langues ;
3. non-régression ;
4. hash du registre canonique ;
5. hash du corpus de test ;
6. artefact de résultats ;
7. provenance ;
8. distinction PASS_LOCAL / LIVE / CERTIFIED ;
9. maintien de `CERTIFIED_100=false` tant que les conditions ne sont pas satisfaites.

## 8. TRAVAUX ANTÉRIEURS À NE PAS ABANDONNER

La priorité du développement est le langage, mais les tâches historiques ouvertes restent dans la file parallèle et ne doivent pas être effacées :

- R431 — device-binding revoke ;
- R432-FHE — FHE réelle pour l'unicité ;
- R433 — FAR/FRR sur capteurs réels ;
- G4 / `reasoning.py` — moteur de déduction natif ;
- DV-02 et validations live distribuées ;
- autres tâches P0/P1 du ledger.

Elles ne doivent toutefois pas interrompre le chemin principal du langage lorsque leur dépendance n'est pas nécessaire.

## 9. ORDRE D'EXÉCUTION POUR L'AGENT

**ORDRE 1 :** relire le HEAD `a36e513` et le registre canonique.

**ORDRE 2 :** construire R486-A à R486-F sans changer le protocole économique.

**ORDRE 3 :** faire fonctionner les 16 langues sur le même corpus et la même batterie.

**ORDRE 4 :** corriger les gaps linguistiques par familles morphologiques/script, pas par duplication anarchique d'alias.

**ORDRE 5 :** obtenir une matrice d'équivalence 16×16 reproductible.

**ORDRE 6 :** intégrer round-trip et provenance.

**ORDRE 7 :** exposer les primitives IR nécessaires aux agents.

**ORDRE 8 :** seulement après stabilisation de R486, exécuter R487.

**ORDRE 9 :** ensuite R488 → R489 → R490 → R491.

**ORDRE 10 :** à chaque étape, exécuter la non-régression complète et produire le rapport correspondant.

## 10. CRITÈRE DE RÉUSSITE DU CHANTIER LANGAGE

Le chantier n'est pas terminé lorsque les 16 tokenizers existent.

Il est terminé lorsque :

`16 langues humaines`

convergent vers :

`1 représentation sémantique canonique`

et que cette représentation peut être :

`créée → comparée → combinée → mémorisée → raisonnée → exécutée → sérialisée → reconstruite`

sans perte sémantique démontrée sur le corpus de référence.

**CERTIFIED_100 reste false jusqu'à preuve complète.**

---

### ORDRE FINAL

**PRIORITÉ ABSOLUE : DÉVELOPPEMENT DU LANGAGE ARTCB.**

Ne pas repartir sur une nouvelle couche économique avant d'avoir construit cette chaîne :

**16 langues → normalisation → ConceptID → IR sémantique → équivalence → round-trip → provenance → raisonnement → outils → runtime → routage sémantique.**

Le but n'est pas simplement que ARTCB « comprenne 16 langues ».

Le but est que les 16 langues deviennent **16 interfaces d'entrée/sortie d'un même langage sémantique natif pour agents**.
