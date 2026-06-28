# Workflow — Bénévoles & Saisie des temps de travaux

> **Statut : PLAN UNIQUEMENT.** Ce document décrit l'implémentation pas à pas.
> Aucun code n'est écrit ici. Exécuter ensuite avec `/sc:implement` phase par phase.

## 1. Objectif

Deux fonctionnalités liées :

1. **Marquage « bénévole » des adhérents** — ajouter un booléen `is_benevole`
   sur les tiers, visible/éditable dans la liste des adhérents
   (`/entities/members`), avec **modification massive** (cocher plusieurs
   adhérents → les marquer bénévoles d'un coup).

2. **Module « Temps de travaux »** — nouvelle entrée dans le menu **Tiers** :
   - **Consultation** des temps saisis (liste filtrable + total heures/valorisation)
   - **Saisie** manuelle d'un temps (date, type de tâche, nb heures, notes)
   - **Import** en masse (CSV/XLSX)
   - **Paramétrage des types de tâches** avec un **taux horaire**
     (ex : *Tenue de la caisse — 25 €/h*).

## 2. Conventions du projet (à respecter)

- **Stack** : Flask + Blueprints + Jinja2 + HTMX + Bootstrap 5 / SQLAlchemy + Alembic.
- **Montants** : toujours stockés en **centimes entiers** (`INTEGER`), filtre Jinja `| euros` pour l'affichage. → le **taux horaire** et la **valorisation** suivent cette règle.
- **Heures** : valeur non monétaire → stockée en `Numeric(6, 2)` (ex : `2.50`). La valorisation se calcule `round(hours * rate_cents)` en centimes.
- **Modèles** : un fichier par modèle dans `app/models/`, ré-exporté dans `app/models/__init__.py` (ajouter à l'import **et** à `__all__`).
- **Migrations** : Alembic, head actuel = **`b3e1a7c2d9f4`**. Tout booléen ajouté à une table existante doit avoir `server_default` (cf. `is_member` dans `28ed324ac0c8`).
- **Blueprints** : enregistrés dans `app/__init__.py` (`register_blueprint`). `url_prefix` dédié.
- **CSRF** : `flask_wtf.CSRFProtect` actif globalement → tout `<form method="post">` doit inclure `<input type="hidden" name="csrf_token" value="{{ csrf_token() }}">`.
- **Listes** : helpers `app/utils/list_filters.py` (`parse_sort`, `parse_month`, `apply_date_sort`, `apply_month_filter`, `sort_and_filter_context`) + macros `app/templates/_list_helpers.html`. Réutiliser pour la consultation des temps.
- **Export** : pattern existant `entities.members_export` (CSV via `csv` + XLSX via `pandas`/`openpyxl`). Réutilisable pour l'export des temps si souhaité.
- **Nav** : menu « Tiers » dans `app/templates/base.html` (lignes ~51-60). Le surlignage `active` dépend de `request.blueprint`.

## 3. Modèle de données

### 3.1 `Entity.is_benevole` (modif table existante)
- Colonne `is_benevole = db.Column(db.Boolean, nullable=False, default=False, server_default="false")` dans `app/models/entity.py`, à côté de `is_member`.

### 3.2 `TaskType` — types de tâches paramétrables (nouvelle table `task_types`)
| Colonne | Type | Notes |
|---|---|---|
| `id` | Integer PK | |
| `name` | String(150), unique, not null | ex : « Tenue de la caisse » |
| `hourly_rate_cents` | Integer, not null, default 0 | taux horaire en centimes (25 €/h → 2500) |
| `is_active` | Boolean, not null, default True, server_default true | désactivable sans suppression |
| `created_at` | DateTime, default utcnow | |

### 3.3 `WorkTime` — temps de travaux (nouvelle table `work_times`)
| Colonne | Type | Notes |
|---|---|---|
| `id` | Integer PK | |
| `entity_id` | Integer FK `entities.id` `ON DELETE CASCADE`, not null, indexé | le bénévole |
| `task_type_id` | Integer FK `task_types.id` `ON DELETE RESTRICT`, not null, indexé | empêche de supprimer un type utilisé |
| `work_date` | Date, not null, indexé | |
| `hours` | Numeric(6, 2), not null | nb d'heures |
| `notes` | Text, nullable | |
| `created_at` | DateTime, default utcnow | |

- `Entity` relation `work_times = db.relationship("WorkTime", backref="entity", cascade="all, delete-orphan", lazy="dynamic")`.
- Propriété calculée `WorkTime.valuation_cents` = `int(round(self.hours * self.task_type.hourly_rate_cents))`.

> **Décision métier à valider** : la saisie est-elle réservée aux entités
> `is_benevole=True` (filtrage du `<select>` bénévole) ? Recommandé : **oui**,
> mais ne pas l'imposer en contrainte SQL (souplesse import historique).

## 4. Phases d'implémentation

### Phase 0 — Préparation & schéma (fondations)
**Dépendances :** aucune.
1. `app/models/entity.py` — ajouter `is_benevole`.
2. `app/models/task_type.py` — créer `TaskType` (+ constante module si besoin).
3. `app/models/work_time.py` — créer `WorkTime` + `valuation_cents`.
4. `app/models/__init__.py` — importer `TaskType`, `WorkTime` ; les ajouter à `__all__`.
5. **Migration Alembic** (`flask db migrate -m "add benevole, task_types, work_times"` puis **relire/ajuster** le fichier généré) :
   - `add_column entities.is_benevole` avec `server_default`.
   - `create_table task_types` + index unique sur `name`.
   - `create_table work_times` + FK + index sur `entity_id`, `task_type_id`, `work_date`.
   - `down_revision = 'b3e1a7c2d9f4'`.
6. `flask db upgrade` puis vérifier le schéma.

**✅ Checkpoint 0 :** `flask db upgrade` OK ; `python -c "from app.models import TaskType, WorkTime"` sans erreur.

---

### Phase 1 — Bénévole sur la liste des adhérents + modif massive
**Dépendances :** Phase 0.
1. `app/views/entities.py` :
   - `new()` / `edit()` — prendre en compte `is_benevole` (`bool(request.form.get("is_benevole"))`).
   - **Nouvelle route** `POST /members/bulk-benevole` : lit `request.form.getlist("selected")` (ids), un champ `action` = `set` / `unset`, met à jour `Entity.is_benevole` pour les ids cochés, commit, flash récap, redirect vers `entities.members` (en conservant `q`/filtres).
   - `members()` / `_member_rows()` — exposer `is_benevole` dans les rows (déjà via `row.entity`/`build_member_rows` ; vérifier que `membership_status.build_member_rows` ne masque pas le champ — sinon lire `row.entity.is_benevole`).
2. `app/templates/entities/members.html` :
   - Englober le tableau dans un `<form method="post" action="{{ url_for('entities.bulk_benevole') }}">` + `csrf_token`.
   - Colonne case à cocher d'en-tête « tout cocher » (JS minimal) + `<input type="checkbox" name="selected" value="{{ row.entity.id }}">` par ligne.
   - Colonne **Bénévole** (badge comme la colonne *Adhérent*).
   - Barre d'actions : boutons « Marquer bénévole » (`action=set`) / « Retirer bénévole » (`action=unset`).
3. `app/templates/entities/form.html` — ajouter la case `is_benevole` (à côté de `is_member`).
4. *(optionnel)* `entities.members_export` — ajouter une colonne « Bénévole » dans `EXPORT_HEADERS` + `_export_record`.

**✅ Checkpoint 1 :** sélectionner 2-3 adhérents → « Marquer bénévole » → badges mis à jour, flash « N adhérent(s) marqué(s) bénévole(s) ». Édition unitaire OK.

---

### Phase 2 — Paramétrage des types de tâches (CRUD)
**Dépendances :** Phase 0.
1. `app/views/work_times.py` — créer le blueprint `work_times` (`url_prefix="/work-times"`).
   - Routes types : `GET /task-types` (liste), `GET|POST /task-types/new`, `GET|POST /task-types/<id>/edit`, `POST /task-types/<id>/delete` (refuser si des `WorkTime` y sont rattachés → flash danger, cf. pattern `entities.delete`).
   - Saisie du taux : champ en **euros** dans le form → conversion en centimes (`int(round(float(rate_eur) * 100))`).
2. Enregistrer le blueprint dans `app/__init__.py`.
3. Templates `app/templates/work_times/task_types.html` + `task_type_form.html` (Bootstrap, affichage taux via `| euros`).

**✅ Checkpoint 2 :** créer « Tenue de la caisse » à 25 €/h → liste affiche `25,00 €`/h ; suppression d'un type utilisé refusée.

---

### Phase 3 — Saisie & consultation des temps
**Dépendances :** Phases 0, 2 (besoin de types pour le `<select>`), 1 (besoin de bénévoles).
1. `app/views/work_times.py` :
   - `GET /` (**index/consultation**) : liste filtrable (bénévole, type, plage de dates via `apply_month_filter`/`apply_date_sort`), tri sur `work_date`, total heures + total valorisation (`sum(valuation_cents)`). Réutiliser `sort_and_filter_context`.
   - `GET|POST /new` (**saisie**) : `<select>` bénévole (entités `is_benevole=True`, triées par nom), `<select>` type de tâche actif, `work_date`, `hours`, `notes`. Validation (champs requis, `hours > 0`). Commit + flash + redirect index.
   - `GET|POST /<id>/edit`, `POST /<id>/delete`.
2. Templates `work_times/index.html` (tableau + barre de filtres + bouton « Saisir un temps » + lien « Types de tâches » + bouton « Importer ») et `work_times/form.html`.
3. **Nav** `app/templates/base.html` — ajouter dans le menu « Tiers » : `<li><a class="dropdown-item" href="{{ url_for('work_times.index') }}">Temps de travaux</a></li>`. Étendre la condition `active` du menu Tiers à `('entities','rules','work_times')`.

**✅ Checkpoint 3 :** saisir un temps (Tenue de la caisse, 2,5 h) → apparaît dans la liste avec valorisation `62,50 €` ; filtres et totaux corrects ; entrée de menu visible et active.

---

### Phase 4 — Import en masse des temps
**Dépendances :** Phase 3.
1. `app/services/work_time_import.py` — `import_work_times(file_stream, ...)` :
   - Lecture CSV (`csv`, délimiteur `;`, encodage `utf-8-sig` comme l'export) **ou** XLSX (`pandas`).
   - Colonnes attendues : `Bénévole` (nom ou email → résolution via `app/services/entity_resolver.py:entity_by_email` / par nom), `Type de tâche` (match sur `TaskType.name`, sinon erreur ligne), `Date` (formats `%d/%m/%Y` et `%Y-%m-%d`), `Heures` (virgule ou point décimal), `Notes`.
   - Retour `{"imported": n, "errors": [...], "skipped": n}` (pattern `import_ofx`/`import_odoo_csv`).
   - Politique doublons à valider (cf. §6).
2. `app/views/work_times.py` — route `GET|POST /import` : upload + appel service + flash récap (pattern `imports.odoo`).
3. Template `work_times/import.html` : formulaire upload + rappel du format des colonnes + lien « modèle CSV » (optionnel : route servant un CSV d'en-têtes).

**✅ Checkpoint 4 :** importer un CSV de 3-4 lignes → lignes créées, valorisations correctes, erreurs de ligne remontées sans bloquer le reste.

---

### Phase 5 — Finitions & tests
**Dépendances :** Phases 1-4.
1. *(optionnel)* Bloc « Temps de travaux » sur la fiche `/entities/<id>` si l'entité est bénévole (liste de ses temps + total), calqué sur les blocs existants.
2. *(optionnel)* Export des temps (CSV/XLSX) depuis `work_times.index`, pattern `members_export`.
3. **Tests** dans `tests/` (cf. style existant) :
   - modèle : `valuation_cents` (arrondi, taux 0).
   - bulk-benevole : set/unset sur ids sélectionnés.
   - import : ligne valide / type inconnu / date invalide / heures `,` vs `.`.
   - suppression d'un `TaskType` référencé → refus.
4. Mettre à jour `doc/` si une doc fonctionnelle par module y est tenue.

**✅ Checkpoint 5 :** `pytest` vert ; parcours complet manuel (marquer bénévole → créer type → saisir → importer → consulter totaux).

## 5. Récapitulatif fichiers

**Créés**
- `app/models/task_type.py`, `app/models/work_time.py`
- `app/views/work_times.py`
- `app/services/work_time_import.py`
- `app/templates/work_times/{index,form,task_types,task_type_form,import}.html`
- `migrations/versions/<rev>_add_benevole_task_types_work_times.py`
- `tests/test_work_times.py` (ou regroupé)

**Modifiés**
- `app/models/entity.py` (+`is_benevole`, relation `work_times`)
- `app/models/__init__.py` (+imports, +`__all__`)
- `app/views/entities.py` (bulk-benevole, `is_benevole` create/edit/export)
- `app/templates/entities/{members,form}.html`
- `app/templates/base.html` (menu Tiers : entrée + `active`)
- `app/__init__.py` (`register_blueprint(work_times_bp)`)

## 6. Points à clarifier avant exécution

1. **Saisie réservée aux `is_benevole` ?** Recommandé : filtrer le `<select>` aux bénévoles, sans contrainte SQL.
2. **Doublons à l'import** : clé (`entity_id`, `task_type_id`, `work_date`, `hours`) ignorée en doublon, ou import toujours additif ? Recommandé : **additif** (un bénévole peut faire 2 sessions le même jour) — pas de dédup.
3. **Stockage des heures** : `Numeric(6,2)` (recommandé) vs minutes entières.
4. **Périmètre v1** : les éléments *(optionnel)* de la Phase 5 (bloc fiche tiers, export temps) sont-ils dans le périmètre initial ?

## 7. Ordre d'exécution conseillé

`Phase 0 → 1 → 2 → 3 → 4 → 5`. Les phases 1 et 2 sont indépendantes après la
phase 0 et peuvent être menées en parallèle ; la phase 3 nécessite 0+1+2 ; la
phase 4 nécessite 3.
