# Invoice Ninja v5 — analyse comparative pour Lyvre

Sources examinées (23/10/2026) :
- Code : https://github.com/invoiceninja/invoiceninja/tree/v5-develop (clone `--depth 1`, lu sans exécution : `app/Models`, `app/Services`, `app/DataMapper/CompanySettings.php`, `composer.json`, `README.md`, `LICENSE`, `openapi/`)
- Doc utilisateur : https://invoiceninja.github.io/en/user-guide/ (le site est rendu en JS, la lecture s'est faite sur les sources markdown du dépôt https://github.com/invoiceninja/invoiceninja.github.io, `docs/user-guide/*`)
- API : https://api-docs.invoicing.co/ (spec OpenAPI `openapi/api-docs.yaml` dans le dépôt)
- Offres : https://invoiceninja.com/pricing-plans/

**En résumé** : Invoice Ninja est un logiciel de **facturation et de gestion commerciale** (facturation clients, encaissement en ligne, temps passé, dépenses), **pas un logiciel de comptabilité**. Il n'a ni plan comptable, ni partie double, ni journaux, ni bilan. Il recoupe donc Lyvre seulement sur les ventes, les achats/dépenses et le rapprochement bancaire, et il est nettement plus riche sur le **cycle client** : portail client, paiement en ligne, relances automatiques, abonnements, facture électronique et PEPPOL.

---

## 1. Technologies

