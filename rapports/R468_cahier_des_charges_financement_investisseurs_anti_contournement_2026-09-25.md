# R468 — Cahier des charges financement investisseurs ARTCB — matrice anti-contournement

**Date :** 2026-09-25  
**HEAD audité :** `5fd4fcad268b059b8eff4549fa56442ad4969944`  
**Type :** cahier des charges juridique / économique / technique / auditabilité  
**Statut :** DRAFT FOR LEGAL REVIEW — ne constitue pas un avis juridique  
**CERTIFIED_100=false**

## 0. Mandat et principe directeur

Ce cahier des charges ne remplace pas l'idée initiale : il a pour objet de **la verrouiller**.

> **L'investisseur finance une activité économique déterminée. Il n'achète pas ARTCB, n'obtient aucune allocation ARTCB du fait de son investissement et ne reçoit aucun droit direct ou indirect sur l'émission, les réserves, le PoL, le HBP ou la politique monétaire ARTCB.**

L'investisseur peut recevoir uniquement le droit économique expressément prévu pour l'activité financée et juridiquement validé.

**Règle supplémentaire :** la rémunération de l'investisseur reste en monnaie fiduciaire et suit strictement la devise d'origine de l'investissement. Un investissement en EUR est rémunéré en EUR ; un investissement en USD est rémunéré en USD. Aucun crypto-actif, stablecoin, token, ARTCB ou autre actif numérique ne peut être accepté comme règlement de cette rémunération.

---

# 1. Invariants absolus

Les règles R468-001 à R468-010 sont des invariants de conception. Toute exception bloque l'opération jusqu'à analyse juridique.

## R468-001 — Aucun ARTCB à l'entrée
- **Processus :** versement du financement en monnaie fiduciaire.
- **Risque :** transformer le financement en prévente de coins.
- **Interdiction :** aucun ARTCB remis ou crédité en contrepartie directe de l'investissement.
- **Contrôle juridique :** contrat et documents d'offre sans allocation ARTCB.
- **Contrôle logiciel :** aucun champ exploitable d'allocation investisseur.
- **Preuve :** contrat + rapprochement bancaire + registre ARTCB.
- **Conséquence :** transaction bloquée.

## R468-002 — Aucun pré-minage investisseur
- **Processus :** création/réserve de coins.
- **Risque :** réserver indirectement l'offre aux financeurs.
- **Interdiction :** aucune réserve ARTCB affectée aux investisseurs.
- **Contrôle juridique :** déclaration d'absence de droit.
- **Contrôle logiciel :** aucun rôle/allocation privilégié.
- **Preuve :** audit des wallets.
- **Conséquence :** gel de l'opération.

## R468-003 — Aucun droit sur l'émission future
- **Processus :** droits économiques futurs.
- **Risque :** créer une créance sur les nouveaux ARTCB.
- **Interdiction :** aucun droit actuel ou futur sur l'émission ARTCB.
- **Contrôle juridique :** clause d'exclusion.
- **Contrôle logiciel :** aucun mécanisme de conversion/claim.
- **Preuve :** analyse contractuelle + tests.
- **Conséquence :** instrument non conforme interdit.

## R468-004 — Aucun droit sur les récompenses PoL
- **Processus :** récompenses PoL.
- **Risque :** transformer l'investissement en droit sur le minage.
- **Interdiction :** aucune part PoL du seul fait de l'investissement.
- **Contrôle juridique :** séparation investisseur/protocole.
- **Contrôle logiciel :** aucun bénéficiaire PoL privilégié.
- **Preuve :** audit des règles de distribution.
- **Conséquence :** distribution bloquée.

## R468-005 — Aucun droit sur le HBP
- **Processus :** mécanisme HBP.
- **Risque :** détourner une composante économique du protocole.
- **Interdiction :** aucune quote-part HBP attachée à l'investissement.
- **Contrôle juridique :** exclusion contractuelle.
- **Contrôle logiciel :** aucune route HBP vers le registre investisseur.
- **Preuve :** logs HBP + rapprochement.
- **Conséquence :** règlement bloqué.

## R468-006 — Aucun droit sur les réserves ARTCB
- **Processus :** gestion des wallets protocolaires.
- **Risque :** droit économique implicite.
- **Interdiction :** aucune sûreté, créance, usufruit ou droit bénéficiaire sur les réserves ARTCB.
- **Contrôle juridique :** inventaire des droits exclus.
- **Contrôle logiciel :** ACL wallets sans privilège investisseur.
- **Preuve :** adresses + permissions + signatures.
- **Conséquence :** révocation et audit.

## R468-007 — Aucun droit de gouvernance monétaire par investissement
- **Processus :** gouvernance entreprise/protocole.
- **Risque :** contrôle indirect de l'émission.
- **Interdiction :** l'investissement ne donne aucun pouvoir permettant de modifier la politique monétaire ARTCB.
- **Contrôle juridique :** séparation des organes/droits.
- **Contrôle logiciel :** séparation des rôles.
- **Preuve :** matrice des permissions.
- **Conséquence :** décision suspendue/revue.

## R468-008 — Aucun droit de conversion investissement → ARTCB
- **Processus :** remboursement/sortie/conversion.
- **Risque :** recréer une prévente différée.
- **Interdiction :** aucune conversion contractuelle vers ARTCB.
- **Contrôle juridique :** absence d'option/warrant/convertible ARTCB.
- **Contrôle logiciel :** aucun endpoint de conversion.
- **Preuve :** tests et inventaire des instruments.
- **Conséquence :** instrument interdit.

## R468-009 — Aucun rendement indexé sur le cours ARTCB
- **Processus :** calcul du rendement.
- **Risque :** exposition économique indirecte au coin.
- **Interdiction :** rémunération non calculée selon prix, capitalisation ou quantité d'ARTCB.
- **Contrôle juridique :** formule indépendante du token.
- **Contrôle logiciel :** aucun oracle ARTCB.
- **Preuve :** formule signée + tests de non-dépendance.
- **Conséquence :** calcul rejeté.

