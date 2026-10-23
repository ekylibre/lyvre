# Besoins — module Ventes (devis, factures, avoirs, encaissements, loyers), abonnements d'achat et intégration Qonto

> Statut : expression de besoins (`/sc:brainstorm`, 23/10/2026). Pas de conception ni de code.
> Décisions du 23/10/2026 au § 3 (questions du § 9 tranchées le même jour). Étape suivante : `/sc:design`.

## 1. Objectif

Émettre les devis et factures de vente de la structure depuis l'application, avec un catalogue
produits / services commun aux achats, et en tirer la comptabilité (journal de ventes, 411, TVA
collectée, encaissements) — **avec ou sans Qonto**. Quand l'intégration Qonto est activée pour les
ventes, une case par facture fait émettre la facture par Qonto (numéro, PDF Factur-X, envoi), et les
clients, produits, devis et factures sont synchronisés, sur le modèle du module Achats.

## 2. Existant (code au 23/10/2026)

| Élément | Aujourd'hui | Réutilisable |
|---|---|---|
| Catalogue (`products`) | Nature achat / vente / les deux, compte de vente `sale_account`, TVA par défaut | Oui : lignes de vente |
| Tiers (`entities`) | Types dont CLIENT, adresse, SIREN/TVA côté fournisseur | Oui : clients |
| Factures clients **Odoo** | Import en lecture (`customer_invoices`), **non comptabilisées**, menu Odoo | Conservées à côté (décision V3) |
| Achats Qonto | Synchro, lignes du catalogue, compta en engagement (AC, 401NNN), règlements, case « Envoyer à Qonto » | Modèle du processus |
| Reçus fiscaux | PDF généré, envoi par email via SMTP en tâche de fond, notifications | PDF et envoi |
| Organisation | Nom, SIREN, RNA, adresse, signataire | À compléter (mentions légales, § 4.8) |
| Intégration Qonto | Relevés (transactions) + factures d'achat, un seul interrupteur | Périmètre à découper (§ 4.9) |

## 3. Décisions prises (23/10/2026)

| # | Sujet | Décision |
|---|---|---|
| V1 | Émetteur avec Qonto | Case cochée : la facture est **créée et finalisée dans Qonto**, qui attribue le numéro et produit le PDF ; l'application les récupère. Case décochée (ou sans Qonto) : l'application numérote et produit le PDF. **Deux séries distinctes**, chacune continue |
| V2 | Périmètre | Factures **et** devis, avoirs, encaissements, relances d'impayés |
| V3 | Structures | **Toutes** (associations, SCI, sociétés) ; les factures clients Odoo restent importées à côté, sans double comptabilisation |
| V4 | Envoi par email | **Manuel** : bouton « Envoyer » (PDF joint), depuis la fiche ou une sélection dans la liste ; aucun envoi automatique (Q1) |
| V5 | Relances d'impayés | **Manuelles** : sélection dans la liste des échues, ou depuis la facture (Q2) |
| V6 | TVA des prestations de services | **Option par exercice comptable** : exigible à l'encaissement ou d'après les débits (Q3) |
| V7 | Numérotation de l'application | `D-AAAA-NNNN` (devis), `F-AAAA-NNNN` (factures), `AV-AAAA-NNNN` (avoirs), compteur par année civile (Q4) |
| V8 | Loyers | **Factures récurrentes** et **quittances** dans le périmètre, avec un **bail simple** (Q5, § 4.12) |
| V9 | Factur-X | PDF Factur-X produit par l'application si possible avec la bibliothèque `factur-x` d'Akretion (licence BSD) ; sinon seules les factures Qonto sont en Factur-X (Q6) |
| V10 | Case « Émettre avec Qonto » | **Décochée** par défaut (Q7) |
| V11 | Paiement Qonto | Encaissement rapproché dans l'application → facture **marquée payée dans Qonto** (Q8) |
| V12 | Factures d'acompte | **Hors premier lot** (Q9) |
| V13 | TVA des associations | Le réglage de TVA de l'exercice (`vat_liable`) suffit (Q10) |
| V14 | Réglages de facturation | Nouvel onglet **« Facturation »** dans Configuration › Structure (Q11) |
| V15 | Factures récurrentes | Préparées **en brouillon à valider** à l'échéance (liste « à émettre »), émises et envoyées en lot ; pas de tâche planifiée |
| V16 | Quittances | Produites à l'**encaissement complet** du loyer de la période (loyer et charges distingués) ; reçu partiel sinon ; envoi manuel |
| V17 | Abonnements d'achat | Ajoutés au module Achats : **facture attendue** à chaque échéance et **suivi des contrats** (§ 4.13) |

