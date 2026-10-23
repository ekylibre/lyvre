# Lyvre et les logiciels de gestion open source — recueil et synthèse

> Statut (23/10/2026, `/sc:brainstorm`) : **1** synthèse faite ; **2** besoins des écarts retenus dans
> `claudedocs/besoins_comparatif_oss.md` (à valider) ; **3** tableau « Lyvre et les autres logiciels
> open source » sur la page À propos (`frontend/src/features/about/openSourceVendors.ts`, Dolibarr retiré
> du premier tableau) ; **4** `doc/base_documentaire/README.md` complété (« Apports du comparatif »).
> Réponses au § 6 : Q1 fiabilité comptable + échéances réglementaires + vie associative et SCI ;
> Q2 Invoice Ninja dans le tableau open source avec mention de licence ; Q3 aucune des deux structures
> n'est assujettie à la TVA. Rapports détaillés par logiciel, avec sources (URL ou fichier:ligne) :
> [comparatif_oss/](comparatif_oss/). Code lu sans être exécuté (dépôts clonés, paquets PyPI).

## Demande

Fait un recueil des technos, fonctionnalités des solutions open source de gestion ci-dessous :
- Invoice Ninja : https://invoiceninja.github.io/docs/user-guide , https://api-docs.invoicing.co/ , https://github.com/invoiceninja/invoiceninja/tree/v5-develop , https://invoiceninja.com/
- Diacamma : https://diacamma.org/ et `~/Téléchargements/Diacamma_setup.tar.gz`
- enDI / CAERP : https://endi.coop/offre , https://doc.endi.coop/ , https://demo.endi.coop/admin , https://framagit.org/caerp/caerp
- Dokos : https://www.dokos.io/features/comptabilite , https://gitlab.com/dokos/dokos
- Frappe Books : https://frappe.io/books , https://github.com/frappe/books
- Tryton : https://www.tryton.org/ , https://docs.tryton.org/latest/ , https://foss.heptapod.net/tryton/tryton

1. Regarder les méthodes et données comptables, les fonctionnalités manquantes ou mieux gérées que dans
   Lyvre, et en faire une synthèse.
2. Reprendre chaque fonctionnalité intéressante selon la réponse au point 1 et proposer une spec.
3. Créer un tableau comparatif « Lyvre et les autres logiciels open source » et enlever les logiciels
   open source du premier tableau (« Lyvre et les autres logiciels »).
4. Mettre à jour le guide `doc/base_documentaire/README.md`.

## 1. Panorama

