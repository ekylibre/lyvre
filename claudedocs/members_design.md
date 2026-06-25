# Design — Évolutions module Adhérents (`/entities/members`)

> Document de conception (spec). Aucune implémentation ici — voir `/sc:implement`.
> Source des exigences : `claudedocs/members.md`.
> Décisions arbitrées : couleur = **sémantique d'échéance** ; formats export = **CSV + XLSX** ;
> emails = **Flask-Mail + modèle stocké en base**.

---

## 1. Contexte & état actuel

| Élément | Fichier | Rôle actuel |
|---|---|---|
| Modèle tiers | `app/models/entity.py` | `Entity` (name, entity_type, email, is_member, notes…) |
| Vue liste adhérents | `app/views/entities.py` → `members()` | filtre `entity_type="ADHERENT"`, recherche `q`, plage de dates |
| Export | `entities.py` → `members_csv()` | CSV `;` UTF-8-BOM, 6 colonnes |
| Template | `app/templates/entities/members.html` | tableau Bootstrap, bouton « Exporter CSV » |
| Dates adhésion | `_last_membership_dates()` | 2 dicts `{entity_id: datetime}` — **HA** (HelloAsso Membership) et **POS** (Odoo, ligne `%adh%sion%`) |
| Tri/filtre listes | `app/utils/list_filters.py` | helpers de tri **SQL** par colonne date (non réutilisables ici, voir §4.3) |

**Point d'architecture clef** : `member_birthday` et `member_status` dérivent des deux dates HA/POS,
qui proviennent de **requêtes agrégées séparées** (pas de colonne sur `Entity`). Les calculs et le tri
correspondant se font donc **en Python après requête**, pas en SQL.

**Multi-tenant** (`app/extensions.py`) : les modèles sans `__bind_key__` ciblent la base **du tenant**.
Le futur `EmailTemplate` est donc per-tenant ; la config SMTP reste **globale** (`.env`).

---

## 2. Spécification des méthodes de calcul

> Implémentées comme **fonctions pures** dans un nouveau module
> `app/services/membership_status.py`, réutilisées par la vue HTML, les exports et la relance.
> (Fonctions plutôt que méthodes de modèle : la logique dépend de données agrégées hors `Entity`.)

### 2.1 `member_birthday(last_ha, last_pos, today=None) -> date`

Date d'**échéance** de l'adhésion (= dernière adhésion + 365 j).

```
candidates = [d for d in (last_ha, last_pos) if d is not None]   # datetimes
si candidates est vide        ->  today (date du jour)
sinon                         ->  max(candidates).date() + 365 jours
```

Cette formulation couvre les **4** combinaisons, dont le cas absent du doc source
(*HA présent & POS vide* → `last_ha + 365`) :

| last_ha | last_pos | résultat |
|---|---|---|
| ∅ | ∅ | `today` |
| ∅ | présent | `last_pos + 365` |
| présent | ∅ | `last_ha + 365` |
| présent | présent | `max(ha, pos) + 365` |

### 2.2 `member_status(last_ha, last_pos, today=None) -> dict`

Retourne `{"status": str, "color": str, "label": str, "css": str}`.