## R468-010 — Aucune promesse de valorisation ARTCB
- **Processus :** communication investisseur.
- **Risque :** créer une attente liant investissement et cours ARTCB.
- **Interdiction :** ne pas présenter l'investissement comme un moyen d'obtenir ou de profiter d'une hausse garantie d'ARTCB.
- **Contrôle juridique :** validation des supports.
- **Contrôle logiciel :** versionnement des documents.
- **Preuve :** hash des supports.
- **Conséquence :** retrait du support.

---

# 2. Monnaie d'entrée et de sortie

## R468-011 — Devise d'origine immuable
- **Processus :** réception du financement.
- **Risque :** ambiguïté sur la devise donnant naissance au droit.
- **Interdiction :** devise d'origine enregistrée et non modifiable silencieusement.
- **Contrôle juridique :** devise au contrat.
- **Contrôle logiciel :** `investment_currency` immuable après settlement.
- **Preuve :** relevé bancaire + transaction ID.
- **Conséquence :** rapprochement manuel si divergence.

## R468-012 — Même devise de règlement
- **Processus :** paiement d'une rémunération.
- **Risque :** substitution d'une autre monnaie.
- **Interdiction :** `payment_currency == investment_currency`.
- **Contrôle juridique :** clause same-currency.
- **Contrôle logiciel :** contrôle bloquant.
- **Preuve :** journal de paiement.
- **Conséquence :** paiement refusé.

## R468-013 — Aucun paiement en ARTCB
- **Processus :** règlement investisseur.
- **Risque :** contournement direct.
- **Interdiction :** ARTCB interdit comme monnaie de règlement.
- **Contrôle juridique :** exclusion expresse.
- **Contrôle logiciel :** actif blockchain refusé.
- **Preuve :** transaction bancaire uniquement.
- **Conséquence :** rejet.

## R468-014 — Aucun paiement en autre crypto-actif
- **Processus :** choix du moyen de paiement.
- **Risque :** substitution BTC/ETH/etc.
- **Interdiction :** aucun crypto-actif ne satisfait l'obligation.
- **Contrôle juridique :** définition large des actifs exclus.
- **Contrôle logiciel :** rail non blockchain obligatoire.
- **Preuve :** référence bancaire.
- **Conséquence :** rejet.

## R468-015 — Aucun stablecoin
- **Processus :** proposition USDC/USDT ou équivalent.
- **Risque :** considérer un stablecoin comme équivalent au fiat.
- **Interdiction :** aucun stablecoin comme règlement.
- **Contrôle juridique :** exclusion nominative et générique.
- **Contrôle logiciel :** actif numérique refusé.
- **Preuve :** absence de transaction blockchain.
- **Conséquence :** paiement refusé.

## R468-016 — Aucun token interne
- **Processus :** crédit représentant la rémunération.
- **Risque :** paiement différé/converti.
- **Interdiction :** aucun token interne n'éteint la dette.
- **Contrôle juridique :** clause d'extinction monétaire stricte.
- **Contrôle logiciel :** aucun règlement par token.
- **Preuve :** grand livre.
- **Conséquence :** dette non éteinte tant que le paiement conforme n'est pas effectué.

## R468-017 — Aucun paiement par wallet
- **Processus :** enregistrement du bénéficiaire.
- **Risque :** accepter une adresse crypto.
- **Interdiction :** adresse blockchain non admissible.
- **Contrôle juridique :** moyen de paiement défini.
- **Contrôle logiciel :** IBAN/rail fiat autorisé.
- **Preuve :** preuve bancaire.
- **Conséquence :** bénéficiaire refusé.

## R468-018 — Aucun paiement indirect en crypto
- **Processus :** société → intermédiaire → crypto.
- **Risque :** contournement par interposition.
- **Interdiction :** aucun arrangement ayant cet effet économique.
- **Contrôle juridique :** clause anti-interposition.
- **Contrôle logiciel :** contrôle des bénéficiaires effectifs.
- **Preuve :** chaîne de paiement.
- **Conséquence :** incident de conformité.

## R468-019 — Aucun échange automatique de devise
- **Processus :** conversion EUR/USD avant règlement.
- **Risque :** rupture du same-currency.
- **Interdiction :** aucune conversion automatique dans le mécanisme de rémunération sans régime juridique distinct validé.
- **Contrôle juridique :** devise figée.
- **Contrôle logiciel :** devise de settlement verrouillée.
- **Preuve :** relevé et montant natif.
- **Conséquence :** paiement bloqué si devise différente.

## R468-020 — Aucun paiement en nature
- **Processus :** paiement par actif/service.
- **Risque :** substitut économique.
- **Interdiction :** aucun actif non monétaire ne remplace la rémunération.
- **Contrôle juridique :** règlement admissible défini.
- **Contrôle logiciel :** types de règlement limités.
- **Preuve :** pièce bancaire.
- **Conséquence :** obligation de paiement maintenue.

---

# 3. Substituts et contournements économiques

## R468-021 — Pas de warrant ARTCB
- **Processus :** attribution d'un droit futur.
- **Risque :** prévente différée.
- **Interdiction :** aucun warrant donnant accès à ARTCB.
- **Contrôle juridique :** inventaire des instruments.
- **Contrôle logiciel :** aucun registre de warrants ARTCB.
- **Preuve :** due diligence.
- **Conséquence :** instrument interdit.

## R468-022 — Pas d'option ARTCB
- **Processus :** droit d'achat futur privilégié.
- **Risque :** avantage économique caché.
- **Interdiction :** aucune option réservée à l'investisseur.
- **Contrôle juridique :** clause d'exclusion.
- **Contrôle logiciel :** aucun droit d'exercice.
- **Preuve :** registre des droits.
- **Conséquence :** revue juridique.

