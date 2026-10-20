# États financiers

## Balance des comptes

**URL :** `/reports/balance`

Liste tous les comptes ayant au moins un mouvement sur l'exercice sélectionné.

**Colonnes :**

| Colonne | Description |
|---------|-------------|
| Code | Code du compte |
| Libellé | Libellé du compte |
| Débit | Total des mouvements débiteurs (en euros) |
| Crédit | Total des mouvements créditeurs (en euros) |
| Solde débiteur | `max(débit - crédit, 0)` |
| Solde créditeur | `max(crédit - débit, 0)` |

La ligne de totaux en bas vérifie l'équilibre général : Σ soldes débiteurs = Σ soldes créditeurs.

---

## Grand livre

**URL :** `/reports/grand-livre?fy_id=X&account_id=Y`

Détail chronologique de tous les mouvements d'un compte sur un exercice, avec solde courant.

**Colonnes :**

| Colonne | Description |
|---------|-------------|
| Date | Date de l'écriture |
| Réf. | Référence de l'écriture (lien vers le détail) |
| Journal | Code du journal |
| Libellé | Libellé de la ligne ou de l'écriture |
| Débit | Montant débiteur |
| Crédit | Montant créditeur |
| Solde | Solde cumulé (débit - crédit) depuis le début de l'exercice |

Le solde est affiché en rouge quand il est négatif.

---

## Principes communs (Bilan et Compte de résultat)

Les deux états s'adaptent au **plan comptable de l'instance** (`Instance.chart`,
choisi à la création de l'instance) :

| Plan | Bilan / Compte de résultat |
|------|----------------------------|
| `asso` | Modèle du plan comptable des associations (règlement ANC 2018-06) : fonds propres, fonds reportés et dédiés, contributions volontaires en nature, ligne finale **EXCÉDENT / DÉFICIT** |
| `sci` | Plan comptable général présenté pour une SCI : capital, comptes courants d'associés, dépôts de garantie, loyers, taxe foncière, ligne finale **BÉNÉFICE / PERTE** |

Règles de calcul, identiques pour les deux plans (mises en page déclaratives
`BILAN_LAYOUTS` / `CDR_SECTIONS` dans `app/services/reports.py`) :

- **Chaque compte est compté une seule fois.** Les lignes sont définies par des préfixes de
  comptes, avec exclusions (`60 sauf 603, 607`) ; les préfixes sont disjoints et couvrent
  toutes les classes 1 à 7 des deux référentiels (vérifié par `tests/test_reports_charts.py`).
- **Lignes « dont »** (ventes de dons en nature, parrainages) : informatives, exclues des totaux.
- **Comptes de tiers et de trésorerie ventilés selon le sens de leur solde**, compte par compte :
  un solde débiteur va à l'actif (`[soldes débiteurs]`), un solde créditeur au passif
  (`[soldes créditeurs]`). Un fournisseur payé en trop devient une créance, un découvert
  bancaire un concours bancaire courant.
- **Valeurs nettes** : les amortissements et dépréciations (28, 29, 39, 49) viennent en déduction.
- **Résultat de l'exercice au bilan** = compte 12 **+ classes 6/7** de l'exercice : la clôture
  ne passe pas d'écriture de résultat, le bilan est donc équilibré à tout moment
  (**TOTAL ACTIF = TOTAL PASSIF**), à condition que l'exercice contienne les écritures
  d'à-nouveaux (seules les écritures de l'exercice affiché sont lues).
- Comparaison **N / N-1** avec l'exercice qui précède immédiatement (colonne vide sans N-1).

---

## Bilan

**URL :** `/reports/bilan`

### Association (`asso`) — actif

```
ACTIF IMMOBILISÉ
Immobilisations incorporelles
    Frais d'établissement                                 (201)
    Frais de recherche et développement                   (203)
    Donations temporaires d'usufruit                      (204)
    Concessions, brevets, licences…                       (205)
    Autres immobilisations incorporelles                  (20 sauf 201, 203, 204, 205)
    Immobilisations incorporelles en cours                (232, 237)
Immobilisations corporelles
    Terrains                                              (211, 212)
    Constructions                                         (213, 214)
    Installations techniques, matériel…                   (215)
    Autres immobilisations corporelles                    (21, 22 sauf 211, 212, 213, 214, 215)
    Immobilisations corporelles en cours                  (23 sauf 232, 237)
  Biens reçus par legs ou donations                       (24)
Immobilisations financières
    Participations et créances rattachées                 (26)
    Autres titres immobilisés                             (27 sauf 274, 275, 276)
    Prêts                                                 (274)
    Autres                                                (275, 276)
  Amortissements et dépréciations des immobilisations     (28, 29)
ACTIF CIRCULANT
  Stocks et en-cours                                      (3)
  Créances clients, usagers                               (41) [soldes débiteurs]
  Créances reçues par legs ou donations                   (461)
  Autres créances                                         (40, 42, 43, 44, 45, 46, 47 sauf 461, 466, 476, 477) [soldes débiteurs]
  Dépréciations des comptes de tiers                      (49)
  Valeurs mobilières de placement                         (50, 59)
  Instruments de trésorerie                               (52) [soldes débiteurs]
  Disponibilités                                          (51, 53, 54, 58) [soldes débiteurs]
  Charges constatées d'avance                             (486)
COMPTES DE RÉGULARISATION
  Frais d'émission des emprunts et charges à répartir     (48 sauf 486, 487)
  Primes de remboursement des emprunts                    (169)
  Écarts de conversion actif                              (476)
TOTAL ACTIF
```

