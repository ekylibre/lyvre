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
| [Base documentaire](base_documentaire/README.md) | Cadrage (sans code) d'une base de connaissances comptables par référentiel (PCG, ANC 2018-06, SCI) et d'un assistant contextuel : besoins, fiches, règles YAML, architecture, plan |
| [Clôturer un exercice](cloture.md) | Assistant de clôture : contrôles, inventaire, fonds dédiés, FEC, clôture provisoire / définitive, à-nouveaux, affectation |
| [États financiers](reports.md) | Balance, grand livre, Bilan, Compte de résultat (asso / SCI) |
| [Saisie et rapprochement](saisie_rapprochement.md) | Écrans au clavier : saisie d'écriture, espace de rapprochement, raccourcis |
| [Factures d'achat](achats.md) | Factures fournisseurs Qonto ou saisies (lecture Factur-X / PDF / OCR, pièce jointe) : catalogue, TVA de l'exercice, comptabilisation en engagement, règlements Qonto ou OFX |

## Fonctionnalités

- **Plan comptable** — choisi à la création de l'instance : **association** (783 comptes du PCA) ou **SCI** (576 comptes, dont les sous-comptes des lignes de la déclaration 2072) ; arborescence hiérarchique, recherche instantanée
- **Menus par plan comptable** — navigation déclarée dans `app/menu_config.py` ; les menus propres aux associations (adhérents, bénévolat, Stancer, Odoo, indicateurs) sont masqués pour une SCI
- **Interface** — Application d'une seule page (React + Mantine, charte Lyvre claire / sombre) aux mêmes adresses que les anciennes pages : tableaux triables aux colonnes masquables (mémorisées dans le compte), filtres dans l'URL, fenêtres de saisie, palette de recherche **Ctrl+K**, messages en notifications ; lisible sur mobile
- **Notifications** — Cloche dans l'en-tête : fin des synchronisations en arrière-plan (Qonto, factures d'achat, Stancer) avec résumé, erreurs et lien vers l'écran, même si l'on a quitté la page ; message à l'arrivée
- **Saisie comptable** — Écritures en partie double dans un formulaire **entièrement au clavier** (autocomplétion des comptes, écart en direct, ligne d'équilibre préremplie, enregistrer et enchaîner), validation serveur par champ, génération automatique des références
- **Import bancaire** — Fichiers OFX/QFX (banques françaises), déduplication automatique par FITID
- **Factures d'achat Qonto** — Synchronisation des factures fournisseurs, lignes issues d'un **catalogue** produits / services, comptabilisation automatique en engagement (journal AC, compte 401NNN par fournisseur, TVA selon l'exercice), règlements 401 / banque rapprochés à partir des paiements Qonto, remplacement en lot des écritures de règle antérieures
- **Saisie des factures d'achat** — Dépôt du PDF, du scan ou de la photo, lecture (Factur-X, texte, OCR Tesseract) et formulaire prérempli, fournisseur reconnu (TVA, SIRET, IBAN, nom), doublons signalés, pièce rangée par instance, envoi facultatif à Qonto, règlement automatique depuis l'import OFX ; sauvegardes `.zip` (base + pièces)
- **Import Odoo** — CSV de lignes de facturation, table de staging avant comptabilisation
- **Rapprochement bancaire** — Espace de travail au clavier : suggestions notées (compte bancaire, montant, date), rapprochement en un geste ou en masse, création d'écriture en panneau latéral, règles sur la sélection, annulation (Ctrl+Z), contrôles de montant et de compte
- **États financiers** — Balance, grand livre, Bilan et Compte de résultat au format du plan de l'instance (associatif ou SCI) avec comparaison N/N-1 ; chaque compte compté une seule fois, tiers ventilés selon le sens du solde, bilan équilibré avant comme après clôture
- **Projets / activités** — Axe analytique unique : projet sur les lignes d'écriture (saisie, fiche avec affectation et **ventilation** d'une ligne sur plusieurs projets, même rapprochée), les lignes de facture d'achat et les règles ; liste des projets avec charges, produits et résultat, par exercice
- **Prévisionnel de trésorerie** — 12 mois glissants : soldes actuels (banques, caisses), factures d'achat et clients non réglées, budget restant, saisies manuelles répétées ; graphique, détail par mois, alerte de solde négatif (aussi au tableau de bord)
- **Budget** — Grille comptes × mois par exercice, générale ou par projet : saisie annuelle (douzièmes) ou mensuelle, comptes de regroupement admis, copie du budget ou du réalisé N-1 ; colonne des comptes figée au défilement ; **suivi** prévu / réalisé / écart à date par poste et par projet (hors budget signalé), graphique, export tableur, carte au tableau de bord ; **compte de résultat d'un projet** sur une période pour un financeur (factures jointes, impression, tableur)
- **Clôture d'exercice** — Assistant en 8 étapes : contrôles avec liens, écritures d'inventaire extournées en N+1, fonds dédiés, résultat, FEC (art. A47 A-1 du LPF) contrôlé à blanc, clôture provisoire (écritures numérotées) puis définitive (FEC figé), réouverture motivée, à-nouveaux et affectation du résultat ; rôle expert-comptable en lecture seule
- **Entités** — Répertoire de tiers (clients, fournisseurs, salariés, organismes) liés aux transactions bancaires
- **Moteur de règles** — Fichier YAML de règles pour catégoriser automatiquement les transactions importées et générer les écritures comptables associées (charges 6xx / produits 7xx)
- **Tableau de bord** — Sélecteur d'exercice, indicateurs (écritures, transactions non rapprochées, écritures déséquilibrées), graphiques Mantine Charts (résultat mensuel, ventes mensuelles, solde bancaire cumulé)
- **Versements Stancer** — Synchronisation **asynchrone** (thread daemon + table `sync_jobs`) des Payouts via l'API REST v2 (`https://api.stancer.com/v2`) et de leurs Payments associés (route `/v2/payouts/{id}/payments`). Rapprochement automatique des payouts avec les transactions bancaires importées via la référence Stancer présente dans le libellé OFX (`No <ref>`). Avancement suivi en direct (tâche interrogée chaque seconde, `GET /api/v1/jobs/<id>`).
- **Commandes POS Odoo** — Synchronisation XML-RPC de `pos.order` + lignes + paiements. Création automatique d'entités CLIENT par email (`res.partner`), détection des adhérents via libellé d'article (`Adhésion`).
- **Factures clients Odoo** — Synchronisation XML-RPC de `account.move` (`move_type='out_invoice'`) + lignes produit. Affichage du double statut comptable (`state` : draft/posted/cancel) et paiement (`payment_state` : not_paid/in_payment/partial/paid/reversed). Création automatique d'entités CLIENT par email du partenaire.
- **HelloAsso** — Synchronisation OAuth2 des commandes et adhésions (`/v5/organizations/{slug}/orders`). Marquage automatique des adhérents.
- **Tri & filtre temporel** — Sur les 8 listes datées (écritures, transactions, versements, paiements, commandes POS, factures clients, rapprochement, lot Odoo) : clic sur l'en-tête `Date` pour basculer asc/desc et filtre par mois (les 12 mois de l'exercice courant), conservés dans l'URL.
- **Indicateurs — Visibilité & Impact** (`/impact`) — Tableau de bord 4 dimensions (visibilité, environnemental, social, économique). L'**impact environnemental** (CO₂ évité, poids réemployé, taux de réemploi) est calculé à partir des **tonnages déclarés aux éco-organismes** (`eco_declarations`). Connecteurs GA4 / Facebook + saisie manuelle.
- **Indicateurs — Rapport d'activité** (`/rapport-activite`) — Rapport annuel mis en page (identité Seconde Nature), blocs narratifs éditables en **WYSIWYG (Tiptap, avec accès au code HTML)**, photos, tonnages éco-organismes (import `.xlsx`), aperçu à l'écran (HTML produit par le serveur). Exports **PDF** (weasyprint), **HTML** autonome, **DOCX** et **ODT** (LibreOffice headless) avec styles.
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
| Frontend | SPA React 19 + Mantine 9 + TypeScript (TanStack Query, react-router, mantine-datatable ; build Vite, Node 22 au build uniquement) ; tests Vitest et Playwright |
| Import OFX | ofxtools |
| Import CSV | pandas |
| Moteur de règles | PyYAML |
| Export ODS | odfpy |
| Rapport PDF | weasyprint (rendu serveur, graphes en SVG) |
| Export DOCX / ODT | LibreOffice headless (`soffice --convert-to`) depuis un HTML autonome |
| Éditeur de texte | Tiptap 3 via @mantine/tiptap (blocs du rapport d'activité, gabarit de relance) |
| Graphiques | Mantine Charts (tableau de bord, tendances des indicateurs) ; SVG serveur pour le rapport d'activité |
| API Stancer | requests + SDK officiel `stancer` |
| API Odoo | xmlrpc.client (stdlib) — endpoints `/xmlrpc/2/common` + `/xmlrpc/2/object` |
| API HelloAsso | requests — OAuth2 client_credentials v5 |
