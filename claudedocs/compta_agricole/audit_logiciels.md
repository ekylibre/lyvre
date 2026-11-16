# Audit concurrentiel : logiciels de comptabilité agricole en France

Date : 3 novembre 2026. Préparé pour l'ajout de la comptabilité agricole à Lyvre.

Méthode : lecture des pages données par l'utilisateur (WebFetch), lecture du dépôt GitHub de Gleba (README, arborescence et extraits de code via `gh api`), puis recherches web. Les pages des éditeurs sont promotionnelles. Quand une fonction n'apparaît dans aucune source, le rapport indique « non documenté » : cela ne prouve pas qu'elle manque.

Source inaccessible : https://www.lafabriquedunet.fr/logiciels/gestion/comptabilite/comptabilite-agriculture a répondu HTTP 403. Je n'ai que ses extraits dans les résultats de recherche : Isacompta y est donné comme la référence, vendu sur devis, et Ekylibre comme gratuit en auto-hébergement, à condition d'avoir un peu d'aisance technique.

Rappel sur les liasses (BOFiP et impots.gouv) :
- 2139 : réel simplifié.
- 2143 à 2154 : réel normal.
- 2342 : déclaration de l'ancien forfait agricole, remplacé par le micro-BA. Au micro-BA, les recettes se reportent sur la 2042 C PRO. La 2342 ne sert plus que dans des cas résiduels, par exemple les bois au forfait.

Sources : https://bofip.impots.gouv.fr/export/pdf/4527, https://www.impots.gouv.fr/sites/default/files/formulaires/2143-sd/2026/2143-sd_5402.pdf

---

## 1. Fiches par logiciel

### 1.1 Isacompta (ISAGRI), et Agiris pour les cabinets
- **Éditeur** : groupe ISAGRI (Beauvais). AGIRIS, du même groupe, vend la version destinée aux experts-comptables (ISACOMPTA Connect et « Modules agricoles »).
- **Cible** : toutes les exploitations, surtout la polyculture-élevage, ainsi que les ETA, les centres de gestion et les AFOCG. ISAGRI annonce 35 000 entreprises utilisatrices.
- **Prix** : ISACOMPTA LIVE (cloud) à partir de 35 €/mois avec contrat de services. Les autres formules sont sur devis.
- **Licence** : propriétaire.
- **Fonctionnalités documentées** :
  - comptabilité générale et analytique, plan agricole ;
  - collecte automatique des relevés bancaires, fichiers de virement et lettres-chèques ;
  - assistant de déclaration de TVA agricole ;
  - immobilisations, emprunts, trésorerie, budget prévisionnel ;
  - marges et rentabilité par activité, coûts de production par catégorie, tableaux de bord ;
  - liasse fiscale agricole ;
  - module stocks (option) ;
  - FEC, facture électronique (plateforme agréée), multi-utilisateurs ;
  - AMICOMPTA : lecture des factures fournisseurs par IA, puis synchronisation vers ISACOMPTA ;
  - ISAFACT (facturation) et ISAETA (ETA) passent leurs écritures directement dans ISACOMPTA.
- **Côté cabinet (Agiris, « Modules agricoles »)** :
  - dossier de gestion technico-économique, bilan projeté agricole ;
  - marges brutes par production et marges nettes ;
  - gestion des DPA/DPI/DEP, abattement JA, option 75-0 B (moyenne triennale), dossier Jeunes Agriculteurs ;
  - module Stocks : valorisation automatique par barèmes, import des inventaires animaux, décote, prix de revient viticole par appellation ;
  - SOFI BA : assistant au remplissage de la liasse, plus-values, simulations d'optimisation fiscale, répartition du résultat entre associés, module MSA (cotisations et points de retraite).
- **Non documenté** : avances aux cultures côté exploitant, application mobile, échéancier des démarches.
- **Sources** : https://www.isagri.fr/logiciels/isacompta-logiciel-de-comptabilite-agricole, https://www.isagri.fr/ressources/articles/temoignage-amicompta-exploitation-agricole, https://www.agiris.fr/hubfs/agiris/logiciels/modules-agricoles.pdf, https://www.capterra.fr/software/1034804/isacompta (un seul avis : 4/5, « complexe pour les novices »), https://www.comptabilite-agriculteur.fr/quel-logiciel-comptable-choisir-pour-gerer-son-exploitation-agricole/

