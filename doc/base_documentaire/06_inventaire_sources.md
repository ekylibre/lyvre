# 6. Inventaire des sources, fiches à produire, lacunes

## 6.1 Sources présentes dans le dépôt

| Clé | Fichier | Taille | Structure exploitable | Usage |
|---|---|---|---|---|
| `SYNTH-ANC` | `doc/ref_compta/Base_compta.md` | 956 lignes, 33 fiches, FAQ de 20 questions, 92 sources | titres `### X-nn · Titre` ; rubriques Entité / Résumé / Exemple / Référence / Implications | **Matière première des fiches** (découpage par script, lot 1.2) |
| `PCG26` | `doc/ref_compta/PCG--1er-janvier-2026.pdf` | 183 p. | environ 570 en-têtes `Art. nnnn-n` en début de ligne | textes primaires (FTS5) |
| `REC-EIC26` | `doc/ref_compta/Recueil-PCG-Janvier-2026-2-.pdf` | 663 p. | environ 670 en-têtes d'article | textes primaires, couche `eic` (non chargée pour asso et SCI au lot 1) |
| `REC-NL26` | `doc/ref_compta/Recueil-non-lucratif-2026.pdf` | 236 p. | environ 310 en-têtes `Art. 111-1` … `Art. 433-2` | textes primaires de la couche `asso_2018_06` |
| `GUIDE-BENEVOLAT` | `doc/ref_compta/valorisation_comptable_benevolat_0 (1).pdf` | 24 p. | guide pratique (rappel des règles 2018-06, retours d'expérience, outils ; cite l'ANC, l'OEC, la CNCC et le HCVA) | textes primaires de `C-05` ; source des **taux de valorisation** à documenter |
| `MODELE-RAG` | `doc/ref_compta/modele-rapport-annuel-gestion.doc` | Word 97, 2018 | modèle de rapport de gestion | **hors corpus normatif** : gabarit pour le rapport d'activité (`/rapport-activite`) ; à convertir en `.md` si l'assistant doit aider à le rédiger |
| `PLAN-SCI` | `doc/plan-comptable-SCI.pdf` | 19 p. | sens `C` / `D` devant chaque compte ; mention « (ligne n) » de la 2072 ; libellés en italique = comptes repris par défaut dans le résultat foncier | `sci/comptes.yml` (sens), `sci/correspondance_2072.yml` |
| `PCA-XLS` | `Modele-document-Nouveau-Plan-comptable-Bilan-CDR.xls` | 5 feuilles | plan asso (783 comptes), Bilan, CDR (1) et (2) avec CVN | source historique de `data/plan_comptable_asso.json` et de `reports.py` |
| — | `data/plan_comptable_asso.json` | 783 comptes | `code`, `label`, `account_type`, `is_header` | plan du référentiel `asso_2018_06` |
| — | `data/plan_comptable_sci.json` | 576 comptes | idem ; la ligne 2072 est dans `label` | plan du référentiel `sci` |
| — | `data/rules.yml` | 20 règles | gabarit de règles de catégorisation bancaire (propres à une instance) | **hors corpus** : ce sont des règles d'instance, pas des règles comptables. Un schéma (doc 3 §3.5) pourra en revanche servir de base à `propose_rule` |

Externes consultées pour ce cadrage :
- Ekylibre `config/accountancy/*.yml`, `app/services/accountancy_computation.rb`, `app/models/journal.rb#sum_entry_items` : syntaxe des expressions, voir doc 3 §3.1 ;
- paperasse : les 6 skills, les scripts et les évaluations, analysés au doc 7. Il n'apporte **aucun contenu** sur les associations ni sur la comptabilité des SCI, seulement des méthodes, et quelques éléments de droit et de fiscalité des SCI à vérifier (§6.3) ;
- **arrhes/PCG** (CC0), source des données PCG de paperasse : PCG 2026 en JSON (838 comptes, obligatoires ou facultatifs, diff avec 2025) et en Markdown (PCG et recueil EIC, articles balisés). Ajouté au registre : clés `PCG26` (texte et plan) et `REC-EIC26` (texte).

## 6.2 Découpage de `Base_compta.md` en fiches

| Fiche | Titre | Référentiel | Risque | Statut initial |
|---|---|---|---|---|
| A-01 | Principes comptables fondamentaux | pcg2026 | aucun | publie |
| A-02 | Organisation, documentation, chemin de révision | pcg2026 | aucun | publie (Livre IV vérifié) |
| A-03 | Livres obligatoires et partie double | pcg2026 | aucun | publie (Livre IV vérifié) |
| A-04 | Pièces justificatives | pcg2026 | aucun | publie (Livre IV vérifié) |
| A-05 | Validation et irréversibilité | pcg2026 | aucun | publie (Livre IV vérifié) |
| A-06 | Procédure de clôture | pcg2026 | aucun | publie (Livre IV vérifié) |
| A-07 | Conservation et FEC | pcg2026 | aucun | publie |
| A-08 | Structure du plan de comptes | pcg2026 | aucun | publie |
| A-09 | Règlement ANC 2022-06 | pcg2026 (`applicable: exercices_ouverts_depuis 2025-01-01`) | attention | publie |
| A-10 | Immobilisations, amortissements, dépréciations | pcg2026 | expert | publie |
| A-11 | Stocks, créances, provisions | pcg2026 | expert | publie |
| A-12 | Régularisations de fin d'exercice | pcg2026 | attention | publie |
| A-13 | Opérations en devises | pcg2026 | attention | publie |
| A-14 | TVA (comptes 445x) | pcg2026 | expert | publie |
| A-15 | Clôture d'exercice et documents de synthèse | pcg2026 | attention | publie |
| B-01…B-03 | Entreprises (EIC) | eic | — | publie (non chargé au lot 1) |
| C-01 | Champ d'application | asso_2018_06 | aucun | publie |
| C-02 | Fonds propres associatifs | asso_2018_06 | attention | publie |
| C-03 | Fonds dédiés | asso_2018_06 | expert | publie (exemple complet dans `exemples/fiches/`) |
| C-04 | Legs, donations, assurances-vie, fonds reportés | asso_2018_06 | expert | publie |
| C-05 | Contributions volontaires en nature | asso_2018_06 | attention | publie |
| C-06 | Cotisations, dons, mécénat, subventions | asso_2018_06 | attention | publie |
| C-07 | Générosité du public, CROD, CER | asso_2018_06 | expert | publie |
| C-08 | Plan de comptes associatif (657 / 754 / 756) | asso_2018_06 | aucun | publie |
| C-09 | Fiscalité et TVA des associations | asso_2018_06 | expert | publie |
| D-01…D-06 | Banque, import, imputation, 471, 580, rapprochement | pcg2026 | aucun | publie (D-04 en exemple) |

Les sources `Qonto` des fiches D-02 et D-03 restent valables, mais le logiciel importe aussi l'OFX, Stancer, HelloAsso et Odoo. Il faut ajouter à D-03 un paragraphe « Autres sources d'import » qui décrit le comportement réel (`ofx_importer`, `rules_engine`, `purchase_settlement`), car l'assistant doit décrire **ce logiciel**.

Une fiche **L-01 « Fonctionnement de ce logiciel »** (référentiel `pcg2026`, sans risque) décrit les écrans et les statuts (brouillon, validée, numérotée, exercice provisoire, définitif). Elle s'appuie sur `doc/cloture.md` et `doc/saisie_rapprochement.md`, pour que l'assistant guide dans l'interface.

## 6.3 Lacune principale : la couche SCI

`Base_compta.md` ne contient **aucune fiche SCI**. Le logiciel gère pourtant des instances SCI (576 comptes, CDR SCI dans `reports.py`). Fiches à rédiger, en `statut: brouillon` jusqu'à validation par un expert-comptable (question ouverte n° 5 du doc 1) :

| Fiche | Sujet | Sources primaires à consulter | Point de départ dans paperasse (à recouper) | Risque |
|---|---|---|---|---|
| S-01 | Champ : SCI à l'IR (transparence fiscale) ou à l'IS, conséquences sur le référentiel | CGI art. 8, 206-2, 239, 239 bis AA ; C. civ. art. 1832 à 1873 ; BOFiP RFPI (premières références dans paperasse, doc 7 §7.6) | notaire `references/societes.md` l. 7-68 : au moins 2 associés, capital libre, 99 ans au plus, acte notarié si apport d'immeuble ; IR par défaut, option IS irrévocable | expert |
| S-02 | Loyers et charges refacturées : comptes 7083 / 7085 du plan, ligne 1 / 2 de la 2072 | plan SCI ; notice 2072 de l'année | — (2072 citée une seule fois, sans détail) | attention |
| S-03 | Charges déductibles du résultat foncier et lignes 2072 (6, 8, 9, 12, 14, 15, 16, 17, 20a, 20b, 22) | notice 2072 ; BOFiP BOI-RFPI-BASE-20 | fiscaliste `revenus-fonciers-lmnp.md` l. 31-53 et `regimes-fonciers-lmnp.json` : charges déductibles au réel ; déficit foncier imputable sur le revenu global jusqu'à 10 700 €, intérêts jamais imputables sur le revenu global, report sur 10 ans (art. 156-I-3°) ; micro-foncier exclu pour les SCI (nuance à vérifier) | expert |
| S-04 | Emprunt immobilier : capital (164), intérêts, assurance. **Le plan SCI n'a aucun compte d'intérêts (66 = en-tête seul)**, voir §6.5 | notice 2072 | fiscaliste : intérêts d'emprunt déductibles du revenu foncier | attention |
| S-05 | Comptes courants d'associés (455x) : apports, remboursements, intérêts | PCG ; statuts | comptable `legal-forms.md` l. 228-265 : écritures 512/455, 455/512, 6615/4558 ; ⚠️ plafond « BCE + 2 points » probablement erroné (art. 39-1-3° CGI) | attention |
| S-06 | Affectation du résultat et répartition entre associés au prorata des parts | Code civil art. 1832 et suivants ; statuts | notaire `templates/statuts-sci.md` art. 22 : affectation au prorata des parts ; ⚠️ l'ordre d'affectation de `legal-forms.md` (réserve légale 5 %) vaut pour les sociétés commerciales, pas pour les SCI | expert |
| S-07 | Dépôts de garantie reçus des locataires | PCG | — | aucun |
| S-08 | Amortissement des immeubles : traitement comptable ou fiscal (SCI à l'IR : non déductible du revenu foncier) | PCG ; BOFiP | notaire `cas-speciaux.md` l. 47 : SCI à l'IS, amortissement et plus-value professionnelle (prix − VNC) | expert |
| S-09 | Plusieurs immeubles : ventilation par immeuble (axe projet utilisé comme axe immeuble ?) | PDF du plan SCI (« s'il y a un seul immeuble ») | — | — (question produit) |
| S-10 | Obligations : approbation des comptes, reddition annuelle aux associés | Code civil art. 1856 ; statuts | notaire `statuts-sci.md` art. 17-21 : AG dans les six mois de la clôture, convocation 15 jours avant, majorités ; **art. 1856 C. civ. absent** | attention |

Paperasse ne contient **aucune comptabilité de SCI** (ni plan de comptes, ni écritures types, ni description de la 2072). Il ne fournit que du droit et de la fiscalité, en point de départ. Deux erreurs probables sont à ne pas reprendre : le taux des intérêts de compte courant (S-05), et l'abattement de 23 000 € sur les cessions de parts de SCI, que `notaire/references/societes.md` l. 118 applique à tort aux sociétés à prépondérance immobilière. Le détail est au doc 7 §7.5 et §7.6.

⚠️ Le tableau ci-dessus fixe la **liste des sujets et des sources à consulter**. Il ne contient pas de règle à coder. Rien ne passe dans `regles/sci/` tant que la fiche correspondante n'est pas `publie`.

## 6.4 Autres lacunes et points à arbitrer

1. **Citations du Livre IV** : **vérifiées le 2026-10-23** dans le texte Markdown du PCG 2026 (arrhes/PCG). Les articles 1011-1, 1021-1, 1031-1 à 1031-4, 1032-1, 1032-2, 1121-1, 513-5 et 811-7 sont présents (doc 7 §7.3). A-02 à A-06 peuvent passer en `publie`, avec la ligne du texte en preuve.
2. **657 / 754 / 756** : arbitrage fait par couche (doc 3 §3.6). Vérifié le 2026-10-23 : `data/plan_comptable_asso.json` porte bien les libellés 2018-06 (657 « Aides financières », 754 « Ressources liées à la générosité du public », 756 « Cotisations »). Seule la couche `comptes.yml` est à écrire.
3. **Seuils** (CAC à 153 000 € de subventions, seuils de dons) : seul le seuil du Code de commerce est sourcé. On les code dans `regles/asso_2018_06/seuils.yml`, avec source et date, ou on ne les code pas.
4. **Taux de valorisation du bénévolat** : le guide de 24 pages décrit des méthodes, il ne fixe pas de taux légal. Le taux reste un **paramètre de l'instance**, que l'assistant explique sans l'imposer.
5. **Correspondance 2072** : la numérotation de lignes vient des libellés du plan. Il faut la contrôler sur le formulaire de l'année en cours (le millésime n'est pas indiqué dans le PDF).
6. **Sens normal des comptes asso** : non fourni par le XLS. Il faut le déduire de la classe et des fiches, puis le faire relire.
7. **Transferts de charges en asso** : le CDR asso actuel (`ASSO_CDR_SECTIONS`) agrège encore `78 79` (« … et transferts de charges »). `A-09` indique que 2022-06 supprime 791/796/797 dans le PCG. Il faut vérifier si cette suppression s'applique aux comptes des associations (recueil non lucratif 2026) avant de figer `asso_2018_06/etats.yml`.
8. **Recueil non lucratif** : en-tête « 1er janvier 20XX ». Utiliser la date du pied de page, 1er janvier 2026, comme le fait `Base_compta.md`.

## 6.5 Écarts entre les plans de l'application et les fiches (relevés le 2026-10-23)

`kb_check` devra les détecter automatiquement : chaque compte cité par une fiche ou un schéma doit exister dans le plan du référentiel.

| Constat | Plan | Conséquence | Action proposée |
|---|---|---|---|
| Pas de 580 : seul `581 Virements de fonds` existe | asso | **pas une anomalie** : le PCG 2026 n'a lui-même que `58` (doc 7 §7.3) ; D-05 cite « 580 » par usage | rôle `compte_virement: "581"` dans `asso/comptes.yml` ; fiche D-05 rédigée sur « 58x » |
| **58 : en-tête seul**, aucun compte de détail | sci | virement interne impossible sans créer un compte | ajouter `581` (ou `580`) au plan SCI ; rôle `compte_virement` |
| **66 : en-tête seul**, aucun compte d'intérêts | sci | **intérêts d'emprunt non comptabilisables** ; aucune ligne 2072 associée | ajouter `6611 Intérêts des emprunts` avec sa ligne 2072 (à vérifier sur la notice) ; schéma `echeance_emprunt` bloqué d'ici là |
| **741 et 441 absents** (seuls `74`, `4417`…) | asso | les exemples de `Base_compta.md` (D 441 / C 741) ne sont pas saisissables tels quels | exemples des fiches réécrits avec les comptes du plan (fait pour C-03) |
| `471` libellé « jusqu'à 474 » / « 471 à 475 » | asso / sci | plage plus large que le PCG (art. 1214-47 : attente = 471 à 473 ; 474 = différences d'évaluation ; 476 / 477 = écarts de conversion) | `closing.checks` teste tout le préfixe `47` : risque de fausse anomalie sur 476 / 477 ou 4741. Restreindre à `471 472 473` au lot 2.3 |
| Lignes de plan « 61490 à 61494 », « 4551 à 4557 »… | sci | un code représente une plage de comptes | `correspondance_2072.yml` garde le code de tête ; à détailler si des sous-comptes sont créés |
