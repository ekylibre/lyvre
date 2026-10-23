# Besoins — module « Associés » (sociétés : SCI, entreprises)

> Statut : expression de besoins (`/sc:brainstorm`, 23/10/2026). Pas de conception ni de code.
> Étape suivante : `/sc:design`. Questions ouvertes tranchées le 23/10/2026 (§ 8).

## 1. Objectif

Une société (SCI aujourd'hui, entreprise demain) doit tenir **qui détient son capital** et **ce
qu'elle doit à chaque associé** (compte courant). Aujourd'hui l'application ne connaît ni les
associés, ni leurs parts, ni leurs comptes courants : les 455 du plan SCI existent, mais rien ne
les alimente hors saisie manuelle d'écritures. L'affectation du résultat d'une SCI sur les 455
(étape 8 de la clôture, D9) se fait sans registre pour la répartir.

Le module doit permettre :

1. de déclarer les associés, leurs parts et la nature de leurs droits (pleine propriété,
   usufruit, nue-propriété), avec l'historique des mouvements de parts ;
2. de suivre le compte courant de chaque associé (solde, relevé, évolution par exercice) ;
3. de faire passer par ce compte courant les opérations courantes : facture payée par un associé,
   apport ou remboursement par la banque, dépense avancée sans facture, affectation du résultat.

## 2. Référence observée : Ekylibre (instance SCI des Chênes Verts)

Consultée le 23/10/2026 (`/backend/associates`, `outgoing_payment_modes`, `cashes`).

| Élément | Ekylibre |
|---|---|
| Associé | Tiers + type de part (Associé / Actionnaire – Pleine propriété, Usufruitier, Nu-propriétaire) + entrée au capital (date, obligatoire) + sortie du capital (date) |
| Parts | Nombre d'actions + montant unitaire de l'action ; pourcentage de détention calculé ; pièces jointes |
| Compte courant | Une trésorerie de nature « Compte courant d'associé » par associé, avec son compte 455 (ex. 455103xx) et son propre journal |
| Payer avec le compte courant | Un mode de décaissement par associé, dont la trésorerie est son compte courant : régler une facture avec ce mode passe 401 au débit, 455 de l'associé au crédit |
| Vues | Liste (date d'entrée, tiers, type, nombre d'actions, %, compte courant, solde) ; graphique des parts ; graphique empilé des soldes des comptes courants par exercice |
| Limites constatées | Pas d'historique des mouvements de parts (une cession = modifier les lignes) ; un associé démembré = une ligne par nature ; pas de lien explicite entre usufruitier et nu-propriétaires d'un même lot |

## 3. Décisions déjà prises (réponses du 23/10/2026)

| # | Sujet | Décision |
|---|---|---|
| R1 | Mouvements du compte courant | **Tous** : facture payée par l'associé, apport / remboursement par la banque, dépense sans facture, affectation du résultat |
| R2 | Démembrement | **Comme Ekylibre** : chaque associé détient un nombre de parts d'une nature (PP, usufruit, nue-propriété) ; % calculé. Pas de lots numérotés liés |
| R3 | Historique des parts | **Registre des mouvements** : chaque mouvement de parts est une ligne datée ; la situation à une date est recalculée |
| R4 | Périmètre | **Option par instance** (« Société avec associés »), indépendante du plan comptable ; jamais proposée par défaut à une association |

## 4. Exigences fonctionnelles

### F1 — Activation

- F1.1 L'administrateur de l'instance active ou désactive l'option « Société avec associés »
  (Configuration). Désactivée : menu et écrans masqués, données conservées.
- F1.2 Proposée par défaut à la création d'une instance au plan SCI (case cochée), décochée pour
  le plan association.
- F1.3 Désactiver l'option alors qu'un compte courant d'associé a un solde non nul : **avertissement**
  (soldes listés), sans refus.

### F2 — Associés

- F2.1 Un associé est un **tiers** existant (personne physique ou morale) ou créé à la volée.
- F2.2 Chaque associé a **un compte courant** : sous-compte proposé **4551001, 4551002…** (premier
  numéro libre), modifiable, ou compte 455 existant choisi (reprise).
- F2.3 Fiche associé : identité (depuis le tiers), parts détenues par nature à la date du jour,
  % de détention, solde du compte courant, relevé, mouvements de parts, pièces jointes (statuts,
  actes de cession, donation).
- F2.4 Un associé sorti du capital (plus aucune part) reste consultable ; son compte courant
  peut garder un solde (à rembourser).

### F3 — Registre des mouvements de parts

- F3.1 Types de mouvement :
  - souscription (constitution, augmentation de capital) ;
  - cession entre associés ou à un tiers ;
  - donation ou succession, en pleine propriété ou avec démembrement (ex. le donateur garde
    l'usufruit, le donataire reçoit la nue-propriété) ;
  - réunion de l'usufruit et de la nue-propriété (décès de l'usufruitier, fin d'usufruit
    temporaire) ;
  - réduction de capital, retrait.
- F3.2 Chaque mouvement porte : date, type, nombre de parts, nature (PP / usufruit /
  nue-propriété), cédant(s) et bénéficiaire(s), valeur nominale, prix ou valeur déclarée
  (informative), pièce jointe, commentaire.
- F3.3 Situation à une date : par associé et par nature, nombre de parts et % du capital.
  - Une part démembrée compte une fois dans le total : capital = PP + NP = PP + usufruit.
  - Une incohérence (parts démembrées dont la NP et l'usufruit ne s'équilibrent pas) est signalée.
- F3.4 Capital social = total des parts × valeur nominale. Un écart avec le solde du compte 101
  est signalé (contrôle, pas de blocage).
- F3.5 Le registre reste **hors comptabilité** pour l'instant : aucun mouvement de parts (même
  souscription ou réduction) ne génère d'écriture ; le capital est saisi en écritures comme
  aujourd'hui, le contrôle F3.4 signale les écarts.