## R468-023 — Pas de conversion conditionnelle
- **Processus :** investissement convertible.
- **Risque :** conversion future en coins.
- **Interdiction :** aucun trigger ne convertit l'investissement en ARTCB.
- **Contrôle juridique :** analyse de chaque trigger.
- **Contrôle logiciel :** aucun trigger ARTCB.
- **Preuve :** tests de scénarios.
- **Conséquence :** scénario bloqué.

## R468-024 — Pas de bonus en coins
- **Processus :** bonus commercial/fidélité.
- **Risque :** allocation indirecte.
- **Interdiction :** aucun bonus ARTCB lié au financement.
- **Contrôle juridique :** catalogue fermé.
- **Contrôle logiciel :** aucune récompense investisseur en ARTCB.
- **Preuve :** registre des bonus.
- **Conséquence :** bonus annulé.

## R468-025 — Pas de remise de coins pour conseil
- **Processus :** investisseur/advisor apporte du conseil.
- **Risque :** advisory allocation cachée.
- **Interdiction :** aucune allocation ARTCB liée au statut d'investisseur.
- **Contrôle juridique :** contrats séparés et qualification indépendante.
- **Contrôle logiciel :** pas de rôle spécial.
- **Preuve :** registre services/paiements.
- **Conséquence :** revue indépendante.

## R468-026 — Pas de rémunération indexée sur ARTCB
- **Processus :** formule de quote-part.
- **Risque :** indexation indirecte.
- **Interdiction :** aucun multiplicateur/oracle ARTCB.
- **Contrôle juridique :** formule fermée.
- **Contrôle logiciel :** dépendances testées.
- **Preuve :** hash de formule/version.
- **Conséquence :** calcul rejeté.

## R468-027 — Pas de droit sur market cap
- **Processus :** rendement lié à la capitalisation.
- **Risque :** exposition à ARTCB.
- **Interdiction :** aucun rendement calculé sur la market cap ARTCB.
- **Contrôle juridique :** exclusion.
- **Contrôle logiciel :** aucun feed market cap.
- **Preuve :** audit des dépendances.
- **Conséquence :** blocage.

## R468-028 — Pas de droit sur quantité minée
- **Processus :** rémunération proportionnelle à la production de coins.
- **Risque :** droit indirect sur PoL.
- **Interdiction :** aucun pourcentage de coins minés comme rémunération.
- **Contrôle juridique :** exclusion.
- **Contrôle logiciel :** aucune variable de quantité PoL.
- **Preuve :** formule auditée.
- **Conséquence :** paiement non conforme.

## R468-029 — Pas de droit sur trésorerie crypto
- **Processus :** investisseur réclame une quote-part d'actifs numériques.
- **Risque :** exposition indirecte à ARTCB.
- **Interdiction :** aucun droit contractuel sur la trésorerie crypto du protocole.
- **Contrôle juridique :** périmètre des actifs exclus.
- **Contrôle logiciel :** wallets séparés.
- **Preuve :** inventaire mensuel.
- **Conséquence :** contestation et blocage.

## R468-030 — Pas de droit économique masqué
- **Processus :** instrument non nommé token.
- **Risque :** substance équivalente.
- **Interdiction :** tout mécanisme ayant pour effet économique de conférer un droit sur ARTCB est interdit.
- **Contrôle juridique :** analyse substance-over-form.
- **Contrôle logiciel :** cartographie des flux.
- **Preuve :** memo juridique + diagramme.
- **Conséquence :** instrument suspendu.

---

# 4. Périmètre de la rémunération

## R468-031 — Droit limité à l'activité financée
- **Processus :** base de rémunération.
- **Risque :** droit sur toute l'économie ARTCB.
- **Interdiction :** quote-part attachée à l'activité définie.
- **Contrôle juridique :** activité et base précisément définies.
- **Contrôle logiciel :** `revenue_source_id` obligatoire.
- **Preuve :** comptabilité analytique.
- **Conséquence :** revenus hors périmètre exclus.

## R468-032 — Brut/net explicitement défini
- **Processus :** calcul du pourcentage.
- **Risque :** conflit sur le montant.
- **Interdiction :** aucune formule ambiguë.
- **Contrôle juridique :** brut, coûts admissibles et net définis.
- **Contrôle logiciel :** formule versionnée.
- **Preuve :** calcul reproductible.
- **Conséquence :** paiement suspendu si données insuffisantes.

## R468-033 — Pas de pourcentage implicite de toute l'entreprise
- **Processus :** financement d'une activité spécifique.
- **Risque :** droit général sur les profits.
- **Interdiction :** périmètre fermé.
- **Contrôle juridique :** aucune formulation générale de participation.
- **Contrôle logiciel :** comptes analytiques dédiés.
- **Preuve :** mapping revenus→activité.
- **Conséquence :** ligne hors périmètre rejetée.

## R468-034 — Pas de droit automatique sur nouvelles activités
- **Processus :** lancement d'un nouveau service.
- **Risque :** extension automatique du droit.
- **Interdiction :** nouvelle activité exclue sans avenant validé.
- **Contrôle juridique :** liste fermée.
- **Contrôle logiciel :** nouveau `revenue_source_id` refusé par défaut.
- **Preuve :** journal des avenants.
- **Conséquence :** revenu exclu.

## R468-035 — Pas de droit automatique sur Artiste TV/protocole
- **Processus :** plusieurs flux économiques.
- **Risque :** confusion activité commerciale/monnaie.
- **Interdiction :** seul le flux contractuellement identifié est rémunérable.
- **Contrôle juridique :** périmètre Artiste TV précis.
- **Contrôle logiciel :** séparation des sources.
- **Preuve :** grand livre par activité.
- **Conséquence :** flux mal classé bloqué.

## R468-036 — Validation des frais déductibles
- **Processus :** calcul du revenu net.
- **Risque :** manipulation des coûts.
- **Interdiction :** seuls les coûts définis sont déductibles.
- **Contrôle juridique :** liste fermée.
- **Contrôle logiciel :** catégories autorisées.
- **Preuve :** factures/justificatifs.
- **Conséquence :** dépense non justifiée non déductible.

