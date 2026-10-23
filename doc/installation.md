# Installation et démarrage

## Prérequis

- Python 3.10 ou supérieur
- pip
- **Node.js 22** (`.nvmrc`) et npm — uniquement pour construire le front (SPA React + Mantine) ; inutile
  pour un déploiement Docker, où le build est fait dans l'image
- **Tesseract** avec le français, pour l'OCR des factures d'achat scannées ou photographiées
  (`sudo apt install tesseract-ocr tesseract-ocr-fra`) ; facultatif : sans lui, les PDF texte et
  Factur-X restent lus, un scan ouvre un formulaire à remplir. Inclus dans l'image Docker.

## Installation

### 1. Créer l'environnement virtuel

```bash
cd ~/projects/compta-asso
python3 -m venv .venv
source .venv/bin/activate      # Linux/macOS
# ou .venv\Scripts\activate    # Windows
```

### 2. Installer les dépendances

```bash
pip install -r requirements.txt
```

### 3. Configurer l'environnement

Copier et éditer le fichier `.env` :

```bash
cp .env .env.local
```

Variables disponibles :

| Variable | Défaut | Description |
|----------|--------|-------------|
| `SECRET_KEY` | `change-me-in-production` | Clé de signature des sessions Flask. **À changer impérativement en production.** |
| `DATABASE_URL` | (chemin absolu vers `instance/seconde-nature.db`) | URL SQLAlchemy de la base **tenant par défaut** (sert de fallback pour les scripts CLI ; chaque instance gère ensuite sa propre URL en base de méta). Voir le piège SQLite ci-dessous. |
| `META_DATABASE_URL` | (chemin absolu vers `instance/meta.db`) | URL SQLAlchemy de la **méta-base** (tables `users` + `instances`). |

> ⚠️ **Piège des URLs SQLite relatives**
>
> Flask-SQLAlchemy 3 résout les URLs SQLite **relatives** (`sqlite:///nom.db`, 3 slashes) **par rapport au dossier `instance/`** de Flask. Conséquences pratiques pour `DATABASE_URL` / `META_DATABASE_URL` :
>
> | Valeur dans `.env` | Fichier réellement ouvert | Statut |
> |--------------------|---------------------------|--------|
> | `sqlite:///seconde-nature.db` | `instance/seconde-nature.db` | ✅ correct (recommandé) |
> | `sqlite:///instance/seconde-nature.db` | `instance/**instance**/seconde-nature.db` (double `instance/`) | ❌ erreur `unable to open database file` |
> | `sqlite:////chemin/absolu/seconde-nature.db` (**4 slashes**) | `/chemin/absolu/seconde-nature.db` | ✅ correct, explicite |
> | variable absente | fallback `config.py` → chemin absolu calculé sur `instance/` | ✅ correct |
>
> Si tu écris ces variables en `.env` ou en config Dokploy / Kubernetes, utilise soit `sqlite:///<nom>.db` (sans `instance/`), soit un chemin absolu à 4 slashes, soit n'écris rien et laisse le fallback faire le travail.
| `FLASK_ENV` | `development` | Mode de démarrage (`development` ou `production`) |
| `ADMIN_EMAIL` | `admin@local` | Email du premier utilisateur admin créé par `seed_meta.py`. |
| `ADMIN_PASSWORD` | `admin` | Mot de passe du premier admin (uniquement utilisé par `seed_meta.py`). |
| `DEFAULT_INSTANCE_SLUG` | `seconde-nature` | Slug de la 1ère instance créée par `seed_meta.py`. |
| `DEFAULT_INSTANCE_LABEL` | `Seconde Nature` | Libellé de la 1ère instance. |
| `DEFAULT_INSTANCE_CHART` | `asso` | Plan comptable de la 1ère instance (`asso` ou `sci`) : chargé par `seed_accounts.py` sans argument dans une base vide, et enregistré par `seed_meta.py`. Une base déjà remplie garde son plan. |
| `DEFAULT_INSTANCE_URL` | `sqlite:///seconde-nature.db` | URL de la base tenant de la 1ère instance (relative au dossier `instance/`). |
| `STANCER_SECRET_KEY` | (vide) | Clé secrète Stancer (`sk_xxx`) utilisée pour interroger l'API v2 (`/v2/payouts` et `/v2/payouts/{id}/payments`). Tant qu'elle n'est pas définie, le bouton de synchronisation des Versements Stancer reste désactivé. |
| `STANCER_MODE` | `live` | Mode Stancer : `live` ou `test` |
| `QONTO_LOGIN` (ou `QONTO_API_ID`) | (vide) | Identifiant de l'organisation Qonto (clé API, menu Qonto › Intégrations et partenariats). **Repli commun à toutes les instances** : préférer la saisie dans Configuration › Intégrations › Qonto de l'instance concernée. |
| `QONTO_SECRET_KEY` (ou `QONTO_API_SECRET`) | (vide) | Clé secrète Qonto (même remarque). |
| `QONTO_STAGING_TOKEN` | (vide) | Jeton du bac à sable Qonto ; renseigné = bac à sable, vide = production. |
| `ODOO_URL` | (vide) | URL de l'instance Odoo (ex : `https://erp.example.org`). Requise par la sync POS (`/api/v1/orders/sync`) et factures clients (`/api/v1/customer-invoices/sync`). |
| `ODOO_DB` | (vide) | Nom de la base Odoo. |
| `ODOO_USERNAME` | (vide) | Login Odoo (souvent un email). |
| `ODOO_API_KEY` | (vide) | API key Odoo (générée dans Préférences → Compte → Clés API). Passée comme `password` aux endpoints XML-RPC. |
| `HELLOASSO_CLIENT_ID` | (vide) | Identifiant client OAuth2 HelloAsso (généré dans l'espace admin HelloAsso). |
| `HELLOASSO_CLIENT_SECRET` | (vide) | Secret OAuth2 HelloAsso. |
| `HELLOASSO_ORG_SLUG` | (vide) | Slug de l'organisation HelloAsso (visible dans l'URL : `helloasso.com/associations/{slug}`). |