- F3.6 Un mouvement se corrige ou se supprime tant qu'aucun mouvement postérieur ne s'appuie
  dessus (sinon refus motivé).

### F4 — Comptes courants

- F4.1 Liste des associés avec solde de leur compte courant à la date du jour et à la clôture
  de chaque exercice. Le sens est explicite : solde créditeur = la société doit à l'associé.
- F4.2 Relevé par associé : écritures du sous-compte 455, avec origine (facture réglée, apport,
  remboursement, note de frais, affectation), lien vers la pièce ou la facture.
- F4.3 Graphique de l'évolution des soldes par exercice (équivalent du graphique empilé
  d'Ekylibre).
- F4.4 **Intérêts des comptes courants** : taux annuel par associé (ou par défaut pour la société),
  **0 % par défaut** ; à la clôture, calcul des intérêts courus sur les soldes créditeurs (prorata
  temporis) et proposition de l'écriture 6615 / 4558 (ou 455 de l'associé). Taux nul : rien proposé.
- F4.5 Un solde débiteur (associé débiteur de la société) est signalé : interdit pour une SARL
  ou une SA, à surveiller pour une SCI.

### F5 — Facture d'achat payée par un associé

- F5.1 Sur une facture d'achat (saisie ou reçue de Qonto), action « Réglée par un associé » :
  associé, date, montant (par défaut le reste à payer).