## R468-037 — Pas de frais fictifs
- **Processus :** diminution artificielle de la base.
- **Risque :** transfert de valeur vers une partie liée.
- **Interdiction :** dépenses sans substance/justificatif interdites.
- **Contrôle juridique :** parties liées et prix de marché.
- **Contrôle logiciel :** rapprochement factures/comptes.
- **Preuve :** audit tiers.
- **Conséquence :** retraitement comptable.

## R468-038 — Pas de transfert de revenus hors périmètre
- **Processus :** facturation par une autre entité.
- **Risque :** faire disparaître la base.
- **Interdiction :** pas de transfert artificiel réduisant la rémunération.
- **Contrôle juridique :** clauses anti-abus/parties liées.
- **Contrôle logiciel :** analyse des flux intersociétés.
- **Preuve :** factures + contrats + banques.
- **Conséquence :** retraitement/incident.

## R468-039 — Période de calcul déterminée
- **Processus :** calcul périodique.
- **Risque :** décalage artificiel de revenus.
- **Interdiction :** période définie et stable.
- **Contrôle juridique :** dates contractuelles.
- **Contrôle logiciel :** période immuable après clôture.
- **Preuve :** snapshot signé.
- **Conséquence :** réouverture uniquement selon procédure.

## R468-040 — Audit du calcul investisseur
- **Processus :** génération du montant.
- **Risque :** erreur/manipulation.
- **Interdiction :** aucun paiement sans calcul reproductible.
- **Contrôle juridique :** droit de vérification.
- **Contrôle logiciel :** fonction déterministe + journal.
- **Preuve :** hash du calcul et dataset source.
- **Conséquence :** paiement suspendu.

---

# 5. Contrats et structure juridique

## R468-041 — Contrat principal obligatoire
- **Processus :** entrée investisseur.
- **Risque :** engagement hors cadre.
- **Interdiction :** aucun financement sans contrat signé et versionné.
- **Contrôle juridique :** signature/capacité vérifiées.
- **Contrôle logiciel :** `contract_id` obligatoire.
- **Preuve :** document signé + hash.
- **Conséquence :** fonds non activés.

## R468-042 — Clause de séparation protocole/entreprise
- **Processus :** rédaction.
- **Risque :** confusion des droits.
- **Interdiction :** aucune formulation présentant l'investissement comme acquisition d'ARTCB.
- **Contrôle juridique :** clause dédiée.
- **Contrôle logiciel :** version documentaire contrôlée.
- **Preuve :** hash du contrat.
- **Conséquence :** version non approuvée interdite.

## R468-043 — Clause same-currency
- **Processus :** définition du paiement.
- **Risque :** substitution de devise/actif.
- **Interdiction :** paiement uniquement dans la devise d'investissement.
- **Contrôle juridique :** clause explicite.
- **Contrôle logiciel :** règle bloquante.
- **Preuve :** settlement record.
- **Conséquence :** paiement rejeté.

## R468-044 — Clause anti-crypto
- **Processus :** définition du règlement.
- **Risque :** crypto comme substitut.
- **Interdiction :** aucun crypto-actif ne satisfait la dette.
- **Contrôle juridique :** définition large et évolutive.
- **Contrôle logiciel :** type d'actif autorisé fermé.
- **Preuve :** audit du rail.
- **Conséquence :** obligation maintenue.

## R468-045 — Clause anti-contournement
- **Processus :** structuration.
- **Risque :** accord parallèle.
- **Interdiction :** interdiction de tout mécanisme ayant pour objet/effet de contourner les invariants.
- **Contrôle juridique :** clause à rédiger par conseil.
- **Contrôle logiciel :** cartographie parties/flux.
- **Preuve :** registre des conventions.
- **Conséquence :** incident + revue juridique.

## R468-046 — Clause parties liées
- **Processus :** opérations affiliées.
- **Risque :** transfert artificiel de revenus/droits.
- **Interdiction :** aucune opération liée non documentée.
- **Contrôle juridique :** groupe et bénéficiaire effectif définis.
- **Contrôle logiciel :** liste entités liées.
- **Preuve :** registre corporate.
- **Conséquence :** validation préalable.

## R468-047 — Aucun accord oral parallèle
- **Processus :** négociation.
- **Risque :** promesse non documentée d'ARTCB/rendement crypto.
- **Interdiction :** aucun droit hors documentation approuvée.
- **Contrôle juridique :** clause d'intégralité.
- **Contrôle logiciel :** CRM avec version de l'offre.
- **Preuve :** archivage selon droit applicable.
- **Conséquence :** offre non autorisée retirée.

## R468-048 — Avenant sous contrôle de version
- **Processus :** modification contractuelle.
- **Risque :** ajout d'un droit interdit.
- **Interdiction :** aucun avenant sans revue juridique.
- **Contrôle juridique :** double validation.
- **Contrôle logiciel :** version immuable après signature.
- **Preuve :** hash + signatures.
- **Conséquence :** avenant non validé non activé.

## R468-049 — Aucun droit de gouvernance monétaire caché
- **Processus :** actions/parts/pactes/votes.
- **Risque :** influence indirecte sur le protocole.
- **Interdiction :** aucun droit acquis par investissement ne permet de modifier les invariants monétaires.
- **Contrôle juridique :** analyse statuts/pactes.
- **Contrôle logiciel :** permissions séparées.
- **Preuve :** matrice gouvernance.
- **Conséquence :** droit non conforme non activé.

## R468-050 — Qualification réglementaire préalable
- **Processus :** avant sollicitation.
- **Risque :** régime réglementaire non anticipé.
- **Interdiction :** aucun lancement public avant qualification écrite.
- **Contrôle juridique :** memo France/UE + juridictions ciblées.
- **Contrôle logiciel :** statut `LEGAL_APPROVED` requis.
- **Preuve :** avis conseil compétent.
- **Conséquence :** lancement bloqué.

---

# 6. Banque, trésorerie et comptabilité