| Logiciel | Nature | Technologies | Licence | Compta en partie double | Plan associatif / SCI |
|---|---|---|---|---|---|
| **Lyvre** | Comptabilité asso / SCI | Python Flask, React + Mantine, SQLite | AGPL-3.0 | Oui, complète (clôture, FEC) | Oui / oui |
| **Invoice Ninja** v5 | Facturation, gestion commerciale | PHP Laravel, MySQL, React, Flutter | **Elastic License 2.0** (code visible, *non libre* au sens OSI) | Non (solde par client, export QuickBooks/CSV) | Non |
| **Diacamma** (Asso, Syndic, Financial) | Gestion associative + compta | Python, Django 5.2 (Lucterios), SQLite/MySQL/PostgreSQL, client web générique + PyQt | GPL-3.0 | Oui (brouillard, validation, lettrage), montants en `float` | Asso oui (PCG asso), pas SCI ; syndic de copropriété |
| **enDI / CAERP** | Gestion commerciale et RH de CAE | Python Pyramid, SQLAlchemy, MariaDB, Celery, Vue 3 | GPL-3.0 | Non : écritures exportées vers Sage, Cegid…, grand livre réimporté | Non |
| **Dokos** | ERP (fork français d'ERPNext) | Python Frappe/Dodock, MariaDB, Redis | GPL-3.0 | Oui, très complète | PCG 2025 seulement (module non-profit retiré) |
| **Frappe Books** | Compta TPE de bureau | Electron, Vue, SQLite (knex) | AGPL-3.0 | Minimale (ni clôture, ni FEC, ni banque) | Non — **dépôt archivé le 02/10/2026** |
| **Tryton** 8.2 | ERP modulaire (~200 modules) | Python, ORM maison, PostgreSQL (SQLite possible), clients GTK et web | GPL-3.0 | Oui, très complète | PCG ancien (classe 77), ni asso ni SCI |

**Constat** : aucun des six ne couvre à la fois la comptabilité associative française (ANC 2018-06,
fonds dédiés, 86/87, Cerfa), la SCI et la banque moderne (Qonto, rapprochement assisté). Les ERP
(Tryton, Dokos) sont plus riches sur la **comptabilité générale « entreprise »** ; Diacamma sur la
**vie associative** et les **règlements** ; Invoice Ninja et enDI sur la **chaîne de vente / achat**.

## 2. Méthodes et données comptables comparées

| Sujet | Lyvre aujourd'hui | Ce que font les autres |
|---|---|---|
| **Intangibilité** | Écriture modifiable jusqu'à la clôture provisoire, qui numérote (`validation_number`) ; exercice clos figé | Diacamma, Tryton, Dokos : **brouillard → validée** écriture par écriture (numéro à la validation), correction **par contrepassation uniquement** ; Dokos ajoute l'**amendement** (`amended_from`) et l'historique des modifications ; enDI et Tryton **scellent le PDF** de facture (hash, révisions) |
| **Périodes** | Exercice ouvert / provisoire / clos | Tryton : périodes mensuelles `open → closed → locked` ; Dokos : verrou des périodes **déclarées en TVA** |
| **Lettrage des tiers** | Factures d'achat / vente reliées à leurs règlements (statut payé), pas de lettrage des comptes 411 / 401 / 467 | Diacamma, Tryton, Dokos : lettrage avec proposition automatique, écart en perte / profit, délettrage, **inter-exercices** (Diacamma) ; base de la **balance âgée** et du **relevé de compte** |
| **TVA** | `vat_liable` par exercice ; TVA des prestations exigible à l'encaissement (ventes) | Tryton : ~113 **codes de taxe calqués sur les cases de la CA3** + rapport par période, TVA sur encaissements au prorata ; Dokos : **CA3/CA12 préparée + EDI-TVA** |
| **Régularisations** | Écritures d'inventaire 486/487 à la clôture, avec extourne | Tryton, Dokos : **dates de service sur la ligne de facture** → étalement automatique par période |
| **Immobilisations** | Comptes présents, aucun suivi | Tryton (linéaire, créée depuis la facture, révisions, cession), Dokos (linéaire, dégressif, prorata, composants) |
| **Analytique** | 1 axe « projets », ventilation manuelle d'une ligne | Tryton, Dokos : **plusieurs axes**, comptes **répartiteurs en %**, **règles d'affectation**, axe **obligatoire** par compte ; Diacamma : 1 axe, obligatoire, grand livre et balance par code |
| **Budget** | Annuel / mensuel, copie N-1, suivi prévu / réalisé | Dokos : **contrôle à la saisie** (alerte / blocage) ; Tryton : copie avec coefficient |
| **Banque** | OFX, Qonto, rapprochement assisté, règles de catégorisation | Tryton : **CAMT.053/054**, MT940, règles par **expression régulière à groupes nommés** (tiers, facture, référence de paiement) ; Invoice Ninja : règles qui **comptabilisent seules** ; Diacamma : **aucun** rapprochement |
| **Encaissements** | Virement / chèque / espèces saisis ou rapprochés ; HelloAsso, Stancer importés | Diacamma, enDI, Dokos : **remises de chèques** (bordereau, 511) ; Tryton, Dokos, Invoice Ninja : **prélèvement SEPA** avec mandats, **paiement en ligne** qui crée le règlement |
| **Facture électronique** | Factur-X produit (ventes) et lu (achats) ; émission possible via Qonto | Diacamma, enDI : **connecteur PDP** (API AFNOR, annuaire, statuts de cycle de vie, réception) ; Invoice Ninja : **PEPPOL** (Storecove) ; Tryton : **Chorus Pro** |
| **Reprise de données** | Imports OFX, CSV Odoo, temps de travaux, associés | Dokos : **import FEC** ; Diacamma : import d'écritures tableur ; Frappe Books : import CSV générique |

## 3. Écarts consolidés

Lecture : **Qui** = logiciels qui le font (IN Invoice Ninja, DI Diacamma, EN enDI, DO Dokos, FB Frappe
Books, TR Tryton). **Intérêt** = estimation pour la cible (associations, SCI) : ★★★ fort, ★★ moyen, ★ faible.
Les identifiants **E1…E49** servent à répondre au § 6.

### 3.1 Comptabilité générale

| # | Écart | Qui | Intérêt | Pourquoi |
|---|---|---|---|---|
| E1 | **Lettrage** des comptes de tiers (411, 401, 467, 455), proposition automatique, écart en perte / profit, délettrage, lettrage inter-exercices | DI, DO, TR | ★★★ | Impayés lus dans la compta (loyers, cotisations, subventions à recevoir) ; préalable à E21, E22 et à des reçus fondés sur les dons encaissés |
| E2 | **Validation des écritures** une à une (brouillard → validée, numéro définitif), correction par contrepassation seulement ; **historique des modifications** | DI, DO, TR, EN | ★★★ | Exigence d'intangibilité (expert-comptable, commissaire aux comptes, financeurs publics) ; aujourd'hui seule la clôture fige |
| E3 | **Verrouillage de périodes** (mois rapprochés, période de TVA déclarée) | TR, DO | ★★ | Le trésorier ne modifie plus un mois transmis ou déclaré |
| E4 | **Écritures modèles / récurrentes** (quote-part de charges, intérêts d'emprunt SCI) | DI, TR | ★★ | Saisie en un clic des écritures répétitives |
| E5 | **Import d'écritures** (tableur, **FEC**) pour reprendre un historique | DO, DI, FB | ★★ | Cible = d'autres associations, qui arrivent avec un historique |
| E6 | **Outils d'intégrité du grand livre** (déséquilibres, recalcul) | DO | ★ | Diagnostic avant clôture (en partie couvert par les contrôles de l'assistant) |

### 3.2 TVA, immobilisations, régularisations

| # | Écart | Qui | Intérêt | Pourquoi |
|---|---|---|---|---|
| E7 | **Déclaration de TVA préparée** (cases de la CA3 / CA12 depuis la compta), éventuellement EDI-TVA | TR, DO | ★★ | SCI optant pour la TVA, associations à activités lucratives |
| E8 | **Immobilisations et amortissements** (création depuis la facture d'achat, tableau, cession ; composants pour l'immeuble de SCI) | TR, DO | ★★★ | Déjà listé dans les limites de Lyvre ; obligatoire dès qu'il y a du matériel ou un immeuble |
| E9 | **Charges / produits constatés d'avance depuis la ligne de facture** (dates de service, étalement automatique) | TR, DO | ★★ | Assurances, abonnements, cotisations à cheval sur deux exercices, sans saisie à la clôture |

### 3.3 Analytique, budget, pilotage

| # | Écart | Qui | Intérêt | Pourquoi |
|---|---|---|---|---|
| E10 | **Analytique multi-axes** (projet × financeur × site), **répartiteurs en %**, **règles d'affectation**, axe **obligatoire** par compte | TR, DO, DI | ★★ | Comptes rendus par financeur (Cerfa 15059), répartition des frais de structure |
| E11 | **Contrôle budgétaire à la saisie** (alerte ou blocage au-delà de l'enveloppe) | DO | ★ | Respect des enveloppes de subvention |
| E12 | **Prévisionnel par scénarios** (pessimiste : subvention en retard) | DO | ★ | Affinage du prévisionnel 12 mois existant |
| E13 | **États paramétrables** par préfixes (SIG, tableaux pour le CA) sans développement | EN | ★ | Rejoint les états YAML prévus dans `doc/base_documentaire/` |

### 3.4 Banque et encaissements

| # | Écart | Qui | Intérêt | Pourquoi |
|---|---|---|---|---|
| E14 | **Remises de chèques** : bordereau imprimable, compte 511, une ligne de banque = une remise | DI, EN, DO | ★★★ | Cotisations, dons, chèques-vacances : cas massif en association ; rapprochement simplifié |
| E15 | **Import CAMT.053/054** (et MT940) | TR | ★★ | Toutes les banques, au-delà d'OFX et Qonto |
| E16 | **Règles de rapprochement avancées** : expression régulière à groupes nommés, **référence de paiement structurée** sur facture / avis d'échéance, règles qui comptabilisent **sans validation** | TR, IN | ★★ | Loyers, versements HelloAsso et frais bancaires traités seuls |
| E17 | **Frais du prestataire imputés au règlement**, petit écart passé en perte | DI, FB | ★ | Commissions Stripe / Stancer / HelloAsso sans saisie |
| E18 | **Prélèvement SEPA** : mandats (RUM, CORE/B2B, PDF), fichier pain.008, rejets | TR, DO, IN | ★★ | Loyers et cotisations mensuels sans HelloAsso ni Qonto |
| E19 | **Virements SEPA groupés** (pain.001) pour fournisseurs et notes de frais | TR, EN, DO | ★★ | Paiement en lot avec n'importe quelle banque |
| E20 | **Paiement en ligne natif** (lien « payer » dans le courriel, règlement créé au retour du prestataire) | DI, IN, DO, TR | ★★ | Factures, loyers, cotisations payés par carte |

### 3.5 Ventes, relances, facture électronique

| # | Écart | Qui | Intérêt | Pourquoi |
|---|---|---|---|---|
| E21 | **Relances automatiques à niveaux** (J+N, courriel / lettre, frais et pénalités, blocage en cas de litige) | IN, TR, DO | ★★ | Aujourd'hui relances manuelles (choix V5 du lot ventes) |
| E22 | **Balance âgée** et **relevé de compte** client / locataire, envoi planifié | IN, DO | ★★ | Suivi des impayés d'un coup d'œil (suppose E1) |
| E23 | **Factures d'acompte** et échéancier depuis le devis, compte 4191 | EN, TR, IN | ★★ | Arrhes, locations de salle, séjours ; écarté du 1er lot ventes (V12) |
| E24 | **Avoirs et trop-perçus réutilisables**, **dépôts de garantie** | IN, TR | ★ | Trop-perçus imputés plus tard ; dépôt de garantie des locataires (165) |
| E25 | **Récurrentes envoyées automatiquement**, abonnements riches (prorata, calendrier complexe) | IN, TR, DO | ★ | Contraire au choix V15 (brouillons à valider) — à confirmer |
| E26 | **Devis acceptés / signés en ligne** | IN | ★ | Suppose un espace client (E36) |
| E27 | **Numérotation par gabarit**, séries par activité | EN, IN, DI | ★ | Séries distinctes (locations, formations, buvette) |
| E28 | **Tarifs par catégorie** (adhérent / non-adhérent / famille), remises automatiques | DI | ★ | Tarification sociale des clubs |
| E29 | **Raccordement à une plateforme agréée (PDP)** : réception des factures fournisseurs, émission, statuts de cycle de vie, annuaire | DI, EN, IN (PEPPOL) | ★★★ | Réception obligatoire depuis le 01/09/2026 pour les structures assujetties à la TVA ; Lyvre produit et lit le Factur-X mais ne dialogue avec aucune plateforme |
| E30 | **Chorus Pro** (facturation des collectivités) | TR | ★ | Associations qui facturent des collectivités |
| E31 | **Boîte courriel entrante** pour les factures fournisseurs (lecture Factur-X / OCR) | IN | ★★ | Le bénévole transfère la facture au lieu de la déposer |

### 3.6 Achats et frais

| # | Écart | Qui | Intérêt | Pourquoi |
|---|---|---|---|---|
| E32 | **Notes de frais** : frais réels, **indemnités kilométriques au barème**, justificatifs, remboursement ; **abandon de frais converti en don** (reçu fiscal) | EN, DI | ★★★ | Cas très courant chez les bénévoles ; l'abandon de frais est un don à part entière |
| E33 | **Cycle de validation** des pièces (brouillon → en attente → validée, historique) et **pièces obligatoires** | EN | ★★ | Double contrôle trésorier / président, justificatifs exigés par les financeurs |
| E34 | **Bons de commande** / engagements de dépense | EN, IN | ★ | Suivi budgétaire en amont de la facture |

### 3.7 Vie associative et SCI

| # | Écart | Qui | Intérêt | Pourquoi |
|---|---|---|---|---|
| E35 | **Adhésions natives** sans HelloAsso : saisons, types de cotisation, activités, licences fédérales, familles, renouvellement en masse, cotisation → facture → règlement | DI | ★★ | Clubs et associations qui n'utilisent pas HelloAsso (cible élargie) |
| E36 | **Espace adhérent / locataire / client** : documents, relevé, paiement | DI, IN | ★★ | Moins de demandes au trésorier ; quittances en libre-service |
| E37 | **Reçus fiscaux limités aux dons encaissés** (lettrés), **abandon de revenus**, **duplicata** à la réédition | DI | ★★ | Lyvre fige déjà les PDF ; ici la garantie vient du lettrage (E1) |
| E38 | **Événements / stages** facturés aux participants | DI | ★ | Stages, sorties |
| E39 | **Publipostage** courriel / courrier / SMS, suivi d'ouverture | DI, IN | ★ | Convocations d'AG |
| E40 | **Statistiques adhérents** (ville, âge, ancienneté) | DI | ★ | Demandes des mairies et fédérations |
| E41 | **Charges récupérables** : provisions sur charges et **régularisation annuelle** par locataire (logique tantièmes du syndic) | DI | ★★ | SCI : régularisation des charges locatives des baux |
| E42 | **Plan d'apurement** (rééchelonnement d'une dette), compensation client / fournisseur | TR | ★ | Loyers impayés |

### 3.8 Plateforme

| # | Écart | Qui | Intérêt | Pourquoi |
|---|---|---|---|---|
| E43 | **API publique documentée** et **webhooks** | IN | ★ | Brancher site, CRM, n8n |
| E44 | **Champs personnalisés**, **import CSV générique**, **éditeur de modèles d'impression** | FB, DI | ★ | Adapter sans développer |
| E45 | **Permissions fines** (responsable d'activité qui ne voit que ses pièces) | IN, EN | ★ | Au-delà des 3 rôles actuels |
| E46 | **Consolidation** de plusieurs structures | TR | ★ | Fédération et antennes, SCI familiales |
| E47 | **Synchronisation avec le cabinet** (MyUnisoft), **journal des exports** | DO, EN | ★ | Le FEC couvre déjà l'expert-comptable |
| E48 | **Caisse de point de vente** (ouverture / fermeture, comptage), **stock** | FB, DI, IN | ★ | Aujourd'hui via Odoo POS |
| E49 | **Multidevise** et réévaluation | IN, TR, DO | ★ | Rare (solidarité internationale) |

## 4. Où Lyvre est en avance

- **Comptabilité associative** : plan ANC 2018-06, contributions volontaires (86/87) et bénévolat
  valorisé, fonds dédiés liés aux projets, assistant de clôture associatif (contrôles, inventaire avec
  extourne, résultat, provisoire / définitive, à-nouveaux, affectation), reçus Cerfa 11580 / 16216.
  Aucun des six ne réunit tout cela ; Tryton et Dokos n'ont même pas le plan associatif.
- **SCI** : plan SCI, registre des parts, comptes courants d'associés, baux et quittances.
- **Banque** : synchronisation Qonto, rapprochement au clavier avec suggestions (Diacamma n'a aucun
  rapprochement), factures d'achat lues (Factur-X, OCR).
- **Simplicité** : mode recettes / dépenses avec passage en partie double sans ressaisie ; SQLite ;
  interface pensée pour des trésoriers bénévoles (Tryton et Dokos demandent un comptable formé).
- **Pilotage** : prévisionnel 12 mois, budget, impact, rapport d'activité.
- **Déjà fait, contrairement à ce qu'on pouvait croire** : TVA des prestations à l'encaissement,
  un virement réglant plusieurs factures, comptes 401 et 411 propres à chaque tiers, PDF de reçus figés.

## 5. Lecture d'ensemble

Trois familles se dégagent :

1. **Fiabilité comptable** (attendue par l'expert-comptable et indispensable pour diffuser Lyvre à
   d'autres associations) : E1 lettrage, E2 validation / intangibilité, E3 verrouillage, E8
   immobilisations, E9 régularisations depuis la facture, E5 import d'historique.
2. **Encaissements associatifs** (le quotidien du trésorier) : E14 remises de chèques, E32 notes de
   frais et abandon de frais, E18 / E20 prélèvement et paiement en ligne, E21 / E22 relances et
   balance âgée.
3. **Échéances réglementaires** : E29 plateforme agréée (réception déjà obligatoire pour les
   assujettis), E7 TVA, E30 Chorus Pro.

Le reste (vie associative native, espace adhérent, multi-axes, plateforme) dépend du **public visé** :
Seconde Nature et la SCI aujourd'hui, ou d'autres associations demain.

## 6. Questions ouvertes (à trancher avant le point 2)

| # | Question |
|---|---|
| Q1 | Quels écarts retenir pour les specs du point 2 ? (liste d'identifiants E…, ou une famille du § 5) |
| Q2 | Invoice Ninja n'est pas un logiciel libre (Elastic License 2.0) : le mettre dans le tableau « open source » avec cette mention, ou dans le premier tableau ? Frappe Books (archivé) : le garder ? |
| Q3 | Plateforme agréée (E29) : Seconde Nature et la SCI sont-elles assujetties à la TVA, donc concernées dès maintenant ? Qonto, déjà intégré, peut-il servir de plateforme de réception ? |
| Q4 | Vie associative native (E35, E36) : la cible « autres associations » justifie-t-elle de ne plus dépendre de HelloAsso pour les adhésions ? |
| Q5 | Récurrentes envoyées automatiquement (E25) : revenir sur le choix V15 (brouillons à valider) ? |