### Association (`asso`) — passif

```
FONDS PROPRES
Fonds propres sans droit de reprise
    Fonds propres statutaires                             (1021, 1022)
    Fonds propres complémentaires                         (102 sauf 1021, 1022)
Fonds propres avec droit de reprise
    Fonds statutaires                                     (1032)
    Fonds propres complémentaires                         (103 sauf 1032)
  Écarts de réévaluation                                  (105)
Réserves
    Réserves statutaires ou contractuelles                (1063)
    Réserves pour projet de l'entité                      (10681)
    Autres réserves                                       (10 sauf 102, 103, 105, 1063, 10681, 108)
  Report à nouveau                                        (11)
  Excédent ou déficit de l'exercice                       (12, 6, 7)
  Fonds propres consomptibles                             (108)
  Subventions d'investissement                            (13)
  Provisions réglementées                                 (14)
FONDS REPORTÉS ET DÉDIÉS
  Fonds reportés liés aux legs ou donations               (191, 192)
  Fonds dédiés                                            (19 sauf 191, 192)
PROVISIONS
  Provisions pour risques                                 (151)
  Provisions pour charges                                 (15 sauf 151)
DETTES
  Emprunts obligataires et assimilés (titres associatifs) (161, 163)
  Emprunts établissements de crédit                       (164)
  Concours bancaires courants                             (51, 53, 54, 58) [soldes créditeurs]
  Emprunts et dettes financières diverses                 (16, 17, 18 sauf 161, 163, 164, 169)
  Dettes fournisseurs et comptes rattachés                (40 sauf 404, 405) [soldes créditeurs]
  Dettes des legs ou donations                            (466)
  Dettes sur immobilisations et comptes rattachés         (404, 405) [soldes créditeurs]
  Dettes fiscales et sociales                             (42, 43, 44) [soldes créditeurs]
  Autres dettes                                           (41, 45, 46, 47 sauf 461, 466, 476, 477) [soldes créditeurs]
  Instruments de trésorerie                               (52) [soldes créditeurs]
  Produits constatés d'avance                             (487)
  Écarts de conversion passif                             (477)
TOTAL PASSIF
```

### SCI (`sci`) — actif

```
  Capital souscrit non appelé                             (109)
ACTIF IMMOBILISÉ
  Immobilisations incorporelles                           (20, 232, 237)
  Terrains                                                (211, 212)
  Constructions                                           (213, 214)
  Autres immobilisations corporelles                      (21, 22 sauf 211, 212, 213, 214)
  Immobilisations corporelles en cours                    (23 sauf 232, 236, 237)
  Immobilisations financières                             (26, 27, 236)
  Amortissements et dépréciations                         (28, 29)
ACTIF CIRCULANT
  Stocks et en-cours                                      (3)
  Créances locataires et comptes rattachés                (41) [soldes débiteurs]
  Associés — comptes débiteurs                            (45) [soldes débiteurs]
  Autres créances                                         (40, 42, 43, 44, 46, 47) [soldes débiteurs]
  Dépréciations des comptes de tiers                      (49)
  Valeurs mobilières de placement                         (50, 59)
  Disponibilités                                          (51, 52, 53, 54, 58) [soldes débiteurs]
  Charges constatées d'avance                             (486)
  Charges à répartir sur plusieurs exercices              (48 sauf 486, 487)
  Primes de remboursement des obligations                 (169)
TOTAL ACTIF
```

### SCI (`sci`) — passif