## R468-051 — Compte bancaire dédié ou traçabilité dédiée
- **Processus :** réception des fonds.
- **Risque :** mélange des flux.
- **Interdiction :** séparation ou traçabilité analytique renforcée obligatoire.
- **Contrôle juridique :** structure approuvée par conseil/comptable.
- **Contrôle logiciel :** mapping compte→activité.
- **Preuve :** relevés bancaires.
- **Conséquence :** rapprochement obligatoire.

## R468-052 — Aucun règlement investisseur depuis un wallet crypto
- **Processus :** décaissement.
- **Risque :** paiement indirect en crypto.
- **Interdiction :** paiement depuis un rail fiat autorisé.
- **Contrôle juridique :** moyen contractuel.
- **Contrôle logiciel :** source account allowlist.
- **Preuve :** transaction bancaire.
- **Conséquence :** paiement refusé.

## R468-053 — Rapprochement investissement bancaire
- **Processus :** comptabilisation entrée.
- **Risque :** montant/devise incorrects.
- **Interdiction :** aucun investissement non rapproché.
- **Contrôle juridique :** provenance selon KYC/AML applicable.
- **Contrôle logiciel :** reconciliation obligatoire.
- **Preuve :** bank statement + investment ID.
- **Conséquence :** statut non réglé.

## R468-054 — Rapprochement paiement sortant
- **Processus :** rémunération.
- **Risque :** paiement différent du montant autorisé.
- **Interdiction :** aucun paiement sans matching contrat/calcul/banque.
- **Contrôle juridique :** mandat de paiement.
- **Contrôle logiciel :** three-way match.
- **Preuve :** ordre bancaire + calcul + contrat.
- **Conséquence :** blocage.

## R468-055 — Pas de compensation croisée
- **Processus :** plusieurs dettes.
- **Risque :** masquer un règlement non conforme.
- **Interdiction :** pas de compensation avec crypto ou actif non autorisé.
- **Contrôle juridique :** clause de règlement.
- **Contrôle logiciel :** règles de netting.
- **Preuve :** journal de compensation.
- **Conséquence :** rejet si contournement.

## R468-056 — Comptabilité séparée du protocole
- **Processus :** enregistrement.
- **Risque :** confusion des actifs/droits.
- **Interdiction :** livres distincts ou axes analytiques incontestables.
- **Contrôle juridique :** périmètres définis.
- **Contrôle logiciel :** comptes analytiques dédiés.
- **Preuve :** balance + grand livre.
- **Conséquence :** correction comptable.

## R468-057 — Pas de nantissement ARTCB au profit investisseur
- **Processus :** garantie du financement.
- **Risque :** droit indirect sur les coins.
- **Interdiction :** principe de base = aucune sûreté sur ARTCB du protocole sans analyse juridique spécifique.
- **Contrôle juridique :** registre des sûretés.
- **Contrôle logiciel :** wallets non grevés.
- **Preuve :** certificat de situation.
- **Conséquence :** financement non approuvé.

## R468-058 — Pas de garantie de rendement ARTCB
- **Processus :** présentation du rendement.
- **Risque :** engagement indirect sur le token.
- **Interdiction :** aucune garantie basée sur la valeur ARTCB.
- **Contrôle juridique :** revue marketing.
- **Contrôle logiciel :** projections versionnées.
- **Preuve :** support approuvé.
- **Conséquence :** retrait.

## R468-059 — Réserve de liquidité investisseur en fiat
- **Processus :** provisionnement.
- **Risque :** obligation payée en crypto faute de fiat.
- **Interdiction :** obligations provisionnées selon cadre financier retenu.
- **Contrôle juridique :** politique de trésorerie.
- **Contrôle logiciel :** alerte de couverture.
- **Preuve :** état de trésorerie.
- **Conséquence :** alerte avant échéance.

## R468-060 — Audit comptable périodique
- **Processus :** clôture.
- **Risque :** dérive progressive.
- **Interdiction :** aucune période non auditée au-delà de la fréquence approuvée.
- **Contrôle juridique :** droit d'audit et conservation.
- **Contrôle logiciel :** calendrier.
- **Preuve :** rapport signé.
- **Conséquence :** blocage des nouvelles souscriptions si critique.

---

# 7. Logiciel, API, wallets et blockchain

## R468-061 — Fail-closed sur devise
- **Processus :** création paiement.
- **Risque :** erreur humaine.
- **Interdiction :** aucune transaction si devise sortie ≠ devise entrée.
- **Contrôle juridique :** règle contractuelle.
- **Contrôle logiciel :** assertion bloquante.
- **Preuve :** log d'erreur + test.
- **Conséquence :** aucune transaction.

## R468-062 — Fail-closed sur actif numérique
- **Processus :** choix du moyen de paiement.
- **Risque :** substitution crypto.
- **Interdiction :** toute destination blockchain refusée pour rémunération investisseur.
- **Contrôle juridique :** clause anti-crypto.
- **Contrôle logiciel :** validation du rail.
- **Preuve :** test négatif.
- **Conséquence :** rejet.

## R468-063 — Aucun endpoint de conversion
- **Processus :** API finance.
- **Risque :** conversion cachée.
- **Interdiction :** pas d'API permettant investissement→ARTCB.
- **Contrôle juridique :** inventaire des fonctions.
- **Contrôle logiciel :** route absente/inaccessible.
- **Preuve :** tests API.
- **Conséquence :** build non conforme.

## R468-064 — RBAC séparé
- **Processus :** accès financier/protocole.
- **Risque :** contrôle d'un wallet protocolaire.
- **Interdiction :** privilèges séparés.
- **Contrôle juridique :** gouvernance des accès.
- **Contrôle logiciel :** RBAC/ABAC.
- **Preuve :** export permissions.
- **Conséquence :** privilège révoqué + incident.

## R468-065 — Clés wallets protocolaires hors périmètre investisseur
- **Processus :** gestion cryptographique.
- **Risque :** accès économique indirect.
- **Interdiction :** aucune clé investisseur ne signe une opération monétaire privilégiée.
- **Contrôle juridique :** matrice signataires.
- **Contrôle logiciel :** multisig/HSM selon architecture.
- **Preuve :** audit clés/signatures.
- **Conséquence :** rotation + incident.

