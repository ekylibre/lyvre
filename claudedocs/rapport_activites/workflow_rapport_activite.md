# Workflow — Rapport d'activité Seconde Nature

> **Statut : PLAN UNIQUEMENT.** Implémentation pas à pas. Aucun code ici.
> Exécuter ensuite avec `/sc:implement` **phase par phase**.
> Entrées : `besoins_rapport_activite.md`, `design_rapport_activite.md`,
> modèle `La_Matière_Rapport_Activités_2025.pdf`. Date : 2026-06-28.

## 1. Objectif

Générer dans l'app compta une page **« Rapport d'activité »** par **exercice
comptable**, en **identité visuelle Seconde Nature** (kraft / vert, motif
étiquette), reprenant la structure La Matière. Données **hybrides** : chiffres
live + textes éditables + tonnages éco-organismes (import xlsx). Sortie HTML
imprimable → PDF.

## 2. Conventions & décisions verrouillées

- **Stack** : Flask + Blueprints + Jinja2 + Bootstrap 5 (override tokens SN) + ECharts / SQLAlchemy + Alembic.
- **Montants** : centimes entiers ; **tonnages** : `Numeric(10,3)` (tonnes).
- **Multi-tenant** : nouvelles tables en base **tenant** ; **pas de FK vers `users`** (bind `meta`).
- **Migration** : head actuel = **`e2a9c4d77b51`** → `down_revision` du nouveau script.
- **Période** = **exercice comptable** (`FiscalYear` : `label/start_date/end_date/closed`).
- **Réutilisation** : `metrics_aggregator`, module Visibilité & Impact (`dashboard_service`,
  `MetricSnapshot`), `impact_engine`/`impact_factors`, `services/reports.py`
  (`build_bilan`, `build_compte_resultat`), `work_times`, ECharts (`from echarts import …`).
- **Décisions actées** (défauts du design §0) : import xlsx + table éditable ;
  trimestre éco indivisible rattaché par sa date de début ; contenus édités dans
  l'app ; photos uploadées ; bilan financier synthétique ; un rapport/exercice.
- **Identité** : palette kraft/vert (tokens `assets/css/custom.scss` du site), motif
  **étiquette kraft** pour section-tags & gros chiffres ; **flux Collecté ▶ Réemployé**
  pour l'impact.

## 3. Prérequis (hors code)

| Prérequis | Bloque | État |
|---|---|---|
| **Facteurs ADEME par matière** (meubles, D3E, jouets…) | Phase 3 (calcul CO₂) | à relever (placeholders « à valider » sinon) |
| `Declaration Ecoorganismes.xlsx` accessible | Phase 3 (import) | présent dans `claudedocs/rapport_activites/` |
| Exercice comptable défini (`FiscalYear`) | sélection période | existant |

> Les phases 0–2, 4–7 ne dépendent d'aucun prérequis externe.

---

## 4. Phases d'implémentation

### Phase 0 — Socle data, blueprint & gabarit identité
**Dépendances :** aucune.
1. `app/models/eco_declaration.py` (`EcoDeclaration`, unicité `(organism,material,quarter_label)`),
   `report_content.py` (`ReportContent`, FK `fiscal_years` CASCADE, unicité `(fiscal_year_id,block_key)`),
   `report_asset.py` (`ReportAsset`). Cf. design §4.
2. `app/models/__init__.py` — imports + `__all__`.
3. **Migration** (`create_table` ×3 + index/contraintes), `down_revision='e2a9c4d77b51'`, `flask db upgrade`.
4. `app/services/activity_report_service.py` — `ReportView` + `build_report(fy)` renvoyant
   les **sections ordonnées** (placeholders vides au départ) + catalogue des blocs narratifs.