### 1.2 ISTEA (réseaux CER France et AFOCG)
- **Éditeur** : non trouvé.
- **Usage** : outil de saisie utilisé dans les formations CER France et AFOCG pour l'autocomptabilité accompagnée. L'AFOCG Atlantique, elle, utilise Isacompta.
- **Prix** : licence non publique. Les formations coûtent par exemple 196 € HT la journée chez CER France Poitou-Charentes, sans financement VIVEA. L'AFOCG PACA propose un cycle de 4 journées en première année, en groupes de 6 à 8 personnes.
- **Fonctionnalités documentées** :
  - paramétrage du dossier, journal de saisie, filtres d'analyse ;
  - lettrage des clients et fournisseurs ;
  - bilan d'ouverture ;
  - télédéclaration de la TVA.
- **Non documenté** : version web, stocks, analytique, liasse.
- **Ce qui différencie ce modèle** : le logiciel est couplé à une formation de groupe. L'agriculteur saisit lui-même et l'association l'accompagne.
- **Sources** : https://poitoucharentes.cerfrance.fr/wp-content/uploads/2025/01/utilisation_logiciel_istea.pdf, https://www.agriculturepaysanne.org/formations/detail.php?id=9745, https://jobs.makesense.org/fr/jobs/afocg-paca-formateurice-animateurice-comptabilite-gestion-agricole-3lVLIWH0SS6NEMH3Bj8b

### 1.3 Pennylane (offre agricole pour cabinets)
- **Cible** : les cabinets d'expertise-comptable, pas les exploitants en direct. L'offre est co-construite avec des cabinets comme COGEDIS. Le cabinet CPA (audit-cpa) l'utilise pour ses clients agriculteurs.
- **Calendrier** : annonce en septembre 2025, « fondations agricoles » livrées le 3 février 2026, écosystème annoncé pour fin 2026.
- **Prix** : non publié pour l'agricole. **Licence** : propriétaire.
- **Fonctionnalités documentées** :
  - plan comptable pour l'agriculture conforme aux règlements ANC 2020-04 et 2022-06, bascule du PCG en un clic ;
  - états financiers au format agricole ;
  - TVA des exploitants au bénéfice agricole sur les encaissements : CA3, 3525 bis (acomptes trimestriels), CA12A/3517-AGR pré-remplie, 3517 DDR (remboursement de crédit) ;
  - liasse 2139 et liasses 2143 à 2154 en partie pré-remplies, avec télédéclaration ;
  - banque, facturation et e-facture : socle Pennylane standard.
- **Annoncé (pas encore livré)** : gestion des quantités, sections agricoles du dossier permanent, stocks, suivi des options fiscales.
- **Non documenté** : avances aux cultures, DEP, analytique par atelier.
- **« PAC » chez Pennylane** : c'est le Pennylane Agri Club, une communauté avec newsletter, pas une fonction de gestion des aides.
- **Sources** : https://www.pennylane.com/fr/blog/produit/lancement-agricole, https://www.pennylane.com/fr/blog/produit/comptabilit%C3%A9-agricole-fondations, https://hello.audit-cpa.com/secteur/agriculture/

### 1.4 Ekylibre
- **Éditeur** : Ekylibre SAS (Pessac), depuis 2008.
- **Cible** : exploitations de grandes cultures, viticulture, élevage et arboriculture. Variantes Ekyagri et Ekyviti, centrées sur la viticulture et l'arboriculture selon comptabilite-agriculteur.fr.
- **Prix** : non publié. La vente passe par une démo et un contact commercial, et la société vit des services (intégration, formation, connecteurs). L'auto-hébergement est gratuit.
- **Licence** : AGPL-3.0, code sur https://github.com/ekylibre/ekylibre (493 étoiles, activité en octobre 2026).
- **Modèles présents dans le code** :
  - Account, Journal, JournalEntry, FinancialYear (archives et échanges avec le cabinet) ;
  - BankStatement (rapprochement) ;
  - TaxDeclaration (TVA) ;
  - FixedAsset et FixedAssetDepreciation ;
  - Loan ;
  - Inventory (inventaires de stocks) ;
  - ActivityBudget (budgets par activité) ;
  - Crop et Animal ;
  - codes de production PAC ;
  - indicateurs économiques de trésorerie.
- **Fonctionnalités documentées** :
  - les écritures sont générées à partir des interventions au champ ;
  - relevés bancaires récupérés automatiquement ;
  - analytique par activité ;
  - stocks et traçabilité.