## R468-066 — Journal d'audit immuable
- **Processus :** opération financière.
- **Risque :** suppression de traces.
- **Interdiction :** aucune modification silencieuse.
- **Contrôle juridique :** conservation des preuves.
- **Contrôle logiciel :** append-only + hash.
- **Preuve :** journal signé.
- **Conséquence :** incident si rupture d'intégrité.

## R468-067 — Tests adversariaux
- **Processus :** avant production.
- **Risque :** angle mort non testé.
- **Interdiction :** aucune version financière sans scénarios de contournement.
- **Contrôle juridique :** validation des cas.
- **Contrôle logiciel :** tests négatifs obligatoires.
- **Preuve :** rapport de tests.
- **Conséquence :** déploiement bloqué.

## R468-068 — Liste noire d'actifs dynamique
- **Processus :** identification d'actifs numériques.
- **Risque :** nouveau stablecoin/token non prévu.
- **Interdiction :** contrôle fondé sur le rail/type, pas seulement ticker.
- **Contrôle juridique :** définition fonctionnelle.
- **Contrôle logiciel :** allowlist fiat.
- **Preuve :** tests actifs inconnus.
- **Conséquence :** fail-closed.

## R468-069 — Aucun oracle crypto dans le calcul investisseur
- **Processus :** calcul rendement.
- **Risque :** dépendance cachée au marché crypto.
- **Interdiction :** pas de prix ARTCB/BTC/ETH/etc. dans le calcul.
- **Contrôle juridique :** formule indépendante.
- **Contrôle logiciel :** dependency graph.
- **Preuve :** analyse statique.
- **Conséquence :** build non conforme.

## R468-070 — Reproductibilité du calcul
- **Processus :** génération redevance.
- **Risque :** montant invérifiable.
- **Interdiction :** résultat non reproductible interdit.
- **Contrôle juridique :** droit de vérification.
- **Contrôle logiciel :** calcul déterministe.
- **Preuve :** input/output hash + version.
- **Conséquence :** paiement suspendu.

---

# 8. Gouvernance, investisseurs et parties liées

## R468-071 — KYC/qualification investisseur avant entrée
- **Processus :** onboarding.
- **Risque :** non-conformité ou bénéficiaire inconnu.
- **Interdiction :** aucun financement accepté sans contrôles applicables.
- **Contrôle juridique :** KYC/AML selon juridiction.
- **Contrôle logiciel :** `KYC_APPROVED` requis.
- **Preuve :** dossier KYC selon conservation applicable.
- **Conséquence :** fonds non activés.

## R468-072 — Bénéficiaire effectif identifié
- **Processus :** investissement via société.
- **Risque :** véhicule opaque.
- **Interdiction :** UBO inconnu = droits non activés.
- **Contrôle juridique :** due diligence.
- **Contrôle logiciel :** UBO obligatoire.
- **Preuve :** dossier corporate.
- **Conséquence :** onboarding bloqué.

## R468-073 — Aucun transfert libre des droits sans contrôle
- **Processus :** cession des droits investisseur.
- **Risque :** tiers non qualifié.
- **Interdiction :** cession soumise aux restrictions contractuelles/réglementaires.
- **Contrôle juridique :** agrément si nécessaire.
- **Contrôle logiciel :** statut bénéficiaire.
- **Preuve :** acte de cession.
- **Conséquence :** cession non reconnue jusqu'à validation.

## R468-074 — Aucun changement de bénéficiaire bancaire non vérifié
- **Processus :** changement de compte.
- **Risque :** fraude/détournement.
- **Interdiction :** changement non vérifié interdit.
- **Contrôle juridique :** procédure de modification.
- **Contrôle logiciel :** double validation + délai de sécurité.
- **Preuve :** journal + justificatif.
- **Conséquence :** paiement suspendu.

## R468-075 — Séparation des pouvoirs
- **Processus :** validation/paiement.
- **Risque :** auto-approbation.
- **Interdiction :** maker/checker séparés.
- **Contrôle juridique :** gouvernance financière.
- **Contrôle logiciel :** RBAC + approbation multiple.
- **Preuve :** logs signatures.
- **Conséquence :** paiement rejeté sans quorum.

## R468-076 — Investisseur sans pouvoir de modification protocolaire
- **Processus :** gouvernance.
- **Risque :** capture du protocole.
- **Interdiction :** investissement sans capacité de modification monétaire.
- **Contrôle juridique :** pacte/statuts/protocole.
- **Contrôle logiciel :** permissions indépendantes.
- **Preuve :** test gouvernance.
- **Conséquence :** proposition bloquée.

## R468-077 — Interdiction des arrangements parallèles
- **Processus :** négociation individuelle.
- **Risque :** side letter donnant accès à ARTCB.
- **Interdiction :** aucune side letter contradictoire.
- **Contrôle juridique :** registre central.
- **Contrôle logiciel :** contrat maître requis.
- **Preuve :** audit documentaire.
- **Conséquence :** accord non approuvé exclu.

## R468-078 — Contrôle des promoteurs/intermédiaires
- **Processus :** levée via tiers.
- **Risque :** promesse commerciale non autorisée.
- **Interdiction :** intermédiaire ne peut promettre ARTCB/rendement crypto.
- **Contrôle juridique :** mandat + script approuvé.
- **Contrôle logiciel :** identifiant intermédiaire.
- **Preuve :** support/version.
- **Conséquence :** suspension du canal.

## R468-079 — Enregistrement des communications critiques
- **Processus :** présentation investisseurs.
- **Risque :** contradiction contrat/promesse.
- **Interdiction :** aucune communication non approuvée présentant un droit ARTCB.
- **Contrôle juridique :** compliance marketing.
- **Contrôle logiciel :** supports versionnés.
- **Preuve :** hash/date/version.
- **Conséquence :** retrait + incident.

