# Workflow — Règles de catégorisation en base + CRUD UI + aide REGEX

**Date :** 2026-05-21
**Auteur :** /sc:workflow
**Statut :** Plan d'implémentation — code non écrit, exécution réservée à `/sc:implement`

---

## 1. Contexte et objectifs

Aujourd'hui, les règles de catégorisation automatique des transactions bancaires vivent dans `data/rules.yml`, **partagé entre toutes les instances**. Ce n'est pas viable en multi-tenant : chaque association a ses propres fournisseurs, clients, libellés bancaires.

Trois évolutions :

1. **Migrer les règles** du fichier YAML vers une **table tenant** (per-instance).
2. **CRUD complet** depuis `/rules/` : bouton « Nouvelle règle », actions « Modifier » et « Supprimer » sur chaque ligne, plus un toggle activé/désactivé et une réorganisation simple.
3. **Aide REGEX** dans le formulaire : explication des syntaxes courantes + testeur interactif (saisir un libellé d'exemple, voir si la regex matche).

Décisions implicites :

- **Stockage** : table `rules` dans la base tenant (mêmes mécanismes que `external_connections`).
- **Évaluation** : ordre par champ `position` (entier, croissant). Première règle qui matche → appliquée. Les autres ignorées.
- **YAML** : `data/rules.yml` conservé comme **gabarit** lu par un script d'import one-shot (`seed_rules.py`). Plus jamais lu par l'app en runtime.
- **Migration** : pour l'instance existante (seconde-nature), seed manuel après migration. Pour les nouvelles instances, le provisioning charge les règles par défaut automatiquement.

---

## 2. Modèle de données

### Table `rules` (base **tenant**)

| Colonne | Type | Description |
|---|---|---|
| `id` | Integer PK | |
| `position` | Integer NOT NULL (indexé) | Ordre d'évaluation (croissant). Détermine la priorité. |
| `name` | String(200) NOT NULL | Libellé affiché, ex : `"Salaires"`, `"MAIF / Assurance"` |
| `label_contains` | String(500) nullable | Sous-chaîne à chercher dans le libellé (case-insensitive, comme aujourd'hui). |
| `label_regex` | String(500) nullable | Regex Python (le moteur applique `re.IGNORECASE`). |
| `amount_min_cents` | Integer nullable | Borne basse signée (en centimes) sur `amount_cents`. |
| `amount_max_cents` | Integer nullable | Borne haute signée. |
| `raw_type` | String(20) nullable | Filtre sur le type OFX (`DEBIT`, `CREDIT`, `INT`, …). |
| `entity_name` | String(200) nullable | Si renseigné, l'`Entity` est créée à la volée (et un type peut être proposé). |
| `entity_type` | String(20) nullable | `CLIENT`, `FOURNISSEUR`, `SALARIE`, `ORGANISME`, `ADHERENT`, `AUTRE`. |
| `category` | String(200) nullable | Étiquette libre apposée sur la transaction. |
| `account_code` | String(20) nullable | Code compte 6xx ou 7xx → déclenche la création d'écriture comptable. |
| `is_active` | Boolean default=True | Désactivation sans suppression — la règle est ignorée. |
| `created_at` | DateTime default=utcnow | |
| `updated_at` | DateTime default=utcnow onupdate=utcnow | |

**Index** : `position` (pour le `ORDER BY position` à chaque évaluation).

**Validations métier** (côté Python, dans le service) :

- Au moins **une condition** définie (`label_contains`, `label_regex`, `amount_min_cents`, `amount_max_cents`, `raw_type`).
- Si `label_regex` non vide : `re.compile(label_regex)` doit réussir.
- Si `account_code` non vide : doit commencer par `6` ou `7` et exister dans `accounts`.

---

## 3. Architecture technique

### 3.1 Refactor `rules_engine.py`

Avant :
```python
def load_rules(path=None):
    return yaml.safe_load(open(path or DEFAULT_RULES_PATH)).get("rules", [])
```

Après :
```python
def load_rules() -> list[Rule]:
    return db.session.query(Rule).filter_by(is_active=True).order_by(Rule.position).all()
```

`_match_rule(rule, txn)` lit désormais les attributs du modèle (`rule.label_contains`, etc.) au lieu d'un dict YAML. Le reste du moteur (`apply_rules`, `_post_entry_for_transaction`, `_get_or_create_entity`) ne change pas — il consomme la liste retournée.

Signature publique préservée : `apply_rules(transactions=None, overwrite=False)` (le paramètre `rules_path` disparaît).

### 3.2 Script de seed — `seed_rules.py`

Module one-shot lancé manuellement (ou par le provisioning d'instance) :

```python
def seed_rules_from_yaml(yaml_path=DEFAULT_RULES_YAML, app=None) -> int:
    """Insère les règles du YAML dans la table tenant. Idempotent.

    Retourne le nombre de règles créées. Si la table contient déjà des règles,
    ne fait rien (refuse d'écraser).
    """
```

- Lit le YAML existant (`data/rules.yml`).
- Pour chaque entrée : crée une `Rule` avec `position = i + 1`.
- Convertit `amount_min`/`amount_max` (euros) → `amount_min_cents`/`amount_max_cents` (entiers).
- `commit` final.
- Si la table contient déjà des lignes → message « ignoré » et exit 0.

**Hook provisioning** : `app/services/instance_provisioning.py:provision_sqlite_database()` ajoute un 3ᵉ subprocess :

```python
_run([sys.executable, "seed_rules.py"], database_url)
```

Pour l'instance existante (seconde-nature.db), l'admin lance le script manuellement après application de la migration.

### 3.3 Validations dans le service

Nouveau module helpers `app/services/rules_validator.py` (ou directement dans `rules_engine.py`) :

```python
class RuleValidationError(ValueError):
    pass

def validate_rule_data(data: dict) -> dict:
    """Valide les champs d'un formulaire de règle, lève RuleValidationError sinon.

    - name obligatoire.
    - Au moins une condition.
    - label_regex compile.
    - account_code (si fourni) : 6xx ou 7xx, non en-tête, existe dans accounts.
    - amount_min_cents ≤ amount_max_cents si les deux sont fournis.
    - Retourne un dict normalisé prêt à être passé à Rule(**data).
    """
```

### 3.4 Réorganisation des positions

Algorithme simple : positions = entiers (1, 2, 3…) avec gaps autorisés. Insertions et suppressions n'ont pas besoin de renuméroter.

- **Création** : `position = (SELECT MAX(position) FROM rules) + 1`.
- **Suppression** : laisse un gap (acceptable, l'évaluation reste correcte).
- **Move up / Move down** : swap `position` avec la règle voisine (ASC ou DESC). Implémentation en 2 UPDATE dans une transaction.
- **Move to top / bottom** : facultatif — pas en v1.

### 3.5 Aide REGEX

Section accordéon (`<details>` ou Bootstrap collapse) dans le formulaire `rules/form.html`, contenant :

1. **Patterns courants** — table avec colonnes [Syntaxe / Effet / Exemple], couvrant :
   - `(?i)` — insensible à la casse
   - `|` — OU logique (`A|B`)
   - `\d`, `\w`, `\s` — chiffre / mot / espace
   - `^`, `$` — début / fin de chaîne
   - `.*`, `.+`, `?` — quantificateurs
   - `[...]`, `[^...]` — classes de caractères
   - Échappement des caractères spéciaux (`\.`, `\+`, `\(`, `\)`)
2. **Testeur live** — deux champs (Regex / Libellé d'exemple) + résultat « ✓ match » ou « ✗ pas de match » + surlignage de la portion matchée.

**Choix d'implémentation** :

- **Option A (JS pur)** : utilise `new RegExp(pattern)` côté navigateur, `String.prototype.match`. Avantages : zéro latence, pas de roundtrip. Limite : la syntaxe JS RegExp diffère **légèrement** de Python `re` (les groupes nommés `(?P<name>...)` sont JS-incompatibles, mais ils ne sont pas utilisés dans les règles existantes).
- **Option B (HTMX server-side)** : `GET /rules/test-regex?pattern=...&sample=...` retourne le fragment HTML « match » ou « pas de match » via `re.search`. Garantit la fidélité Python.

**Décision** : JS pur (Option A), avec une note « Le moteur d'évaluation utilise Python `re` — quelques constructions avancées (groupes nommés `(?P<name>...)`) peuvent ne pas être disponibles dans le testeur ; ouvrez une issue si vous en avez besoin. »

### 3.6 Routes — vue d'ensemble

| Méthode | URL | Description |
|---------|-----|-------------|
| GET | `/rules/` | Liste avec actions (existant — enrichi) |
| GET | `/rules/new` | Formulaire de création |
| POST | `/rules/new` | Crée la règle |
| GET | `/rules/<id>/edit` | Formulaire de modification |
| POST | `/rules/<id>/edit` | Met à jour |
| POST | `/rules/<id>/delete` | Supprime |
| POST | `/rules/<id>/toggle-active` | Bascule `is_active` |
| POST | `/rules/<id>/move-up` | Échange position avec la règle au-dessus |
| POST | `/rules/<id>/move-down` | Échange position avec la règle au-dessous |
| POST | `/rules/apply` | Existant — applique le moteur |

Authentification : `@login_required` partout, **pas** d'`@admin_required` (les règles font partie de la config métier accessible à tout comptable). À reconsidérer si le rôle « comptable » est introduit.

---

## 4. Phases d'implémentation

### Phase 1 — Modèle Rule + migration

**Fichiers à créer :**
- `app/models/rule.py` — modèle SQLAlchemy (default bind = tenant)
- Migration Alembic : `flask db migrate -m "add rules table"`

**Fichiers à modifier :**
- `app/models/__init__.py` — export `Rule`

**Validation :**
- `flask db upgrade` applique la migration sur `instance/seconde-nature.db`.
- Tests existants verts.

### Phase 2 — Seed depuis YAML

**Fichiers à créer :**
- `seed_rules.py` — script idempotent au root du projet.

**Fichiers à modifier :**
- `app/services/instance_provisioning.py` — appeler `seed_rules.py` dans `_run(...)`.

**Validation :**
- `python seed_rules.py` sur l'instance existante → ~22 règles insérées avec `position = 1..N`.
- Relancer → message « rules already present, skipping » et exit 0.
- Provisioning d'une nouvelle instance test → règles présentes automatiquement.

### Phase 3 — Refactor rules_engine.py + validations

**Fichiers à modifier :**
- `app/services/rules_engine.py` :
  - `load_rules()` lit la table.
  - `_match_rule(rule, txn)` accède aux attributs du modèle (au lieu du dict YAML).
  - `apply_rules(transactions=None, overwrite=False)` : suppression du `rules_path`.
- `app/views/rules.py` : `apply()` n'appelle plus `load_rules` avec un path.

**Fichier à supprimer (logique, mais on le garde physiquement comme gabarit) :**
- ❌ Pas supprimer `data/rules.yml` — devient un gabarit consulté uniquement par `seed_rules.py`. Documenter.

**Validation :**
- Bouton « Appliquer les règles » sur `/rules/` fonctionne identiquement à avant.
- Aucune ligne d'écriture créée en doublon.

### Phase 4 — UI CRUD

**Fichiers à créer :**
- `app/templates/rules/form.html` — formulaire complet (create + edit).
- `app/services/rules_validator.py` (ou helpers dans `rules_engine.py`) — `validate_rule_data(form_data)`.

**Fichiers à modifier :**
- `app/views/rules.py` — ajout :
  - `GET/POST /rules/new`
  - `GET/POST /rules/<id>/edit`
  - `POST /rules/<id>/delete`
  - `POST /rules/<id>/toggle-active`
  - `POST /rules/<id>/move-up`
  - `POST /rules/<id>/move-down`
- `app/templates/rules/index.html` :
  - Bouton « Nouvelle règle » dans l'en-tête.
  - Colonne « Actions » à droite : « Modifier », « Activer/Désactiver », « ↑ » « ↓ », « Supprimer ».
  - Ligne grisée si `is_active = False`.
  - Suppression du bloc « Comment modifier les règles » + cheat sheet YAML (remplacé par l'aide REGEX dans le formulaire).

**Validation :**
- Création d'une règle de test (« TEST regex », `label_regex=(?i)test`, `category=Test`) → ligne visible.
- Édition → modifications persistées.
- Move up/down → ordre changé.
- Suppression → ligne disparue.
- Toggle-active → ligne grisée, exclue de l'évaluation.

### Phase 5 — Aide REGEX

**Fichiers à modifier :**
- `app/templates/rules/form.html` — section accordion ou card :
  - Tableau des patterns Python courants.
  - Mini-testeur JS : 2 input + 1 zone résultat. Le testeur lit la valeur du champ `label_regex` du formulaire et permet d'en saisir une à part pour ne pas modifier le formulaire en cours.

**Choix UX** :
- Le testeur réutilise par défaut la valeur du champ `label_regex` (bouton « copier la regex courante »).
- Le testeur peut aussi prendre un échantillon issu d'une vraie transaction : ajouter un sélecteur (HTMX) qui propose les 20 derniers libellés `BankTransaction.label` distincts pour faciliter le test sur des cas réels.

> Décision finale : v1 = pur JS, échantillon = saisie libre. Le sélecteur HTMX « libellé existant » est noté hors-périmètre (mais facile à brancher plus tard).

**Validation :**
- Saisie `(?i)maif` + libellé `PRELEVEMENT MAIF` → ✓ match.
- Saisie d'une regex invalide (`(?i)(` sans fermeture) → message d'erreur côté JS, pas de crash.

### Phase 6 — Documentation

**Fichiers à modifier :**
- `doc/models.md` — ajouter `Rule` (tenant).
- `doc/routes.md` — ajouter les 7 nouvelles routes `/rules/*`.
- `doc/services.md` — section `rules_engine.py` : indiquer que `load_rules()` lit la table.
- `doc/architecture.md` — mentionner la table dans la liste des modèles métier.
- `doc/multi_tenant.md` — note rapide sur le fait que les règles sont per-instance.
- `data/rules.yml` — ajouter un commentaire en tête : « Ce fichier sert de gabarit pour `seed_rules.py`. Il n'est plus lu par l'application en runtime. Les modifications de règles passent par l'UI `/rules/`. »

**Validation :**
- Doc à jour, exemples fonctionnels.

---

## 5. Dépendances entre phases

```
Phase 1 (modèle) ──▶ Phase 2 (seed) ──▶ Phase 3 (refactor moteur)
                                            │
                                            ▼
                                       Phase 4 (UI CRUD) ──▶ Phase 5 (aide REGEX)
                                                                  │
                                                                  ▼
                                                             Phase 6 (doc)
```

Phases strictement séquentielles. Pas de parallélisme possible : chaque phase consomme la précédente.

---

## 6. Risques et points d'attention

| Risque | Mitigation |
|---|---|
| **Perte de règles existantes pendant migration** | Le YAML reste intact ; le seed l'importe sans le modifier. Si la table est déjà peuplée, le seed refuse d'écraser. |
| **Regex invalide soumise via UI** | Validation `re.compile()` côté serveur dans `validate_rule_data`. Erreur 400 + message en flash, formulaire repré-rempli. |
| **Account_code 6/7 invalide ou compte d'en-tête** | Validation lookup dans `accounts`. Cohérent avec ce que fait déjà le moteur au runtime. |
| **Ordre des règles changé accidentellement** | Move up/down via boutons explicites uniquement. Pas de drag-drop pour éviter mauvais clics. Confirmation JS sur la suppression. |
| **Concurrence sur les positions** | SQLite + Flask-SQLAlchemy : transaction par requête. Deux move-up simultanés sur deux navigateurs ne casseront pas l'unicité mais peuvent produire un ordre inattendu — acceptable v1, fréquence très faible. |
| **Conflit YAML / DB après seed** | Une fois le seed appliqué, le YAML n'est plus lu. Documenter clairement. La date du seed est tracée par `created_at` de chaque règle (toutes la même date = repère). |
| **REGEX testeur trompeur (JS vs Python)** | Note explicite dans le panneau d'aide. Si l'utilisateur veut vraiment tester en Python, il peut sauvegarder la règle et cliquer « Appliquer ». |

---

## 7. Hors-périmètre (v1)

- **Drag-drop reordering** (le couple ↑/↓ suffit pour 22 règles).
- **Import/export YAML** depuis l'UI — réservé au seed initial. Si l'utilisateur veut exporter, requête SQL directe.
- **Historique des modifications** d'une règle (audit log) — non.
- **Test d'une règle sur un échantillon de transactions** (« quelle règle aurait matché cette transaction du 15 mars ? ») — utile, mais v2.
- **Règles transverses inter-instances** (« même règle pour toutes mes assos ») — non, chaque instance gère les siennes.
- **Validation regex 100% Python côté UI** — soit on accepte la divergence JS, soit on bascule plus tard sur option B (HTMX).

---

## 8. Checkpoints de validation

- [ ] **Phase 1** — Migration appliquée, table `rules` présente, modèle importable.
- [ ] **Phase 2** — `python seed_rules.py` insère ~22 règles ; re-run silencieux.
- [ ] **Phase 3** — `/rules/apply` continue de catégoriser les transactions correctement.
- [ ] **Phase 4** — Cycle complet : créer → éditer → désactiver → réactiver → réordonner → supprimer.
- [ ] **Phase 5** — Aide REGEX visible et testeur fonctionnel.
- [ ] **Phase 6** — Doc à jour ; `data/rules.yml` mentionne son nouveau rôle.

---

## 9. Étape suivante

```
/sc:implement claudedocs/workflow_rules_crud.md
```

Les phases sont strictement séquentielles. On peut s'arrêter après Phase 4 (CRUD fonctionnel sans aide REGEX) si le temps presse — l'aide REGEX vient en bonus.
