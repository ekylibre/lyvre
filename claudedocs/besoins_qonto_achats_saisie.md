# Besoins — Qonto, lot 2b : saisie de factures d'achat, pièce jointe et OCR

> Statut : **validé** (brainstorm du 2026-10-21, décisions QB1 à QB8 au §8). Prochaine étape : `/sc:design`.
> Sources : [`besoins_qonto_achats.md`](besoins_qonto_achats.md) §8 (cadrage), lot 2a réalisé
> ([`design_qonto_achats.md`](design_qonto_achats.md)).

## 1. Contexte

Le lot 2a fait entrer dans l'application les factures **reçues dans Qonto**. Il manque les factures
qui n'y passent pas, et la situation diffère selon l'instance :

| Instance | Banque | Besoin |
|----------|--------|--------|
| **SCI des Chênes Verts** | Qonto | Saisir une facture reçue hors Qonto (papier, e-mail), l'envoyer à Qonto pour qu'elle y soit payée et archivée ; quelques factures payées autrement restent locales |
| **Seconde Nature** | Banque classique, **import OFX** | Saisir **toutes** ses factures d'achat dans l'application (seul point d'entrée), les comptabiliser en engagement comme au lot 2a et les régler depuis les transactions OFX |

| Constat (état au commit `1e25e63`) | Valeur |
|------------------------------------|--------|
| Factures | `purchases` prévoit `source = 'manual'` (`qonto_id` NULL) ; états, lignes, catalogue, comptabilisation AC, annulation : **réutilisables tels quels** |
| Règlements | `purchase_payments.qonto_transaction_id` **NOT NULL** : lien réservé aux transactions Qonto ; rien pour l'OFX |
| Fournisseurs | Reconnaissance par identifiant Qonto, n° de TVA, nom ; pas de SIRET sur `entities` |
| OCR | Tesseract 5 avec le français installé sur le poste de développement ; **PyMuPDF absent** des dépendances ; ni l'un ni l'autre dans l'image Docker |
| Fichiers | Convention `instance/uploads/…` (rapport d'activité, logo), **non séparée par instance** ; les **sauvegardes d'instance ne contiennent que la base `.db`** |
| API Qonto | `POST /v2/supplier_invoices/bulk` (multipart, ≤ 20 fichiers, `idempotency_key` par facture) : réponse 200 avec `supplier_invoices[]` (dont `id`) **et** `errors[]` — toujours vérifier les deux ; Qonto analyse ensuite le fichier (OCR) |
| Accès Qonto de test | Clé de la SCI en **lecture seule** (consigne) : l'envoi ne peut être essayé que sur le **bac à sable** ou avec un accord explicite pour le compte réel |

## 2. Objectifs

- **O1** — Saisir une facture d'achat **à partir de son fichier** : le formulaire est prérempli, le
  trésorier vérifie et valide.
- **O2** — La facture saisie suit **le même cycle** que celles du lot 2a : lignes, catalogue,
  comptabilisation automatique en engagement, annulation.
- **O3** — **SCI** : la facture part dans Qonto (sauf exception) et revient sans doublon.
- **O4** — **Seconde Nature** : la facture est réglée **depuis la transaction OFX** qui la paie,
  automatiquement quand il n'y a pas d'ambiguïté.
- **O5** — La pièce est **conservée et consultable** depuis la fiche de la facture.

## 3. Utilisateurs

| Profil | Usage | Attentes |
|--------|-------|----------|
| Trésorier | Fréquent : déposer une facture, vérifier, valider ; contrôler les règlements | Saisie rapide (dépôt → vérification → validation), champs douteux signalés, pas de doublon |
| Administrateur | Ponctuel | Rien de plus que le lot 2a (catalogue, TVA de l'exercice) |

## 4. Besoins fonctionnels

### S1 — Nouvelle facture
- S1.1 Bouton « Nouvelle facture » (page Factures d'achat) : dépôt d'un fichier **PDF, JPEG ou PNG**
  (glisser-déposer ou sélection), ou saisie sans fichier.
- S1.2 Formulaire prérempli (S2) : fournisseur, n° de facture, date, échéance, avoir oui / non,
  montants HT / TVA / TTC, ventilation par taux ; lignes par défaut depuis le produit du fournisseur
  (même règle que le lot 2a) ; les champs issus de l'OCR **à vérifier** sont signalés.
- S1.3 Fournisseur : reconnu (n° de TVA, SIRET, IBAN, nom) ou choisi dans la liste, ou **créé** depuis
  le formulaire (nom, TVA, SIRET, IBAN lus sur la facture). Nouveau champ **SIRET** sur la fiche
  entité (QB6).
- S1.4 À l'enregistrement : facture `source = 'manual'`, fichier conservé (S5) ; comptabilisée
  automatiquement si elle est complète (lot 2a).
- S1.5 **Doublon** : même fournisseur et même n° de facture (ou, sans n°, même fournisseur, date et
  TTC) → avertissement ; enregistrement seulement après confirmation explicite.
- S1.6 Une facture saisie reste modifiable (en-tête et lignes) tant qu'elle n'est pas comptabilisée.

### S2 — Lecture du fichier (OCR)
- S2.1 Ordre : **Factur-X / ZUGFeRD** (XML CII embarqué dans le PDF : données exactes) → **texte
  du PDF** (PyMuPDF) → **OCR** Tesseract en français pour les pages scannées et les images.
- S2.2 Champs recherchés : n° de TVA intracommunautaire, SIRET, IBAN, dates (facture, échéance),
  n° de facture, montants (« Total TTC », « Net à payer », « Total HT », « TVA »), taux et montants
  de TVA ; cohérence vérifiée (HT + TVA = TTC).
- S2.3 Fournisseur proposé : n° de TVA, puis SIRET, puis IBAN, puis nom (même normalisation que le lot 2a).
- S2.5 Lecture **pendant la requête** (indicateur de chargement), limitée aux **3 premières pages** (QB7).
- S2.4 Échec ou lecture partielle : le formulaire s'ouvre quand même, champs vides ou signalés ;
  jamais de blocage.

### S3 — Envoi à Qonto (instances avec l'intégration Qonto)
- S3.1 Case **« Envoyer à Qonto »** affichée seulement si l'intégration Qonto est disponible dans
  l'instance, **cochée par défaut** ; décochée pour une facture payée par un autre compte (QB1).
- S3.2 Envoi à l'enregistrement : `POST /v2/supplier_invoices/bulk` avec le fichier et une
  `idempotency_key` propre à la facture ; l'`id` renvoyé est mémorisé (`qonto_id`).
- S3.3 Échec (réseau, erreur dans `errors[]`) : la facture est enregistrée et marquée « envoi à
  Qonto en échec » avec le message ; bouton **Renvoyer** (même clé d'idempotence : pas de doublon).
- S3.4 Envoi impossible sans fichier.

### S4 — Retour de Qonto
- S4.1 À la synchronisation (lot 2a), la facture renvoyée par Qonto est reconnue par son `qonto_id` :
  **pas de doublon**.
- S4.2 **La saisie l'emporte** (QB2) : fournisseur, n°, dates, montants et lignes saisis sont gardés ;
  Qonto complète les champs vides et met à jour statut, date de paiement et transactions liées.
- S4.3 Le règlement suit le lot 2a (transactions Qonto désignées par la facture).

### S5 — Pièce jointe
- S5.1 Fichier rangé dans un dossier **propre à l'instance** :
  `instance/uploads/<instance>/achats/AAAA/MM/` (date de facture), nom de fichier sûr (QB4).
- S5.2 Consultation et téléchargement depuis la fiche (aperçu PDF / image) ; remplacement possible
  tant que la facture n'est pas envoyée à Qonto.
- S5.3 Factures reçues dans Qonto : pas de téléchargement de leur pièce dans ce lot (lot Google Drive).

### S8 — Sauvegardes avec pièces (QB5)
- S8.1 La sauvegarde d'une instance devient une **archive `.zip`** : base + dossier des pièces de
  l'instance ; téléchargement et restauration depuis l'écran Instances comme aujourd'hui.
- S8.2 Les anciennes sauvegardes `.db` restent restaurables (base seule).
- S8.3 La restauration remplace les pièces de l'instance par celles de l'archive.

### S6 — Règlement depuis un compte hors Qonto (OFX)
- S6.1 Pour une facture saisie **comptabilisée** et non réglée, recherche des **débits non
  rapprochés** des comptes bancaires **non rattachés à Qonto** : montant égal au TTC (ou au net à
  payer), date entre la date de facture − 5 jours et l'échéance (à défaut la date) + 60 jours.
- S6.2 **Un seul candidat** → lien et règlement 401 / banque **automatiques**, rapprochés (QB3) ;
  plusieurs → **suggestions** sur la fiche (préférence au même fournisseur), confirmation en un clic ;
  aucun → la facture reste « non réglée ».
- S6.3 Déclenchement : à la comptabilisation de la facture **et** après chaque import OFX (pour les
  factures en attente).
- S6.4 Une transaction liée à une facture est ignorée par les règles (comme au lot 2a) ; une
  transaction déjà passée par une règle rejoint la liste « règlements à remplacer ».
- S6.5 Lien défaisable depuis la fiche (supprime le règlement, défait le rapprochement).

### S7 — Liste et fiche
- S7.1 Liste : colonne / filtre **origine** (Qonto, saisie) ; badge « envoi en échec » ; filtre
  « non réglée ».
- S7.2 Fiche d'une facture saisie : en-tête modifiable avant comptabilisation, pièce, état de l'envoi
  à Qonto, suggestions de règlement.

## 5. Besoins non fonctionnels

- NF1 **Fichiers** : 10 Mo maximum, type vérifié sur le contenu (pas seulement l'extension), nom
  assaini, aucun chemin fourni par l'utilisateur ; accès réservé aux utilisateurs de l'instance.
- NF2 **OCR** : traitement local (aucun service externe) ; PDF texte < 2 s ; scan d'une page < 10 s ;
  au-delà de quelques pages, lecture des premières pages seulement (à préciser en design).
- NF3 **Docker** : image avec `tesseract-ocr` et `tesseract-ocr-fra`, PyMuPDF dans `requirements.txt`.
- NF4 **Qonto** : écriture limitée au dépôt de factures ; clé d'idempotence ; jamais d'essai d'écriture
  sur le compte réel sans accord explicite (bac à sable).
- NF5 **Multi-instance** : fichiers, factures et règlements propres à chaque instance.
- NF6 **Testabilité** : PDF de test générés dans les tests (texte, Factur-X, image scannée simulée),
  client Qonto simulé ; Tesseract optionnel en CI (tests OCR ignorés s'il est absent).

## 6. Récits utilisateur et critères d'acceptation

**US1 — Saisir depuis un PDF (Seconde Nature).** Le trésorier dépose la facture PDF d'un fournisseur connu.
- [ ] Fournisseur, n°, date, HT / TVA / TTC sont préremplis ; les lignes viennent du produit par défaut.
- [ ] Après validation, la facture est comptabilisée (AC) et la pièce est consultable depuis la fiche.
- [ ] Redéposer la même facture déclenche l'avertissement de doublon.

**US2 — Scan ou photo.** Le trésorier dépose une facture scannée (image ou PDF image).
- [ ] L'OCR préremplit au moins le TTC et la date ; les champs incertains sont signalés.

**US3 — Facture électronique.** Le trésorier dépose un PDF Factur-X.
- [ ] Tous les champs (montants, TVA par taux, n° de TVA du fournisseur) sont repris sans erreur.

**US4 — Règlement OFX.** L'import OFX amène le débit qui paie la facture.
- [ ] Débit unique de même montant dans la fenêtre → règlement 401 / banque passé et rapproché.
- [ ] Deux candidats → suggestions sur la fiche ; un clic règle la facture.

**US5 — SCI avec Qonto.** Le trésorier saisit une facture, case « Envoyer à Qonto » cochée.
- [ ] La facture apparaît dans Qonto ; la synchronisation suivante ne crée pas de doublon et garde la saisie.
- [ ] Case décochée : la facture reste locale et se règle comme en US4.
- [ ] Envoi en échec : message clair, bouton Renvoyer sans doublon.

## 7. Hors périmètre

- Téléchargement des pièces des factures reçues dans Qonto, Google Drive (lot dédié).
- Paiement d'une facture depuis l'application ; paiements partiels ou multiples hors Qonto.
- Factures en devise ; saisie de factures de vente (lot ventes).
- Lecture des lignes détaillées d'une facture papier (seuls totaux et ventilation par taux).

## 8. Décisions et questions

| # | Question | Décision (2026-10-21) |
|---|----------|------------------------|
| QB1 | Envoi à Qonto | Case « Envoyer à Qonto », affichée si Qonto est disponible, **cochée par défaut** |
| QB2 | Priorité au retour de Qonto | **La saisie l'emporte** ; Qonto complète les vides, statut et paiements |
| QB3 | Règlement OFX | **Automatique si un seul candidat**, sinon suggestions |
| QB4 | Stockage des pièces | **Dossier de l'instance** `instance/uploads/<instance>/achats/AAAA/MM/` |

| QB5 | Sauvegardes | **Dans ce lot** : archive `.zip` base + pièces ; anciennes `.db` restaurables |
| QB6 | SIRET | **Oui** : champ sur l'entité, lu sur la facture, utilisé pour la reconnaissance |
| QB7 | OCR long | **Pendant la requête**, 3 premières pages |
| QB8 | Essai de l'envoi à Qonto | **Un envoi réel ponctuel** sur le compte de la SCI, autorisé au moment voulu par l'utilisateur (facture choisie par lui), puis retour à la lecture seule |