```
CAPITAUX PROPRES
  Capital social                                          (101, 108)
  Primes liées au capital social                          (104)
  Écarts de réévaluation                                  (105)
  Réserves                                                (10 sauf 101, 104, 105, 108, 109)
  Report à nouveau                                        (11)
  Résultat de l'exercice                                  (12, 6, 7)
  Subventions d'investissement                            (13)
  Provisions réglementées                                 (14)
PROVISIONS
  Provisions pour risques et charges                      (15)
DETTES
  Emprunts auprès des établissements de crédit            (164)
  Concours bancaires courants                             (51, 52, 53, 54, 58) [soldes créditeurs]
  Dépôts de garantie reçus                                (165)
  Autres emprunts et dettes financières                   (16, 17, 18 sauf 164, 165, 169)
  Associés — comptes courants                             (45) [soldes créditeurs]
  Dettes fournisseurs et comptes rattachés                (40) [soldes créditeurs]
  Dettes fiscales et sociales                             (42, 43, 44) [soldes créditeurs]
  Autres dettes                                           (41, 46, 47) [soldes créditeurs]
  Produits constatés d'avance                             (487)
TOTAL PASSIF
```

---

## Compte de résultat

**URL :** `/reports/compte-de-resultat` — exports `…/compte-de-resultat.csv` et `…/compte-de-resultat.ods`

Les deux plans partagent la même ossature :

```
PRODUITS D'EXPLOITATION (I) / CHARGES D'EXPLOITATION (II)
1 — RÉSULTAT D'EXPLOITATION (I - II)
PRODUITS FINANCIERS (III) / CHARGES FINANCIÈRES (IV)
2 — RÉSULTAT FINANCIER (III - IV)
3 — RÉSULTAT COURANT avant impôts (I - II + III - IV)
PRODUITS EXCEPTIONNELS (V) / CHARGES EXCEPTIONNELLES (VI)
4 — RÉSULTAT EXCEPTIONNEL (V - VI)
Participation des salariés aux résultats (VII)   (691)
Impôts sur les bénéfices (VIII)                  (69 sauf 691)
Total des produits (I+III+V)
Total des charges (II+IV+VI+VII+VIII)
EXCÉDENT / DÉFICIT (asso)  —  BÉNÉFICE / PERTE (sci)
```

### Association (`asso`)

À l'écran, les produits d'exploitation sont regroupés comme dans le modèle
(« Ventes de biens et services », « Produits de tiers financeurs »,
« Ressources liées à la générosité du public »).

```
PRODUITS D'EXPLOITATION (I)
  Cotisations                                             (756)
  Ventes de biens                                         (701, 702, 703, 707)
    dont ventes de dons en nature                         (7073)
  Ventes de prestations de services                       (70 sauf 701, 702, 703, 707)
    dont parrainages                                      (7063)
  Concours publics et subventions d'exploitation          (73, 74)
  Versements des fondateurs / dotation consomptible       (753)
  Dons manuels                                            (754 sauf 7542, 7543)
  Mécénats                                                (7542)
  Legs, donations et assurances-vie                       (7543)
  Contributions financières                               (755)
  Reprises sur amortissements, dépréciations, provisions et transferts de charges  (78, 79 sauf 786, 787, 789, 796, 797)
  Utilisations des fonds dédiés                           (789)
  Autres produits                                         (71, 72, 75 sauf 753, 754, 755, 756)
CHARGES D'EXPLOITATION (II)
  Achats de marchandises                                  (607)
  Variation de stocks                                     (603)
  Autres achats et charges externes                       (60, 61, 62 sauf 603, 607)
  Aides financières                                       (657)
  Impôts, taxes et versements assimilés                   (63)
  Salaires et traitements                                 (641, 642)
  Charges sociales                                        (64 sauf 641, 642)
  Dotations aux amortissements et aux dépréciations       (68 sauf 6815, 686, 687, 689)
  Dotations aux provisions                                (6815)
  Reports en fonds dédiés                                 (689)
  Autres charges                                          (65 sauf 657)
PRODUITS FINANCIERS (III)
  De participations                                       (761)
  D'autres valeurs mobilières et créances de l'actif immobilisé  (762, 763, 764)
  Autres intérêts et produits assimilés                   (76 sauf 761, 762, 763, 764, 766, 767)
  Reprises sur provisions et transferts de charges        (786, 796)
  Différences positives de change                         (766)
  Produits nets sur cessions de VMP                       (767)
CHARGES FINANCIÈRES (IV)
  Dotations aux amortissements, dépréciations et provisions  (686)
  Intérêts et charges assimilées                          (66 sauf 666, 667)
  Différences négatives de change                         (666)
  Charges nettes sur cessions de VMP                      (667)
PRODUITS EXCEPTIONNELS (V)
  Sur opérations de gestion                               (77 sauf 775, 777, 778)
  Sur opérations en capital                               (775, 777, 778)
  Reprises sur provisions et transferts de charges        (787, 797)
CHARGES EXCEPTIONNELLES (VI)
  Sur opérations de gestion                               (67 sauf 675, 678)
  Sur opérations en capital                               (675, 678)
  Dotations aux amortissements, dépréciations et provisions  (687)
CONTRIBUTIONS VOLONTAIRES EN NATURE
  Dons en nature                                          (870)
  Prestations en nature                                   (871)
  Bénévolat                                               (875)
CHARGES DES CONTRIBUTIONS VOLONTAIRES
  Secours en nature                                       (860)
  Mise à disposition gratuite de biens                    (861)
  Prestations en nature                                   (862)
  Personnel bénévole                                      (864)
```