| Sujet | Invoice Ninja v5 |
|---|---|
| Langage / framework back | PHP ≥ 8.2 (jusqu'à 8.5), **Laravel 12** (`composer.json`) |
| Base de données | **MySQL / MariaDB** par défaut (`DB_CONNECTION=mysql`), driver pgsql déclaré dans la config. Environ 317 migrations. Plusieurs connexions MySQL pour le sharding en SaaS (`db-ninja-01`, `db-ninja-02`). |
| Front admin | SPA **React + TypeScript** (dépôt séparé `invoiceninja/ui`, démo https://react.invoicing.co/demo). L'ancien front **Flutter** (`admin-portal`) sert aux applis bureau et mobiles. |
| Portail client | Rendu côté serveur par Laravel (Blade + Livewire) |
| Applications | iOS, Android (aussi sur F-Droid), macOS, Windows, Linux (Snap, Flatpak). Elles fonctionnent aussi avec une instance auto-hébergée. |
| Licence | **Elastic License 2.0 (ELv2)**, *source-available* et **pas open source au sens OSI**. On peut auto-héberger, mais pas revendre le logiciel comme service. Toutes les fonctions Pro/Enterprise sont dans le code. Une licence « white-label » à 40 $/an retire la marque côté client. Contributions sous CLA. |
| Déploiement | SaaS (invoicing.co), auto-hébergement (serveur/VM, image Docker officielle, Cloudron, Softaculous, Elestio, YunoHost). Files d'attente Laravel et cron obligatoires (relances, récurrences, synchronisation bancaire). |
| API | REST JSON complète (environ 320 routes), authentification par en-tête `X-API-TOKEN`, spec OpenAPI publiée. Environ 65 types d'événements **webhooks** (`app/Models/Webhook.php`). |
| Intégrations notables | Stripe (et Stripe Connect), PayPal, GoCardless (prélèvement SEPA/BACS), Mollie, Square, Braintree, Authorize.net, Checkout.com, Razorpay, BTCPay, Blockonomics et une vingtaine d'autres passerelles (`app/PaymentDrivers`). Flux bancaires **Yodlee** (US) et **GoCardless/Nordigen** (UE). Synchronisation **QuickBooks Online** (`app/Services/Quickbooks`). OCR **Mindee** pour les justificatifs. Postmark, Mailgun, Brevo pour l'e-mail. Accès PEPPOL via **Storecove** et **Qvalia**. |
| Tarifs SaaS | Gratuit (5 clients) ; Pro 14 $/mois ; Enterprise à partir de 18 $/mois (multi-utilisateurs, synchronisation bancaire, e-facturation/PEPPOL, 250 crédits PEPPOL inclus). |

---

## 2. Méthodes et données comptables

### Le modèle de fond : des documents commerciaux et des soldes, sans partie double
- Aucune entité écriture, journal ou compte. Le seul « grand livre » est `CompanyLedger` : `client_id`, `adjustment`, `balance`, `notes`, et un lien polymorphe `company_ledgerable` vers une facture ou un paiement. C'est un **historique du solde client** (un compte 411 implicite par client), pas une comptabilité générale.
- `TransactionEvent` est un instantané horodaté à chaque événement : `client_balance`, `client_paid_to_date`, `client_credit_balance`, `invoice_balance`, `invoice_paid_to_date`, `invoice_status`, `payment_amount`, `payment_applied`, `payment_refunded`, `credit_balance`, `period`, `reporting_data`. Il sert aux rapports de TVA par période et aux rapports « à la date de » : on recalcule l'état à une date passée sans rejouer d'écritures.
- Le passage en comptabilité passe par l'export CSV ou par la **synchronisation QuickBooks Online** (clients, factures, paiements, produits, codes de taxe).

### Factures (`Invoice`)
- Champs : `number`, `date`, `due_date`, `status_id`, `po_number`, `line_items` (JSON embarqué, pas de table de lignes), `discount` + `is_amount_discount`, `partial` + `partial_due_date` (**acompte demandé**), `amount`, `balance`, `paid_to_date`, `total_taxes`, `uses_inclusive_taxes` (TTC ou HT), `tax_name1..3` / `tax_rate1..3` (jusqu'à 3 taxes au niveau facture, plus 3 par ligne), `custom_surcharge1..4` (frais additionnels, taxables ou non), `exchange_rate`, `project_id`, `vendor_id`, `location_id` (adresse ou établissement de livraison), `recurring_id`, `design_id`, `e_invoice` (données e-facture en JSON), `backup`, `sync` (état QuickBooks), `custom_value1..4`, `public_notes`, `private_notes`, `terms`, `footer`.
- Statuts : Brouillon, Envoyée, Partielle, Payée, Annulée, **Extournée** (*reversed* : annulation qui génère un avoir), plus deux statuts calculés, En retard et Impayée.
- Option `lock_invoices` : verrouillage de la facture après envoi ou après paiement.
- Option `auto_archive_invoice` à l'état payé ou annulé.

### Paiements (`Payment` + table pivot `Paymentable`)
- Un paiement s'impute sur **plusieurs factures et avoirs** via `paymentables` (montant imputé, montant remboursé).
- Champs : `amount`, `applied` (montant imputé, le reste reste **non affecté**), `refunded`, `status_id` (En attente, Annulé, Échoué, Terminé, Partiellement remboursé, Remboursé), `type_id` (moyen de paiement), `company_gateway_id`, `gateway_type_id`, `transaction_reference`, `exchange_rate`, `exchange_currency_id` (devise de conversion), `is_manual`, `idempotency_key`, `refund_meta`.
- **Remboursements** partiels ou totaux, renvoyés à la passerelle quand c'est possible.
- **Prépaiements** : depuis le portail, le client paie sans facture (acompte, provision), éventuellement en récurrent. Le montant reste non affecté jusqu'à son imputation.

### Avoirs (`Credit`)
- C'est un document à part entière avec statuts Brouillon, Envoyé, Partiel, Appliqué. Il porte un `balance` consommable : on l'**utilise comme moyen de paiement** sur d'autres factures, ou le client l'applique depuis le portail.
- On peut le créer depuis une facture (« Credit Note ») avec la référence à la facture d'origine, exigée par PEPPOL. Une **facture négative** est aussi acceptée.

### Taxes
- Deux modes : **taxe par ligne ou taxe globale**, prix **TTC ou HT**, et **taux manuels ou calculés**.
- Calcul automatique : taxe de vente US (ZipTax, catégories de produits, exonérations) et **TVA UE**, avec seuils, **OSS (guichet unique)**, catégories de produits (service, numérique, physique, exonéré, taux réduit) et autoliquidation intracommunautaire selon le client.
- Contrôle des numéros de TVA (`VatNumberCheck`, VIES).
- Rapports « Tax Summary » et **Tax Period Report**, ce dernier en comptabilité d'engagement ou de trésorerie.

### Dépenses (`Expense`, `ExpenseCategory`, `RecurringExpense`)
- Champs : `vendor_id`, `client_id`, `project_id`, `category_id`, `amount`, `foreign_amount` + `exchange_rate` + `invoice_currency_id`, `tax_name/rate/amount1..3`, `calculate_tax_by_amount`, `uses_inclusive_taxes`, `payment_date`, `payment_type_id`, `transaction_id` (lien bancaire), `should_be_invoiced` (**dépense refacturable**), `invoice_documents` (joindre le justificatif à la facture client), `e_invoice` (facture fournisseur électronique reçue).
- **Dépenses récurrentes**, avec génération automatique.
- **Bons de commande** fournisseurs (`PurchaseOrder`) : Brouillon, Envoyé, Accepté (par le fournisseur sur un **portail fournisseur**), Reçu, puis conversion en dépense. La réception peut **incrémenter le stock produit**.
- **Réception par e-mail** des factures fournisseurs (boîte entrante Mailgun, Brevo ou IMAP), avec OCR Mindee ou lecture des **XML ZUGFeRD/Factur-X/UBL** (`FacturXXmlExtractor`, `ZugferdEDocument`, `UblEDocument`).

### Récurrence (`RecurringInvoice`, `RecurringQuote`, `RecurringExpense`, `Scheduler`)
- Champs : `frequency_id` (de quotidien à triennal), `next_send_date`, `remaining_cycles` (nombre fini ou infini), `due_date_days`, `auto_bill` (off, optin, optout, always) et `auto_bill_enabled`.
- Les factures récurrentes sont **envoyées automatiquement** (pas seulement créées en brouillon) et peuvent être **prélevées automatiquement** sur le moyen de paiement enregistré (`ClientGatewayToken`) : carte, SEPA, ACH.
- Variables de date dans le texte des lignes (`:MONTH`, `:YEAR`…).
- Option `is_proforma`.
- `Scheduler` : tâches planifiées génériques, comme l'**envoi périodique des relevés de compte client** (`EmailStatementService`), l'envoi de rapports par e-mail ou la facturation automatique des tâches en cours.

### Multi-devises
- Une devise par client. Le taux de change est figé sur chaque document (`exchange_rate`) et **mis à jour chaque jour automatiquement** (`app/Jobs/Util/UpdateExchangeRates.php`).
- Conversion des paiements (`exchange_currency_id`) et des dépenses (`foreign_amount`).
- Rapports convertis dans la devise de la société.

### Numérotation
- Motifs paramétrables par type de document : `{$counter}`, `{$year}`, `{$date:Y-m-d}`, `{$client_counter}`, `{$group_counter}`, `{$client_number}`, `{$user_id}`, champs personnalisés…
- Remise à zéro périodique (`reset_counter_frequency_id`), **compteur partagé devis/factures** en option, compteurs propres aux **groupes de clients**, unicité garantie.

### Facture électronique
- Formats produits : **PEPPOL BIS (UBL)**, **ZUGFeRD / XRechnung / Factur-X** via la bibliothèque `horstoeko/zugferd` (XML embarqué dans le PDF/A-3 avec l'option « Merge E-Invoice and PDF »), **EN16931** générique, Facturae (ES), **Verifactu** (ES, alpha, transmission à l'AEAT), FatturaPA (IT) et FACT1 (RO) en génération seule. Devis électroniques en **Order-X**.
- **Point d'accès PEPPOL** opéré par Invoice Ninja (via Storecove) : envoi et **réception** d'e-factures. Les instances auto-hébergées passent par le proxy hébergé, sans stockage côté éditeur d'après la doc. France listée parmi les pays supportés : le **SIRET (schéma 0009)** du destinataire est requis.
- **E-reporting France** en cours de développement dans le code (`app/Services/EDocument/Standards/France`) : profils de déclaration par décade, mensuel ou bimestriel, variantes transaction ou paiement (initiale ou rectificative), calcul de deltas, notification des encaissements, callbacks de soumission. Cela vise la réforme française 2026-2027 (e-reporting B2C, international, encaissements de prestations de services). La doc utilisateur n'en parle pas encore.
- Règles d'intégrité : une facture envoyée en e-facture n'est plus modifiable, une correction passe par un avoir, et chaque ligne doit porter un **code ou motif d'exonération** (`EInvoicingLog` et `EInvoicingToken` tracent les envois).

### Portail client
- Espace par contact (`ClientContact`, invitations par document `*Invitation` avec suivi d'ouverture), avec mot de passe en option.
- Onglets : factures, factures récurrentes, paiements, devis, avoirs, **moyens de paiement enregistrés**, documents, **relevé de compte** (PDF), abonnements, prépaiement.
- **Acceptation et signature électronique des devis**, conditions à accepter, paiement partiel ou en trop (`client_portal_allow_under_payment` / `over_payment`, avec un minimum), téléversement de documents par le client.
- Thème personnalisable par CSS, domaine personnalisé en SaaS.
- **Portail fournisseur** symétrique pour les bons de commande.

### Passerelles de paiement
- Une trentaine de pilotes. `CompanyGateway` porte la configuration chiffrée, les frais ajoutés selon le moyen de paiement (*fees and limits*), les montants minimum et maximum, et les moyens acceptés.
- Les tokens clients (`ClientGatewayToken`) permettent le prélèvement récurrent : carte, **mandat SEPA** via GoCardless ou Stripe, ACH, BACS.
- Les **webhooks des passerelles** marquent les paiements terminés ou échoués.

### Banque et rapprochement (`BankIntegration`, `BankAccount`, `BankTransaction`, `BankTransactionRule`)
- Sources : synchronisation automatique Yodlee ou GoCardless/Nordigen, import CSV, saisie manuelle.
- `BankTransaction` : `amount`, `currency_id`, `base_type` (crédit ou débit), `description`, `participant`, `participant_name`, `category_id`, `invoice_ids` (rapprochement **multi-factures**), `payment_id`, `expense_id`, `vendor_id`, `status_id` (Non rapprochée → **Rapprochée** (suggestion) → **Convertie**), `bank_transaction_rule_id`.
- Deux conversions : encaissement → **paiement imputé sur une ou plusieurs factures**, décaissement → **dépense** (fournisseur et catégorie), en masse possible.
- Règles (`BankTransactionRule`) : conditions JSON sur description, montant, référence ou participant, combinées en ET ou en OU (`matches_on_all`), avec `applies_to` crédit ou débit, `on_credit_match` et **`auto_convert`** (création automatique de la dépense ou du paiement sans validation). Repérage automatique d'un numéro de facture dans le libellé.

### Rapports (`app/Services/Report`)
- Exports CSV ou XLSX à colonnes personnalisables, par entité : clients, factures, lignes de facture, devis, paiements, avoirs, dépenses, récurrences, produits, tâches.
- Rapports spéciaux : **Profit & Loss** (sur base encaissements ou facturation), **balance âgée clients** détaillée et synthétique (*AR detail / summary*), soldes clients, ventes par client, par utilisateur et par produit, **synthèse TVA**, **TVA par période**, rapport projet, remboursements, e-factures.
- Envoi des rapports par e-mail avec un **ZIP des justificatifs**. Rapports planifiés.

---

## 3. Fonctionnalités (par domaine)

**Tiers**
- Clients avec plusieurs contacts, adresses de facturation et de livraison, **établissements** (`Location`) avec leur fiscalité propre, devise, langue et conditions de paiement par client.
- **Groupes de clients** avec paramètres hérités (numérotation, modèles, relances, passerelles).
- Fusion de doublons, purge RGPD, champs personnalisés (4 par entité), **tags**.
- Fournisseurs avec contacts et portail fournisseur.

**Ventes**
- Devis (Brouillon, Envoyé, Approuvé, Converti, Rejeté, Annulé, Expiré ; conversion automatique en facture ; devis récurrents ; Order-X).
- Factures, factures récurrentes, avoirs.
- Acomptes demandés (`partial`), remises, frais additionnels, pro forma.
- Produits avec **gestion de stock** (quantités, seuil d'alerte, décrément à la facturation).
- Éditeur de **modèles PDF** (designs HTML/CSS, 11+ modèles), QR code de paiement (Swiss QR, EPC/IBAN), arrondi suisse.
- **Propositions commerciales** (`Proposal`).

**Encaissement**
- Paiement en ligne via une trentaine de passerelles, moyens de paiement enregistrés, **facturation automatique** (*auto-bill*), prélèvement SEPA (GoCardless, Stripe), remboursements.
- Prépaiements, paiements partiels ou en trop, frais de passerelle refacturés au client.
- **Liens de paiement / abonnements** (`Subscription`) : page publique d'achat avec produits récurrents et optionnels, essai gratuit, code promo, tarif par siège, changement de formule, annulation et remboursement au prorata, webhooks d'éligibilité.

**Relances**
- 3 relances automatiques plus une **relance sans fin**, chacune à J±N par rapport à la date de facture ou d'échéance, avec heure d'envoi.
- **Pénalités de retard** fixes ou en pourcentage, ajoutées à chaque niveau.
- Modèles d'e-mail par niveau.
- Relevés de compte périodiques.

**Temps et projets**
- Tâches avec **chronomètre** (`time_log`, `is_running`), vue **Kanban** avec statuts personnalisables, tâches facturables (tarif par tâche, projet ou client).
- Projets avec `budgeted_hours`, `budgeted_amount`, `task_rate`, et refacturation des tâches et dépenses vers la facture.

**Achats / dépenses**
- Dépenses, dépenses récurrentes, catégories.
- Bons de commande avec portail fournisseur et réception en stock.
- Réception des factures fournisseurs par e-mail (OCR Mindee ou XML Factur-X/UBL) et **réception d'e-factures PEPPOL**.
- Dépenses refacturables au client.

**Banque**
- Synchronisation automatique Yodlee ou Nordigen, import CSV, règles avec conversion automatique, rapprochement multi-factures.

**Conformité**
- E-facturation PEPPOL (point d'accès intégré), ZUGFeRD/Factur-X/XRechnung, Verifactu, e-reporting France en préparation.
- TVA UE et OSS, contrôle VIES, verrouillage des factures.

**Collaboration**
- Utilisateurs avec **permissions fines** par entité et par action (créer, voir, modifier, et « tout » vs « les siens »).
- Affectation d'un document à un utilisateur (`assigned_user_id`), notifications par utilisateur.
- **Journal d'activité** (`Activity`) sur toutes les entités, double authentification et **passkeys** (`PasskeyCredential`).
- Signatures électroniques avancées via le produit séparé DocuNinja.

**Plateforme**
- API REST complète, webhooks, import/export CSV et JSON (migration depuis Invoice Ninja v4, Freshbooks, Wave, Zoho, Invoicely), synchronisation QuickBooks.
- Multi-sociétés par compte, applications mobiles et bureau, notifications push, traduction dans de nombreuses langues (dont le français).

---

## 4. Écarts vs Lyvre

Seules les fonctions absentes de Lyvre, ou nettement plus abouties chez Invoice Ninja, sont listées. Lyvre reste très au-dessus pour tout ce qui est comptable : plan comptable associatif ou SCI, partie double, clôture, bilan, FEC, dons et reçus fiscaux, bénévolat, budget.

| # | Fonctionnalité Invoice Ninja | Intérêt pour une association / SCI | Source |
|---|---|---|---|
| 1 | **Portail client** (factures, devis, avoirs, paiements, relevé de compte, documents, mot de passe en option) | Adhérents, locataires et clients consultent et téléchargent leurs pièces seuls, ce qui fait moins de demandes au trésorier. Pour une SCI : quittances et avis d'échéance en libre-service. | https://github.com/invoiceninja/invoiceninja.github.io/blob/main/docs/user-guide/client-portal.mdx |
| 2 | **Paiement en ligne intégré** (Stripe, Mollie, PayPal, GoCardless… ; lien « payer » dans chaque e-mail de facture) | Encaisser les factures de prestations, locations de salle ou loyers par CB ou SEPA sans passer par HelloAsso, avec rapprochement automatique du paiement. | https://github.com/invoiceninja/invoiceninja.github.io/blob/main/docs/user-guide/gateways.mdx |
| 3 | **Prélèvement SEPA récurrent et facturation automatique** (`auto_bill` sur les factures récurrentes, mandat stocké via `ClientGatewayToken`) | Loyers de SCI ou cotisations mensuelles prélevés automatiquement à l'échéance, ce qui supprime la relance des retards de loyer. | https://github.com/invoiceninja/invoiceninja/blob/v5-develop/app/Models/RecurringInvoice.php |
| 4 | **Relances automatiques à 3 niveaux plus une relance sans fin**, à J±N de la date de facture ou d'échéance, heure d'envoi réglable | Lyvre ne relance qu'à la main pour les ventes. L'automatisation fait gagner du temps aux bénévoles, sur les impayés de prestations comme de loyers. | https://github.com/invoiceninja/invoiceninja.github.io/blob/main/docs/user-guide/advanced-settings.mdx (Templates & Reminders) |
| 5 | **Pénalités de retard automatiques** (montant fixe ou pourcentage par niveau de relance) | Pour une SCI : application des pénalités ou de l'indemnité forfaitaire de 40 € prévues au bail ou par la loi, sans calcul manuel. | idem, `late_fee_amount1..3` / `late_fee_percent1..3` dans `app/DataMapper/CompanySettings.php` |
| 6 | **Factures récurrentes envoyées automatiquement** (pas seulement créées en brouillon), avec cycles restants et variables de période (`:MONTH`) | Avis d'échéance et appels de loyer émis seuls chaque mois. Lyvre s'arrête au brouillon. | https://github.com/invoiceninja/invoiceninja.github.io/blob/main/docs/user-guide/recurring-invoices.mdx |
| 7 | **Relevé de compte client** (PDF, envoi planifié via `Scheduler`) | Envoyer à chaque locataire ou client un état de son compte (dû, payé, solde), utile en fin d'année ou en cas de litige. | https://github.com/invoiceninja/invoiceninja/blob/v5-develop/app/Services/Scheduler/EmailStatementService.php |
| 8 | **Acceptation et signature électronique des devis en ligne**, avec conversion automatique en facture | Devis de prestations (formations, locations de salle) validés par le client sans échange papier, avec une trace de l'acceptation. | https://github.com/invoiceninja/invoiceninja.github.io/blob/main/docs/user-guide/quotes.md |
| 9 | **Avoir utilisable comme moyen de paiement** (solde d'avoir consommable sur d'autres factures, depuis le portail) et **paiements non affectés / prépaiements** | Gérer proprement les trop-perçus, les dépôts de garantie ou les provisions sur charges imputés plus tard. | https://github.com/invoiceninja/invoiceninja.github.io/blob/main/docs/user-guide/credits.md ; client-portal.mdx (Pre-Payment) |
| 10 | **Acompte demandé sur facture** (`partial` + `partial_due_date`) | Demander 30 % à la réservation d'une salle ou d'un séjour, le solde à la date de l'événement, sur un seul document. | `app/Models/Invoice.php` |
| 11 | **Point d'accès PEPPOL intégré** (envoi et réception d'e-factures, SIRET 0009 pour la France) et **e-reporting France en préparation** | Préparer la réforme 2026-2027 : Lyvre produit le PDF Factur-X mais ne le transmet pas. Invoice Ninja montre une voie de transmission « clé en main » via un opérateur (Storecove). C'est surtout utile aux associations assujetties à la TVA. | https://github.com/invoiceninja/invoiceninja.github.io/blob/main/docs/user-guide/einvoicing.md ; `app/Services/EDocument/Standards/France/` |
| 12 | **Réception des factures fournisseurs par e-mail** (boîte dédiée, OCR et lecture XML Factur-X/UBL) | Les bénévoles transfèrent la facture reçue à une adresse et elle arrive pré-saisie. C'est plus simple que l'upload manuel de Lyvre. | https://github.com/invoiceninja/invoiceninja.github.io/blob/main/docs/user-guide/expenses.md (Expense Inbound Email) |
| 13 | **Règles bancaires avec conversion automatique** (`auto_convert`) et **rapprochement d'un virement sur plusieurs factures** | Lyvre suggère mais fait valider chaque ligne. La conversion automatique traite seuls les flux répétitifs (frais bancaires, loyers fixes, versements HelloAsso). | https://github.com/invoiceninja/invoiceninja.github.io/blob/main/docs/user-guide/banking.mdx (Bank Rules, Auto-Convert) |
| 14 | **Temps et tâches facturables** (chronomètre, Kanban, tarif horaire par projet ou client, refacturation sur facture) | Associations prestataires (formation, accompagnement, conseil) : facturer le temps passé par les salariés. À distinguer du bénévolat valorisé, déjà présent dans Lyvre. | https://github.com/invoiceninja/invoiceninja.github.io/blob/main/docs/user-guide/tasks.md |
| 15 | **Dépenses refacturables au client** (`should_be_invoiced`, justificatif joint à la facture) | Refacturer des frais engagés pour un partenaire ou, en SCI, des charges récupérables aux locataires avec leur justificatif. | https://github.com/invoiceninja/invoiceninja.github.io/blob/main/docs/user-guide/expenses.md |
| 16 | **Bons de commande fournisseurs** avec portail fournisseur et conversion en dépense | Engager une dépense avant facture (travaux SCI, achats d'événement), avec acceptation par le fournisseur. Cela alimente aussi le suivi budgétaire. | https://github.com/invoiceninja/invoiceninja.github.io/blob/main/docs/user-guide/purchase-orders.md |
| 17 | **Multi-devises avec taux de change mis à jour automatiquement** | Rare pour la cible, mais utile aux associations de solidarité internationale ou aux factures fournisseurs étrangères. | `app/Jobs/Util/UpdateExchangeRates.php` ; https://github.com/invoiceninja/invoiceninja.github.io/blob/main/docs/user-guide/clients.md |
| 18 | **Balance âgée clients** (détaillée et synthétique) et soldes clients | Suivre l'ancienneté des impayés (loyers, prestations) d'un coup d'œil. Lyvre n'a pas de lettrage ni de balance âgée. | https://github.com/invoiceninja/invoiceninja.github.io/blob/main/docs/user-guide/reports.md |
| 19 | **Liens de paiement / abonnements publics** (page d'achat, essai, code promo, changement de formule) | Vendre en ligne des abonnements (adhésion premium, abonnement à un atelier) sans billetterie tierce. | https://github.com/invoiceninja/invoiceninja.github.io/blob/main/docs/user-guide/subscriptions.md |
| 20 | **Numérotation par motifs** (`{$year}-{$counter}`, compteurs par groupe de clients, remise à zéro annuelle, compteur partagé devis/factures) | Séries distinctes par activité (locations, formations) ou par immeuble de SCI tout en restant continues. | https://github.com/invoiceninja/invoiceninja.github.io/blob/main/docs/user-guide/advanced-settings.mdx (Generated Numbers) |
| 21 | **Groupes de clients avec paramètres hérités** (modèles, relances, conditions de paiement, langue) | Traiter différemment adhérents, collectivités (délais de paiement longs, Chorus) et particuliers. | advanced-settings.mdx (Group Settings) |
| 22 | **Stock produits** (quantités, alerte de seuil, décrément à la facture, réception par bon de commande) | Buvette, boutique ou merchandising d'une association sans dépendre d'Odoo. | https://github.com/invoiceninja/invoiceninja.github.io/blob/main/docs/user-guide/products.md |
| 23 | **API REST publique documentée et webhooks** (environ 65 événements) | Brancher le site de l'association, un CRM ou Zapier/n8n sur la facturation. Lyvre n'a pas d'API publique documentée. | https://api-docs.invoicing.co/ |
| 24 | **Applications mobiles et bureau** (iOS, Android, F-Droid, desktop) | Saisir une dépense ou photographier un justificatif sur le terrain, consulter les impayés. | https://github.com/invoiceninja/invoiceninja (README) |
| 25 | **Permissions fines par entité et affectation des documents à un utilisateur** (« voir seulement les siens ») | Plus fin que les 3 rôles de Lyvre : un responsable d'activité gère seulement ses factures et dépenses sans voir le reste. | advanced-settings.mdx (User Management > Permissions) |
| 26 | **Journal d'activité et suivi d'ouverture des e-mails/documents par le client** (`Activity`, invitations) | Savoir si un locataire ou client a vu la facture avant de le relancer, avec une piste d'audit des modifications. | `app/Models/Activity.php`, `app/Models/InvoiceInvitation.php` |
| 27 | **Rapports planifiés envoyés par e-mail avec ZIP des justificatifs** | Envoyer chaque mois ou trimestre au cabinet comptable ou au commissaire aux comptes les ventes et dépenses avec pièces, sans intervention. | https://github.com/invoiceninja/invoiceninja.github.io/blob/main/docs/user-guide/reports.md |
| 28 | **Rapport TVA par période** (engagement ou encaissement) et **TVA UE/OSS calculée** | Lyvre n'a pas de CA3. Ce rapport ne remplace pas la déclaration, mais il montre comment préparer les montants à partir de `TransactionEvent` (instantanés datés). | `app/Services/Report/TaxPeriodReport.php` ; https://github.com/invoiceninja/invoiceninja.github.io/blob/main/docs/user-guide/taxes.mdx |

### Ce que Lyvre fait mieux ou qu'Invoice Ninja n'a pas
- Comptabilité en partie double (plan comptable ANC 2018-06 ou SCI, journaux, balance, bilan, compte de résultat N/N-1, FEC, clôture et à-nouveaux).
- Mode recettes-dépenses simplifié.
- Fonds dédiés, bénévolat valorisé (86/87), dons et reçus fiscaux Cerfa, adhérents HelloAsso.
- Budget et prévisionnel de trésorerie, analytique projets avec ventilation.
- Associés de SCI (registre des parts, comptes courants), baux et quittances.
- Synchronisation Qonto, factures d'achat comptabilisées en charges à payer avec un sous-compte 401 par fournisseur.
- Licence **AGPL**, réellement open source, alors que celle d'Invoice Ninja est ELv2.
- Déploiement **SQLite** léger, quand Invoice Ninja demande MySQL, une file d'attente et un cron.

### Idées de reprise prioritaires pour Lyvre
1. Relances automatiques à J+N configurables, avec pénalités de retard.
2. Envoi automatique des factures et quittances récurrentes, plus encaissement SEPA ou CB via un PSP (Stancer, déjà intégré pour les versements, ou GoCardless/Mollie).
3. Portail locataire, adhérent ou client minimal : documents, relevé, lien de paiement.
4. Conversion automatique dans les règles bancaires et rapprochement d'un virement sur plusieurs factures.
5. Boîte e-mail entrante pour les factures fournisseurs.
6. Balance âgée clients.
7. Transmission des e-factures et de l'e-reporting via une plateforme agréée (le schéma Storecove d'Invoice Ninja est un modèle).
