# Compta Asso — Documentation

Application web de comptabilité pour associations loi 1901, conforme au Plan Comptable Associatif (PCA 1999).

## Sommaire

| Document | Contenu |
|----------|---------|
| [Installation](installation.md) | Prérequis, installation, premier démarrage |
| [Architecture](architecture.md) | Structure du projet, stack technique, flux de données |
| [Modèles](models.md) | Schéma de base de données, tables, relations |
| [Routes](routes.md) | Référence complète de toutes les URLs |
| [Services](services.md) | Logique métier : comptabilité, imports, rapprochement |
| [Imports](imports.md) | Guide import OFX (banque) et CSV Odoo |
| [États financiers](reports.md) | Balance, grand livre, Bilan, Compte de résultat |

## Fonctionnalités

- **Plan comptable** — 783 comptes du PCA chargés, arborescence hiérarchique, recherche instantanée
- **Saisie comptable** — Écritures en partie double, validation débit = crédit, génération automatique des références
- **Import bancaire** — Fichiers OFX/QFX (banques françaises), déduplication automatique par FITID
- **Import Odoo** — CSV de lignes de facturation, table de staging avant comptabilisation
- **Rapprochement bancaire** — Suggestions automatiques par montant/date, rapprochement en un clic
- **États financiers** — Balance, grand livre, Bilan et Compte de résultat au format PCA avec comparaison N/N-1
- **Clôture d'exercice** — Verrouillage des écritures (obligation légale française)
- **Entités** — Répertoire de tiers (clients, fournisseurs, salariés, organismes) liés aux transactions bancaires
- **Moteur de règles** — Fichier YAML de règles pour catégoriser automatiquement les transactions importées et générer les écritures comptables associées (charges 6xx / produits 7xx)
- **Tableau de bord** — Sélecteur d'exercice, indicateurs (écritures, transactions non rapprochées, écritures déséquilibrées), graphiques ECharts (résultat mensuel, ventes mensuelles, solde bancaire cumulé)
- **Versements Stancer** — Synchronisation **asynchrone** (thread daemon + table `sync_jobs`) des Payouts via l'API REST v2 (`https://api.stancer.com/v2`) et de leurs Payments associés (route `/v2/payouts/{id}/payments`). Rapprochement automatique des payouts avec les transactions bancaires importées via la référence Stancer présente dans le libellé OFX (`No <ref>`). Suivi en temps réel via fragment HTMX qui poll toutes les 2 s.
- **Exports** — CSV (séparateur `;`, UTF-8 BOM, virgule décimale) et ODS (OpenDocument avec formules `=SUM`, références de cellules et styles) pour le compte de résultat ; impression PDF stylisée pour tous les états

## Démarrage rapide

```bash
cd ~/projects/compta-asso
source .venv/bin/activate
python run.py
# Accès : http://127.0.0.1:5000  —  Mot de passe : admin
```

## Stack technique

| Couche | Technologie |
|--------|-------------|
| Backend | Python 3 / Flask 3.1 |
| Base de données | SQLite (SQLAlchemy + Alembic) |
| Frontend | Jinja2 + Bootstrap 5 + HTMX |
| Import OFX | ofxtools |
| Import CSV | pandas |
| Moteur de règles | PyYAML |
| Export ODS | odfpy |
| Graphiques | echarts-python (génère le JSON) + Apache ECharts 5 (rendu navigateur) |
| API Stancer | requests + SDK officiel `stancer` |