5. `app/views/activity_report.py` — blueprint `activity_report` (`/rapport-activite`),
   routes `GET /` (sélecteur d'exercice) et `GET /print`.
6. `app/__init__.py` — `register_blueprint`. `base.html` — entrée nav.
7. `assets/css/report.scss` + `templates/activity_report/{report,print}.html` — gabarit
   scopé `.report` avec **tokens SN** (kraft/vert) + composants vides (cover, section-tag, sommaire).

**✅ Checkpoint 0 :** `flask db upgrade` OK ; `/rapport-activite/` se charge avec couverture +
sommaire + sections vides aux couleurs Seconde Nature ; `/print` rend en A4.

---

### Phase 1 — Contenus narratifs éditables
**Dépendances :** Phase 0.
1. Catalogue des blocs (`edito`, `rapport_moral`, `intro_*`, `gouvernance`, `partenaires`, `perspectives`…).
2. `GET|POST /rapport-activite/edit` (**admin**) — édition par exercice des `ReportContent`
   (titre + `body_html`), pattern du gabarit d'email de relance. Template `edit.html`.
3. `build_report` — injecter les blocs narratifs dans les sections ; `report.html` les rend.

**✅ Checkpoint 1 :** éditer l'édito et le rapport moral d'un exercice → textes affichés dans le rapport.

---

### Phase 2 — Sections live (vie associative, boutique, communication)
**Dépendances :** Phases 0–1. **Aucune dépendance externe.**
1. `activity_report_service` — agréger sur l'exercice :
   - **Vie associative** : adhérents + évolution, bénévoles + heures valorisées
     (réutiliser `metrics_aggregator.social` / `work_times`), adhésions HelloAsso.
   - **Boutique & ventes** : CA POS (`orders`) + Vinted (`MetricSnapshot` manuel).
   - **Communication** : métriques du module Visibilité & Impact (web GA4, groupe FB, Vinted).
2. **Graphes ECharts** : évolution adhérents, CA par canal (réutiliser le pattern `dashboard.py`).
3. `report.html` — cartes `figure-tag` (gros chiffres sur étiquette) + `chart-block`.

**✅ Checkpoint 2 :** sections vie associative / boutique / communication affichent chiffres
réels + graphes pour l'exercice sélectionné.

---

### Phase 3 — Éco-organismes & impact (cœur)
**Dépendances :** Phases 0–2 ; facteurs ADEME (placeholders acceptés).
1. `app/services/eco_declaration_import.py` — `import_eco_xlsx(stream)` : parse la feuille
   `Bilan` (matière × trimestre, lignes Entrant/Sortant + facturation), upsert `eco_declarations`,
   retour `{imported, updated, errors}`.
2. `GET|POST /rapport-activite/eco` (**admin**) — **import** (`POST /eco/import`) + **table éditable**
   des tonnages. Template `eco.html`.
3. Étendre `impact_factors` : facteurs **par matière** (`reemploi.<matiere>.co2e_per_t`),
   seed ADEME « à valider ».
4. `activity_report_service.eco_impact(fy)` — agrège les trimestres dont `period_start ∈ exercice` :
   tonnage collecté/réemployé, **taux de réemploi**, **CO₂ évité** (Σ sortant × facteur matière),
   financement éco-organismes.
5. `report.html` — composant **`flow-reuse`** (Collecté ▶ Réemployé + jauge taux) + chart tonnages
   par matière + équivalents.

**✅ Checkpoint 3 :** importer le `.xlsx` → tonnages en base, corrigeables ; section impact affiche
collecté / réemployé / taux / CO₂ ; financement éco repris.

---

### Phase 4 — Bilan financier de l'exercice
**Dépendances :** Phase 0.
1. `activity_report_service` — appeler `build_compte_resultat(fy, fy_prev)` + `build_bilan(fy, fy_prev)`
   et en extraire une **synthèse** (produits / charges / résultat + financement éco-organismes).
2. `report.html` — section bilan financier (synthèse + commentaire éditable).

**✅ Checkpoint 4 :** synthèse produits/charges/résultat de l'exercice (et N-1) affichée, cohérente
avec les rapports comptables existants.

---

### Phase 5 — Photos & frise
**Dépendances :** Phases 0–1.
1. `report_assets` — `GET|POST /rapport-activite/photos` (**admin**) : upload vers
   `instance/uploads/report/<fy>/`, légendes ; slots (`cover`, `section_impact`…). Template `photos.html`.
2. `report.html` — couverture avec photo + `photo-full` dans les sections ; **frise/perspectives**
   éditable (timeline).

**✅ Checkpoint 5 :** uploader une photo de couverture → visible ; frise rendue.

---

### Phase 6 — Mise en page & impression (frontend-design)
**Dépendances :** Phases 0–5.
1. `report.scss` / `print.html` — finaliser : **étiquette kraft** (section-tag avec coin perforé +
   ficelle `--red`), **couverture** (photo + étiquette titre + logo), **sommaire numéroté**,
   `figure-tag`, `stat-band`, `partner-grid`, `quote`.
2. **Impression A4** : `@page`, sauts de page (`break-before: page` par section, `break-inside: avoid`
   sur cartes), masquer la nav (`@media print`), bouton « Imprimer / PDF ».
3. Plancher qualité : focus clavier, `prefers-reduced-motion` (animations écran uniquement).

**✅ Checkpoint 6 :** aperçu impression A4 propre, sauts de page corrects, identité Seconde Nature
fidèle (étiquettes, kraft/vert).

---

### Phase 7 — Finitions & tests
**Dépendances :** Phases 0–6.
1. **Tests** `tests/test_activity_report.py` (client `LOGIN_DISABLED`, style existant) :
   - `import_eco_xlsx` : parsing du `Bilan` (matières, entrant/sortant, facturation, lignes vides).
   - `eco_impact` : tonnage agrégé sur l'exercice, taux de réemploi, CO₂ (facteur manquant → défaut).
   - `report_contents` : édition + rendu d'un bloc.
   - `build_report` : assemblage des sections (live + narratif + éco) pour un exercice.
   - intégration bilan : synthèse cohérente avec `build_compte_resultat`.
2. **v2 / backlog** (documenté) : PDF serveur `weasyprint`, **archivage/versionnage** consultable,
   **pro-rata** des trimestres éco, lecture optionnelle des `_data/*.yml` du site.

**✅ Checkpoint 7 :** `pytest` vert ; parcours complet (éditer textes → importer tonnages →
sélectionner exercice → consulter → imprimer).

---

## 5. Ordre d'exécution & parallélisation

`0 → 1 → 2 → 3 → 4 → 5 → 6 → 7`.

- **Valeur rapide** : 0→2 livre un rapport avec couverture, textes et sections live.
- **Indépendances après Phase 1** : Phase 2 (live), Phase 4 (financier), Phase 5 (photos)
  parallélisables ; Phase 3 (éco) autonome (sauf facteurs). Phase 6 consomme tout.
- **Prérequis non bloquants** : sans facteurs ADEME, faire la Phase 3 avec placeholders « à valider ».

## 6. Récapitulatif fichiers

**Créés** : `app/models/{eco_declaration,report_content,report_asset}.py` ;
`app/services/{eco_declaration_import,activity_report_service}.py` ;
`app/views/activity_report.py` ;
`app/templates/activity_report/{report,print,edit,eco,photos}.html` ;
`assets/css/report.scss` ; `migrations/versions/<rev>_add_activity_report_tables.py` ;
`tests/test_activity_report.py`.

**Modifiés** : `app/models/__init__.py` ; `app/__init__.py` (blueprint) ;
`app/templates/base.html` (nav) ; seed facteurs matière dans `impact_engine`/factors.

## 7. Points à confirmer avant exécution

1. **Valeurs ADEME par matière** (sinon placeholders « à valider »).
2. **Dates d'exercice** vs trimestres éco (règle « trimestre indivisible »).
3. **Emplacement nav** : entrée dédiée vs bouton depuis le dashboard Impact.
4. **Bilan** : niveau de détail (synthèse vs compte de résultat complet en annexe).
5. **Double comptage** : CA boutique (POS/Vinted) vs ventes/dons de l'éco-déclaration — périmètres disjoints à confirmer.

**Prochaine étape** : `/sc:implement claudedocs/rapport_activites/workflow_rapport_activite.md`
(commencer par la Phase 0).