Tant que les 4 variables `ODOO_*` ne sont pas définies (et qu'aucune valeur n'est saisie dans l'UI), ou si l'intégration est désactivée, les boutons de synchronisation POS et factures clients restent désactivés. Idem pour les 3 variables `HELLOASSO_*` et `STANCER_SECRET_KEY`.

> **Depuis octobre 2026** : les réglages des intégrations se saisissent par instance (**Configuration › Intégrations**, admin uniquement), où chaque intégration est aussi activée (désactivée par défaut) et testée. Les variables ci-dessus ne servent de **repli qu'en développement** (`INTEGRATIONS_ENV_FALLBACK`, vrai par défaut en développement, toujours faux en production). Voir [integrations.md](integrations.md). Voir [multi_tenant.md](multi_tenant.md) et [models.md](models.md#externalconnection--credentials-services-externes-tenant).

### 4. Initialiser la base tenant (1ère association)

```bash
# Créer les tables comptables dans instance/seconde-nature.db
FLASK_APP=run.py flask db upgrade

# Charger le plan comptable et les journaux par défaut
python seed_accounts.py          # plan associatif (783 comptes) — défaut
# python seed_accounts.py sci    # plan SCI (576 comptes)
```

L'argument choisit le référentiel : `asso` (`data/plan_comptable_asso.json`) ou
`sci` (`data/plan_comptable_sci.json`, généré depuis `doc/plan-comptable-SCI.pdf`).
Sans argument, le script complète le plan **déjà présent** dans la base (détecté par ses comptes
propres) ; une base vide reçoit `DEFAULT_INSTANCE_CHART` (défaut `asso`). Un argument contraire au
plan déjà chargé est refusé, pour ne jamais mélanger les deux référentiels.

La sortie attendue :

```
Plan comptable: 783 comptes créés (783 au total).
Journaux: 6 journaux créés.
```

### 5. Initialiser la méta-base (users + instances)

```bash
# Crée instance/meta.db, le 1er utilisateur admin et l'instance par défaut
python seed_meta.py
```

La sortie attendue :

```
Admin user created: admin@local
Default instance created: seconde-nature → sqlite:///seconde-nature.db
```

> Le script est idempotent : un second lancement n'écrase ni l'admin ni l'instance par défaut.

### 6. Démarrer l'application

```bash
# Construire le front (SPA React + Mantine) une première fois
npm --prefix frontend ci
npm --prefix frontend run build      # → app/static/dist/

python run.py
```

Sans build, les pages de saisie et de rapprochement affichent un message
« Interface indisponible : les fichiers du front ne sont pas construits ».

**Développement du front** (rechargement à chaud) :

```bash
npm --prefix frontend run dev                      # serveur Vite sur :5173
VITE_DEV_SERVER=http://localhost:5173 python run.py
```

**Vérification complète** avant de pousser : `make check` (typecheck TypeScript, tests Vitest,
build, puis `pytest`). Les tests n'appellent aucun service externe (clients Qonto, Stancer, Odoo… simulés) et
écrivent dans des dossiers temporaires ; les tests d'OCR (`tests/test_invoice_reader.py`) sont ignorés
si Tesseract n'est pas installé. Tests des factures d'achat : `tests/test_purchase_*.py`,
`tests/test_invoice_reader.py`, `tests/test_attachments.py`, `tests/test_instance_backup.py`.
Tests de l'API de la SPA : `tests/api/`.

**Parcours de bout en bout** (Playwright) : `make e2e` construit le front puis lance
`scripts/e2e_server.py` (Flask sur le port 5099, bases et dossier d'instance jetables, compte de
`frontend/e2e/fixtures.json`) et les tests de `frontend/e2e/`. Une seule fois avant :
`npx --prefix frontend playwright install chromium`.

L'application est accessible sur **http://127.0.0.1:5000**.

Connexion avec **l'email** (`ADMIN_EMAIL`) et **le mot de passe** (`ADMIN_PASSWORD`) renseignés en étape 5. Si une seule instance est active, elle est auto-sélectionnée après login.

### 7. Déploiement Docker (alternative à la procédure manuelle)

Pour la production ou un setup reproductible, l'application fournit un `Dockerfile` et un `docker-compose.yml` (1 seul service, volume sur `instance/`). Voir [doc/docker.md](docker.md) pour le guide complet.

```bash
docker compose up -d --build
# → http://localhost:5000
```

Le bootstrap (migrations + seeds) est exécuté automatiquement par l'entrypoint.

### 8. Provisionner d'autres instances (optionnel)

Depuis l'UI, un admin peut créer d'autres instances via le menu **Utilisateur → Instances → Nouvelle instance**. En mode "Automatique", le système :

1. Crée le fichier SQLite `instance/tenants/<slug>.db`
2. Applique les migrations du schéma comptable
3. Charge le plan comptable choisi dans le formulaire (**Association** : 783 comptes, **SCI** : 576 comptes) + 6 journaux

Le plan comptable est mémorisé sur l'instance (`Instance.chart`) et adapte les menus et la
présentation du Bilan / Compte de résultat (voir [multi_tenant.md](multi_tenant.md#plan-comptable-de-linstance)).

En mode "Manuel", l'admin fournit lui-même une URL (utile pour Postgres ou base préexistante).

---

## Journaux créés par défaut

| Code | Libellé |
|------|---------|
| `BQ` | Banque |
| `CA` | Caisse |
| `VT` | Ventes |
| `AC` | Achats |
| `OD` | Opérations diverses |
| `AN` | À-nouveaux |

D'autres journaux peuvent être ajoutés depuis **Paramètres → Journaux**.

---

## Mise à jour du schéma

Après une modification des modèles SQLAlchemy :

```bash
FLASK_APP=run.py flask db migrate -m "description du changement"
FLASK_APP=run.py flask db upgrade
```

---

## Configuration des comptes bancaires

Avant d'importer des fichiers OFX, il faut créer au moins un compte bancaire :

1. S'assurer qu'un compte `512xxx` existe dans le plan comptable (créé par le seed).
2. Aller dans **Paramètres → Plan comptable**, trouver le compte `512`.
3. Créer le compte bancaire via la future page `/bank-accounts/new` (ou directement en base) en liant ce compte GL.

Aller sur **Paramètres → Comptes bancaires → Nouveau compte**, sélectionner le compte GL `512x` correspondant et renseigner le libellé et l'IBAN.

---

## Structure des fichiers générés

```
instance/
├── meta.db              # Méta-base (users + instances)
├── seconde-nature.db    # Base tenant de la 1ère association
└── tenants/
    └── *.db             # Bases tenant des autres instances

migrations/              # Migrations Alembic du schéma tenant (default bind)
├── alembic.ini
├── env.py
└── versions/
    └── *.py
```

> Le schéma de la méta-base (`users`, `instances`) n'a pas de pipeline Alembic dédié dans cette version. Il est créé par `seed_meta.py` via `db.create_all(bind_key=['meta'])`. Une migration manuelle sera nécessaire si ce schéma évolue.
