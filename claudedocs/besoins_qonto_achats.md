# Besoins — Qonto, lot 2 : factures d'achat, fournisseurs et catalogue

> Statut : **validé** (brainstorm du 2026-10-21, décisions au §9). Lot découpé en **2a** (détaillé ici)
> et **2b** (cadré au §8). Prochaine étape : `/sc:design` du lot 2a.
> Source : note [`qonto.md`](qonto.md) (« Gestion des achats », « catalogue ») ; lot précédent :
> [`besoins_qonto_transactions.md`](besoins_qonto_transactions.md) (réalisé).

## 1. Contexte

Depuis le 01/09/2026, toute entreprise doit pouvoir **recevoir** des factures électroniques ; Qonto
est Plateforme Agréée et reçoit les factures fournisseurs de l'association (e-invoicing, transfert
par e-mail, dépôt). Qonto est **maître** des factures qu'il reçoit ; l'application les récupère et les
**comptabilise en engagement** (achat à la date de facture, paiement soldant le compte fournisseur).
Certaines factures sont payées par un **autre compte bancaire** que Qonto : elles seront saisies dans
l'application (lot 2b).

| Constat (état au commit `5757e78`) | Valeur |
|------------------------------------|--------|
| Intégration Qonto | Clé API dans Intégrations › Qonto ; `qonto_client` (pagination `next_page`, 429, 401) ; `sync_jobs` (arrière-plan, progression) |
| Transactions Qonto | `bank_transactions` (`source='qonto'`, `fitid` = UUID Qonto, métadonnées des pièces jointes) |
| Comptabilisation actuelle | **Trésorerie** : règles → écriture directe 6xx / 512 au paiement, rapprochement automatique |
| Fournisseurs | `entities` (`entity_type='FOURNISSEUR'`, `account_code`, `email`) ; ni identifiant Qonto, ni TVA, ni IBAN ; propositions de contreparties (`counterparties.py`, lot 1) |
| Catalogue | Aucun |
| Factures existantes | `customer_invoices` (Odoo, ventes, lecture seule) : modèle de référence pour une table synchronisée |
| Journaux | `AC` « Achats » (plan asso) ; comptes 401, 44566 dans le plan |

**API Qonto** (vérifiée sur docs.qonto.com, endpoints accessibles **par clé API**) :
`GET /v2/supplier_invoices` (filtres `filter[updated_at_from/to]`, `filter[status]`,
`sort_by=updated_at:asc`, pagination `page` / `per_page` / `meta.next_page`), `GET /v2/supplier_invoices/{id}`,
`GET /v2/attachments/{id}` (URL valable 30 min), `POST /v2/supplier_invoices/bulk` (dépôt de fichiers,
≤ 20 par requête, `idempotency_key` ; Qonto fait l'OCR — lot 2b).
Champs d'une facture : `id`, `status` (`to_review`, `to_approve`, `awaiting_payment`, `pending`,
`scheduled`, `paid`, `archived`, `rejected`, `discarded`), `invoice_number`, `supplier_id`,
`supplier_name`, `supplier_snapshot` (nom, IBAN, TVA, e-mail), `issue_date`, `due_date`, `payment_date`,
`total_amount` (TTC, chaîne décimale « 22.10 »), `total_amount_excluding_taxes` et `total_tax_amount`
(souvent **null** hors e-facture), `taxes[]` (taux, montant de TVA), `payable_amount`, `is_credit_note`,
`related_invoices`, `is_einvoice`, `source`, `attachment_id`, `attachment_category`,
`is_attachment_non_financial`, `matched_transactions[]` (`transaction_id` = UUID de transaction
Qonto = `fitid`), `updated_at`. **Aucune ligne de facture** : les lignes sont construites dans
l'application à partir du catalogue (A3).

## 2. Objectifs

- **O1** — Les factures d'achat reçues dans Qonto arrivent dans l'application **sans saisie**.
- **O2** — Elles sont **comptabilisées en engagement** : achat (6xx + TVA / 401) puis règlement (401 / 512).
- **O3** — Chaque facture est reliée à son **fournisseur**, à ses **lignes** (catalogue → compte de charge)
  et à son **paiement**.
- **O4** — Un **catalogue** produits / services (achat et vente) porte les comptes comptables.
- **O5** — Synchronisation fiable et rejouable (mêmes garanties que le lot 1).

## 3. Utilisateurs

| Profil | Usage | Attentes |
|--------|-------|----------|
| Trésorier | Fréquent : synchroniser, compléter les lignes, valider, suivre les paiements | Liste filtrable, facture prête à valider en un clic quand le fournisseur est connu |
| Administrateur | Ponctuel : catalogue, produit par défaut des fournisseurs | Catalogue simple, fiche fournisseur complète |

## 4. Besoins fonctionnels — lot 2a

### A1 — Catalogue produits / services
- A1.1 Table locale : libellé, référence optionnelle, **sens** (achat, vente, les deux), compte d'achat
  (6xx) et/ou de vente (7xx), taux de TVA par défaut, actif / archivé.
