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

## Bilan

**URL :** `/reports/bilan`

Bilan conforme au modèle PCA (Plan Comptable Associatif), avec comparaison exercice N / N-1.

### Structure de l'actif

```
ACTIF IMMOBILISÉ
  Immobilisations incorporelles
    Frais d'établissement                    (201x)
    Frais de recherche et développement      (203x)
    Donations temporaires d'usufruit         (204x)
    Concessions, brevets, licences…          (205x)
    Immobilisations incorporelles en cours   (232x)
  Immobilisations corporelles
    Terrains                                 (211x)
    Constructions                            (213x, 214x)
    Installations techniques, matériel…      (215x)
    Immobilisations corporelles en cours     (231x)
  Biens reçus par legs ou donations          (24x)
  Immobilisations financières
    Participations et créances rattachées    (261x, 267x)
    Autres titres immobilisés                (271x, 272x)
    Prêts                                    (274x)
    Autres                                   (275x, 276x)

ACTIF CIRCULANT
  Stocks et en-cours                         (31x–37x)
  Créances clients, usagers                  (411, 413, 416, 418)
  Créances reçues par legs ou donations      (461)
  Autres créances                            (40x, 42x–47x)
  Valeurs mobilières de placement            (50x)
  Disponibilités                             (51x, 53x, 54x)
  Charges constatées d'avance                (486)
```

### Structure du passif

```
FONDS PROPRES
  Fonds propres sans droit de reprise
    Fonds propres statutaires                (1021, 1022)
    Fonds propres complémentaires            (1023, 1024, 1025)
  Fonds propres avec droit de reprise
    Fonds statutaires                        (1032)
    Fonds propres complémentaires            (1034, 1035)
  Écarts de réévaluation                     (105x)
  Réserves                                   (106x)
  Report à nouveau                           (110, 115, 119)
  Excédent ou déficit de l'exercice          (120, 129)
  Fonds propres consomptibles                (108x)
  Subventions d'investissement               (131x, 138, 139)
  Provisions réglementées                    (14x)

FONDS REPORTÉS ET DÉDIÉS  ← spécifique associations
  Fonds reportés liés aux legs ou donations  (191, 192)
  Fonds dédiés                               (193, 194, 195, 196)

PROVISIONS
  Provisions pour risques                    (151)
  Provisions pour charges                    (152, 153, 155, 157, 158)

DETTES
  Emprunts obligataires                      (163)
  Emprunts établissements de crédit          (164)
  Emprunts et dettes financières diverses    (165, 167, 168)
  Dettes fournisseurs et comptes rattachés   (401–408)
  Dettes des legs ou donations               (466)
  Dettes fiscales et sociales                (43x, 44x)
  Autres dettes                              (419, 46x, 47x)
  Produits constatés d'avance                (487)
```

---

## Compte de résultat

**URL :** `/reports/compte-de-resultat`

Compte de résultat conforme au modèle PCA, avec comparaison N / N-1.

### Structure

```
PRODUITS D'EXPLOITATION (I)
  Cotisations                                     (756)
  Ventes de biens et services
    Ventes de biens                               (701, 702, 703, 707)
      dont ventes de dons en nature               (7073)
    Ventes de prestations de services             (704, 705, 706, 708)
      dont parrainages                            (7063)
  Produits de tiers financeurs
    Concours publics et subventions d'expl.       (74)
    Versements fondateurs / dotation consomptible (753)
    Ressources liées à la générosité du public
      Dons manuels                                (75411)
      Mécénats                                    (7542)
      Legs, donations et assurances-vie           (7543)
    Contributions financières                     (755)
  Reprises sur amortissements, provisions…        (781, 786, 787, 789)
  Utilisations des fonds dédiés                   (789)
  Autres produits                                 (71, 72, 75, 79)

CHARGES D'EXPLOITATION (II)
  Achats de marchandises                          (607)
  Variation de stocks                             (603, 6037)
  Autres achats et charges externes               (60x, 61x, 62x)
  Aides financières                               (657)
  Impôts, taxes et versements assimilés           (63x)
  Salaires et traitements                         (641, 642)
  Charges sociales                                (645, 647, 648)
  Dotations aux amortissements et dépréciations   (681, 686)
  Dotations aux provisions                        (6815, 6816, 6817)
  Reports en fonds dédiés                         (689)  ← spécifique associations
  Autres charges                                  (65x, 67x, 68x, 69x)

1 — RÉSULTAT D'EXPLOITATION (I - II)

PRODUITS FINANCIERS (III)
  De participations                               (761)
  Autres intérêts et produits assimilés           (762–768)
  Produits nets sur cessions de VMP               (767)

CHARGES FINANCIÈRES (IV)
  Intérêts et charges assimilées                  (661, 664–668)

2 — RÉSULTAT FINANCIER (III - IV)
3 — RÉSULTAT COURANT avant impôts (I-II+III-IV)

PRODUITS EXCEPTIONNELS (V)                        (771, 775, 777, 787)
CHARGES EXCEPTIONNELLES (VI)                      (671, 675, 678, 687)

4 — RÉSULTAT EXCEPTIONNEL (V - VI)
   Participation des salariés (VII)               (691)
   Impôts sur les bénéfices (VIII)                (695, 696, 699)

Total des produits (I+III+V)
Total des charges (II+IV+VI+VII+VIII)
6 — EXCÉDENT / DÉFICIT

─────────────────────────────────────────────────────
CONTRIBUTIONS VOLONTAIRES EN NATURE  ← hors résultat
  Dons en nature                                  (870)
  Prestations en nature                           (871)
  Bénévolat                                       (875)

CHARGES DES CONTRIBUTIONS VOLONTAIRES EN NATURE
  Secours en nature                               (860)
  Mise à disposition gratuite de biens            (861)
  Prestations en nature                           (862)
  Personnel bénévole                              (864)
```

> Les contributions volontaires en nature (classes 86 et 87) sont affichées **après** le résultat. Elles sont équilibrées entre elles (emplois = ressources) et n'impactent pas l'excédent ou le déficit. Cette section est obligatoire pour les associations dont le bénévolat est significatif.

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
