# Workflow — Tableau de bord « Visibilité & Impact »

> **Statut : PLAN UNIQUEMENT.** Décrit l'implémentation pas à pas.
> Aucun code ici. Exécuter ensuite avec `/sc:implement` **phase par phase**.
> Entrées : `besoins_dashboard_visibilite_impact.md`, `design_dashboard_visibilite_impact.md`,
> `config_acces_ga4_facebook.md`. Date : 2026-06-27.

## 1. Objectif

Construire la page **« Visibilité & Impact »** (4 dimensions : visibilité,
environnemental, social, économique), avec dashboard live + rapport exportable,
en intégrant GA4 (auto), HelloAsso/POS/bénévoles (interne), et Vinted/groupe
Facebook (saisie manuelle). Cf. design pour l'architecture.

## 2. Conventions & décisions verrouillées

- **Stack** : Flask + Blueprints + Jinja2 + HTMX + Bootstrap 5 / SQLAlchemy + Alembic.
- **Montants** : centimes entiers (`INTEGER`/`Numeric`), affichage `| euros`.
- **Multi-tenant** : nouvelles tables dans la base **tenant** (bind par défaut).
- **Migration** : head actuel = **`c7f2e9b1a4d3`** → `down_revision` du nouveau script.
- **Réutilisation** : `external_config` (registre → UI auto), `SyncJob`, `list_filters`,
  `work_times`, `membership_status`, `orders`, `helloasso_*`.
- **Décisions actées** : facteurs env. = **ADEME Base Empreinte** ; Vinted + groupe FB
  = **saisie manuelle** ; Facebook v1 = **abonnés seulement** (insights = v2) ;
  cadence = **mensuelle** ; objectifs (`metric_targets`) = **v2**.
- **Stockage** : interne (éco/social) + environnemental = **calculés live** ; GA4 +
  Facebook + manuel = **stockés** (`metric_snapshots`). On ne duplique pas le recalculable.

## 3. Dépendances externes (hors code)

| Prérequis | Bloque | État |
|---|---|---|
| Identifiants **GA4** (compte de service + accès Viewer) | Phase 5 | à fournir (cf. doc config) |
| **Page Access Token** Facebook longue durée | Phase 6 | à fournir |
| Valeurs **ADEME** (poids, CO₂, eau) | Phase 3 (saisie des facteurs) | à relever |

> Les phases 0–4 et 7–8 **ne dépendent d'aucun accès externe** : on peut livrer un
> dashboard utile (interne + environnemental + saisie manuelle + rapport) avant
> même d'avoir GA4/Facebook.

---

## 4. Phases d'implémentation

### Phase 0 — Socle data & registre (fondations)
**Dépendances :** aucune.
1. `app/models/metric_snapshot.py` — `MetricSnapshot` (cf. design §3.1) : unicité
   `(source, metric_key, period_start, granularity)`, FK `users` ON DELETE SET NULL.
2. `app/models/impact_factor.py` — `ImpactFactor` (design §3.2) : `key` unique, `value`
   `Numeric(18,6)`, `source_label`/`source_url`.
3. `app/models/__init__.py` — importer + ajouter à `__all__`.
4. `app/models/sync_job.py` — ajouter `SYNC_KIND_METRICS = "metrics"`.
5. `app/services/metric_catalog.py` — registre déclaratif (design §4) : dataclass
   `Metric` + liste `METRICS` + helpers `by_dimension()`, `manual_metrics()`, `get(key)`.
6. **Migration Alembic** (`flask db migrate` puis relire) : `create_table metric_snapshots`
   (+ index `(metric_key, period_start)`, contrainte unique), `create_table impact_factors`
   (+ index unique `key`). `down_revision = 'c7f2e9b1a4d3'`.
7. `flask db upgrade`.

**✅ Checkpoint 0 :** `flask db upgrade` OK ; `python -c "from app.models import MetricSnapshot, ImpactFactor"` ; `metric_catalog.METRICS` chargé sans doublon de clé.

