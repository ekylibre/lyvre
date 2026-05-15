# Installation et démarrage

## Prérequis

- Python 3.10 ou supérieur
- pip

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
| `DATABASE_URL` | `sqlite:///instance/compta.db` | URL de connexion SQLAlchemy. Supporte PostgreSQL : `postgresql://user:pass@host/db` |
| `FLASK_ENV` | `development` | Mode de démarrage (`development` ou `production`) |
| `ADMIN_PASSWORD` | `admin` | Mot de passe de l'utilisateur administrateur |
| `STANCER_SECRET_KEY` | (vide) | Clé secrète Stancer (`sk_xxx`) utilisée pour interroger l'API v2 (`/v2/payouts` et `/v2/payouts/{id}/payments`). Tant qu'elle n'est pas définie, le bouton de synchronisation des Versements Stancer reste désactivé. |
| `STANCER_MODE` | `live` | Mode Stancer : `live` ou `test` |
| `ODOO_URL` | (vide) | URL de l'instance Odoo (ex : `https://erp.example.org`). Requise par la sync POS (`/orders/sync`) et factures clients (`/customer-invoices/sync`). |
| `ODOO_DB` | (vide) | Nom de la base Odoo. |
| `ODOO_USERNAME` | (vide) | Login Odoo (souvent un email). |
| `ODOO_API_KEY` | (vide) | API key Odoo (générée dans Préférences → Compte → Clés API). Passée comme `password` aux endpoints XML-RPC. |
| `HELLOASSO_CLIENT_ID` | (vide) | Identifiant client OAuth2 HelloAsso (généré dans l'espace admin HelloAsso). |
| `HELLOASSO_CLIENT_SECRET` | (vide) | Secret OAuth2 HelloAsso. |
| `HELLOASSO_ORG_SLUG` | (vide) | Slug de l'organisation HelloAsso (visible dans l'URL : `helloasso.com/associations/{slug}`). |

Tant que les 4 variables `ODOO_*` ne sont pas définies, les boutons de synchronisation POS et factures clients restent désactivés. Idem pour les 3 variables `HELLOASSO_*`.

### 4. Initialiser la base de données

```bash
# Créer les tables
FLASK_APP=run.py flask db upgrade

# Charger le plan comptable (783 comptes) et les journaux par défaut
python seed_accounts.py
```

La sortie attendue :

```
Plan comptable: 783 comptes créés (783 au total).
Journaux: 6 journaux créés.
```

### 5. Démarrer l'application

```bash
python run.py
```

L'application est accessible sur **http://127.0.0.1:5000**.

Connexion avec le mot de passe `admin` (ou la valeur de `ADMIN_PASSWORD`).

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
└── compta.db          # Base de données SQLite (gitignorée)

migrations/
├── alembic.ini
├── env.py
└── versions/
    └── *.py           # Fichiers de migration Alembic
```