- F5.2 Effet comptable : 401 du fournisseur au débit, 455 de l'associé au crédit. La facture
  passe « payée » (paiement d'origine « associé »). Défaire le règlement supprime l'écriture.
- F5.3 À la saisie d'une facture, le règlement par un associé peut être indiqué directement.
  Le règlement n'est connu **que de l'application** : rien n'est écrit dans Qonto (une facture
  envoyée y reste « à payer », à traiter dans Qonto par l'utilisateur).
- F5.4 Une facture déjà rapprochée d'une transaction bancaire ne peut pas être aussi réglée par
  un associé (pas de double paiement).

### F6 — Apport et remboursement par la banque

- F6.1 Dans le rapprochement bancaire (OFX, Qonto), une transaction peut être affectée au compte
  courant d'un associé :
  - entrée d'argent = apport : 512 au débit, 455 de l'associé au crédit ;
  - sortie = remboursement : 455 au débit, 512 au crédit.
- F6.2 Une règle bancaire peut cibler le compte courant d'un associé (ex. virements récurrents).

### F7 — Dépense avancée sans facture (note de frais)

- F7.1 Saisie d'une dépense payée par l'associé sans facture fournisseur : date, libellé, compte
  de charge, montant, TVA éventuelle (si la société récupère la TVA), justificatif.
- F7.2 Effet comptable : charge (et 44566) au débit, 455 de l'associé au crédit.
- F7.3 Le justificatif est rangé comme une pièce de facture (sauvegardes incluses).

### F8 — Affectation du résultat

- F8.1 À l'étape « affectation » de la clôture (D9), une répartition sur les 455 des associés est
  proposée au prorata de leurs parts à la date de clôture. Elle reste modifiable et se rattache
  aux comptes 455 du registre.
- F8.2 Avec démembrement, le résultat revient à **l'usufruitier** (parts en usufruit) et aux
  pleins propriétaires (parts en PP) ; rien aux nu-propriétaires. La répartition proposée reste
  modifiable.
- F8.3 Ce point reprend D9 (« affectation SCI 455x ») : la règle F8.2 est retenue ; la relecture
  par l'expert-comptable reste souhaitable avant la mise en service.

### F9 — Reprise de l'existant

- F9.1 Saisie initiale de la situation à une date (bilan d'ouverture) : parts par associé et
  nature, soldes des comptes courants. Ce sont des mouvements de « reprise » plutôt que
  l'historique complet.
- F9.2 **Import CSV** : associés (tiers créé ou rapproché par nom), compte courant (numéro),
  parts par nature à la date de reprise, solde d'ouverture du compte courant. Aperçu avant
  import, lignes en erreur signalées, rien d'importé tant qu'il reste une erreur. Cible : reprise
  des 8 associés de la SCI des Chênes Verts depuis Ekylibre.

## 5. Rôles et droits

| Action | Admin. instance | Trésorier | Expert-comptable |
|---|---|---|---|
| Activer l'option | ✔ | — | — |
| Associés, registre des parts, import CSV, taux d'intérêt | ✔ | lecture | lecture |
| Factures réglées par un associé, apports, remboursements, notes de frais | ✔ | ✔ | lecture |
| Affectation du résultat | selon les règles de clôture existantes | | |

## 6. Exigences non fonctionnelles

- **Données personnelles** : uniquement le nécessaire (identité, adresse, pour la future
  déclaration 2072). Les associés sont exportés dans les sauvegardes, comme les autres tiers.
- **Traçabilité** : chaque écriture générée porte son origine et renvoie à sa pièce ; aucune
  écriture d'un exercice clôturé n'est modifiée.
- **Cohérence comptable** : la somme des soldes des sous-comptes 455 des associés égale le solde
  du 455 au bilan ; un écart est signalé.
- **Mêmes conventions que le reste** : API JSON, écrans Mantine, tests pytest, Vitest et e2e,
  documentation utilisateur (`doc/`).

## 7. Récits utilisateurs et critères d'acceptation

- **US1** — En tant qu'administrateur, j'active « Société avec associés » et le menu
  « Associés » apparaît. *Critère :* invisible tant que l'option est désactivée, et pour un
  expert-comptable non membre.
- **US2** — Je déclare la constitution : souscription de 1 000 parts de 10 € réparties entre
  trois associés. *Critère :* capital 10 000 €, % 50/30/20, écart signalé si le 101 ne vaut pas
  10 000 €.
- **US3** — Je saisis une donation de la nue-propriété de 300 parts d'un parent à ses deux
  enfants, avec réserve d'usufruit. *Critère :* le parent apparaît usufruitier de 300 parts, les
  enfants nu-propriétaires de 150 chacun ; le total du capital ne change pas.
- **US4** — Un associé a payé la facture EDF de 70,59 € avec sa carte. Je clique « Réglée par un
  associé ». *Critère :* écriture 401 / 455 de l'associé, facture payée, relevé de l'associé
  crédité de 70,59 €.
- **US5** — Un associé vire 3 000 € sur le compte de la SCI. *Critère :* dans le rapprochement,
  j'affecte la transaction à son compte courant (512 / 455) et son solde augmente de 3 000 €.
- **US6** — Je rembourse 500 € à un associé. *Critère :* la sortie bancaire est affectée à son
  455 et le solde diminue.
- **US7** — Un associé a acheté des ampoules sans facture au nom de la SCI. *Critère :* note de
  frais avec le ticket, charge 606x / 455.
- **US8** — À la clôture, le résultat de 12 000 € est réparti sur les 455 au prorata des parts
  (règle F8.2), modifiable avant validation.
- **US9** — Je consulte la situation du capital au 31/12/2024. *Critère :* parts et % recalculés
  depuis le registre à cette date.

## 8. Décisions sur les questions ouvertes (23/10/2026)

| # | Question | Décision |
|---|---|---|
| Q1 | Écritures de capital | Registre **hors comptabilité** pour l'instant (F3.5) |
| Q2 | Intérêts des comptes courants | **Oui**, taux **0 % par défaut** (F4.4) |
| Q3 | Journal | **Journal unique** « Associés » pour les écritures du module ; l'associé se lit par son sous-compte |
| Q4 | Résultat avec démembrement | À **l'usufruitier** (et aux pleins propriétaires) (F8.2) |
| Q5 | Numérotation | **4551001, 4551002…** (F2.2) |
| Q6 | Reprise Ekylibre | **Import CSV** (F9.2) |
| Q7 | Facture Qonto réglée par un associé | Réglée **dans l'application seulement** (F5.3) |
| Q8 | Désactivation avec soldes | **Avertissement** (F1.3) |
| Q9 | Registre des parts | **Administrateur de l'instance** seulement ; trésorier en lecture |
| Q10 | Hors périmètre | **Confirmé** : déclaration 2072, dividendes (457), assemblées et procès-verbaux, valorisation des parts |