- A1.2 Écran de gestion (Paramètres) : créer, modifier, archiver ; un produit utilisé n'est pas supprimé.
- A1.3 Fiche fournisseur : **produit par défaut** (achat). À défaut, un produit générique « Achats
  divers » est proposé (compte choisi à l'initialisation selon le plan).
- A1.4 Le lien avec les produits Qonto (vente) relève du lot ventes.

### A2 — Synchronisation des factures d'achat
- A2.1 Bouton « Synchroniser les factures Qonto » (page Factures d'achat), en **arrière-plan** avec progression.
- A2.2 **Incrémentale** sur `updated_at` ; première synchro à partir d'une date choisie (défaut : début de l'exercice).
- A2.3 Dédoublonnage par `id` Qonto ; une facture modifiée (statut, paiement, montants) est **mise à jour**
  sans écraser ce qui a été saisi dans l'application (lignes, fournisseur rattaché) ; un écart de
  montant sur une facture déjà comptabilisée est **signalé**, pas corrigé.
- A2.4 Toutes les factures sont importées ; `rejected`, `discarded` et documents non financiers sont
  **masqués par défaut** (filtre pour les voir) et ne sont jamais comptabilisés. Une facture
  comptabilisée qui passe dans un de ces statuts est **signalée**.
- A2.5 Avoirs (`is_credit_note`) importés et comptabilisés en sens inverse, liés à la facture
  d'origine (`related_invoices`) quand Qonto la fournit.
- A2.6 Résumé : nouvelles, mises à jour, masquées, signalées, erreurs ; dernière synchronisation de l'intégration.

### A3 — Lignes par défaut
- A3.1 À l'import, la facture reçoit des lignes : **une par taux de TVA** (`taxes[]`) si Qonto la fournit,
  sinon **une ligne** TTC avec HT / TVA si connus ; chaque ligne prend le **produit par défaut du
  fournisseur** (donc son compte 6xx).
- A3.2 Le trésorier peut modifier, scinder, ajouter des lignes (produit, libellé, HT, taux, TVA) ;
  le total des lignes doit égaler le TTC Qonto pour valider.
- A3.3 Sans HT connu (facture non analysée), la ligne est créée avec le TTC et un taux à confirmer :
  la facture est « à compléter ».

### A4 — Fournisseurs
- A4.1 Rattachement d'une facture à une entité : par **identifiant fournisseur Qonto** déjà connu,
  puis **numéro de TVA**, puis **nom** (normalisation du lot 1).
- A4.2 Sans correspondance : le fournisseur est **proposé à la validation** (créer, rattacher à une
  entité existante, ignorer), dans le même écran que les contreparties du lot 1.
- A4.3 Une entité rattachée mémorise l'identifiant Qonto, la TVA et l'IBAN ; la synchro ne modifie plus
  ensuite son nom, son compte ni son produit par défaut.
- A4.4 Compte fournisseur : 401 (ou le compte auxiliaire de l'entité s'il est renseigné).

### A5 — Comptabilisation en engagement
- A5.1 États dans l'application : **à compléter** (fournisseur ou lignes manquants) → **prête** →
  **comptabilisée**. Comptabiliser = écriture au journal **AC** à la date de facture :
  débit 6xx par ligne (HT), débit 44566 (TVA), crédit 401 (TTC) ; avoir = inverse.
- A5.2 Comptabilisation **unitaire ou par lot** (toutes les factures prêtes) ; jamais automatique à la
  synchronisation (QA à confirmer en design).
- A5.3 Une facture comptabilisée n'est plus modifiable que par annulation de l'écriture
  (même garde que les écritures rapprochées).
- A5.4 Date hors exercice ouvert : refus avec message, comme la saisie manuelle.

### A6 — Règlement
- A6.1 Lien facture ↔ transaction par `matched_transactions[].transaction_id` (= `fitid` de la
  transaction Qonto importée), y compris pour une transaction arrivée **avant** la facture.
- A6.2 Transaction liée à une facture comptabilisée et **non encore rapprochée** : écriture de
  règlement **401 / 512** automatique et rapprochement, **à la place des règles** (6xx / 512).
- A6.3 Transaction déjà comptabilisée par une règle (6xx / 512) avant l'arrivée de la facture :
  **signalée** (risque de double charge) avec une action « remplacer par un règlement 401 / 512 ».
- A6.4 Paiement partiel ou multiple (plusieurs transactions) : chaque transaction solde sa part du 401.
- A6.5 Vue du compte bancaire : transaction liée → numéro de facture et fournisseur ; filtre
  « débit sans facture ».

### A7 — Consultation
- A7.1 Page « Factures d'achat » (menu principal) : liste (date, n°, fournisseur, TTC, statut Qonto,
  état comptable, payée / liée, e-facture), filtres (période, état, statut Qonto, fournisseur,
  non payée, masquées).
- A7.2 Fiche : en-tête, lignes éditables, ventilation TVA, échéance, règlement(s), écritures, lien vers
  la facture dans Qonto. Fiche fournisseur : ses factures et son solde 401.

## 5. Besoins non fonctionnels

