# Compta Asso — Documentation

Application web de comptabilité pour associations loi 1901 (plan comptable des associations) et SCI (plan comptable général adapté aux SCI). Le plan comptable est choisi par instance.

## Sommaire

| Document | Contenu |
|----------|---------|
| [Installation](installation.md) | Prérequis, installation, premier démarrage |
| [Architecture](architecture.md) | Structure du projet, stack technique, flux de données |
| [Multi-tenant & users](multi_tenant.md) | Gestion des instances (1 DB par asso) et des utilisateurs |
| [Sauvegardes](backups.md) | Sauvegarde / restauration d'instances SQLite depuis l'UI |
| [Docker](docker.md) | Déploiement conteneurisé (Dockerfile + docker-compose) |
| [Modèles](models.md) | Schéma de base de données, tables, relations |
| [Routes](routes.md) | Référence complète de toutes les URLs |
| [Services](services.md) | Logique métier : comptabilité, imports, rapprochement |
| [Imports](imports.md) | Guide import OFX (banque) et CSV Odoo |
| [États financiers](reports.md) | Balance, grand livre, Bilan, Compte de résultat (asso / SCI) |
| [Saisie et rapprochement](saisie_rapprochement.md) | Îlots React au clavier : saisie d'écriture, espace de rapprochement, raccourcis |
| [Factures d'achat](achats.md) | Factures fournisseurs Qonto ou saisies (lecture Factur-X / PDF / OCR, pièce jointe) : catalogue, TVA de l'exercice, comptabilisation en engagement, règlements Qonto ou OFX |

## Fonctionnalités

- **Plan comptable** — choisi à la création de l'instance : **association** (783 comptes du PCA) ou **SCI** (576 comptes, dont les sous-comptes des lignes de la déclaration 2072) ; arborescence hiérarchique, recherche instantanée
- **Menus par plan comptable** — navigation déclarée dans `app/menu_config.py` ; les menus propres aux associations (adhérents, bénévolat, Stancer, Odoo, indicateurs) sont masqués pour une SCI
- **Interface réactive** — Filtres, tri, recherche, actions et formulaires sans rechargement de page (HTMX), messages en notifications
- **Saisie comptable** — Écritures en partie double dans un formulaire **entièrement au clavier** (autocomplétion des comptes, écart en direct, ligne d'équilibre préremplie, enregistrer et enchaîner), validation serveur par champ, génération automatique des références
- **Import bancaire** — Fichiers OFX/QFX (banques françaises), déduplication automatique par FITID
- **Factures d'achat Qonto** — Synchronisation des factures fournisseurs, lignes issues d'un **catalogue** produits / services, comptabilisation automatique en engagement (journal AC, compte 401NNN par fournisseur, TVA selon l'exercice), règlements 401 / banque rapprochés à partir des paiements Qonto, remplacement en lot des écritures de règle antérieures
- **Saisie des factures d'achat** — Dépôt du PDF, du scan ou de la photo, lecture (Factur-X, texte, OCR Tesseract) et formulaire prérempli, fournisseur reconnu (TVA, SIRET, IBAN, nom), doublons signalés, pièce rangée par instance, envoi facultatif à Qonto, règlement automatique depuis l'import OFX ; sauvegardes `.zip` (base + pièces)
- **Import Odoo** — CSV de lignes de facturation, table de staging avant comptabilisation
- **Rapprochement bancaire** — Espace de travail au clavier : suggestions notées (compte bancaire, montant, date), rapprochement en un geste ou en masse, création d'écriture en panneau latéral, règles sur la sélection, annulation (Ctrl+Z), contrôles de montant et de compte
- **États financiers** — Balance, grand livre, Bilan et Compte de résultat au format du plan de l'instance (associatif ou SCI) avec comparaison N/N-1 ; chaque compte compté une seule fois, tiers ventilés selon le sens du solde, bilan équilibré avant comme après clôture
- **Clôture d'exercice** — Verrouillage des écritures (obligation légale française)
- **Entités** — Répertoire de tiers (clients, fournisseurs, salariés, organismes) liés aux transactions bancaires
- **Moteur de règles** — Fichier YAML de règles pour catégoriser automatiquement les transactions importées et générer les écritures comptables associées (charges 6xx / produits 7xx)
- **Tableau de bord** — Sélecteur d'exercice, indicateurs (écritures, transactions non rapprochées, écritures déséquilibrées), graphiques ECharts (résultat mensuel, ventes mensuelles, solde bancaire cumulé)
- **Versements Stancer** — Synchronisation **asynchrone** (thread daemon + table `sync_jobs`) des Payouts via l'API REST v2 (`https://api.stancer.com/v2`) et de leurs Payments associés (route `/v2/payouts/{id}/payments`). Rapprochement automatique des payouts avec les transactions bancaires importées via la référence Stancer présente dans le libellé OFX (`No <ref>`). Suivi en temps réel via fragment HTMX qui poll toutes les 2 s.
- **Commandes POS Odoo** — Synchronisation XML-RPC de `pos.order` + lignes + paiements. Création automatique d'entités CLIENT par email (`res.partner`), détection des adhérents via libellé d'article (`Adhésion`).
- **Factures clients Odoo** — Synchronisation XML-RPC de `account.move` (`move_type='out_invoice'`) + lignes produit. Affichage du double statut comptable (`state` : draft/posted/cancel) et paiement (`payment_state` : not_paid/in_payment/partial/paid/reversed). Création automatique d'entités CLIENT par email du partenaire.
- **HelloAsso** — Synchronisation OAuth2 des commandes et adhésions (`/v5/organizations/{slug}/orders`). Marquage automatique des adhérents.
- **Tri & filtre temporel** — Sur les 8 listes datées (écritures, transactions, versements, paiements, commandes POS, factures clients, rapprochement, lot Odoo) : clic sur l'en-tête `Date` pour basculer asc/desc (avec indicateur ▲/▼) et filtre par mois (dropdown alimenté par les 12 mois de l'exercice courant).
- **Indicateurs — Visibilité & Impact** (`/impact`) — Tableau de bord 4 dimensions (visibilité, environnemental, social, économique). L'**impact environnemental** (CO₂ évité, poids réemployé, taux de réemploi) est calculé à partir des **tonnages déclarés aux éco-organismes** (`eco_declarations`). Connecteurs GA4 / Facebook + saisie manuelle.
- **Indicateurs — Rapport d'activité** (`/rapport-activite`) — Rapport annuel mis en page (identité Seconde Nature), blocs narratifs éditables en **WYSIWYG (Quill)**, photos, tonnages éco-organismes (import `.xlsx`), étiquette ADEME `impactco2.fr`. Exports **PDF** (weasyprint), **HTML** autonome, **DOCX** et **ODT** (LibreOffice headless) avec styles.
- **Exports** — CSV (séparateur `;`, UTF-8 BOM, virgule décimale) et ODS (OpenDocument avec formules de totaux, références de cellules et styles) pour le compte de résultat ; impression PDF stylisée pour tous les états

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
| Frontend | Jinja2 + Bootstrap 5 + HTMX ; îlots React 18 + TypeScript (build Vite, Node 22 au build uniquement) |
| Import OFX | ofxtools |
| Import CSV | pandas |
| Moteur de règles | PyYAML |
| Export ODS | odfpy |
| Rapport PDF | weasyprint (rendu serveur, graphes en SVG) |
| Export DOCX / ODT | LibreOffice headless (`soffice --convert-to`) depuis un HTML autonome |
| Éditeur de texte | Quill 2.0.3 (WYSIWYG, blocs narratifs du rapport d'activité) |
| Graphiques | Mantine Charts (tableau de bord) ; ECharts et SVG serveur pour le rapport d'activité |
| API Stancer | requests + SDK officiel `stancer` |
| API Odoo | xmlrpc.client (stdlib) — endpoints `/xmlrpc/2/common` + `/xmlrpc/2/object` |
| API HelloAsso | requests — OAuth2 client_credentials v5 |
