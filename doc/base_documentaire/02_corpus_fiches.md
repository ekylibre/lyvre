# 2. Corpus : fiches, référentiels, sources

## 2.1 Trois niveaux de connaissance

| Niveau | Forme | Rôle | Exemple |
|---|---|---|---|
| **Fiches** | Markdown + en-tête YAML, 1 fiche = 1 sujet | Explication, exemple d'écriture, implications. Lisible par un humain et injectée telle quelle dans le contexte de l'assistant | `C-03` Fonds dédiés |
| **Règles** | YAML par référentiel (doc 3) | Ce que le logiciel exécute : états, contrôles, schémas d'écriture, correspondances | `asso/controles.yml#19x_jamais_debiteur` |
| **Textes primaires** | Textes ANC découpés par article : Markdown arrhes/PCG pour le PCG et le recueil EIC, PDF pour le recueil non lucratif | Preuve et citation exacte ; l'assistant y fait une recherche quand une fiche ne suffit pas | PCG 2026, art. 1031-3 |

Les fiches sont **courtes et normatives**. Les textes primaires sont **longs et exhaustifs**. Les fiches renvoient aux textes, les règles renvoient aux fiches.

## 2.2 Arborescence cible (implémentation)

```
data/kb/
├── referentiels.yml              # pile des référentiels, plan de comptes de chacun
├── sources.yml                   # registre des sources (URL, version, récupération, prochaine vérification)
├── pcg/                          # socle open data (arrhes/PCG, CC0) : pcg_2026.json, pcg_20260101.md, recueil_20260101.md
├── fiches/
│   ├── pcg2026/        A-01…A-15, D-01…D-06    (socle + banque)
│   ├── eic/            B-01…B-03               (entreprises, non chargé pour asso/sci)
│   ├── asso_2018_06/   C-01…C-09
│   └── sci/            S-01…                   (à rédiger, cf. doc 6)
├── regles/
│   ├── pcg2026/   controles.yml  schemas.yml
│   ├── asso_2018_06/  etats.yml  controles.yml  schemas.yml
│   └── sci/       etats.yml  controles.yml  schemas.yml  correspondance_2072.yml
├── faq/                          # questions-réponses courtes (amorce : FAQ de Base_compta.md)
└── primaires/                    # PDF de doc/ref_compta (ou lien), + extraits générés (gitignorés)
```

`data/plan_comptable_asso.json` et `data/plan_comptable_sci.json` restent où ils sont. `referentiels.yml` les référence, rien n'est déplacé. Exemple complet : [exemples/referentiels.yml](exemples/referentiels.yml).

Le socle `pcg2026` a désormais son propre plan, `data/kb/pcg/pcg_2026.json` (arrhes/PCG). Il ne remplace pas les plans d'instance. Il sert à trois choses :
- vérifier qu'un compte cité par une fiche du socle existe dans le PCG ;
- marquer les comptes obligatoires ou facultatifs (`system: minimal | facultatif`) ;
- signaler, à la mise à jour annuelle, les comptes ajoutés, supprimés ou modifiés (`diff`), à reporter dans les plans asso et SCI.

## 2.3 Format d'une fiche

```markdown
---
id: C-03
titre: Fonds dédiés
referentiels: [asso_2018_06]          # visibilité
comptes: ["194", "195", "196", "6894", "6895", "6896", "7894", "7895", "7896"]
articles: ["2018-06 art. 132-1", "2018-06 art. 132-2", "2018-06 art. 132-3", "2018-06 art. 132-4", "2018-06 art. 431-6"]
sources: [REC-NL26]                   # clés de sources.yml
mots_cles: [subvention non utilisée, report, projet défini, 689, 789]
risque: expert                        # aucun | attention | expert (⚠️)
statut: publie                        # brouillon | a_confirmer | publie
verifie_le: 2026-10-22
verifie_par: synthese-ANC             # personne ou document
regles: [asso.controles.19x_jamais_debiteur, asso.schemas.fonds_dedies_report]
ecrans: ["/fiscal-years/*/closing"]     # pages où la fiche est suggérée
---

## Résumé
…
## Exemple
| Compte | Débit | Crédit |
…
## Référence
…
## Dans le logiciel
…
```

Règles d'écriture :
- **Une fiche fait au plus 600 mots** environ. Un sujet plus long se découpe.
- **Au moins un exemple d'écriture** en tableau D/C, avec des comptes du référentiel de la fiche.
- La **section « Dans le logiciel »** dit quel écran ou quel contrôle applique la règle. C'est la reprise des « Implications pour le logiciel » de `Base_compta.md`.
- **Pas de seuil ni de taux** non sourcé sur une source primaire. Les seuils vont dans les règles (doc 3), avec leur source et leur date d'effet.

Exemples complets : [exemples/fiches/](exemples/fiches/).

## 2.4 Identifiants

| Préfixe | Référentiel | Origine |
|---|---|---|
| `A-xx` | `pcg2026` (socle) | `Base_compta.md` partie A |
| `B-xx` | `eic` | partie B (non chargé en asso ou SCI ; prêt pour une future couche entreprise) |
| `C-xx` | `asso_2018_06` | partie C |
| `D-xx` | `pcg2026` | partie D (banque, rapprochement, 471, 580) |
| `S-xx` | `sci` | **à rédiger** (doc 6) |
| `FAQ-xx` | selon la question | FAQ de `Base_compta.md` |

Les identifiants sont **stables**. Une fiche remplacée garde son id et change de version : l'historique est dans git. Une fiche supprimée laisse une fiche `statut: retiree` qui pointe vers sa remplaçante, pour que les anciens liens et conversations restent lisibles.

