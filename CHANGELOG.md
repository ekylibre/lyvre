# Changelog — Lyvre

<!-- Fichier généré à partir de data/changelog.yml : ne pas le modifier à la main,
     lancer `python scripts/release.py build`. -->

Versions au format calendaire `AAAA.MM.N` (année, mois, numéro dans le mois). Les mêmes
nouveautés s'affichent dans l'application (menu utilisateur › Nouveautés).

## 2026.11.3 — Correctif : saisie d'une facture d'achat sans fichier (01/11/2026)

### Corrections

- Achats › Nouvelle facture — le lien « Saisir sans fichier » ouvre de nouveau le formulaire vide (il fallait recharger la page). — *PurchaseFormPage, mode « manual » piloté par l'adresse.*

## 2026.11.2 — Factures réglées en plusieurs fois (01/11/2026)

### Nouveautés

- Une facture se règle en plusieurs fois — acomptes, échéancier, virements échelonnés. Sur la fiche d'une facture d'achat ou à l'encaissement d'une vente, on coche une ou plusieurs lignes de relevé (total sélectionné face au restant) ; la fiche d'achat affiche le montant déjà réglé et le restant à régler. — *purchase_settlement.remaining_cents / paid_cents, link_manual(p, ids), POST /purchases/<id>/payments {bank_transaction_ids}, sale_settlement.match_transactions, POST /sales/<id>/match, TransactionPicker.*
- « Rattacher à une facture » dans Banque › Transactions — une ligne de relevé règle (ou encaisse) en tout ou partie une facture d'achat ou de vente déjà saisie, avec le restant après rattachement ; l'écriture est passée et rapprochée. — *GET /bank-transactions/<id>/open-invoices, can_link_invoice dans la liste des transactions, LinkInvoiceModal.*

## 2026.11.1 — Société, déclarations de TVA et relevés de compte (01/11/2026)

### ⚠️ Action requise

- Pour les comptes Qonto : lancer une fois « Synchroniser Qonto » — elle relit toute la période pour reprendre les catégories Qonto des transactions déjà importées et récupère les relevés de compte de l'exercice.

### Nouveautés