## R468-080 — Droit d'audit et de vérification
- **Processus :** vie de l'investissement.
- **Risque :** flux invérifiables.
- **Interdiction :** aucun contrat sans mécanisme d'audit compatible avec le droit applicable.
- **Contrôle juridique :** clause d'audit/confidentialité/conservation.
- **Contrôle logiciel :** export du dossier de preuve.
- **Preuve :** audit trail complet.
- **Conséquence :** escalade contractuelle/réglementaire selon cas.

---

# 9. Contrôle de bout en bout

## R468-081 — Dossier de preuve par investisseur
- **Processus :** cycle complet.
- **Risque :** opération non reconstructible.
- **Interdiction :** dossier incomplet interdit.
- **Contrôle juridique :** checklist obligatoire.
- **Contrôle logiciel :** `evidence_bundle_status`.
- **Preuve :** contrat + KYC + banque + calcul + paiement.
- **Conséquence :** nouvelle opération bloquée.

## R468-082 — Hash documentaire
- **Processus :** contrats/annexes.
- **Risque :** modification post-validation.
- **Interdiction :** version non hashée non autorisée.
- **Contrôle juridique :** version signée.
- **Contrôle logiciel :** SHA-256 ou équivalent validé.
- **Preuve :** manifeste.
- **Conséquence :** document rejeté.

## R468-083 — Reconciliation blockchain ↔ comptabilité
- **Processus :** actifs ARTCB.
- **Risque :** transfert caché vers investisseur.
- **Interdiction :** allocation ARTCB uniquement selon règles du protocole, jamais selon investissement.
- **Contrôle juridique :** registre des droits.
- **Contrôle logiciel :** reconciliation wallets/ledger.
- **Preuve :** snapshot + hash.
- **Conséquence :** anomalie critique.

## R468-084 — Reconciliation banque ↔ comptabilité
- **Processus :** fiat.
- **Risque :** paiement hors livre.
- **Interdiction :** aucun flux non rapproché.
- **Contrôle juridique :** contrôle financier.
- **Contrôle logiciel :** rapprochement automatisé.
- **Preuve :** rapport.
- **Conséquence :** investigation.

## R468-085 — Reconciliation contrat ↔ paiement
- **Processus :** règlement.
- **Risque :** montant/devise incorrects.
- **Interdiction :** paiement uniquement si montant, devise, bénéficiaire et période correspondent.
- **Contrôle juridique :** obligation contractuelle.
- **Contrôle logiciel :** four-way match.
- **Preuve :** payment packet.
- **Conséquence :** rejet.

## R468-086 — Tests de scénarios de contournement
- **Processus :** audit périodique.
- **Risque :** protection obsolète.
- **Interdiction :** aucun changement majeur sans re-tests.
- **Contrôle juridique :** revue de changement.
- **Contrôle logiciel :** suite adversariale.
- **Preuve :** rapport signé.
- **Conséquence :** déploiement bloqué.

## R468-087 — Contrôle des forks et upgrades
- **Processus :** évolution protocole.
- **Risque :** nouvelle allocation investisseur.
- **Interdiction :** aucun upgrade ne modifie les invariants sans procédure dédiée.
- **Contrôle juridique :** impact assessment.
- **Contrôle logiciel :** CI avec tests R468.
- **Preuve :** release manifest.
- **Conséquence :** release bloquée.

## R468-088 — Contrôle des nouveaux actifs
- **Processus :** nouveau moyen de paiement.
- **Risque :** nouveau contournement.
- **Interdiction :** aucun actif accepté sans analyse juridique.
- **Contrôle juridique :** classification préalable.
- **Contrôle logiciel :** allowlist.
- **Preuve :** fiche d'intégration.
- **Conséquence :** actif refusé par défaut.

## R468-089 — Contrôle des nouvelles juridictions
- **Processus :** investisseur étranger.
- **Risque :** régime local différent.
- **Interdiction :** aucune sollicitation sans analyse juridictionnelle.
- **Contrôle juridique :** country memo.
- **Contrôle logiciel :** pays autorisés selon statut juridique.
- **Preuve :** validation conseil.
- **Conséquence :** onboarding bloqué.

## R468-090 — Revue annuelle complète
- **Processus :** gouvernance annuelle.
- **Risque :** dérive progressive.
- **Interdiction :** aucune reconduction sans revue.
- **Contrôle juridique :** revue annuelle.
- **Contrôle logiciel :** campagne de tests complète.
- **Preuve :** rapport annuel R468.
- **Conséquence :** plan correctif obligatoire.

---

# 10. Dossier de preuve minimal

Pour chaque investissement, l'audit doit pouvoir reconstruire :

```text
Investor_ID
→ KYC/UBO status
→ Contract_ID + contract_hash
→ Investment_ID
→ Investment_currency
→ Investment_amount
→ Bank_transaction_ID
→ Revenue_source_ID
→ Calculation_version
→ Calculation_input_hash
→ Calculation_output
→ Payment_currency
→ Payment_amount
→ Bank_payment_ID
→ Payment_status
→ Audit_log_hash
```

Aucun chemin ne doit permettre :

```text
Investment → ARTCB allocation
Investment → Crypto remuneration
Investment → ARTCB price/index → Investor return
```

---

# 11. Tests négatifs obligatoires avant lancement

Le système doit refuser au minimum :