> Les contributions volontaires en nature (classes 86 et 87) sont affichées **après** le résultat. Elles sont équilibrées entre elles (emplois = ressources) et n'impactent pas l'excédent ou le déficit. Cette section est obligatoire pour les associations dont le bénévolat est significatif.

### SCI (`sci`)

Les sous-comptes analytiques à 6 chiffres du référentiel SCI (lignes de la
déclaration 2072) sont agrégés dans la rubrique de leur compte parent.

```
PRODUITS D'EXPLOITATION (I)
  Loyers et fermages                                      (7083)
  Charges refacturées aux locataires                      (7085)
  Autres ventes et prestations de services                (70 sauf 7083, 7085)
  Subventions d'exploitation (ANAH…)                      (74)
  Reprises sur amortissements et provisions, transferts de charges  (78, 79 sauf 786, 787, 796, 797)
  Autres produits                                         (71, 72, 73, 75)
CHARGES D'EXPLOITATION (II)
  Achats et variation de stocks                           (60)
  Charges locatives et de copropriété                     (614)
  Entretien et réparations                                (615)
  Primes d'assurance                                      (616)
  Honoraires                                              (622)
  Autres charges externes                                 (61, 62 sauf 614, 615, 616, 622)
  Taxe foncière                                           (63512)
  Autres impôts et taxes                                  (63 sauf 63512)
  Charges de personnel                                    (64)
  Dotations aux amortissements et provisions              (68 sauf 686, 687)
  Autres charges de gestion courante                      (65)
PRODUITS FINANCIERS (III)
  Produits financiers                                     (76)
  Reprises sur provisions et transferts de charges        (786, 796)
CHARGES FINANCIÈRES (IV)
  Intérêts des emprunts                                   (661)
  Autres charges financières                              (66 sauf 661)
  Dotations financières aux amortissements et provisions  (686)
PRODUITS EXCEPTIONNELS (V)
  Sur opérations de gestion                               (77 sauf 775, 777, 778)
  Sur opérations en capital                               (775, 777, 778)
  Reprises sur provisions et transferts de charges        (787, 797)
CHARGES EXCEPTIONNELLES (VI)
  Sur opérations de gestion                               (67 sauf 675, 678)
  Sur opérations en capital                               (675, 678)
  Dotations aux amortissements et provisions              (687)
```

### Exports

- **CSV** : une ligne par rubrique (`Type ; Libellé ; N ; N-1`), séparateur `;`, UTF-8 BOM, virgule décimale.
- **ODS** : totaux de section en formules (somme des cellules des lignes, lignes « dont » exclues), résultats en références de cellules ; les valeurs sont aussi pré-calculées.

---

## Impression

Tous les rapports disposent d'un bouton **Imprimer** qui ouvre le dialogue d'impression du navigateur.

La feuille CSS `@media print` masque automatiquement :
- La barre de navigation
- Les boutons
- Les formulaires de sélection
- Les alertes

Pour obtenir un PDF, utiliser **Imprimer → Enregistrer en PDF** dans le navigateur.

---

## Rapprochement bancaire

**URL :** `/reconciliation/`

Interface de rapprochement entre les transactions bancaires importées (OFX) et les lignes d'écritures comptables.

### Workflow

1. Sélectionner le compte bancaire dans la liste déroulante
2. Pour chaque transaction non rapprochée, cliquer sur **Voir suggestions**
3. L'application propose les lignes d'écriture correspondantes (même montant, date proche)
4. Cliquer sur **Rapprocher** pour lier la transaction à la ligne

### Rapprochement automatique

Le bouton **Rapprochement automatique** lie automatiquement toutes les transactions qui ont **exactement une** correspondance pour le même montant **à la même date**.

Les transactions avec plusieurs correspondances ou sans correspondance restent en attente de traitement manuel.

### Scores de correspondance

| Situation | Score |
|-----------|-------|
| Même date exacte | 2 points |
| Date dans la fenêtre (±3 jours) | 1 point |

Les suggestions sont triées par score décroissant.

### Annuler un rapprochement

Un rapprochement peut être annulé depuis l'interface en cliquant sur **Annuler** sur les transactions déjà rapprochées (non visible par défaut — filtre les transactions `reconciled=True`).