- [Sociétés] Nouvelle structure « Société (SAS, SASU) » à la création d'une instance, avec le plan comptable général 2026, le bilan et le compte de résultat présentés comme la liasse 2050 et le statut de jeune entreprise innovante dans la Structure. — *Lot T1 : référentiel societe (data/plan_comptable_societe.json extrait du PCG 2026 par scripts/build_pcg_chart.py), rôles de comptes 657 / 757, organization.jei_since (migration b2d4f6a8c0e1).*
- Codes de TVA sur les écritures (TVA par taux et par compte, base HT), régime TVA des tiers (France, Union européenne, hors UE) avec autoliquidation des achats auprès de fournisseurs étrangers, et factures de vente sans TVA française (autoliquidation, exportation) avec leur mention légale. — *Lot T2 : journal_lines.vat_code / vat_base_cents, entities / purchases / sales.vat_regime (migration c3e5a7b9d1f2), data/vat_codes.json, app/services/vat_codes.py, PUT /entries/<id>/lines/<line_id>/vat, PUT /purchases/<id>/vat-regime.*
- Déclarations de TVA mensuelles (CA3) calculées depuis les écritures — cases du formulaire 2026 avec leur code de saisie, lignes de chaque case, contrôles, écriture de liquidation, crédit reporté d'un mois sur l'autre, PDF et tableur pour TeleDEC, mois verrouillé une fois la déclaration déposée. — *Lot T3 : vat_returns, journal_lines.vat_return_id, fiscal_years.vat_period, organization.vat_due_day (migration d4f6b8c0e2a3), data/ca3/2026.json, app/services/vat_return.py, /api/v1/vat-returns, source VAT_RETURN.*
- Règles de catégorisation proposées depuis un mois, d'après les transactions réglées par une facture ou catégorisées à la main ; création des nouvelles et mise à jour de celles dont le tiers ou le compte a changé. — *app/services/rule_suggestions.py, GET / POST /api/v1/rules/suggestions, Tiers › Règles › « Proposer depuis un mois ».*
- Facture d'achat créée depuis le justificatif d'un paiement Qonto (Banque › Transactions, « Créer la facture ») — pièce téléchargée de Qonto et lue, formulaire prérempli, facture réglée par ce paiement. — *app/services/transaction_invoice.py, POST /api/v1/bank-transactions/<id>/purchase-draft, qonto_client.transaction, attachments.stage_bytes, POST /purchases bank_transaction_id.*
- Factures de vente encaissées depuis le relevé — à l'émission d'une facture, le crédit bancaire unique de même montant l'encaisse ; dans Banque › Transactions, « Encaisser F-… » propose les factures ouvertes de même montant. — *sale_settlement.auto_match_sale (émission), sale_settlement.proposals, champ sale_proposals de /bank-accounts/<id>/transactions.*
- [Sociétés] Déclaration de TVA complétée — importations hors UE (TVA à l'importation autoliquidée, lignes A4, I1 à I5 et 24), achats auprès d'un fournisseur non établi dont vous devez la TVA (ligne B4), TVA des avoirs fournisseurs reversée ligne 15, et mention de la TVA autoliquidée sous les lignes concernées. — *Codes AL_I, AL_I10, AL_I55, AL_I21 (compte 4453) et AL_FR (régime fr_rc), data/ca3/2026.json, vérifié sur doc/ref_compta/3310-ca3-sd_5377.pdf et sa notice.*
- Relevés de compte — récupérés de Qonto (au clic et à chaque synchronisation, remplacés s'ils changent) ou déposés en PDF pour les autres banques, consultables dans Banque › Transactions et jamais supprimés. — *Lots RQ1–RQ3 : table bank_statements (migration e5a7c9d1f3b4), app/services/bank_statements.py, /api/v1/bank-accounts/<id>/statements, /bank-statements/<id>.pdf.*
- Archive de l'exercice pour l'expert-comptable (panneau FEC) — le FEC s'il peut être produit, les relevés de compte et la liste des mois sans relevé. — *Lot RQ4 : /fiscal-years/<id>/accountant-archive.zip, views/fec.fec_content.*

### Améliorations

- Banque › Transactions plus lisible — un feu par ligne (à jour, à traiter, anomalie) avec une légende qui filtre, une icône pour le type d'opération et pour le justificatif, la catégorie Qonto, une action principale et les autres dans le menu « … » ; mêmes feux et icônes dans le rapprochement. — *Lots TX1–TX3 : app/services/bank_lights.py, champs light / light_reasons / lights, paramètre light, colonnes qonto_category (migration f6b8d0e2a4c5), frontend/src/components/bank/.*

### Corrections

- Une facture d'achat saisie se règle aussi par une transaction Qonto que Qonto ne rattache à aucune facture (abonnement Qonto, facture absente du module Factures fournisseurs), automatiquement après la synchronisation.
- [Sociétés] Un bien acheté hors de l'Union européenne n'est plus déclaré comme un achat de services (ligne A3) mais comme une importation.

## 2026.10.19 — Version et nouveautés (26/10/2026)

### Nouveautés

- Numéro de version affiché dans le menu utilisateur et sur la page À propos. — *Lot R1 : data/changelog.yml (source unique), app/version.py, scripts/release.py, CHANGELOG.md généré.*
- Page « Nouveautés » dans le menu utilisateur, signalée par une pastille à chaque nouvelle version. — *Lot R2 : GET /api/v1/changelog, préférence changelog_seen.*

## 2026.10.18 — Brevo (26/10/2026)

### ⚠️ Action requise

- [Associations] Pour utiliser Brevo : autoriser l'adresse IP du serveur dans Brevo › Sécurité, puis activer l'intégration, saisir la clé et choisir la liste.

### Nouveautés

- [Associations] La liste des adhérents se synchronise vers une liste de contacts Brevo : un aperçu sans écriture d'abord, puis la synchronisation. — *Lots B1–B3 : intégration brevo, table brevo_links (migration a1c3e5f7b9d2), tâche brevo_sync.*
- [Associations] Pas de doublon : chaque adhérent est lié une fois à son contact, retrouvé par e-mail la première fois ; les désinscrits ne sont jamais réinscrits.
- [Associations] Rapport de synchronisation : contacts créés, rattachés, mis à jour, retirés de la liste, conflits à traiter.

### Améliorations

- [Associations] Après chaque synchronisation HelloAsso, les adhérents concernés sont renvoyés vers Brevo.
- La page À propos présente les nouveautés récentes.

## 2026.10.17 — Structure et Sirene (25/10/2026)

### ⚠️ Action requise

- Ajouter la variable SIRENE_API_KEY au serveur pour faire apparaître les boutons Sirene.

### Nouveautés

- « Compléter depuis Sirene » remplit la Structure (adresse, forme juridique, activité, n° de TVA) à partir de l'API de l'INSEE. — *Lot G3 : services/sirene.py (quota, cache 24 h), nomenclatures INSEE dans data/insee/.*
- Fiche d'un tiers : recherche dans Sirene par nom, SIREN ou SIRET, avec alerte si le SIREN est déjà celui d'un autre tiers. — *Lot G4.*
- Facture d'achat : « Chercher dans Sirene » retrouve un fournisseur connu ou prépare sa création. — *Lot G4 : new_entity appliqué à la création seulement.*
- Mise à jour groupée des tiers depuis Sirene, avec un écran de revue avant d'appliquer. — *Lot G5 : tâche sirene_refresh.*

### Améliorations

- Les mentions légales (forme juridique, capital, greffe, TVA) se saisissent une seule fois, dans Configuration › Structure, et servent aux factures comme aux baux. — *Lot G2, migration f3b5d7e9a1c4 (reprise depuis Facturation).*
- Les tiers ont un SIREN, tiré du SIRET ou saisi seul, et une activité (code NAF).
- [SCI] Une SCI ne voit plus les fonctions réservées aux associations (reçus fiscaux, adhésions, bénévolat, fonds dédiés) ; ses données éventuelles sont conservées. — *Lot G1 : app/association_only.py.*

### Corrections

- Au démarrage, la base de chaque structure est mise à jour, et non plus seulement celle par défaut. — *scripts/migrate_instances.py lancé par l'entrypoint.*

## 2026.10.16 — Mise en production (25/10/2026)

### Nouveautés

- Lyvre est en service sur son nouveau serveur, avec les données et les réglages d'intégration repris. — *Bascule du 25/10/2026 vers le service Dokploy Lyvre ; l'ancien service est arrêté, ses données conservées.*

### Corrections

- Bilan : les colonnes N-1 et Net N-1 restent visibles.
- Graphiques du tableau de bord : les montants de l'axe vertical ne débordent plus (12,3 k€).
- Démarrage du conteneur : le dossier des données est rendu à l'application, sans manipulation. — *docker/entrypoint.sh : chown puis setpriv.*

## 2026.10.15 — Baux (24/10/2026)

### ⚠️ Action requise

- [SCI] Pour signer les baux en ligne : configurer l'intégration Documenso, cocher les gérants (Associés) et renseigner forme juridique et greffe (Structure).

### Nouveautés

- [SCI] Assistant de bail en trois étapes, enregistré en brouillon : conditions, biens loués (bâtiments, terres) avec leur loyer, récapitulatif. — *Lot L1.*
- [SCI] Modèles de bail par type, texte figé à la validation, retouche et PDF. — *Lot L2.*
- [SCI] Carte du bail : photo aérienne, parcelles cadastrales et bâtiments de l'IGN, zones dessinées. — *Lot L3.*
- [SCI] Signature électronique des baux avec Documenso (auto-hébergé), paraphe sur chaque page. — *Lot L4.*
- [SCI] Révision des loyers sur les indices INSEE (ILC, ILAT, IRL) et l'indice des fermages, avec le courrier au locataire. — *Lot L5.*
- Mot de passe oublié : lien sur la page de connexion, nouveau mot de passe choisi depuis un lien reçu par e-mail.

## 2026.10.14 — Reprise Ekylibre (24/10/2026)

### Nouveautés

- [SCI] Reprise d'une comptabilité Ekylibre dans une nouvelle structure : exercices, écritures, tiers, associés, TVA, lettrage, banque, achats, ventes et immobilisations, après un rapport à blanc. — *Lots K1–K4 : app/services/ekylibre.*

### Améliorations

- Les règles de catégorisation passent par le compte du tiers (pièce puis règlement lettré) au lieu d'imputer directement la banque.

## 2026.10.13 — Fiabilité comptable (24/10/2026)

### Nouveautés

- Validation des écritures par lots : une écriture validée ne se modifie plus, elle se corrige par extourne ; historique de chaque écriture. — *Lot F1, migration b1d3f5a7c9e2.*
- Verrouillage de période par exercice : les pièces reçues après sont datées du premier jour ouvert. — *Lot F2.*
- Lettrage des comptes de tiers, automatique ou au clavier, et à-nouveaux détaillés. — *Lot F3 : comptes par rôle à valider avec l'expert-comptable.*
- Charges et produits constatés d'avance proposés à la clôture. — *Lot F4.*
- Immobilisations : composants, plans linéaire et dégressif, dotations à la clôture, cession. — *Lot F5 : méthodes d'Ekylibre, année de 360 jours.*
- Reprise d'historique depuis un fichier FEC ou un tableur. — *Lot F6.*

## 2026.10.12 — Ventes (23/10/2026)

### Nouveautés

- Factures et avoirs numérotés, PDF Factur-X, écriture au journal des ventes, envoi par e-mail. — *Lots S0–S1.*
- Encaissements rapprochés de la banque, relances des factures échues, chiffres de ventes au tableau de bord. — *Lot S2.*
- Devis, transformés en facture. — *Lot S3.*
- Ventes émises par Qonto en option, avec un périmètre choisi pour l'intégration Qonto. — *Lot S4.*
- Factures récurrentes, baux, avis d'échéance et quittances. — *Lot S5.*
- Abonnements d'achat : échéances attendues, facture et prélèvement rattachés, préavis. — *Lot S6.*

## 2026.10.11 — Intégrations par structure (23/10/2026)

### Améliorations

- Les intégrations proposées dépendent de la structure, et les intégrations recommandées sont suggérées. — *Lots I1–I3.*
- Une intégration désactivée ne laisse rien à l'écran ; une action qui en a besoin propose de l'activer. — *Lot I4.*
- Logos des services et rapport de disponibilité sur la page des intégrations. — *Lot I5.*

## 2026.10.10 — Associés (23/10/2026)

### Nouveautés

- [SCI] Module Associés : registre des parts (souscriptions, cessions, démembrement) et capital à une date. — *Lots A1–A2.*
- [SCI] Comptes courants d'associés : facture payée par un associé, notes de frais, apports et retraits. — *Lot A3.*
- [SCI] Intérêts des comptes courants et proposition d'affectation du résultat à la clôture ; import des associés par fichier CSV. — *Lots A4–A5.*

## 2026.10.9 — Utilisateurs et rôles (23/10/2026)

### Nouveautés

- Comptes et rôles choisis à la création ou à l'import d'une structure ; mot de passe à changer à la première connexion. — *Lots E1–E4.*

### Améliorations

- Lecture des factures d'achat plus fiable (montants cohérents, seconde passe OCR, mémoire du fournisseur) ; produit créé depuis une ligne de facture.
- L'envoi d'une facture saisie vers Qonto devient un choix explicite.

## 2026.10.8 — Comptabilité simplifiée (23/10/2026)

### Nouveautés

- Caisse en espèces et dépôts en banque par virement interne. — *Lot D1.*
- Comptabilité simplifiée : recettes et dépenses par catégorie, sans débit ni crédit, états simplifiés et verrouillage d'exercice. — *Lots D2–D4.*
- Passage de la comptabilité simplifiée à la partie double, sans ressaisie. — *Lot D5.*
- Page publique À propos : fonctionnalités et comparaison avec les autres logiciels.

## 2026.10.7 — Reçus fiscaux (23/10/2026)

### Nouveautés

- [Associations] Reçus fiscaux des dons (particuliers et entreprises), annuels ou par don, avec PDF figés et numérotation continue. — *Lots B1–B2 (obligations associatives).*
- [Associations] Envoi des reçus par e-mail, annulation motivée et réémission, état annuel ; dons en nature. — *Lot B3.*

## 2026.10.6 — Projets et budget (23/10/2026)

### Nouveautés

- Projets ou activités sur les écritures, les achats et les règles, avec ventilation d'une ligne. — *Lot C1.*
- Budget annuel ou mensuel par projet, suivi prévu / réalisé et compte de résultat d'un projet. — *Lots C2–C3.*
- Prévisionnel de trésorerie sur 12 mois avec alerte de solde négatif. — *Lot C4.*
- [Associations] Fonds dédiés rattachés à un projet. — *Lot C5.*

## 2026.10.5 — Obligations comptables (23/10/2026)

### Nouveautés

- Rôles par structure : administrateur, trésorier, expert-comptable en lecture seule. — *Lot A1 (obligations associatives).*
- Identité de la structure, numérotation des écritures et export FEC. — *Lots A2–A3.*
- Assistant de clôture : contrôles, écritures d'inventaire, résultat, clôture provisoire puis définitive, réouverture motivée. — *Lot A4.*
- À-nouveaux, extournes et affectation du résultat. — *Lot A5.*
- [Associations] Fonds dédiés à la clôture (dotation et reprise). — *Lot A6.*

## 2026.10.4 — Nouvelle interface (22/10/2026)

### Nouveautés

- Notifications à la fin des tâches longues (synchronisations, envois), avec une cloche dans l'en-tête.

### Améliorations

- Toute l'application passe à une nouvelle interface : plus rapide, utilisable au clavier, thème sombre, lisible sur mobile. — *Front React + Mantine, phases A–I.*

## 2026.10.3 — Factures d'achat (22/10/2026)

### Nouveautés

- Factures fournisseurs Qonto importées dans les achats, avec un catalogue de produits et la TVA de l'exercice. — *Qonto lot 2a.*
- Comptabilisation en engagement (compte par fournisseur) et règlement depuis les paiements Qonto ou les relevés OFX.
- Saisie d'une facture depuis son fichier : lecture Factur-X, texte du PDF ou photo (OCR), pièce conservée, envoi à Qonto en option. — *Qonto lot 2b.*
- Sauvegardes des structures en .zip avec leurs pièces jointes.

## 2026.10.2 — Banque Qonto (21/10/2026)

### Nouveautés

- Comptes Qonto reliés aux comptes bancaires et transactions synchronisées en arrière-plan. — *Qonto phases A–G.*
- Contreparties bancaires rattachées aux tiers, fournisseurs proposés ; opérations annulées et justificatifs gérés.

### Corrections

- [SCI] Une nouvelle SCI ne reçoit plus les règles de catégorisation propres aux associations.

## 2026.10.1 — Plan SCI et intégrations (20/10/2026)

### Nouveautés

- [SCI] Plan comptable SCI au choix à la création d'une structure, menus, bilan et compte de résultat adaptés.
- Saisie d'écriture et rapprochement bancaire au clavier, avec suggestions.
- Écran des intégrations : activer, configurer et tester chaque service.

### Corrections

- [Associations] Bilan associatif : chaque compte apparaît une seule fois, avec le résultat de l'exercice.

## 2026.06.2 — Visibilité et rapport d'activité (28/06/2026)

### Nouveautés

- [Associations] Indicateurs de visibilité et d'impact.
- [Associations] Rapport d'activité exportable.
- [Associations] Statut d'adhésion écrit dans la fiche Odoo de l'adhérent.

## 2026.06.1 — Relances (25/06/2026)

### Nouveautés

- [Associations] Relance par e-mail des adhérents dont l'adhésion arrive à échéance.

## 2026.05.2 — Plusieurs structures (21/05/2026)

### Nouveautés

- Plusieurs structures dans une même installation, une base par structure, restauration d'une structure.
- Déploiement avec Docker.

### Corrections

- Synchronisation Stancer corrigée ; tableau de bord enrichi.

## 2026.05.1 — Odoo (15/05/2026)

### Améliorations

- Factures clients Odoo et menus revus.

## 2026.04.1 — Première version (28/04/2026)

### Nouveautés

- Plan comptable, journaux, écritures et exercices ; bilan, compte de résultat, balance et grand livre.
- Imports bancaires OFX et caisse Odoo, rapprochement bancaire.
- Versements et paiements Stancer, commandes de caisse Odoo, tableau de bord.