- **Assistants** : Duke, assistant vocal prototypé en 2018-2020 (base Mycroft), et Aiffel, assistant vocal ou écrit qui saisit après validation.
- **Non documenté** : liasse 2139 (le cabinet la produit à partir des exports), échéancier des démarches.
- **Lien avec Lyvre** : la mémoire projet mentionne déjà une reprise de données depuis Ekylibre (SCI et SAS).
- **Sources** : https://ekylibre.com/, https://www.reussir.fr/vigne/duke-le-hibou-lassistant-vocal-qui-simplifie-la-gestion-des-vignes, https://www.comptabilite-agriculteur.fr/quel-logiciel-comptable-choisir-pour-gerer-son-exploitation-agricole/

### 1.5 Ouvretaferme
- **Éditeur** : projet associatif (asso.ouvretaferme.org). Communauté optionnelle opérée par la FRAB AuRA.
- **Cible** : maraîchage et circuits courts, petites fermes, micro-BA et réel.
- **Licence** : AGPL-3.0 (dépôt https://github.com/ouvretaferme/ouvretaferme-public).
- **Prix** (« tout est gratuit jusqu'au 15 novembre ») :
  - Essentiel : gratuit ;
  - Gestion : 10 € HT/mois, comprend la comptabilité ;
  - Pilotage : 25 € HT/mois ;
  - Intégrale : 30 € HT/mois ;
  - Communauté FRAB : 9 € HT/mois.
- **Fonctionnalités comptables** (https://www.ouvretaferme.org/fonctionnalite/comptabilite-gestion) :
  - écritures générées automatiquement depuis les ventes, les factures électroniques et les cahiers de caisse, saisie manuelle possible ;
  - plan comptable agricole avec proposition de compte pour les factures reçues ;
  - rapprochement bancaire ;
  - déclaration CA3 ou CA12 selon les paramètres ;
  - immobilisations et plans d'amortissement ;
  - bilans d'ouverture et de clôture, compte de résultat, SIG, balance, journal, grand livre ;
  - indicateurs mois par mois (CA, SIG, trésorerie) ;
  - tenue en trésorerie ou en engagement ;
  - import des FEC antérieurs avec correspondance des comptes, ou import fait par l'équipe ;
  - export FEC et archives légales ;
  - mode « optimisé micro-BA », présenté comme « conforme pour la DJA » ;
  - côté gestion : stocks, caisse, boutiques, facturation électronique, plan de culture.
- **Annoncé pour fin 2026 ou 2027** : plusieurs fonctions comptables.
- **Non documenté** : liasse, analytique par culture, valorisation des stocks en comptabilité, assistant.
- **Contenu pédagogique** : la base d'articles est riche, voir la section 4.
- **Sources** : https://www.ouvretaferme.org/, https://www.ouvretaferme.org/presentation/offres

### 1.6 FermeGestion
- **Éditeur** : non nommé sur la page. **Licence** : non indiquée, propriétaire SaaS.
- **Cible** : micro-BA, cotisants solidaires, pluriactifs, petits exploitants au réel simplifié qui préparent leurs chiffres pour le comptable, vente directe.
- **Prix** :
  - Gratuit : 20 écritures par mois, 20 clients, devis et factures Factur-X illimités ;
  - Pro : 9,90 €/mois ou 99 €/an.
- **Fonctionnalités** :
  - journal des recettes et dépenses par catégories agricoles, sans numéros de compte (choix assumé), ventilation par taux, écritures « hors recette » ;
  - factures liées au journal ;
  - outils TVA pour les non-assujettis, le RFA et le RSA ;
  - bilan annuel et calcul du résultat micro-BA ;
  - immobilisations et amortissements ;
  - suivi des aides PAC ;
  - justificatifs avec lecture automatique ;
  - import et export CSV ;
  - accès en lecture pour le comptable ;
  - e-facture via la plateforme SUPER PDP ;
  - modules par filière : élevage, apiculture, vigne, maraîchage, céréales, équins, horticulture.
- **Limites affichées** : pas de plan de comptes, pas de connexion bancaire directe (seulement l'import de relevés), pas de liasse, pas de télédéclaration. L'outil « prépare les montants ».
- **Source** : https://fermegestion.fr/comptabilite-agricole.php

### 1.7 Gleba (GMS64260)
- **Éditeur** : projet libre (GitHub GMS64260), version 1.1.0, 9 étoiles, très actif (dernier commit le 3 novembre 2026).
- **Licence** : AGPL-3.0 (badge du README ; GitHub affiche « NOASSERTION »).
- **Cible** : fermes diversifiées (maraîchage, verger, élevage), micro-fermes, écolieux.
- **Prix** : gratuit, auto-hébergeable (Docker), démo sur gleba.fr.
- **Pile technique** : Next.js 16, Prisma, PostgreSQL et PostGIS.
- **Fonctionnalités comptables vues dans le code** (`src/app/api/comptabilite/*`, `src/lib/comptabilite/plan-comptable-agricole.ts`) :
  - plan comptable agricole simplifié qui associe chaque catégorie métier à un compte (701100 légumes, 702100 animaux vivants, 701821 bois d'œuvre…) ;
  - écritures automatiques depuis les modules métier (`auto-compta.ts`), y compris les abattages et les ventes d'élevage ;
  - clients et fournisseurs, factures, avoirs, Factur-X, UBL, numérotation séquentielle ;
  - dépenses et ventes manuelles ;
  - banque : connexion Stripe en lecture, relevés CSV, rapprochement multi-pièces, virements internes ;
  - TVA : régimes franchise 293 B, RFA, réel simplifié et réel normal ; aide au remplissage de la CA3 en PDF ou CSV, « à recopier sur impots.gouv.fr ». Aucune mention de la CA12A dans le code.
  - export FEC ;
  - bilan simplifié ;
  - stocks valorisés et coûts de production ;
  - marges et indicateurs mensuels ;
  - aides à la plantation (verger).
- **Assistant IA** : OpenAI (Codex) avec outils applicatifs pour la culture, le verger, l'élevage et la comptabilité. Il lit les données et propose des saisies, que l'utilisateur confirme. Analyse de photos. Serveur MCP publié sur npm (`gleba-mcp-server`).
- **Non trouvé dans le code** : immobilisations et amortissements, liasse, DEP, MSA, échéancier.
- **Sources** : https://github.com/GMS64260/gleba, `docs/banque-reglements.md`, `src/app/(marketing)/assistant-ia-agricole/page.tsx`

### 1.8 Mes Parcelles (Chambres d'agriculture)
- **Éditeur** : réseau des Chambres d'agriculture.
- **Cible** : exploitations de toutes tailles, pour la gestion parcellaire, la traçabilité et la déclaration PAC.
- **Prix** : variable selon la chambre départementale. Exemple de la Drôme en 2024 : dossier PAC à partir de 60 € HT, « petit dossier » à 190 € HT.
- **Fonctionnalités** : cartographie, enregistrement des interventions, traçabilité, PAC, suivi technico-économique (marges, stocks). Selon comptabilite-agriculteur.fr, il fait aussi une « comptabilité simplifiée ».
- **Ce qu'il n'est pas** : un logiciel de comptabilité fiscale. Il complète une comptabilité tenue ailleurs.
- **Sources** : https://www.lafabriquedunet.fr/logiciel/mes-parcelles (extrait de recherche), https://drome.chambres-agriculture.fr/fileadmin/user_upload/Auvergne-Rhone-Alpes/118_Extr-Drome_img/Prestations/Plaquettes/EM_2024_PL_PAC2024.pdf

### 1.9 Smag (Agreo, Smag Farmer)
- **Éditeur** : SMAG, groupe InVivo.
- **Cible** : grandes cultures, coopératives et négoces. Plus de 10 millions d'hectares annoncés.
- **Prix** : sur demande.
- **Fonctionnalités** : parcellaire, traçabilité, marges brutes et semi-nettes, entrées et sorties de stocks d'intrants, tableaux de bord et alertes, préparation de la PAC.
- **Comptabilité générale** : aucune source n'en atteste.
- **Sources** : https://smag.tech/app/uploads/2019/02/SMAG_Smag-Farmer.pdf, https://smag.tech/app/uploads/2018/11/Plaquette_Agreo_Exploitants_web.pdf

### 1.10 FarmLEAP
- **Nature** : plateforme de comparaison entre exploitations (benchmark technico-économique, présentée comme un « CETA numérique »), souvent proposée via les coopératives.
- **Fonctionnalités** : marges brutes en temps réel, objectifs, prévisions simples.
- **Comptabilité** : non.
- **Sources** : https://www.terre-net.fr/gestion-agricole/article/146303/de-nouvelles-fonctionnalites-pour-ce-ceta-numerique, https://agritechobservatory.review.fao.org/en/farmleap

### 1.11 Karnott
- **Nature** : boîtier connecté pour le matériel agricole. Il compte les surfaces et les interventions pour automatiser la facturation dans les CUMA et les ETA. Environ 10 à 12 € par mois et par adhérent pour une CUMA moyenne.
- **Comptabilité** : non. C'est une source de données de facturation et d'analytique matériel.
- **Source** : https://www.reussir.fr/lait/karnott-la-fin-du-carnet-de-notes-en-cuma

### 1.12 Outils cités sans détail vérifiable
- **Agrigest, Comptagri** : aucun produit actuel trouvé. Comptagri est un système de 1970 (CIHEAM, https://ressources.ciheam.org/ressources/om/pdf/r01/CI010304.pdf).
- **Agrilead** (grandes cultures, marchés à terme) et **Kerhis** (coopératives, ristournes) : cités par comptabilite-agriculteur.fr sans éditeur ni source primaire.
- **EBP / Ciel** : EBP a des modules « gestion agricole » et « paye agricole », mais aucune édition agricole de compta Ciel n'a été trouvée (https://www.lafabriquedunet.fr/logiciels/alternatives/alternative-ebp-a-cegid-company).
- **myCuma Compta** : comptabilité des CUMA (fédérations).
- **Tiller** : caisse pour la restauration, sans lien agricole trouvé.

### 1.13 Assistants et échéanciers
- **Hectar** : bibliothèque de chatbots IA pour agriculteurs (charge administrative avec pré-remplissage de formulaires, transmission, nouveaux ateliers, recrutement), pilote en septembre 2025. Ni PAC, ni MSA, ni TVA cités (https://www.reussir.fr/taches-administratives-quoi-va-servir-le-chatbot-ia-agricole-lance-par-hectar).
- **Calendriers officiels** : impots.gouv publie un calendrier fiscal mensuel. Exemple pour novembre 2026 : bulletin d'échéance 3525 bis du 3e trimestre pour la CA12A, CA3 mensuelle entre le 16 et le 24 (https://www.impots.gouv.fr/calendrier-fiscal/2026-11). Les caisses MSA publient des calendriers régionaux en PDF, par exemple https://cotesnormandes.msa.fr/lfp/documents/98930/2199260/CALENDRIER+2026+exploitants+MSA+CN.pdf. Les chambres publient des calendriers réglementaires en PDF. Télépac ouvre le 1er avril et ferme vers le 15 mai.
- **Logiciel avec échéancier personnalisé** : aucun trouvé qui combine PAC, TVA agricole, MSA et clôture et l'applique au dossier de l'exploitant.

---

## 2. Matrice des fonctionnalités

Légende :
- O : documenté ;
- ~ : partiel, annoncé ou côté cabinet seulement ;
- X : explicitement absent ;
- ? : non documenté ;
- n/a : hors périmètre (l'outil n'est pas une comptabilité).

| Fonction | Isacompta/Agiris | ISTEA | Pennylane agri | Ekylibre | Ouvretaferme | FermeGestion | Gleba | Mes Parcelles | Smag/Agreo | FarmLEAP |
|---|---|---|---|---|---|---|---|---|---|---|
| Plan comptable agricole | O | O | O | O | O | X (catégories) | ~ (simplifié) | n/a | n/a | n/a |
| Saisie simplifiée recettes/dépenses | ~ (IA AMICOMPTA) | ~ | ~ | ~ (depuis les interventions) | O (depuis les ventes et la caisse) | O | O | n/a | n/a | n/a |
| Banque (flux, rapprochement) | O (collecte auto) | ? | O | O | O (rapprochement) | ~ (import) | ~ (Stripe et CSV) | n/a | n/a | n/a |
| TVA RSA / CA12A / RFA | O (assistant) | O (télédéclaration) | O (CA12A, 3525 bis, 3517 DDR) | ~ | O (CA3/CA12) | ~ (aide RFA/RSA) | ~ (CA3, RFA, pas de CA12A) | n/a | n/a | n/a |
| Stocks et inventaires (animaux, cultures) | ~ (module ; Agiris : barèmes, import animaux) | ? | ~ (annoncé) | O | ~ (stocks de gestion) | ? | ~ (stocks valorisés) | ~ | ~ (intrants) | X |
| Avances aux cultures | ~ (Agiris) | ? | ? | ? | X (pédagogie seulement) | ? | ? | X | X | X |
| Immobilisations agricoles | O | ? | O (socle) | O | O | O | ? | n/a | n/a | n/a |
| DEP / DPA / DPI | ~ (Agiris) | ? | ? | ? | ? | ? | X | n/a | n/a | n/a |
| Aides PAC en comptabilité | ? | ? | ? | ~ (codes PAC) | ~ (page aides) | O (suivi) | ~ (aides plantation) | O (déclaration) | ~ (préparation) | X |
| Analytique par atelier, culture, parcelle | O | ? | ? | O (activité, parcelle) | ? | ~ (modules filières) | ~ (coûts de production) | ~ | O | ~ |
| Marges brutes | O | ? | ? | O | ~ (SIG) | ? | O | O | O | O |
| Liasse 2139 / 2143 | O (Agiris SOFI BA) | ? | O (télédéclaration) | X | X | X | X | n/a | n/a | n/a |
| Micro-BA (2042 C PRO) | ? | ? | ? | ? | O | O | ? | n/a | n/a | n/a |
| FEC et export cabinet | O | ? | O (natif cabinet) | O | O | ~ (CSV, accès lecture) | O (FEC) | n/a | n/a | n/a |
| MSA (cotisations exploitant, simulation) | ~ (Agiris, côté cabinet) | ? | ? | ? | ~ (pédagogie) | ? | X | n/a | n/a | n/a |
| Facture électronique | O | ? | O | ? | O | O (SUPER PDP) | O (Factur-X, UBL) | n/a | n/a | n/a |
| Mobile / hors ligne | ? | X | O (app Pennylane) | ~ | ~ (caisse marchés) | ? | ~ (app Android prévue) | O | O | O |
| Assistant IA | ~ (lecture de factures) | X | ? | ~ (vocal) | X | ~ (lecture de justificatifs) | O (outils et MCP) | X | X | X |
| Échéancier des démarches | ? | X | ? | ? | X | X | X | ~ (PAC) | ? | X |
| Prix public | 35 €/mois et plus | formation | non | non (libre) | 0 à 30 € HT/mois | 0 à 9,90 €/mois | gratuit | selon la chambre | non | via les coopératives |
| Licence | propriétaire | propriétaire | propriétaire | AGPL | AGPL | propriétaire | AGPL | propriétaire | propriétaire | propriétaire |

---

## 3. Différenciation et manques du marché

### 3.1 Ce qui distingue les acteurs
- **Profondeur fiscale (Isacompta et Agiris, Pennylane)** : liasse 2139/2143 pré-remplie, CA12A, 3525 bis, DEP/DPA, moyenne triennale, simulation MSA. Ces fonctions sont surtout destinées aux cabinets, pas à l'exploitant qui tient seul sa comptabilité.
- **Écritures générées depuis l'activité (Ekylibre, Gleba, Ouvretaferme)** : interventions, ventes, caisse ou abattages produisent les écritures. L'agriculteur ne « fait pas de compta », il gère sa ferme.
- **Simplicité micro-BA (FermeGestion, Ouvretaferme)** : journal de recettes et dépenses sans numéros de compte, résultat micro-BA, aide au RFA.
- **Accompagnement humain (ISTEA avec AFOCG ou CER France, cabinets Advyse ou CPA)** : un groupe de formation ou un collaborateur fait l'essentiel de la valeur.
- **Assistant IA** : seul Gleba a un assistant connecté aux données (avec outils et MCP). Ailleurs, l'IA se limite à la lecture de factures (AMICOMPTA, FermeGestion) ou à des prototypes vocaux (Ekylibre).

### 3.2 Manques constatés
1. **Pas d'accompagnement hebdomadaire des démarches.** Aucun logiciel ne propose un échéancier tiré du dossier lui-même (régime fiscal, régime de TVA, date de clôture, caisse MSA, aides demandées) qui dirait chaque semaine quoi faire, quelle pièce manque et quelle écriture passer. Exemples de tâches :
   - acompte 3525 bis du trimestre et CA12A annuelle (réel simplifié) ;
   - demande de RFA (formulaire 3520) et collecte des attestations des acheteurs ;
   - Télépac du 1er avril au 15 mai, avances PAC à partir du 16 octobre et leur rattachement au compte 441 à la clôture ;
   - appels provisionnels MSA, solde, option pour l'assiette annuelle ou triennale ;
   - inventaire de clôture (stocks, avances aux cultures, cheptel), date de dépôt de la 2139.
   
   Ces dates n'existent aujourd'hui qu'en PDF (calendriers MSA régionaux, chambres) ou en calendrier générique (impots.gouv).
2. **Avances aux cultures et stocks vivants** : traités côté cabinet (barèmes Agiris) ou seulement dans des articles pédagogiques (Ouvretaferme). Aucun outil pour l'exploitant ne guide l'inventaire de clôture (comptage, méthode de l'article 72 A, choix entre stock et immobilisation pour les reproducteurs, option 72 B bis).
3. **Aides PAC en comptabilité** : rattachement à la campagne, avance d'octobre et solde, compte 441 à la clôture, distinction entre 74x et 131/139 (subventions d'investissement, DJA mixte). C'est rarement automatisé, et Ouvretaferme montre que la question revient souvent.
4. **Passage micro-BA vers réel** : aucun outil ne compare le forfait (abattement de 87 %) au résultat réel pour aider à l'option, alors qu'Ouvretaferme décrit précisément ce besoin.
5. **Banque en France** : les outils libres en sont à l'import CSV (Gleba) ou à l'export Stripe. Seuls Isacompta et Ekylibre collectent les relevés automatiquement. Une intégration Qonto ou DSP2, déjà présente dans Lyvre, différencierait.
6. **Multi-structures** : GAEC, EARL ou SCEA d'un côté, et de l'autre une SCI foncière, un GFA, une activité de diversification en société ou une association. Aucun outil pour l'exploitant ne les traite ensemble. C'est le cœur de Lyvre.
7. **Liasse côté exploitant** : seuls les outils pour cabinets la produisent. Pour l'autocomptabilité (public des AFOCG), une aide à la 2139 avec contrôles serait nouvelle.

---

## 4. Ce que disent les ressources pédagogiques

### Advyse (https://www.advyse.fr/comptabilite-agricole/)
- La comptabilité dépend du régime fiscal, des cycles de production et des stocks. Recettes, achats et aides n'ont pas le même calendrier : un solde bancaire élevé n'est pas de la trésorerie disponible.
- Les erreurs coûteuses viennent d'habitudes :
  - inventaire ancien (10 % d'écart sur 140 000 € de céréales font 14 000 €) ;
  - justificatifs dispersés (à conserver 10 ans, à classer chaque mois) ;
  - registre du matériel mal tenu (facture, mise en service, sortie).
- Le cheptel se traite selon sa destination (reproduction ou vente). Une aide d'exploitation ne se traite pas comme une subvention d'investissement.
- Seuils cités : micro-BA jusqu'à 129 200 € HT de moyenne sur trois ans, avec un abattement de 87 % et un minimum de 305 € ; réel normal au-delà de 421 000 €.
- Accompagnement : premier échange de 30 minutes, suivi des postes sensibles (stocks, aides, matériel) pendant l'année, scénarios avant d'investir. Aucun tarif public.

### CPA (https://hello.audit-cpa.com/secteur/agriculture/)
- Besoins mis en avant :
  - piloter au quotidien (marges brutes par atelier) ;
  - optimiser le bénéfice agricole au réel (lissage, DEP) ;
  - valoriser stocks, avances aux cultures et cheptel ;
  - gérer la TVA agricole (remboursement forfaitaire ou réel), les déclarations et cotisations MSA, le suivi des aides PAC ;
  - monter les dossiers JA et le financement du matériel ;
  - préparer la transmission (baux, GFA, pacte Dutreil) ;
  - changer de cabinet sans rupture.
- Formes juridiques couvertes : exploitation individuelle, GAEC, EARL, SCEA.
- Outil utilisé : Pennylane.

### Ouvretaferme (https://www.ouvretaferme.org/articles/?category=how-to)
La base d'articles montre bien les questions concrètes des agriculteurs. Thèmes : PCA, micro-BA, DJA, revente de produits d'autres fermes, certification bio, TVA sur le carburant, trésorerie ou engagement, Stripe et SumUp, dépôt-vente, autofacturation, paie MSA, acomptes, aides PAC, subventions d'investissement, RFA, clôture par cycle.

- **Micro-BA** (https://www.ouvretaferme.org/articles/how-to/comprendre-la-comptabilite-simplifiee-du-micro-ba) :
  - le livre de recettes est le seul document exigé : recettes HT à la date d'encaissement, regroupement possible des ventes de 76 € ou moins par jour, totaux trimestriels et annuels ;
  - le registre des achats devient obligatoire au régime simplifié agricole de TVA ;
  - difficultés : forfait défavorable si les charges dépassent 87 % des recettes, le livre ne suit ni dettes, ni créances, ni trésorerie, les recettes sont difficiles à classer (aides, indemnités, cessions), la PAC, la TVA et les GAEC demandent un conseil.
- **Aides PAC** (https://www.ouvretaferme.org/articles/how-to/comment-comptabiliser-les-aides-pac-et-les-autres-aides-d-exploitation) :
  - aides découplées au compte 745, contrepartie 512 ou 441 ;
  - le compte 741 est réservé au remboursement forfaitaire de TVA ;
  - en engagement, rattachement à l'exercice de la date limite de dépôt (15 mai) ;
  - en trésorerie (réel simplifié), constat du 441 à la clôture ;
  - au micro-BA, seuls les encaissements de l'année comptent ; l'ICHN et les primes d'équipement sont hors recettes ;
  - tolérance du 16 octobre traitée hors comptabilité.
- **Trésorerie ou engagement** : la trésorerie est majoritaire chez les agriculteurs. Au réel simplifié, on enregistre les encaissements et décaissements pendant l'année, puis on régularise créances, dettes et stocks à la clôture.
- **MSA et paie** : salaire au 641, cotisations au 431 ou 437 (complexe selon les organismes), cotisations patronales au 654, DSN mensuelle sans écriture. Taux variables, paie de décembre payée en janvier. Les cotisations de l'exploitant sont annoncées dans un autre article.
- **DJA** (https://www.ouvretaferme.org/articles/how-to/comment-comptabiliser-la-dotation-jeune-agriculteur-dja) :
  - part exploitation au compte 74, part investissement au 131 avec reprise 139 vers 747 au rythme de l'amortissement ;
  - une DJA mixte doit être ventilée, avec prorata temporis ;
  - abattement de l'article 73 B au réel seulement ;
  - pièges fréquents.
- **RFA** (https://www.ouvretaferme.org/articles/vat/qu-est-ce-que-le-remboursement-forfaitaire-agricole) :
  - régime par défaut sous le seuil du RSA (46 000 € en 2026) ;
  - pas de TVA facturée ni déduite, charges saisies TTC ;
  - forfait calculé sur les ventes à des assujettis, avec attestations des acheteurs ;
  - défavorable en cas de gros investissements.
- **Clôture des stocks** (https://www.ouvretaferme.org/articles/closing/le-cycle-stock-dans-la-cloture-d-exercice) :
  - inventaire en quantités avec feuilles de comptage conservées ;
  - animaux destinés à la vente en stock, classement des reproducteurs à valider ;
  - engrais épandu pour la récolte suivante classé en avance aux cultures ;
  - valorisation au prix de revient ou au cours du jour s'il est inférieur (CUMP ou PEPS), méthode forfaitaire possible au réel simplifié, option 72 B bis ;
  - écritures : 35511 et 713554 pour les produits, 31111 et 6031 pour les approvisionnements, dépréciation 68173 et 395 ;
  - au micro-BA, pas de variation de stock.

### comptabilite-agriculteur.fr (https://www.comptabilite-agriculteur.fr/quel-logiciel-comptable-choisir-pour-gerer-son-exploitation-agricole/)
Critères de choix :
- conformité au plan agricole, avec bilan et annexes ;
- saisie guidée pour non-comptables ;
- fonctionnement hors connexion en zone blanche ;
- formation et support ;
- réactivité aux réformes fiscales et PAC ;
- cycles saisonniers, stocks vivants, subventions ;
- analytique par culture ou élevage ;
- simulation d'investissements ;
- intégrations avec le parcellaire (FarmLEAP, Smag Farmer) et l'élevage ;
- retour sur investissement : temps gagné, optimisation fiscale, accès au crédit.

### Synthèse des besoins
1. Un calendrier qui se décale (aides, récoltes, campagnes) et une trésorerie différente du solde bancaire.
2. Une clôture difficile à réaliser seul : stocks, avances aux cultures, cheptel, 441 PAC, créances et dettes.
3. Des classements fiscaux ambigus : aides de classe 74 ou subvention 131, DJA, reproducteurs, recettes micro-BA.
4. Des choix de régime à simuler : micro-BA ou réel, RFA ou RSA, DEP, moyenne triennale.
5. Le besoin d'un accompagnement régulier, aujourd'hui assuré par des humains (AFOCG, CER France, cabinets) et absent des logiciels.