1. EUR investi → paiement ARTCB.
2. EUR investi → paiement BTC.
3. EUR investi → paiement ETH.
4. EUR investi → paiement USDC.
5. EUR investi → paiement USDT.
6. USD investi → paiement EUR si le principe same-currency strict est retenu.
7. Investissement → allocation PoL.
8. Investissement → allocation HBP.
9. Investissement → pré-minage.
10. Investissement → option ARTCB.
11. Investissement → warrant ARTCB.
12. Investissement → conversion conditionnelle ARTCB.
13. Investissement → rendement indexé ARTCB.
14. Investissement → droit sur market cap ARTCB.
15. Investisseur → gouvernance monétaire privilégiée.
16. Investisseur → wallet protocolaire privilégié.
17. Société liée → paiement crypto à la place de la société.
18. Intermédiaire → promesse d'ARTCB.
19. Side letter → droit ARTCB.
20. Nouveau token inconnu → règlement investisseur.
21. Nouveau pays → onboarding sans country memo.
22. Changement de compte bancaire non vérifié.
23. Modification du pourcentage sans avenant signé.
24. Modification de devise après investissement.
25. Dépense fictive diminuant la base de rémunération.
26. Transfert artificiel de revenus vers une société liée.
27. Nouveau service automatiquement inclus.
28. Fork/upgrade introduisant une allocation investisseur.
29. Oracle ARTCB ajouté au moteur de calcul.
30. Paiement sans preuve bancaire.

Tous ces tests doivent être **FAIL-CLOSED** : l'opération interdite ne doit pas être exécutée.

---

# 12. Processus obligatoire avant ouverture de la levée

## A — Qualification juridique

Déterminer pour chaque juridiction ciblée : nature du financement, qualification des droits économiques, entité recevant les fonds, régime de l'offre, régime des services, obligations MiCA éventuelles, éventuelle qualification comme instrument financier, KYC/AML, restrictions de commercialisation, fiscalité, protection des investisseurs et règles de paiement/devises.

**Aucun lancement avant validation écrite.**

## B — Architecture contractuelle

Produire au minimum : contrat d'investissement ; définition de l'activité financée ; formule de rémunération ; clause same-currency ; clause anti-crypto ; clause anti-ARTCB ; clause anti-contournement ; clause parties liées ; gouvernance ; audit ; cession ; modification ; défaut ; annexes de calcul ; informations réglementaires applicables.

## C — Architecture comptable et bancaire

Séparer et tracer :

```text
FIAT INVESTISSEUR → ACTIVITÉ FINANCÉE → REVENUS FIAT → CALCUL → FIAT SAME-CURRENCY → INVESTISSEUR
```

et séparément :

```text
PROTOCOLE → PoL / HBP / règles → ARTCB
```

## D — Architecture logicielle

Chaque règle juridique critique doit avoir un équivalent technique :

```text
LEGAL RULE → POLICY → CODE → TEST NEGATIF → CI GATE → PRODUCTION
```

Une règle critique non testée techniquement reste **non garantie**.

## E — Audit adversarial final

Rechercher volontairement les contournements par société liée, intermédiaire, crypto, stablecoin, option/warrant, gouvernance, wallet, fork, side letter, changement de juridiction, changement de devise, nouvelle activité, comptabilité, logiciel et toute équivalence économique non apparente dans le contrat.

---

# 13. Points à faire valider par avocat — non décidés par R468

R468 fixe l'objectif économique et les garde-fous. Il ne décide pas à la place du conseil juridique :

1. forme exacte de l'investissement ;
2. entité qui reçoit les fonds ;
3. nature juridique de la quote-part de revenus ;
4. caractère réglementé éventuel de cette quote-part ;
5. structure éventuelle d'un SPV ;
6. pays où l'offre pourra être faite ;
7. fiscalité ;
8. KYC/AML précis ;
9. documentation obligatoire ;
10. mécanismes de sortie ;
11. restrictions de transfert ;
12. durée du droit économique ;
13. défaut ;
14. insolvabilité ;
15. protection des investisseurs ;
16. litiges ;
17. devise admissible selon marché ;
18. paiements transfrontaliers ;
19. qualification exacte d'ARTCB et des services ;
20. obligations MiCA ou autre régime financier applicable.

---

# 14. Règle de décision finale

Toute modification future n'est admissible que si elle :

```text
1. respecte l'idée initiale ;
2. ne donne aucun droit privilégié sur ARTCB ;
3. ne crée aucun droit indirect sur l'émission ;
4. conserve la séparation entreprise/protocole ;
5. conserve la séparation fiat/ARTCB ;
6. conserve le principe same-currency ;
7. interdit le règlement en crypto ;
8. est juridiquement validée ;
9. est techniquement testée ;
10. est auditée de bout en bout.
```

Toute proposition qui facilite la levée mais affaiblit un invariant est **NON CONFORME AU MODÈLE ARTCB**.

---

# 15. Conclusion opérationnelle

Le modèle à construire n'est pas une levée de fonds destinée à vendre ou pré-vendre ARTCB. Il s'agit d'un mécanisme de financement d'une activité économique déterminée, avec une rémunération financière séparée, tandis que la monnaie ARTCB reste gouvernée par les règles propres au protocole.

La séparation recherchée est :

```text
                  INVESTISSEUR
                       │
                 FIAT UNIQUEMENT
                       │
                       ▼
              ACTIVITÉ FINANCÉE
                       │
                  REVENUS FIAT
                       │
                       ▼
             RÉMUNÉRATION FIAT
             MÊME DEVISE D'ORIGINE
                       │
                       X
                       │
             aucun crypto-actif
             aucun ARTCB

                  PROTOCOLE ARTCB
                       │
              PoL / HBP / règles
                       │
                       ▼
                     ARTCB
```

**Objectif :** empêcher qu'un investissement financier dans l'activité économique soit transformé, directement ou indirectement, en droit sur la monnaie ARTCB.

**Niveau actuel :** cahier des charges conceptuel et de contrôle. La conformité juridique n'est pas certifiée. Une validation par avocat spécialisé en financement, crypto-actifs et droit des sociétés dans les juridictions ciblées est obligatoire avant toute offre.

---

## Historique et dépendances

- R468 est construit pour renforcer l'idée initiale et non la remplacer.
- Le HEAD audité est `5fd4fcad268b059b8eff4549fa56442ad4969944`, commit R466b du 2026-09-25.
- R466b indique 31/31 tests PASS pour son périmètre propre, mais cela **ne certifie pas R468**.
- R467 reste identifié dans le rapport R466b comme travail POS-guided à faire ; R468 ne le remplace pas et ne le clôt pas.

**CERTIFIED_100=false**