**`status`** (présence de données d'adhésion) :

| condition | status |
|---|---|
| HA ∅ & POS ∅ | `"?"` |
| HA ∅ & POS présent | `"asha"` |
| sinon (HA présent) | `"ok"` |

**`color`** — sémantique **échéance** (arbitrée, cohérente avec la relance §5).
Soit `b = member_birthday(...)` :

| condition | color | css (badge) |
|---|---|---|
| `b <= today` (échéance atteinte/dépassée) | `"red"` | `bg-danger` |
| `today < b <= today + 30 j` (expire bientôt) | `"orange"` | `bg-warning text-dark` |
| `b > today + 30 j` (à jour) | `"green"` | `bg-success` |

> ⚠️ **Inversion volontaire** vs le tableau littéral de `members.md` (qui mettait `b<=now → green`).
> Le doc source se contredisait avec la partie 4 (« anniversaire dépassé → relance »). Décision retenue :
> *passé = expiré = rouge*.

`label` = le `status` affiché (« ? », « asha », « ok ») — pilule colorée par `css`.
Optionnel : mapper vers libellés FR (`"ok"`→« À jour », `"asha"`→« Adhésion POS seule », `"?"`→« Inconnu »)
sans changer la valeur `status` exportée.

### 2.3 Constructeur de lignes partagé `build_member_rows(...)`

Source unique de vérité pour liste + exports + relance. Évite la divergence entre vues.

```
build_member_rows(members_list, last_ha, last_pos, today=None) -> list[dict]
  pour chaque entity:
    ha = last_ha.get(e.id);  pos = last_pos.get(e.id)
    birthday = member_birthday(ha, pos, today)
    status   = member_status(ha, pos, today)
    -> {
        "entity": e, "name": e.name, "email": e.email,
        "is_member": e.is_member, "notes": e.notes,
        "last_ha": ha, "last_pos": pos,
        "birthday": birthday,
        "status": status["status"], "color": status["color"],
        "label": status["label"], "css": status["css"],
       }
```

---

## 3. Diagramme de flux (liste + export + relance)

```
                 GET /entities/members[ ?q&date_from&date_to&sort_by&sort ]
                                  │
        _members_query(q) ──► members_list (ADHERENT)
                                  │
        _last_membership_dates(ids) ──► last_ha{}, last_pos{}
                                  │
        _filter_by_date_range(...) (existant)
                                  │
        build_member_rows(...) ──► rows[]  (birthday + status calculés)   [§2.3]
                                  │
        sort_member_rows(rows, sort_by, sort)  [§4.3]
              ├──────────────► render members.html (tableau triable + pilules)
              │
   GET /entities/members/export?format=csv|xlsx&<mêmes filtres+tri>
              └──► render_csv(rows) | render_xlsx(rows)   [§4.4]

   GET  /entities/members/reminders  ──► preview rows où color=="red" & email présent
   POST /entities/members/reminders  ──► membership_reminders.send_reminders(rows)  [§5]
                                          └─ Flask-Mail + EmailTemplate (DB) + lien HelloAsso
```

---

## 4. Partie 1–3 : Liste, tri, sélecteur & exports

### 4.1 Nouvelles colonnes liste (`members.html`)

Colonnes ajoutées au tableau : **Date anniversaire** et **Statut**.

```
| Nom* | Email | Adhérent | Dernière adh. HA | Dernière adh. POS | Date anniversaire* | Statut* | Notes |
```
`*` = colonnes triables (Nom, Date anniversaire, Statut).

- Date anniversaire : `row.birthday | strftime('%d/%m/%Y')`.
- Statut : `<span class="badge {{ row.css }}">{{ row.label }}</span>`.

### 4.2 Paramètres GET (conserver la convention existante)

| param | valeurs | défaut |
|---|---|---|
| `q` | texte | `""` (existant) |
| `date_from`, `date_to` | `YYYY-MM-DD` | (existant) |
| `sort_by` | `name` \| `birthday` \| `status` | `name` |
| `sort` | `asc` \| `desc` | `asc` |

Réutilise `parse_sort()` de `list_filters.py` pour `sort`. En-têtes de colonne = liens qui
basculent `sort` (asc↔desc) et fixent `sort_by`, avec indicateur ▲/▼ (même UX que les listes existantes).

### 4.3 Tri en Python (nouveau helper)

Les colonnes `birthday`/`status` étant calculées, le tri SQL de `list_filters` ne s'applique pas.
Nouveau helper dans `membership_status.py` :

```
STATUS_ORDER = {"red": 0, "orange": 1, "green": 2}   # gravité croissante

sort_member_rows(rows, sort_by, sort) -> rows triées
  key = {
    "name":     lambda r: r["name"].lower(),
    "birthday": lambda r: r["birthday"],
    "status":   lambda r: (STATUS_ORDER[r["color"]], r["name"].lower()),
  }[sort_by]
  return sorted(rows, key=key, reverse=(sort == "desc"))
```

Volume adhérents d'une asso = petit → tri mémoire sans souci de perf.

### 4.4 Sélecteur de format & route d'export

**UI** (`members.html`) : remplacer le bouton unique par un menu déroulant Bootstrap.

```
[ Exporter ▼ ]
   ├─ CSV     → /entities/members/export?format=csv&<filtres+tri>
   └─ Excel   → /entities/members/export?format=xlsx&<filtres+tri>
```

**Route** : nouvelle `GET /entities/members/export` (paramètre `format`, défaut `csv`).
Conserver `members.csv` comme alias 301→`export?format=csv` (compat liens existants).

Pipeline commun : `members_list → filtres → build_member_rows → sort_member_rows → render_<fmt>(rows)`.

**Colonnes export** (CSV **et** XLSX), enrichies des 3 attributs demandés :

```
Nom ; Email ; Adhérent ; Dernière adhésion HelloAsso ; Dernière adhésion POS ;
Date anniversaire ; Statut ; Couleur ; Notes
```
- `Date anniversaire` : `%d/%m/%Y`
- `Statut` : `row.status`  (`?` / `asha` / `ok`)
- `Couleur` : `row.color`  (`red` / `orange` / `green`)

**CSV** : `render_csv(rows)` — writer `;`, encodage `utf-8-sig`, `Content-Disposition: adherents.csv`
(réutilise l'existant + 3 colonnes).

**XLSX** : `render_xlsx(rows)` — via **pandas + openpyxl** :
```
df = pandas.DataFrame(rows_as_records)
buf = io.BytesIO()
with pandas.ExcelWriter(buf, engine="openpyxl") as xw:
    df.to_excel(xw, index=False, sheet_name="Adhérents")
Response(buf.getvalue(),
         mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
         headers={"Content-Disposition": 'attachment; filename="adherents.xlsx"'})
```
Option (nice-to-have) : colorer la cellule « Statut » selon `color` via `openpyxl PatternFill`
(vert/orange/rouge) pour un rendu visuel.

> `format=xls` (legacy) : **mappé sur xlsx** (alias), pas de dépendance `xlwt` obsolète (décision §0).

### 4.5 Dépendance à ajouter

`requirements.txt` : `openpyxl==3.1.*` (moteur d'écriture XLSX de pandas ; `xlrd` présent ne fait que lire).

---

## 5. Partie 4 : Relance email des adhérents expirés

### 5.1 Périmètre de relance

Adhérents tels que **`color == "red"`** (échéance atteinte/dépassée) **ET** `email` présent.

> Note conception : les adhérents `status == "?"` (aucune donnée d'adhésion) tombent aussi en `red`.
> Recommandation : **les exclure** de la relance par défaut (rien à renouveler / email souvent absent),
> via un filtre `row["status"] != "?"`. À confirmer en implémentation.

### 5.2 Configuration SMTP (`.env` + `config.py`)

Nouvelles clés `.env` (mapping Flask-Mail) :

```
MAIL_SERVER=
MAIL_PORT=587
MAIL_USE_TLS=true
MAIL_USERNAME=
MAIL_PASSWORD=
MAIL_DEFAULT_SENDER="Association <contact@exemple.org>"
```

`config.py` (classe `Config`) : exposer ces 6 valeurs (`os.environ.get`, défauts vides/`587`/`true`).

### 5.3 Extension Flask-Mail

- `requirements.txt` : `flask-mail==0.10.*`.
- `app/extensions.py` : `mail = Mail()` ; `mail.init_app(app)` dans la factory (`app/__init__.py`).

### 5.4 Modèle d'email éditable (DB, per-tenant)

Nouveau modèle `app/models/email_template.py` :

```
class EmailTemplate(db.Model):           # base tenant (pas de __bind_key__)
    __tablename__ = "email_templates"
    id          = Integer PK
    key         = String(50) unique         # ex. "membership_reminder"
    subject     = String(300)
    body_html   = Text                       # corps éditable
    updated_at  = DateTime
```

- **Variables** rendues par Jinja (`render_template_string`) ou substitution simple :
  `{{ nom }}`, `{{ email }}`, `{{ date_anniversaire }}`, `{{ lien_helloasso }}`.
- **Lien HelloAsso de renouvellement** construit depuis la config + le form le plus fréquent
  (même logique que `create_helloasso_memberships`) :
  `https://www.helloasso.com/associations/{HELLOASSO_ORG_SLUG}/adhesions/{form_slug}`.
- Seed d'un gabarit par défaut (migration ou au premier accès) pour que la page ne soit jamais vide.
- **Page de réglages** d'édition : `GET/POST /entities/members/reminder-template`
  (textarea sujet + corps, aperçu des variables). Sous `@login_required`.

### 5.5 Service d'envoi `app/services/membership_reminders.py`

```
members_to_remind(today=None) -> rows[]        # red + email + status!="?"
  réutilise _members_query / _last_membership_dates / build_member_rows / filtre §5.1

render_reminder(template, row, helloasso_url) -> (subject, html)

send_reminders(rows, dry_run=False) -> {sent, skipped, errors, error_lines}
  pour chaque row: construit Message(subject, recipients=[email], html), mail.send()
  capture les exceptions par adhérent → error_lines (ne bloque pas le lot)
```

Anti-spam (recommandé) : colonne `Entity.last_reminder_sent_at` (DateTime, nullable) ;
exclure ceux relancés depuis < N jours ; mise à jour après envoi réussi. → migration §6.

### 5.6 Routes (blueprint `entities`)

| Méthode | URL | Rôle |
|---|---|---|
| `GET` | `/entities/members/reminders` | **Aperçu** : liste des adhérents à relancer (rouge + email), bouton « Envoyer » |
| `POST` | `/entities/members/reminders` | Envoi effectif → `send_reminders()` → `flash` récap (envoyés/ignorés/erreurs) |
| `GET/POST` | `/entities/members/reminder-template` | Édition du gabarit d'email |

UI : bouton « Relancer les expirés » sur `members.html`, à côté de « Exporter » / « Synchroniser HelloAsso ».
Désactivé si SMTP non configuré (helper `_smtp_configured()` calqué sur `_helloasso_configured()`),
avec alerte expliquant les clés `.env` manquantes (même pattern que le bloc HelloAsso existant).

---

## 6. Migrations Alembic

1. **`email_templates`** — création table (§5.4) + insertion du gabarit `membership_reminder` par défaut.
2. **`entities.last_reminder_sent_at`** — `ADD COLUMN` DateTime nullable (§5.5, anti-spam) — *optionnel mais recommandé*.

> Multi-tenant : ces migrations s'appliquent à **chaque base tenant** (process de migration existant du projet).

---

## 7. Carte des fichiers (créés / modifiés)

| Action | Fichier | Contenu |
|---|---|---|
| **+** | `app/services/membership_status.py` | `member_birthday`, `member_status`, `build_member_rows`, `sort_member_rows`, `STATUS_ORDER` |
| **+** | `app/services/membership_reminders.py` | `members_to_remind`, `render_reminder`, `send_reminders` |
| **+** | `app/models/email_template.py` | modèle `EmailTemplate` (+ export dans `app/models/__init__.py`) |
| **+** | `app/templates/entities/reminder_preview.html` | aperçu liste à relancer |
| **+** | `app/templates/entities/reminder_template_form.html` | édition gabarit |
| **~** | `app/views/entities.py` | route `export`, alias `members.csv`, routes `reminders`, `reminder-template`, `_smtp_configured`, intégration `build_member_rows`/`sort_member_rows` dans `members()` |
| **~** | `app/templates/entities/members.html` | colonnes Date anniversaire + Statut, en-têtes triables ▲/▼, menu déroulant export, bouton relance |
| **~** | `app/extensions.py` | `mail = Mail()` |
| **~** | `app/__init__.py` | `mail.init_app(app)` |
| **~** | `app/config.py` | 6 clés `MAIL_*` |
| **~** | `.env` (+ doc `.env.example`) | clés SMTP |
| **~** | `requirements.txt` | `openpyxl`, `flask-mail` |
| **+** | `migrations/versions/*` | tables/colonnes §6 |
| **~** | `doc/routes.md`, `doc/models.md`, `doc/services.md` | documentation |

---

## 8. Contrats d'interface (signatures cibles)

```python
# app/services/membership_status.py
def member_birthday(last_ha, last_pos, today=None) -> date
def member_status(last_ha, last_pos, today=None) -> dict   # {status,color,label,css}
def build_member_rows(members_list, last_ha, last_pos, today=None) -> list[dict]
def sort_member_rows(rows, sort_by="name", sort="asc") -> list[dict]

# app/services/membership_reminders.py
def members_to_remind(today=None) -> list[dict]
def render_reminder(template: EmailTemplate, row: dict, helloasso_url: str) -> tuple[str, str]
def send_reminders(rows, dry_run=False) -> dict   # {sent,skipped,errors,error_lines}

# app/views/entities.py (routes)
GET  /entities/members            ?q&date_from&date_to&sort_by&sort
GET  /entities/members/export     ?format=csv|xlsx&<mêmes filtres+tri>
GET  /entities/members.csv        -> 301 export?format=csv (compat)
GET/POST /entities/members/reminders
GET/POST /entities/members/reminder-template
```

---

## 9. Validation (critères d'acceptation)

- [ ] Colonnes « Date anniversaire » et « Statut » (pilule colorée) visibles dans `/entities/members`.
- [ ] Tri fonctionnel asc/desc sur Nom, Date anniversaire, Statut (indicateur ▲/▼, filtres `q`/dates préservés).
- [ ] `member_birthday` conforme aux 4 cas du §2.1 (dont HA présent & POS vide).
- [ ] `member_status.color` = rouge si échéance ≤ aujourd'hui, orange si ≤ +30 j, vert sinon.
- [ ] Sélecteur d'export CSV/XLSX ; les deux fichiers contiennent les 9 colonnes dont
      `Date anniversaire`, `Statut`, `Couleur` ; filtres & tri courants respectés.
- [ ] XLSX ouvrable dans Excel/LibreOffice (feuille « Adhérents »).
- [ ] SMTP paramétrable via `.env` ; bouton relance désactivé si non configuré.
- [ ] Gabarit d'email éditable ; rendu des variables dont `{{ lien_helloasso }}` pointant vers le form HelloAsso.
- [ ] Aperçu puis envoi des relances aux adhérents rouges avec email ; récap flash (envoyés/ignorés/erreurs).

---

## 10. Étapes d'implémentation suggérées (`/sc:implement`)

1. **Calculs** — `membership_status.py` + tests unitaires (4 cas birthday, 3 couleurs, tri).
2. **Liste** — branchement dans `members()`, colonnes + tri dans `members.html`.
3. **Export** — route `export`, sélecteur, `render_csv`/`render_xlsx`, `openpyxl`, alias `members.csv`.
4. **Infra email** — `flask-mail`, `extensions`/`__init__`/`config`, clés `.env`.
5. **Gabarit** — modèle `EmailTemplate` + migration + page d'édition + seed défaut.
6. **Relance** — `membership_reminders.py`, routes preview/envoi, bouton UI, (option `last_reminder_sent_at`).
7. **Doc** — mise à jour `doc/`.
```
