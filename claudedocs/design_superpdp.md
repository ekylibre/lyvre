# Intégration SUPER PDP (lot PDP1)

> Statut : **implémenté le 08/11/2026**, à essayer en bac à sable. Demande : « ajoute une intégration SuperPDP en gérant le conflit possible avec Qonto (un seul PDP par entreprise à un instant t) ».
> Documentation lue le 08/11/2026 : articles de https://www.superpdp.tech/documentation (rendus par l'API `internal/articles`) et référence OpenAPI 1.39.0.beta (`https://api.superpdp.tech/openapi/superpdp.json`), exemple officiel `superpdp/examples/quick_start.js`.

## 1. Ce que dit SUPER PDP

- **API** : `https://api.superpdp.tech/v1.beta/` ; OAuth 2.1 « client credentials » sur `/oauth2/token` (`client_id`, `client_secret` d'une application créée dans SUPER PDP, **une par entreprise**) ; jeton de 30 minutes. La clé détermine bac à sable ou production.
- **Envoi** : `POST /v1.beta/invoices` avec le fichier (Factur-X `application/pdf`, CII ou UBL `application/xml`), `external_id` (64 caractères) ; dépôt synchrone (`api:uploaded`), validation et acheminement **asynchrones**.
- **Réception** : `GET /v1.beta/invoices?direction=in&starting_after_id=…` ; identifiants strictement croissants, `has_after` pour la pagination ; fichier par `GET /invoices/{id}/download`.
- **Statuts** : liste d'événements (pas une machine à états) : `api:*` (SUPER PDP), `fr:200` à `fr:213` et `fr:501` (réforme), `ppf:*` (portail public). `POST /invoice_events` pour émettre `fr:204` à `fr:212` (par exemple `fr:212` encaissée, avec les montants par taux).
- **Annuaire** : une ligne d'annuaire (adresse de réception, en général le SIREN) ne peut être ouverte que par **une plateforme agréée** ; si le SIREN est déjà inscrit ailleurs, SUPER PDP lance une **portabilité** (confirmation par e-mail, 5 jours pour l'ancienne plateforme) ; la ligne est « en erreur » pendant la migration.

## 2. Décisions

- **PDP1-D1 Une seule plateforme agréée** : SUPER PDP (parties « Envoi » ou « Réception ») et Qonto (partie « Ventes », émission Factur-X par Qonto) ne peuvent pas être actives ensemble. Refus motivé (HTTP 409) à l'activation de l'une ou au cochage de la partie concernée de l'autre (`external_config.PDP_ROLES`, `_check_pdp`, `acting_pdp`). Qonto garde ses relevés et ses achats : ce ne sont pas des rôles de plateforme.
- **PDP1-D2 Envoi à la demande** : bouton « Transmettre (SUPER PDP) » sur une facture ou un avoir émis, au PDF Factur-X conforme ; jamais d'envoi automatique. Refus motivé : brouillon, devis, pièce émise par Qonto, PDF sans Factur-X, pièce déjà transmise.
- **PDP1-D3 Réception par synchronisation** : bouton « Recevoir (SUPER PDP) » dans Achats (tâche de fond) ; reprise après la dernière facture reçue (`max(pdp_id)`) ; facture lue par le lecteur Factur-X/CII/UBL existant ; facture d'achat `source = superpdp`, `is_einvoice`, fournisseur rattaché, lignes par défaut (comme Qonto), fichier rangé avec les pièces. Une autofacture reçue (type 389) est signalée, pas importée (elle relève de Ventes › Autofactures).
- **PDP1-D4 Statuts** : à chaque synchronisation, dernier événement de chaque pièce transmise non terminée (`GET /invoice_events?invoice_id=`), avec son libellé français ; erreur gardée et affichée sur la pièce.
- **PDP1-D5 Sonde** : `GET /companies/me` (entreprise, SIREN, bac à sable ou production) et, si la réception est cochée, les adresses de réception et leur état (« en erreur (portabilité depuis une autre plateforme ?) »).

## 3. Réalisé

- `app/services/superpdp_client.py` (jeton, routes), `app/services/superpdp.py` (envoi, réception, statuts, tâche), sonde dans `integrations.py`.
- Migration `f1a3c5e7b9d2` : `sales.pdp_id`, `pdp_status`, `pdp_error`, `pdp_sent_at` ; `purchases.pdp_id`, `pdp_status`.
- API : `POST /api/v1/sales/<id>/superpdp`, `POST /api/v1/superpdp/sync` ; `pdp` et `pdp_send` dans la fiche de vente ; `meta.superpdp` des achats.
- Écrans : fiche d'intégration (champs et parties), bouton et statut sur la fiche de vente, réception et badge « SUPER PDP » dans Achats.
- Tests : `tests/api/test_superpdp.py` (exclusivité, envoi et statuts, partie requise, réception, sonde), `sales.test.tsx`.

## 4. Suite

- Statut `fr:212` « encaissée » à l'encaissement d'une facture de prestations (montants par taux), avec confirmation.
- Refus / litige d'une facture d'achat reçue (`fr:207`, `fr:210`) depuis la fiche d'achat.
- Création de la ligne d'annuaire depuis Lyvre (aujourd'hui dans l'interface SUPER PDP), flux « authorization code » pour éviter de copier les identifiants.
- E-reporting : l'export B2C existant suit déjà le schéma `POST /b2c_transactions` ; transmission directe à brancher.
- Essai réel en bac à sable (entreprises fictives Burger Queen et Tricatel) avant la production.
