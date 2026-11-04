# Jeu d'essai agricole : valeurs attendues à relire

> Lot AG1.f (AGD2, AGD5). Exploitations **fictives** tirées de FEC réels de cabinets (anonymisés, montants × coefficient, dates décalées d'un an)
> ou synthétiques (D). Valeurs calculées **directement sur les fichiers** (`tests/fixtures/agri/*/expected.json`), indépendamment des états de Lyvre ;
> les tests vérifient que le compte de résultat, le bilan et les soldes de Lyvre les retrouvent.
> Générées par `scripts/agri_fixtures/anonymize.py` et `build_synthetic.py` ; données réelles jamais versionnées.

## A_earl_porcs_rs — EARL des Pins (fictive)

Élevage porcin et maïs, réel simplifié, exercice 01/02 → 31/01. Forme EARL, IR, régime BA `simplified`.
Comptes de l'ancien plan sans correspondance (reclassés en 658 / 758) : {'791': 1}.
Associés (comptes 455) : 2.

**Exercice 2024-02-01 → 2025-01-31** (6992 lignes, total débit = crédit = 13 235 403,64 €)

| Agrégat | Montant |
|---|---:|
| Résultat (classe 7 − classe 6) | 3 528,87 € |
| Ventes (70) | 1 439 456,72 € |
| dont ventes d'animaux (7014) | 725 676,39 € |
| Subventions d'exploitation (74) | 68 036,07 € |
| Production stockée (71) | -33 161,98 € |
| Achats d'animaux (60117) | 84 517,54 € |
| Fermages (6131) | 20 780,13 € |
| Cotisations MSA de l'exploitant (646) | 17 854,84 € |
| Dotations aux amortissements (6811) | 101 626,38 € |
| Biens vivants immobilisés, solde (24) | 50 296,39 € |
| Stocks et en-cours, solde (3) | 399 970,77 € |

## B_scea_legumes_rn — SCEA du Ruisseau (fictive)

Légumes de plein champ et semences sous contrat, réel normal, deux exercices consécutifs. Forme SCEA, IR, régime BA `normal`.
Comptes de l'ancien plan sans correspondance (reclassés en 658 / 758) : {'791': 1}.
Associés (comptes 455) : 2.

**Exercice 2024-02-01 → 2025-01-31** (3940 lignes, total débit = crédit = 9 926 768,18 €)

| Agrégat | Montant |
|---|---:|
| Résultat (classe 7 − classe 6) | 14 792,16 € |
| Ventes (70) | 922 863,73 € |
| dont ventes d'animaux (7014) | 0,00 € |
| Subventions d'exploitation (74) | 135 283,80 € |
| Production stockée (71) | 0,00 € |
| Achats d'animaux (60117) | 0,00 € |
| Fermages (6131) | 1 609,98 € |
| Cotisations MSA de l'exploitant (646) | 4 072,38 € |
| Dotations aux amortissements (6811) | 171 017,57 € |
| Biens vivants immobilisés, solde (24) | 158 475,08 € |
| Stocks et en-cours, solde (3) | 5 181,26 € |

**Exercice 2025-02-01 → 2026-01-31** (953 lignes, total débit = crédit = 1 400 419,57 €)

| Agrégat | Montant |
|---|---:|
| Résultat (classe 7 − classe 6) | -97 413,57 € |
| Ventes (70) | 122 907,83 € |
| dont ventes d'animaux (7014) | 0,00 € |
| Subventions d'exploitation (74) | 21 801,97 € |
| Production stockée (71) | 0,00 € |
| Achats d'animaux (60117) | 0,00 € |
| Fermages (6131) | 0,00 € |
| Cotisations MSA de l'exploitant (646) | 1 629,14 € |
| Dotations aux amortissements (6811) | 0,00 € |
| Biens vivants immobilisés, solde (24) | 0,00 € |
| Stocks et en-cours, solde (3) | 0,00 € |

## C_gaec_ateliers — GAEC des Trois Chênes (fictif)

Grandes cultures et légumes, 3 associés, ateliers analytiques (export Isacompta). Forme GAEC, IR, régime BA `simplified`.
Associés (comptes 455) : 4.

**Exercice 2024-02-01 → 2025-01-31** (1238 lignes, total débit = crédit = 6 928 006,35 €)

| Agrégat | Montant |
|---|---:|
| Résultat (classe 7 − classe 6) | -87 242,11 € |
| Ventes (70) | 596 184,67 € |
| dont ventes d'animaux (7014) | 0,00 € |
| Subventions d'exploitation (74) | 46 639,54 € |
| Production stockée (71) | 0,00 € |
| Achats d'animaux (60117) | 0,00 € |
| Fermages (6131) | 29 600,62 € |
| Cotisations MSA de l'exploitant (646) | 129,52 € |
| Dotations aux amortissements (6811) | 462,62 € |
| Biens vivants immobilisés, solde (24) | 0,00 € |
| Stocks et en-cours, solde (3) | 0,00 € |

## D_micro_rfa — Les Jardins du Coteau (fictifs)

Maraîchage en vente directe, micro-BA, remboursement forfaitaire agricole (synthétique). Forme EI, IR, régime BA `micro`.

| Agrégat | Montant |
|---|---:|
| Recettes encaissées | 33 092,20 € |
| dont recettes retenues au micro-BA | 31 592,20 € |
| dont recettes exclues (cession de matériel) | 1 500,00 € |
| Dépenses | 9 544,48 € |
| Opérations | 91 |

## À vérifier par l'expert-comptable

- Vraisemblance des agrégats au regard des dossiers d'origine (ordres de grandeur, signe du résultat, poids des aides).
- Correspondance ancien plan → titre 5 appliquée (`data/agri_pcga1986_map.json`), en particulier 704 → 7014, 6011 → 60111, 242 → 241, 745 conservé.
- Ancien 791 (transferts de charges) reclassé en 758 : traitement à confirmer.
- D : ventilation des recettes exclues du micro-BA (cession de matériel exclue ; aides PAC retenues).