- NF1 Lot 2a en **lecture seule** côté Qonto ; clé jamais affichée (acquis du lot 1).
- NF2 Limites d'API et reprise : client du lot 1 (429, 401, réseau) ; curseur avancé après succès complet.
- NF3 Montants Qonto (chaînes décimales) convertis en **centimes entiers** sans flottant.
- NF4 Écritures produites par `ledger` (partie double, exercice ouvert), atomiques avec le rapprochement.
- NF5 Multi-instance : données, catalogue et curseur par base tenant ; catalogue initial selon le plan (asso / SCI).
- NF6 Testabilité : client simulé, aucun appel réseau en test ; essai manuel sur la SCI (lecture seule).

## 6. Récits utilisateur et critères d'acceptation — lot 2a

**US1 — Catalogue.** L'admin crée « Électricité » (achat, 6061, 20 %) et le met par défaut sur EDF.
- [ ] Le produit apparaît dans le catalogue ; il ne peut pas être supprimé une fois utilisé.

**US2 — Synchroniser.** Le trésorier synchronise les factures.
- [ ] Les factures depuis la date de début apparaissent ; relancer → 0 nouvelle, 0 doublon.
- [ ] Une facture EDF arrive avec une ligne « Électricité » (6061) par taux de TVA, état « prête ».
- [ ] Une facture d'un fournisseur inconnu est « à compléter » et le fournisseur est proposé.
- [ ] Les factures rejetées / écartées sont masquées par défaut.

**US3 — Comptabiliser.** Le trésorier comptabilise les factures prêtes.
- [ ] Écriture AC : 6061 (HT) + 44566 (TVA) / 401 (TTC), à la date de facture.
- [ ] Un avoir produit l'écriture inverse.

**US4 — Régler.** La transaction Qonto du paiement arrive.
- [ ] Elle est liée à la facture, écriture 401 / 512 passée et rapprochée ; aucune règle 6xx appliquée.
- [ ] Une transaction déjà passée en 6xx / 512 par une règle est signalée, et peut être remplacée.

## 7. Hors périmètre du lot 2a

- Saisie de factures dans l'application, pièce jointe, OCR, dépôt dans Qonto (lot **2b**).
- Téléchargement / stockage des PDF Qonto (lot Google Drive) ; lien vers Qonto seulement.
- Paiement, rejet, approbation de factures depuis l'application.
- Ventes, clients, produits Qonto ; déclaration de TVA.

## 8. Lot 2b — cadrage (besoins détaillés à écrire après 2a)

- Saisie d'une facture d'achat dans l'application : **import de la pièce jointe** (PDF / image),
  **OCR local** avec **PyMuPDF** (texte natif ; OCR Tesseract pour les pages scannées) pour
  préremplir fournisseur, n°, dates, HT / TVA / TTC ; lignes depuis le catalogue ; mêmes états et
  comptabilisation que 2a.
- **Envoi dans Qonto** (`POST /v2/supplier_invoices/bulk`, `idempotency_key`) pour les factures payées
  par Qonto ; les factures payées par **un autre compte bancaire** restent dans l'application et se
  règlent par rapprochement (401 / 512x) depuis ce compte.
- À trancher : stockage local des fichiers avant Google Drive ; dédoublonnage facture saisie ↔ même
  facture revenue de Qonto (identifiant renvoyé par le dépôt) ; écriture dans Qonto impossible sur le
  compte SCI de test (bac à sable requis).

## 9. Décisions (brainstorm du 2026-10-21)

| # | Question | Décision |
|---|----------|----------|
| QA1 | Comptabilisation | **Engagement** : écriture AC (6xx + 44566 / 401), règlement 401 / 512. Saisie de factures dans l'app avec pièce jointe et OCR demandée → lot 2b. |
| QA2 | Lignes (absentes de l'API) | Lignes **gérées dans l'app**, créées par défaut depuis un **catalogue produits / services** lié au compte comptable. |
| QA3 | Fournisseur inconnu | **Proposé à la validation** (comme le lot 1). |
| QA4 | Rejetées / écartées / non financières | **Importées, masquées** par défaut. |
| QA5 | OCR et lieu de la facture | **Les deux** : OCR local (PyMuPDF) pour préremplir, puis dépôt dans Qonto ; certaines factures sont payées par un autre compte → restent locales (lot 2b). |
| QA6 | Catalogue | **Local, achat + vente**, comptes 6xx / 7xx, produit par défaut sur la fiche fournisseur. |
| QA7 | Découpage | **2a** (catalogue, synchro, lignes, engagement, règlement) puis **2b** (saisie, PJ, OCR, dépôt Qonto). |
| QA8 | Règlement | **401 / 512 automatique** pour une transaction liée à une facture comptabilisée, à la place des règles. |

### Points à trancher en design (2a)

1. Comptabilisation : par lot manuel (proposé) ou automatique dès qu'une facture est « prête » ?
2. Compte fournisseur : 401 collectif seul, ou sous-comptes 401xxx par fournisseur (`account_code`) ?
3. Association non assujettie à la TVA : TVA incluse dans la charge (pas de 44566) — paramètre par instance ?
4. Transaction 6xx / 512 antérieure à la facture (A6.3) : remplacement manuel seulement, ou proposé en lot ?
