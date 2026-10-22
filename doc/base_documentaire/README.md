# Base documentaire comptable et assistant contextuel

Dossier de cadrage : il prépare une **base de connaissances comptables** et un **assistant de type chatbot**. Le logiciel et l'assistant s'appuient sur la même base. Aucun code n'est modifié à ce stade. Les fichiers de `exemples/` servent de gabarits. Ils seront déplacés vers `data/kb/` au moment de l'implémentation.

## Idée directrice

Une même connaissance, trois usages :

| Usage | Lecteur | Exemple |
|---|---|---|
| **Règles exécutables** | le logiciel (Python) | lignes du Bilan / CDR, contrôles de clôture, schémas d'écriture |
| **Fiches documentaires** | l'utilisateur dans l'UI, sans IA | aide sur la fiche d'un compte, lien « Pourquoi ? » sur une anomalie de clôture |
| **Contexte de l'assistant** | le modèle (Claude) | réponse sourcée, explication d'un écart, écriture proposée en brouillon |

Les trois usages partagent les **identifiants**. Par exemple, la fiche `C-03` (fonds dédiés) est citée :
- par le contrôle `asso.19x_jamais_debiteur` ;
- par le schéma d'écriture `asso.fonds_dedies.report` ;
- par l'assistant quand il répond.

Une règle n'est écrite qu'à un seul endroit.

## Couches par type de structure

Le plan comptable reste choisi **par instance** (`Instance.chart` : `asso` ou `sci`, cf. `app/tenant.py:current_chart`). La base est organisée en **référentiels empilés** :

```
pcg2026  (socle : PCG, règlement ANC 2014-03 modifié 2022-06)
 ├── asso_2018_06   (surcharge : règlement ANC 2018-06, recueil non lucratif 2026)
 └── sci            (surcharge : PCG + fiscalité foncière 2072, à l'IR par défaut)
```

Une instance `asso` voit `pcg2026` et `asso_2018_06`. En cas de conflit, la couche la plus spécifique l'emporte : 657, 754 et 756 n'ont pas le même sens dans les deux référentiels. Une instance `sci` voit `pcg2026` et `sci`.

## Sommaire

| # | Document | Contenu |
|---|---|---|
| 1 | [01_besoins.md](01_besoins.md) | Objectifs, utilisateurs, exigences fonctionnelles et non fonctionnelles, user stories, questions ouvertes |
| 2 | [02_corpus_fiches.md](02_corpus_fiches.md) | Format des fiches, référentiels, identifiants, sources, fraîcheur, découpage des PDF ANC |
| 3 | [03_regles_par_referentiel.md](03_regles_par_referentiel.md) | Règles déclaratives en YAML (logique Ekylibre adaptée) : plans, états, contrôles, schémas d'écriture, correspondance 2072 |
| 4 | [04_architecture_assistant.md](04_architecture_assistant.md) | Solution technique : API Claude et outils, recherche FTS5, contexte de page, actions vers l'UI, sécurité, coûts |
| 5 | [05_plan_mise_en_oeuvre.md](05_plan_mise_en_oeuvre.md) | Lots, ordre, critères d'acceptation, jeux d'évaluation |
| 6 | [06_inventaire_sources.md](06_inventaire_sources.md) | Inventaire des sources existantes, fiches à produire, lacunes (SCI notamment) |
| 7 | [07_analyse_paperasse.md](07_analyse_paperasse.md) | Annexe : analyse détaillée de paperasse, références aux fichiers, et tableau de ce qui est intégré où |
| — | [exemples/](exemples/) | Gabarits prêts à déplacer dans `data/kb/` (voir ci-dessous) |

### Contenu de `exemples/`

| Fichier | Nature |
|---|---|
| [referentiels.yml](exemples/referentiels.yml) | piles de référentiels par type de structure, comptes redéfinis (657 / 754 / 756), règles datées |
| [asso/etats.yml](exemples/asso/etats.yml), [sci/etats.yml](exemples/sci/etats.yml) | **générés** depuis `app/services/reports.py` : Bilan et CDR actuels en YAML (notation de type Ekylibre) |
| [asso/controles.yml](exemples/asso/controles.yml) | contrôles de clôture existants rattachés à leur fiche, et nouveaux invariants (19x, 191, Σ86 = Σ87…) |
| [asso/schemas.yml](exemples/asso/schemas.yml), [sci/schemas.yml](exemples/sci/schemas.yml) | modèles d'écriture : socle, asso, SCI (en brouillon) |
| [asso/comptes.yml](exemples/asso/comptes.yml) | surcouche du plan : sens normal, rôles (`compte_virement` = 581), fiches |
| [sci/correspondance_2072.yml](exemples/sci/correspondance_2072.yml) | **générée** depuis `data/plan_comptable_sci.json` : 83 comptes, 15 lignes 2072 |
| [fiches/C-03](exemples/fiches/C-03_fonds_dedies.md), [D-04](exemples/fiches/D-04_comptes_attente.md), [S-02](exemples/fiches/S-02_loyers_charges_refacturees.md) | trois fiches au format cible : asso publiée, socle à confirmer, SCI en brouillon |

## Sources mobilisées

- `doc/ref_compta/Base_compta.md` : synthèse ANC (fiches A-xx socle, B-xx entreprises, C-xx associations, D-xx banque), FAQ et limites. C'est la **matière première** des fiches.
- `doc/ref_compta/*.pdf` : PCG au 1er janvier 2026 (183 p.), recueil EIC 2026 (663 p.), recueil non lucratif 2026 (236 p.), guide de valorisation du bénévolat (24 p.). Ce sont les **textes primaires**, consultés par recherche plein texte.
- `doc/plan-comptable-SCI.pdf` et `data/plan_comptable_{asso,sci}.json` : plans de comptes actuels (783 et 576 comptes).
- Ekylibre, `config/accountancy/accountancy_mandatory_documents_fr_*.yml` : un fichier YAML par référentiel, où chaque ligne d'état est une expression de préfixes de comptes. Ce principe est repris, voir doc 3.
- paperasse (romainsimon) : 6 skills Markdown, scripts et évaluations, analysés en détail dans l'annexe (doc 7) et **intégrés** dans les docs 1 à 6. Il ne contient rien sur les associations ni sur la comptabilité des SCI. On en reprend les méthodes :
  - fraîcheur et registre des sources avec date de prochaine vérification ;
  - contexte obligatoire ;
  - format de réponse et niveaux de risque ;
  - calculs déterministes en centimes ;
  - contrôles de clôture, du FEC et de cohérence des états ;
  - évaluations avec et sans corpus, corrigées.

  On en écarte la correspondance des états codée en dur et plusieurs erreurs (775 au lieu de 757, plafond « BCE + 2 », abattement sur les parts de SCI).
- arrhes/PCG (CC0), source des données de paperasse : PCG 2026 en JSON (comptes obligatoires ou facultatifs, diff annuel) et en Markdown (articles balisés). C'est le socle `pcg2026` et le texte primaire `PCG26`. Il a servi à vérifier les citations du Livre IV.