## 2.5 Résolution par type de structure

On calcule la pile de référentiels d'une instance à partir de `Instance.chart` :

```
asso → [pcg2026, asso_2018_06]
sci  → [pcg2026, sci]
```

1. **Visibilité.** Une fiche est visible si l'un de ses `referentiels` est dans la pile.
2. **Surcharge.** Une fiche peut déclarer `remplace: A-xx`. Elle masque alors, dans cette pile, la fiche du socle sur le même sujet.
3. **Comptes au sens différent.** `referentiels.yml` liste les comptes dont le libellé change selon la couche : 657, 754 et 756 en asso. Le libellé affiché et celui donné à l'assistant viennent **du plan de l'instance**, jamais du PCG générique.
4. **Date d'effet.** Une règle ou une fiche peut porter `applicable: {exercices_ouverts_depuis: 2025-01-01}`, par exemple le règlement 2022-06. Pour un exercice, la résolution dépend donc aussi de `FiscalYear.start_date`. Ekylibre fait de même avec un `accounting_system` par exercice (`fr_pcg82`, `fr_pcg2023`…). Nous gardons un seul référentiel par couche, avec des règles datées.

## 2.6 Registre des sources (`sources.yml`)

Les clés reprennent celles de `Base_compta.md` (`PCG26`, `REC-EIC26`, `REC-NL26`, `PDC-ANC`, `LPF`, `BOFIP`, `QONTO`). C'est le principe de `paperasse/data/sources.json`.

```yaml
REC-NL26:
  titre: Recueil des normes comptables du secteur non lucratif 2026
  editeur: ANC
  url: https://www.anc.gouv.fr/files/anc/files/1_Normes_fran%C3%A7aises/Reglements/Recueils/Recueil_Secteur-non-lucratif/2026/Recueil-non-lucratif-2026.pdf
  fichier: doc/ref_compta/Recueil-non-lucratif-2026.pdf
  pages: 236
  version: "2026-01-01"
  recupere_le: 2026-10-23
  frequence: annuelle          # nouveau recueil chaque janvier
  prochaine_verif: 2027-01-15  # paperasse fiscaliste/data/sources.json : next_check
  instructions: "Télécharger le recueil daté du 1er janvier, relancer kb_build.py, comparer les extraits."
  licence: publication officielle

PCG26:
  titre: Règlement ANC 2014-03, version consolidée au 1er janvier 2026
  fichier: doc/ref_compta/PCG--1er-janvier-2026.pdf
  texte: https://github.com/arrhes/PCG/blob/main/sources/2026/pcg_20260101.md   # Markdown CC0, articles balisés
  plan: https://github.com/arrhes/PCG/blob/main/versions/2026/pcg_2026.json     # 838 comptes, system minimal|facultatif, diff 2025→2026
  prochaine_verif: 2027-01-15
```

Un script `scripts/kb_check.py` (lot 1) contrôle :
- que chaque fiche a ses clés ;
- que ses `sources` existent ;
- que ses `comptes` existent dans le plan de chaque référentiel visé ;
- que chaque `regles:` citée existe ;
- que `verifie_le` a moins de 12 mois (sinon avertissement) ;
- qu'aucune source n'a dépassé sa `prochaine_verif`. Sinon le contrôle échoue, comme `update_data.py` dans paperasse (doc 7, P8).

Il tourne dans `make check`.

## 2.7 Textes primaires : découpage

Les PDF sont volumineux : 183 + 663 + 236 + 24 pages. On ne les injecte jamais en entier.

1. **Extraction.** Pour `PCG26` et `REC-EIC26`, on reprend le Markdown d'arrhes/PCG (CC0) : les titres sont conservés et les articles balisés `**Art. n**` ou `***Art. n***` (doc 7 §7.3). Pour `REC-NL26` et le guide du bénévolat, on extrait avec PyMuPDF, déjà en dépendance (`pymupdf`, utilisé par `invoice_reader.py`), à raison d'un texte par page.
2. **Découpage par article.** Les recueils numérotent leurs articles (`Art. 132-1`, `1031-3`). Une expression régulière sur les en-têtes d'article donne des extraits de 200 à 800 mots. Chaque extrait porte `source`, `article`, `page_debut`, `page_fin`, `titre_section`. À défaut d'article, on découpe par titre ou par page.
3. **Index** : table SQLite FTS5 dans la méta-base, partagée par toutes les instances et en lecture seule. Voir doc 4 §4.3.
4. **Régénération** par `scripts/kb_build.py` à chaque nouveau recueil. Les extraits générés ne sont pas versionnés, seul le script l'est.

L'assistant cite un extrait sous la forme `[REC-NL26 art. 132-1, p. 87]`. L'UI transforme la citation en lien vers le PDF (`#page=87`).

## 2.8 Fraîcheur et revue

| Événement | Action |
|---|---|
| Nouveau recueil ANC (janvier) | Mettre à jour `sources.yml`, relancer `kb_build.py`, relire les fiches dont les articles ont changé (diff des extraits) |
| `verifie_le` de plus de 12 mois | `kb_check` avertit ; bandeau « à revérifier » sur la fiche ; l'assistant ajoute une réserve |
| Fiche `a_confirmer` | Visible dans l'UI avec un bandeau ; **non** injectée dans le contexte de l'assistant, qui ne peut que la citer comme « non confirmée » |
| Changement de règle (doc 3) | Les tests des états (`tests/test_reports_charts.py`) doivent rester verts ; une règle modifiée sans fiche à jour fait échouer `kb_check` |