---

### Phase 1 — Blueprint, période & dashboard squelette
**Dépendances :** Phase 0.
1. `app/services/dashboard_service.py` — `Period` (start/end/label/previous, construit
   depuis les query args via `list_filters`), `Kpi`, `DashboardView` ; `build_dashboard(period)`
   renvoyant pour l'instant des **sections vides** (placeholders) + `sources_status`.
2. `app/views/impact.py` — blueprint `impact` (`url_prefix="/impact"`), route `GET /`
   (sélecteur de période mois/trimestre/année/plage, comparaison période précédente).
3. `app/__init__.py` — `register_blueprint(impact_bp)`.
4. `app/templates/impact/dashboard.html` — 4 sections + cartes KPI (macro réutilisable)
   + bandeau fraîcheur ; **états vides** propres. HTMX pour recharger au changement de période.
5. `app/templates/base.html` — entrée nav **1er niveau « Visibilité & Impact »**
   (`active` si `request.blueprint == 'impact'`).

**✅ Checkpoint 1 :** page `/impact/` se charge, sélecteur de période fonctionnel,
4 sections rendues (vides), entrée de menu active.

---

### Phase 2 — Interne : économique + social (live) ⭐ première valeur
**Dépendances :** Phases 0–1. **Aucune dépendance externe.**
1. `app/services/metrics_aggregator.py` :
   - `economic(period)` → `pos_revenue_cents` (`Order.amount_total_cents` filtré
     `date_order`), `donations_cents` / `memberships_cents` (HelloAsso `amount_total_cents`
     / `payment` selon type d'item, filtré `date`).
   - `social(period)` → `active_volunteers` (distinct `WorkTime.entity_id`),
     `volunteer_hours` + `volunteer_value_cents` (somme `hours` / `valuation_cents`),
     `members_count`, `renewal_rate` (via `membership_status`).
2. `dashboard_service` — brancher éco + social ; calcul `delta_pct` (vs `period.previous`)
   et `trend` (N derniers mois, en bouclant l'agrégateur par mois).
3. `dashboard.html` — formats `| euros`, heures, pourcentages, flèches de tendance.

**✅ Checkpoint 2 :** les blocs Économique et Social affichent des chiffres réels
(CA, dons, bénévoles, heures valorisées, adhérents) avec variation vs mois précédent.

---

### Phase 3 — Environnemental (live + facteurs ADEME)
**Dépendances :** Phases 0–2.
1. `app/views/impact.py` — `GET/POST /impact/factors` (**admin**) : édition des
   `ImpactFactor` ; `app/templates/impact/factors.html`.
2. **Seed** des clés ADEME (valeurs à confirmer) : `textile.avg_weight_kg`,
   `textile.co2e_per_kg`, `textile.water_l_per_kg`, `equiv.car_km_per_co2e_kg`
   (insérées au premier accès si absentes, avec `source_label` ADEME).
3. `app/services/impact_engine.py` — `factor(key)` (lecture + défaut documenté) ;
   `compute(period)` → `items_reused`, `weight_kg`, `co2e_avoided_kg`, `water_saved_l`,
   `reuse_rate` (si collectés saisis, sinon masqué).
4. `dashboard_service` — brancher la dimension environnementale + **équivalents**
   (`co2e × equiv.car_km_per_co2e_kg`).

**✅ Checkpoint 3 :** bloc Environnemental calculé depuis les ventes × facteurs ;
facteurs éditables (admin) avec source ; équivalent « km voiture » affiché.

---

### Phase 4 — Saisie manuelle (Vinted, groupe FB, collectés/dons)
**Dépendances :** Phases 0–3 (alimente visibilité + éco + impact).
1. `app/services/metrics_sync.py` — `upsert_snapshot(...)` idempotent (sur la clé unique).
2. `app/views/impact.py` — `GET/POST /impact/manual` : formulaire **par période**
   listant les `metric_catalog.manual_metrics()` (`facebook_group.members`,
   `vinted.followers`, `vinted.items_listed`, `vinted.items_sold`, `vinted.revenue_cents`,
   + `env.items_collected`, `env.items_donated` optionnels). POST → `upsert_snapshot`
   (`is_manual=True`, `entered_by_user_id`). Pré-remplissage avec la valeur existante.
3. `app/templates/impact/manual_form.html` — champs typés (nombre, € → centimes).
4. `dashboard_service` / `impact_engine` — intégrer `vinted.items_sold` à `items_reused`
   et `vinted.revenue_cents` à `agg.total_revenue_cents`.

**✅ Checkpoint 4 :** saisie d'un mois (Vinted + groupe FB) → valeurs persistées,
ré-éditables (upsert), visibles au dashboard et répercutées sur éco/impact.

---

### Phase 5 — Connecteur GA4 (site web, auto)
**Dépendances :** Phase 1 ; **identifiants GA4** (cf. doc config). 
1. `requirements.txt` — ajouter `google-analytics-data`.
2. `app/services/external_config.py` — enregistrer le service **`ga4`**
   (`property_id`, `credentials_json`) dans `SERVICE_KEYS`/`SERVICE_REQUIRED_KEYS`/`SERVICE_LABELS`
   + `ENV_FALLBACK` (`GA4_PROPERTY_ID`, `GA4_CREDENTIALS_JSON`).
3. *(option UI)* `external_connections/index.html` — rendre un `<textarea>` pour les
   valeurs longues/JSON (`credentials_json`).
4. `app/services/ga4_client.py` — `from_app_config()` + `GA4Client.fetch_monthly(y, m)`
   (`BetaAnalyticsDataClient.run_report`, dimension `yearMonth`, métriques `activeUsers`,
   `sessions`, `engagementRate`, `averageSessionDuration`, `screenPageViews`). `GA4ConfigError`.
5. `app/services/metrics_sync.py` — `sync_metrics(months_back=1)` : crée un `SyncJob`
   (`kind=metrics`), appelle GA4, `upsert_snapshot` par métrique, tolérant aux erreurs,
   `result_json` récap.
6. `app/views/impact.py` — `POST /impact/sync` + bouton (dashboard) ; flash récap.
7. `dashboard_service` — brancher les métriques `ga4.*` (depuis `metric_snapshots`).

**✅ Checkpoint 5 :** identifiants saisis → **Synchroniser** → bloc « Site web » rempli,
fraîcheur affichée ; ré-exécution = upsert (pas de doublon).

---

### Phase 6 — Connecteur Facebook Page (abonnés, auto)
**Dépendances :** Phase 5 (orchestration `metrics_sync`) ; **Page token** Facebook.
1. `app/services/external_config.py` — service **`facebook`** (`page_id`, `page_token`,
   `app_id`, `app_secret`) + fallback env.
2. `app/services/facebook_client.py` — `from_app_config()` + `fetch_page_followers()`
   (`GET /{page_id}?fields=followers_count,fan_count`, via `requests`). `FacebookConfigError`.
3. `metrics_sync` — intégrer Facebook au même run (isolé par try/except).
4. `dashboard_service` — brancher `facebook_page.followers` + `agg.total_audience`
   (site + page + groupe + vinted).

**✅ Checkpoint 6 :** sync remplit le bloc Facebook ; « audience totale » agrège les
4 communautés.

---

### Phase 7 — Restitution (rapport + export)
**Dépendances :** Phases 1–6 (fonctionne dès la 2 avec données partielles).
1. `app/views/impact.py` — `GET /impact/report` (vue rapport) + `GET /impact/export.xlsx`
   (pandas/openpyxl, pattern `members_export`).
2. `app/templates/impact/report.html` — mise en page « rapport d'activité », **CSS
   d'impression** (`@media print`), 4 dimensions + agrégats + équivalents + **sources/méthodes**.
3. Bandeau **fraîcheur des sources** (date dernière synchro par source + « en attente
   de saisie » pour le manuel) sur dashboard et rapport.

**✅ Checkpoint 7 :** rapport imprimable propre (PDF via navigateur) ; export XLSX
des données ; sources tracées.

---

### Phase 8 — Finitions & tests
**Dépendances :** Phases 0–7.
1. **Tests** `tests/test_impact_dashboard.py` (style existant, client `LOGIN_DISABLED`) :
   - `metrics_aggregator` : éco/social sur jeu de données connu (montants, bénévoles, heures).
   - `impact_engine` : `compute` avec facteurs (arrondis, facteur manquant → défaut, taux 0).
   - `upsert_snapshot` : idempotence sur la clé unique (insert puis update).
   - `/impact/manual` : saisie € → centimes, ré-édition.
   - `dashboard_service` : `delta_pct` vs période précédente, sections vides si pas de données.
   - `metric_catalog` : intégrité (clés uniques, dimensions valides).
   - GA4/Facebook : tests des connecteurs avec client **mocké** (pas d'appel réseau réel).
2. **v2 / backlog** (documenté, non implémenté) : insights Facebook (revue d'app Meta),
   `metric_targets` (objectifs), cron de synchro, PDF serveur (`weasyprint`), acquisition GA4.

**✅ Checkpoint 8 :** `pytest` vert ; parcours complet manuel
(saisir facteurs → voir éco/social/env → saisir manuel → sync GA4/FB → consulter
totaux → imprimer le rapport).

---

## 5. Ordre d'exécution & parallélisation

`0 → 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8`.

- **Chemin de valeur rapide** : 0→1→2 livre déjà un dashboard interne exploitable.
- **Indépendances après la Phase 1** : Phase 2 (interne), Phase 3 (env), Phase 4
  (manuel) peuvent avancer en parallèle ; Phase 6 dépend de la 5 (orchestration commune) ;
  Phase 7 consomme ce qui existe.
- **Externes non bloquants** : si GA4/Facebook ne sont pas prêts, sauter 5/6 et livrer
  0–4 + 7–8 ; brancher 5/6 plus tard sans refactor (le dashboard lit le store unifié).

## 6. Récapitulatif fichiers

**Créés**
- `app/models/metric_snapshot.py`, `app/models/impact_factor.py`
- `app/services/{metric_catalog,dashboard_service,metrics_aggregator,impact_engine,metrics_sync,ga4_client,facebook_client}.py`
- `app/views/impact.py`
- `app/templates/impact/{dashboard,report,manual_form,factors}.html`
- `migrations/versions/<rev>_add_metric_snapshots_impact_factors.py`
- `tests/test_impact_dashboard.py`

**Modifiés**
- `app/models/__init__.py` (+imports, +`__all__`)
- `app/models/sync_job.py` (`SYNC_KIND_METRICS`)
- `app/services/external_config.py` (services `ga4`, `facebook`)
- `app/__init__.py` (`register_blueprint(impact_bp)`)
- `app/templates/base.html` (entrée nav)
- `app/templates/external_connections/index.html` (textarea valeurs longues — option)
- `requirements.txt` (`google-analytics-data`)

## 7. Points à confirmer avant exécution

1. **Valeurs ADEME** exactes (poids/CO₂/eau textile) — sinon démarrer avec des
   placeholders explicitement marqués « à valider ».
2. **Position nav** : entrée 1er niveau « Visibilité & Impact » (recommandé) vs
   sous-menu du Tableau de bord.
3. **Granularité période** : v1 = mensuelle ; trimestre/année = agrégation de mois.
4. **Canaux de CA** : Vinted (manuel) et POS (auto) restent disjoints — confirmer
   qu'aucune vente n'est comptée deux fois.

**Prochaine étape** : `/sc:implement claudedocs/workflow_dashboard_visibilite_impact.md`
phase par phase (commencer par la Phase 0).