## 4. Exigences fonctionnelles

### 4.1 Clients

- Client = tiers de type client (fiche existante), avec : nom ou prénom/nom (particulier ou
  société), email(s), adresse de facturation (et de livraison si différente), SIREN/SIRET, TVA
  intracommunautaire, compte 411 (sous-compte par client, comme 401NNN côté fournisseurs).
- Création à la volée depuis le devis ou la facture.

### 4.2 Catalogue

- Catalogue existant, produits de nature vente ou les deux : désignation, description, unité
  (heure, jour, pièce…), prix unitaire HT de vente, TVA, compte de vente (70x), motif
  d'exonération éventuel (art. 293 B, 261…).
- Une ligne de devis ou de facture peut partir d'un produit ou être libre ; le produit fournit
  libellé, prix, TVA et compte, modifiables sur la ligne.

### 4.3 Devis

- Brouillon modifiable → **émis** (numéro de la série devis, PDF) → **accepté**, **refusé** ou
  **expiré** (date de validité) → **transformé en facture** (une ou plusieurs, lien conservé).
- Mêmes lignes, remises et mentions que la facture. Envoi manuel par email avec le PDF.
- Avec Qonto (case cochée) : devis créé dans Qonto ; son statut (accepté par signature du client,
  annulé) vient de Qonto — l'API ne permet pas de l'accepter.

### 4.4 Factures

- Brouillon modifiable → **émise** (numéro définitif, PDF, comptabilisée ; plus modifiable ni
  supprimable) → **payée partiellement** / **payée** ; **annulée** seulement par avoir.
- En-tête : client, date d'émission, date d'échéance (conditions de paiement par défaut), dates de
  prestation, référence de commande, remise globale, conditions et mentions.
- Lignes : produit ou libre, quantité, unité, prix unitaire HT, remise, TVA, compte de vente,
  projet (analytique, comme les achats).
- Totaux HT, TVA par taux, TTC ; arrondis cohérents avec les achats.
- **Case « Émettre avec Qonto »** par facture, visible seulement si l'intégration Qonto est activée
  pour les ventes ; décochée par défaut (même choix que « Envoyer à Qonto » des achats, Q7).
- Pièce : PDF de la facture conservé avec la facture (sauvegardes `.zip` comprises).
- Doublons : même client, même montant, même date signalés avant émission.

### 4.5 Avoirs

- Depuis une facture émise : avoir total (annule la facture) ou partiel (lignes et montants),
  motif obligatoire ; numéro de la série avoirs ; PDF ; écriture inverse.
- Facture émise par Qonto : avoir créé dans Qonto (l'API le permet ; total ≤ montant facturé).

### 4.6 Comptabilité

- À l'émission : journal **VE** (ventes), 411 du client au débit (TTC), 70x au crédit par ligne
  (HT), 4457x TVA collectée au crédit ; avoir : écriture inverse. Comme les achats, rien n'est
  comptabilisé à l'état brouillon.
- TVA : selon l'exercice (`vat_liable`) ; structure non assujettie → pas de TVA, mention
  « TVA non applicable, art. 293 B du CGI ».
- Exigibilité de la TVA sur les prestations de services, **option de l'exercice** (V6) :
  à l'encaissement, la TVA est d'abord portée en TVA collectée en attente (44574) puis virée en
  44571 à l'encaissement ; d'après les débits, directement en 44571 et la mention « option pour le
  paiement de la taxe d'après les débits » figure sur la facture. Les livraisons de biens restent
  exigibles à la livraison.
- Les factures clients Odoo ne sont pas comptabilisées par ce module.

### 4.7 Encaissements et relances

- Encaissement : transaction bancaire (Qonto ou import OFX) rapprochée d'une facture ; écriture
  512 au débit, 411 au crédit ; paiements partiels ; proposition automatique (montant, client,
  référence de facture dans le libellé), comme les règlements d'achat.
- Saisie manuelle d'un encaissement (chèque, espèces → caisse 53x).
- Facture Qonto : marquer payée dans Qonto quand l'encaissement est rapproché dans l'application
  (l'API le permet ; Q8).
- **Relances d'impayés** (manuelles, V5) : liste des factures échues non payées ; « Relancer » sur
  une sélection ou depuis la facture : email de relance avec la facture en pièce jointe (modèle
  modifiable) ; date et nombre de relances conservés.

### 4.8 Mentions légales et PDF

Le PDF d'une facture émise par l'application porte les mentions obligatoires françaises :

- vendeur : dénomination, adresse, SIREN/SIRET, forme juridique et capital (sociétés), RCS ou RNA,
  n° TVA intracommunautaire ;
- client : nom, adresse de facturation (et de livraison), SIREN (obligatoire pour une facture entre
  professionnels avec la réforme 2026-2027) ;
- numéro unique, date d'émission, date ou période de la prestation, nature de l'opération (biens,
  services, les deux) ;
- lignes (désignation, quantité, prix unitaire HT, taux de TVA), totaux par taux, TTC ;
- échéance, conditions d'escompte, taux des pénalités de retard, indemnité forfaitaire de 40 € pour
  frais de recouvrement (clients professionnels), option pour le paiement de la TVA d'après les
  débits le cas échéant ;
- coordonnées bancaires (IBAN, BIC), logo.

Nouveaux réglages de l'organisation (Configuration › Structure ou Ventes) : forme juridique,
capital, RCS, TVA intracommunautaire, IBAN/BIC, conditions de paiement par défaut, pénalités,
logo, pied de page ; préfixes et compteurs des séries (devis, factures, avoirs).

Le PDF est un **Factur-X** (PDF avec XML embarqué), que l'application sait déjà lire (V9). La
bibliothèque `factur-x` (Akretion, BSD) embarque et contrôle le XML (CII, profil à choisir, au
moins BASIC/EN 16931) ; le XML lui-même est produit par l'application, et le PDF de base doit être
compatible PDF/A-3 (polices embarquées). Si ce n'est pas tenable, seules les factures émises par
Qonto sont en Factur-X.

### 4.9 Intégration Qonto : périmètre et synchronisation

- La fiche de l'intégration Qonto propose trois cases de **périmètre** : **Relevés de compte**,
  **Achats**, **Ventes** ; chaque fonction n'apparaît que si son périmètre est coché (même règle
  que pour une intégration désactivée). Pour la SCI : relevés et achats cochés (usage actuel),
  ventes à cocher.
- Ventes, quand le périmètre est coché :
  - **clients** : envoyés à Qonto à la première facture Qonto du client (recherche avant création :
    SIREN, TVA, email, nom ; Qonto n'empêche pas les doublons) ; clients créés dans Qonto
    importés ;
  - **produits** : catalogue de vente envoyé à Qonto (création seulement, l'API n'a pas de
    modification) et produits Qonto importés ; dans Qonto les lignes de facture ne sont pas liées
    aux produits, le libellé d'une ligne est limité à **40 caractères** (le reste passe en
    description) ;
  - **devis et factures** créés dans Qonto (hors application) : importés, comptabilisés comme une
    facture émise ; statuts (payée, annulée) et avoirs mis à jour à chaque synchronisation ;
  - **factures émises depuis l'application** avec la case : création en brouillon dans Qonto, puis
    finalisation à l'émission ; numéro et PDF Factur-X récupérés (PDF disponible en différé) ;
  - synchronisation en tâche de fond avec notification de fin, comme les achats (pas de webhook
    possible avec la clé API : relecture par date de modification).
- Paiement par lien Qonto : hors périmètre (OAuth obligatoire).

### 4.10 Envoi par email

- Envoi **manuel** (V4) : bouton **Envoyer** sur un devis, une facture, un avoir, une quittance
  ou une relance, ou sur une sélection dans la liste : destinataires (email du client, copies),
  objet et message (modèles modifiables), PDF joint automatiquement.
- Facture de l'application : envoi par l'intégration **SMTP** (message « intégration nécessaire »
  si elle est désactivée). Facture Qonto : envoi par Qonto (`/send`).
- Date et destinataires de chaque envoi conservés ; facture « envoyée » visible dans la liste.

### 4.11 Écrans

- Menu **Ventes** : Devis, Factures (avoirs compris), Factures à émettre (récurrentes), Baux,
  Encaissements à rapprocher, Relances ; le Catalogue reste dans Compta (commun aux achats).
- Menu **Achats** : ajout de **Abonnements**.
- Liste des factures : filtres (état, client, mois, échues, origine application / Qonto), totaux,
  actions groupées (émettre, envoyer) ; fiche de facture comme celle d'un achat.
- Tableau de bord : chiffre d'affaires facturé, encours clients, factures échues.

### 4.12 Factures récurrentes, baux et quittances

- **Facture récurrente** (modèle) : client, lignes, périodicité (mensuelle, trimestrielle,
  annuelle), jour d'échéance, date de début et de fin, terme à échoir ou échu, émission avec Qonto
  ou non. À chaque échéance, une facture **brouillon** est préparée et apparaît dans « Factures à
  émettre » ; l'utilisateur les émet et les envoie en lot (V15). Une échéance n'est jamais préparée
  deux fois ; une échéance oubliée reste dans la liste.
- **Bail simple** (V8) : locataire (client), lot (adresse, désignation), date d'effet et de fin,
  loyer hors charges, provisions sur charges, jour d'échéance, dépôt de garantie (encaissé au
  compte 165 « dépôts et cautionnements reçus »), comptes de produits (706/708 ou 752 selon la
  structure, à confirmer avec l'expert-comptable). Le bail porte la facture récurrente de loyer
  (avis d'échéance). Révision de loyer (IRL) et régularisation annuelle des charges : plus tard.
- **Quittance** (V16) : quand le loyer d'une période est entièrement encaissé, quittance PDF
  (bailleur, locataire, lot, période, loyer et charges distingués, date de paiement) disponible sur
  la facture et le bail ; paiement partiel → **reçu** du montant versé, pas de quittance. Envoi
  manuel au locataire ; quittances conservées avec le bail.

### 4.13 Abonnements d'achat (module Achats)

- **Abonnement** (V17) : fournisseur, désignation (internet, téléphone, assurance, frais
  bancaires…), produit du catalogue (compte de charge, TVA), montant TTC attendu (fixe ou estimé),
  périodicité, jour d'échéance, moyen de paiement (prélèvement sur tel compte), date de début, date
  de fin ou de reconduction, préavis de résiliation, pièce (contrat).
- **Facture attendue** : à chaque échéance, une facture d'achat attendue est créée ; elle est
  rapprochée de la facture réelle (Qonto ou déposée) et du prélèvement bancaire, le montant réel
  remplaçant l'estimation. Une échéance passée sans facture ni prélèvement est signalée.
- **Suivi des contrats** : liste des abonnements avec coût mensuel et annuel, total par catégorie,
  prochaine échéance, date de reconduction, rappel avant la fin du préavis de résiliation.
- Les abonnements sans facture (frais bancaires prélevés sans document) continuent de passer par
  les règles de catégorisation du rapprochement.

## 5. Exigences non fonctionnelles

- Numérotation **continue et chronologique** par série, sans trou ni doublon, même en cas d'échec
  (même garantie que les reçus fiscaux) ; une facture émise n'est jamais supprimée.
- Aucun appel à Qonto si l'intégration ou le périmètre Ventes est désactivé ; aucune écriture dans
  Qonto sans action explicite (case cochée, bouton) ; jamais d'identifiants Qonto dans les copies
  de test.
- Conservation des factures et PDF 10 ans (sauvegardes de l'instance).
- Droits : administrateur et trésorier émettent et encaissent ; expert-comptable en lecture.
- Tests : jamais de vrai serveur SMTP ni de vrai Qonto (bac à sable ou faux client).

## 6. Récits utilisateur et critères d'acceptation

**U1 — Facture sans Qonto.** Une association non assujettie émet une facture de 2 lignes du
catalogue : numéro F-2026-0001 attribué à l'émission, PDF avec « TVA non applicable, art. 293 B
du CGI », écriture VE 411/706 équilibrée ; la facture n'est plus modifiable.

**U2 — Facture avec Qonto.** Une SCI avec le périmètre Ventes coché émet une facture, case « Émettre
avec Qonto » cochée : la facture est créée puis finalisée dans Qonto, le numéro Qonto et le PDF
Factur-X sont récupérés, l'écriture VE est passée ; décochée, elle suit U1 (série de
l'application).

**U3 — Devis → facture.** Un devis accepté devient une facture reprenant ses lignes ; le devis
indique la facture créée.

**U4 — Avoir.** Un avoir total sur une facture émise la passe « annulée » et contre-passe l'écriture.

**U5 — Encaissement.** Une transaction bancaire du montant d'une facture, au nom du client, est
proposée au rapprochement ; une fois rapprochée, la facture est payée (512/411) et, si elle vient
de Qonto, marquée payée dans Qonto.

**U6 — Relance.** Les factures échues non payées sont listées ; « Relancer » envoie l'email avec le
PDF par SMTP ; sans SMTP, message « intégration nécessaire ».

**U7 — Périmètre Qonto.** Ventes décochée dans l'intégration Qonto : aucune case « Émettre avec
Qonto », aucune synchronisation des ventes, aucun message Qonto sur les écrans de vente.

**U8 — Loyer.** Un bail mensuel prépare le 1er du mois une facture brouillon de loyer et charges ;
émise et envoyée en lot ; quand le prélèvement du locataire est rapproché pour le total, la
quittance du mois est disponible.

**U9 — Abonnement.** L'abonnement internet (45 € TTC par mois, prélevé le 5) crée une facture
attendue chaque mois ; la facture Qonto du fournisseur et le prélèvement s'y rattachent ; un mois
sans facture est signalé dans la liste des abonnements.

## 7. Réforme de la facturation électronique (à prendre en compte)

- Depuis le **1er septembre 2026**, toute entreprise doit pouvoir **recevoir** des factures
  électroniques ; l'**émission** devient obligatoire le 1er septembre 2027 pour les PME et
  micro-entreprises (SCI comprises), avec e-reporting des ventes aux particuliers.
- Une facture électronique passe par une **plateforme agréée (PA)**. Qonto en est une : une facture
  émise par Qonto peut lui être transmise (`send_by_einvoice`) si l'organisation est inscrite à
  l'annuaire et le client joignable.
- Une facture émise par l'application seule (Factur-X) ne remplit pas l'obligation d'émission de
  2027 sans PA : à traiter plus tard (Q6). Les associations non assujetties sont largement hors
  champ.

## 8. Hors périmètre

- Paiement en ligne (lien de paiement Qonto, prélèvement SEPA).
- Factures en devise autre que l'euro.
- Transmission par une PA autre que Qonto.
- Remplacement de l'import des factures Odoo.
- Factures d'acompte et de solde (V12) ; révision IRL des loyers et régularisation annuelle des
  charges ; envoi automatique des factures et des relances (V4, V5).

## 9. Questions ouvertes

Questions Q1 à Q11 tranchées le 23/10/2026 (décisions V4 à V14 du § 3). Restent, pour la conception :

| # | Question | Proposition |
|---|---|---|
| Q12 | Comptes des loyers (706, 708, 752) et des charges refacturées selon la structure | À valider avec l'expert-comptable |
| Q13 | Profil Factur-X (BASIC ou EN 16931) et conformité PDF/A-3 du PDF produit | EN 16931 ; essai de faisabilité en début de conception |
| Q14 | Ordre des lots | 1) catalogue, clients, factures, avoirs, compta, PDF, envoi ; 2) encaissements et relances ; 3) devis ; 4) Qonto (périmètre, synchro, émission) ; 5) récurrentes, baux, quittances ; 6) abonnements d'achat |
