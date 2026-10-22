# Besoins — Obligations associatives : clôture, FEC, reçus fiscaux, budget et projets

> Statut : **validé** (brainstorm du 2026-10-22, décisions OA1–OA14). Suite : `/sc:design`. Point de départ : comparaison de Lyvre avec
> deux comparatifs de logiciels de comptabilité associative (Pennylane, fiche pratique
> « meilleur logiciel comptabilité association », informations du 27/04/2026 ; Independant.io,
> page « logiciel comptabilité association »).

## 1. Contexte : comparaison

Critères communs aux deux articles : plan comptable associatif (règlement ANC n° 2018-06), partie
double, adhésions et cotisations (relances, paiement en ligne), dons avec **reçus fiscaux**,
subventions, banque (import, rapprochement, automatisation), bilan / compte de résultat / journaux,
rapport d'AG, **suivi par projet ou activité, budget, prévisionnel**, **fonds dédiés**, TVA,
**export FEC**, collaboration (trésorier, président, expert-comptable), mobile, support.

| Thème | Lyvre (2026-10-22) |
|---|---|
| Plan associatif ANC 2018-06 / SCI, partie double, bilan, CdR, journaux, grand livre, N/N-1 | ✅ |
| Contributions volontaires en nature (86 / 87) au CdR | ✅ |
| Banque : OFX, Qonto, rapprochement au clavier, règles, annulation | ✅ (au-dessus des outils cités) |
| Factures d'achat avec lecture Factur-X / PDF / OCR, engagement, 401 par fournisseur | ✅ |
| TVA par exercice | ✅ |
| Adhésions (HelloAsso, POS), relances email | ✅ |
| Rapport d'AG (rapport d'activité PDF / DOCX / ODT, indicateurs d'impact) | ✅ |
| Multi-structures, logiciel libre auto-hébergé, sauvegardes | ✅ |
| Reçus fiscaux des dons | ❌ |
| Export FEC, export pour l'expert-comptable | ❌ |
| Clôture : affectation du résultat, à-nouveaux | ⚠️ verrouillage seul |
| Budget, prévisionnel de trésorerie, suivi par projet / activité | ❌ |
| Fonds dédiés, immobilisations / amortissements | ⚠️ comptes présents, aucun suivi ni calcul |
| Rôles (trésorier, lecture seule, expert-comptable), accès par instance | ⚠️ admin / utilisateur, toutes instances |
| Remise de chèques, factures clients émises, devis | ❌ (factures clients via Odoo seulement) |
| Application mobile, comptabilité simplifiée (trésorerie) | ❌ (lisible sur mobile, partie double seule) |

## 2. Décisions du brainstorm (2026-10-22)

| # | Question | Réponse |
|---|---|---|
| OA1 | Priorités | **Clôture et obligations** (clôture complète, FEC, export expert-comptable), **reçus fiscaux des dons**, **budget et projets** |
| OA2 | Reçus fiscaux aujourd'hui (Seconde Nature) | Aucun : pas de dons ouvrant droit à réduction d'impôt. Le besoin vient de la cible élargie (OA3) |
| OA3 | Cible | **D'autres associations** que Seconde Nature et la SCI : prise en main, documentation et paramétrage par instance comptent |
| OA4 | Expert-comptable | **Oui** : il faut lui transmettre les comptes |
| OA5 | Ordre des lots | **A** (clôture, FEC, rôle expert-comptable) → **C** (budget, projets) → **B** (reçus fiscaux) → **D** (comptabilité simplifiée) |
| OA6 | Rôles | **Rôle expert-comptable ajouté au lot A** (accès en lecture à l'instance), ce qui suppose des accès par instance |
| OA7 | Comptabilité simplifiée | **Retenue** (lot D) pour les petites associations de la cible élargie |
| OA8 | Format pour l'expert-comptable | **Export FEC uniquement** (pas d'export propre à un logiciel, pas d'archive des états ni des pièces) |
| OA9 | Clôture | **Assistant de clôture avec toutes les étapes** : contrôles, écritures d'inventaire (charges à payer, produits à recevoir, charges et produits constatés d'avance), fonds dédiés, résultat, FEC, clôture, à-nouveaux, affectation du résultat |
| OA10 | Rôles | Administrateur, trésorier, expert-comptable : **suffisant** |
| OA11 | Analytique | **Un seul axe** « projet / activité » |
| OA12 | Prévisionnel | **Par mois, sur 12 mois** |
| OA13 | Reçus fiscaux | **Récapitulatif annuel** par défaut, **dons des entreprises couverts** dès le départ |
| OA14 | Comptabilité simplifiée | **Pas de FEC ni de clôture complète** dans ce mode ; la **caisse** (espèces) est un compte à part entière (**53x**) |

Hors priorités : remise de chèques, facturation émise, immobilisations / amortissements, mobile.

## 3. Objectifs

1. Permettre de **clôturer un exercice de bout en bout** dans Lyvre, de façon conforme, et de
   **transmettre les comptes** à l'expert-comptable sans ressaisie.
2. Permettre à une association éligible d'**émettre ses reçus fiscaux** à partir des dons
   comptabilisés, sans outil externe.
3. Donner au trésorier et au bureau un **budget** et un **suivi par projet / activité** (prévu /
   réalisé), et une vue **prévisionnelle de trésorerie**.

## 4. Utilisateurs

- **Trésorier** (bénévole, peu à l'aise avec les écritures de clôture) : clôture, reçus, budget.
- **Président / bureau** : lit le budget et le suivi des projets, valide l'affectation du résultat
  (AG).
- **Expert-comptable** (externe) : reçoit le FEC ; consulte l'instance en lecture (rôle dédié) ;
  peut demander des corrections avant clôture définitive.
- **Donateur** (externe) : reçoit son reçu fiscal (email ou PDF).
- **Administrateur Lyvre** (autre association, cible élargie) : active et paramètre ces fonctions
  pour son instance.

## 5. Exigences fonctionnelles

### 5.1 Clôture et obligations (lot A)

- **FA1 — Export FEC.** Générer le fichier des écritures comptables d'un exercice au format
  réglementaire (fichier texte, 18 champs de `JournalCode` à `Idevise`, séparateur tabulation ou
  barre verticale, nom `<SIREN>FEC<AAAAMMJJ>`) : toutes les écritures validées de l'exercice, dans
  l'ordre chronologique de validation, numérotation continue par journal, comptes et libellés,
  tiers (compte auxiliaire 401NNN / 411…), pièce, lettrage / rapprochement si disponible.
  Contrôle avant export : écritures équilibrées, dates dans l'exercice, aucune écriture en
  brouillon.
- **FA2 — SIREN et identité de la structure** par instance (SIREN / RNA, raison sociale, adresse),
  utilisés par le FEC, les reçus et les états.
- **FA3 — Assistant de clôture** (OA9) : parcours pas à pas d'un exercice, chaque étape avec son
  état (à faire, fait, ignorée en connaissance de cause), reprenable plus tard, réservé aux rôles
  administrateur et trésorier (la dernière étape à l'administrateur, FA6) :
  1. **Contrôles** : transactions bancaires et de caisse non rapprochées, écritures déséquilibrées,
     factures d'achat non comptabilisées ou non réglées, comptes d'attente (47x) non soldés, soldes
     anormaux (banque ou caisse créditrice) ; chaque point avec un lien vers l'écran concerné ;
  2. **Écritures d'inventaire** : charges à payer et produits à recevoir (factures non parvenues,
     subventions acquises non versées), charges et produits constatés d'avance (486 / 487), saisies
     guidées et datées du dernier jour de l'exercice, **extournées automatiquement** à l'ouverture
     de l'exercice suivant ;
  3. **Fonds dédiés** (FA8) : report de la part non utilisée des ressources affectées ;
  4. **Résultat** : compte de résultat et bilan provisoires, résultat de l'exercice ;
  5. **FEC** (FA1) : contrôle puis export ;
  6. **Clôture** provisoire puis définitive (FA6) ;
  7. **À-nouveaux** (FA4) dans l'exercice suivant ;
  8. **Affectation du résultat** (FA5), une fois la décision prise.
- **FA4 — Écritures de clôture et d'ouverture.** À la clôture : calcul du résultat ; à l'ouverture
  de l'exercice suivant, écritures d'**à-nouveaux** (journal dédié, comptes de bilan seulement,
  résultat en attente d'affectation sur 120 / 129), générées automatiquement et regénérables tant
  que l'exercice N+1 n'est pas clôturé (si N est modifié après coup : rouverture contrôlée, cf. FA6).
- **FA5 — Affectation du résultat** selon la décision de l'organe compétent (assemblée générale
  pour une association, assemblée des associés pour une SCI : la date et l'organe sont saisis) :
  saisie guidée (report à nouveau 110 / 119, réserves 106, fonds associatifs ; pour une SCI,
  comptes des associés) produisant l'écriture correspondante.
- **FA6 — Clôture définitive et réouverture.** Clôture provisoire (verrou, réversible) puis
  définitive (irréversible, horodatée, liée au FEC exporté). Réouverture d'une clôture provisoire
  réservée à un rôle autorisé (au minimum : administrateur), tracée.
- **FA7 — Transmission à l'expert-comptable : FEC uniquement** (OA8). Pas d'export vers un
  logiciel tiers ni d'archive des états ou des pièces : il consulte le reste dans Lyvre (FA9).
- **FA9 — Rôle expert-comptable et accès par instance** (OA6). Un utilisateur n'a accès qu'aux
  instances qui lui sont attribuées, avec un rôle par instance : **administrateur** (tout, dont
  paramétrage et réouverture), **trésorier** (saisie, rapprochement, clôture provisoire),
  **expert-comptable** (lecture de toute la comptabilité : écritures, états, pièces justificatives ;
  export FEC ; aucune modification). Les utilisateurs actuels gardent leurs accès lors de la mise
  en place (reprise : accès à toutes les instances existantes avec leur rôle actuel). La clôture
  définitive est réservée à l'administrateur. Invitation d'un expert-comptable par l'administrateur
  de l'instance (compte créé ou existant), accès révocable.
- **FA8 — Fonds dédiés (suivi minimal).** Pour une subvention ou un don affecté à un projet :
  enregistrer le montant affecté, le montant utilisé sur l'exercice, et proposer à la clôture
  l'écriture de report en fonds dédiés (689 / 19x) puis sa reprise (789) ; lié au lot C (projets).

### 5.2 Reçus fiscaux des dons (lot B, après le lot C)

- **FB1 — Activation par instance** avec déclaration de l'éligibilité par la structure
  (intérêt général / reconnue d'utilité publique / autre cas prévu par le CGI, et référence d'un
  éventuel rescrit), et mentions de l'organisme (objet, adresse, signataire, signature scannée).
  L'outil n'évalue pas l'éligibilité : il affiche un avertissement de responsabilité.
- **FB2 — Source des dons.** Dons issus des écritures (comptes 754x), de HelloAsso (dons déjà
  synchronisés) et saisie manuelle ; donateur = tiers Lyvre (nom, adresse obligatoire pour le reçu).
- **FB3 — Reçu conforme au modèle CERFA n° 11580 en vigueur** (particuliers) : numéro d'ordre
  unique et continu par instance, bénéficiaire, donateur, montant en chiffres et en lettres, date,
  forme (acte authentique / sous seing privé / déclaration de don manuel / autre), nature (numéraire,
  titres, autres — dons en nature valorisés), mode de versement, article(s) du CGI cochés.
- **FB3b — Reçus des entreprises** (OA13) dès le départ : donateur personne morale (raison
  sociale, SIREN), modèle de reçu applicable aux entreprises en vigueur, mêmes règles de numérotation.
- **FB4 — Récapitulatif annuel** par donateur **par défaut** (OA13), par année civile ; reçu
  unitaire possible au cas par cas ; génération en lot.
- **FB5 — Envoi** par email (réutilise l'intégration SMTP) avec PDF joint, ou téléchargement ;
  historique d'envoi.
- **FB6 — Annulation** d'un reçu émis à tort : jamais de suppression ni de renumérotation ; reçu
  annulé conservé avec motif, nouveau reçu éventuel sous un nouveau numéro.
- **FB7 — État annuel** : nombre de reçus et montant total des dons ayant donné lieu à reçu, par
  année civile (utile aux déclarations de l'organisme).

### 5.3 Budget, projets et prévisionnel (lot C, après le lot A)

- **FC1 — Projets / activités** (**axe analytique unique**, OA11) : liste par instance (nom, période,
  responsable, actif / archivé) ; affectation d'une ligne d'écriture, d'une ligne de facture
  d'achat ou d'une transaction catégorisée par règle à un projet ; ventilation possible d'une ligne
  sur plusieurs projets (pourcentage ou montant).
- **FC2 — Budget** par exercice, par compte (ou regroupement de comptes du CdR) et optionnellement
  par projet ; saisie mensuelle ou annuelle répartie ; copie du budget ou du réalisé N-1 comme base.
- **FC3 — Suivi budgétaire** : prévu / réalisé / écart (montant et %) par poste et par projet, à
  date ; graphique ; export tableur ; intégré au tableau de bord.
- **FC4 — Compte de résultat par projet** (et rapport pour un financeur : dépenses et recettes d'un
  projet sur une période, avec pièces).
- **FC5 — Prévisionnel de trésorerie** **par mois sur 12 mois glissants** (OA12) : soldes actuels
  des comptes bancaires et de caisse + encaissements / décaissements attendus (factures d'achat non
  réglées avec échéance, factures clients non réglées, budget restant à réaliser, saisies
  manuelles) ; alerte de trésorerie négative.
- **FC6 — Règles et projets** : une règle de catégorisation peut fixer le projet.

### 5.4 Comptabilité simplifiée (lot D)

Pour les petites associations sans obligation de comptabilité en partie double (OA7).

- **FD1 — Mode par instance** choisi à la création (ou plus tard) : « comptabilité simplifiée »
  (recettes / dépenses) ou « partie double » ; le mode pilote les menus affichés, comme le plan
  comptable aujourd'hui.
- **FD2 — Saisie recettes / dépenses** : date, libellé, montant, compte bancaire ou caisse,
  **catégorie** (liste simple issue du plan associatif : cotisations, dons, subventions, ventes,
  achats, locations…), tiers, projet (lot C), pièce jointe. Pas de vocabulaire débit / crédit.
- **FD3 — Banque et caisse** : import OFX / Qonto, rapprochement et règles disponibles dans ce mode,
  une transaction devenant directement une recette ou une dépense catégorisée. La **caisse**
  (espèces) est un compte de trésorerie à part entière (**53x**, OA14) : solde, mouvements, virements
  banque ↔ caisse (dépôt d'espèces) sans effet sur les recettes et dépenses. Dans les deux modes.
- **FD4 — États** : **compte de résultat simplifié** (recettes / dépenses par catégorie, N / N-1),
  **situation de trésorerie** (soldes des comptes et caisses en début et fin d'exercice), budget
  (lot C) ; adhésions, relances et rapport d'activité inchangés.
- **FD5 — Passage en partie double** sans ressaisie : les opérations saisies en mode simplifié
  restent exploitables (reprise en écritures) si l'association doit passer en partie double
  (subventions importantes, salariés, seuils).
- **FD6 — Obligations** (OA14) : **pas de FEC ni d'assistant de clôture complète** en mode
  simplifié ; un exercice se verrouille simplement. Reçus fiscaux (lot B) et budget / projets
  (lot C) restent disponibles. Le passage en partie double (FD5) rend FEC et clôture accessibles.

## 6. Exigences non fonctionnelles

- **NA1 — Conformité et traçabilité** : FEC conforme et reproductible ; reçus numérotés sans trou ;
  aucune modification possible d'un exercice clôturé définitivement ni d'un reçu émis (annulation
  seulement) ; journal des opérations de clôture.
- **NA2 — Multi-instance** : tout est paramétré par instance (identité, éligibilité aux reçus,
  projets, budgets) ; plan asso et plan SCI (reçus et fonds dédiés non proposés pour une SCI).
- **NA3 — Prise en main** (cible élargie, OA3) : assistants pas à pas pour la clôture et
  l'activation des reçus ; documentation utilisateur dans `doc/` ; libellés en français clair.
- **NA4 — Cohérence avec l'existant** : SPA React + Mantine (charte Lyvre), API `/api/v1`, exports
  et PDF côté serveur, tests pytest / Vitest / E2E, notifications pour les traitements longs
  (génération en lot des reçus, archive expert-comptable).
- **NA5 — Données personnelles** : adresses des donateurs (RGPD) : accès limité, conservation
  alignée sur les obligations fiscales, export / suppression d'un donateur sans casser la
  numérotation.

## 7. Récits utilisateur et critères d'acceptation

**US-A1 — Transmettre les comptes.** Le trésorier (ou l'expert-comptable) exporte le FEC.
- [ ] FEC d'un exercice de test accepté par l'outil de contrôle « Test Compta Demat » de la DGFiP
      (ou validateur équivalent) ; totaux débit = crédit = balance.

**US-A3 — Donner accès à l'expert-comptable.** L'administrateur invite l'expert-comptable sur son
instance.
- [ ] L'expert-comptable ne voit que les instances attribuées ; il consulte écritures, états et
      pièces, exporte le FEC ; toute modification lui est refusée (interface et API).
- [ ] Accès révocable ; les utilisateurs existants gardent leurs accès après la mise en place.

**US-A2 — Clôturer.** Le trésorier clôture N et ouvre N+1 avec l'assistant.
- [ ] Les 8 étapes s'enchaînent, chacune avec son état ; l'assistant se reprend là où on l'a laissé.
- [ ] Contrôles avec liens ; écritures d'inventaire saisies, extournées automatiquement en N+1.
- [ ] Clôture provisoire puis définitive (administrateur seulement).
- [ ] À-nouveaux générés dans N+1 : bilan d'ouverture N+1 = bilan de clôture N.
- [ ] Affectation du résultat saisie après l'AG ; écriture générée et datée.

**US-B1 — Émettre les reçus.** Une association éligible émet les reçus annuels de ses donateurs,
particuliers et entreprises.
- [ ] Activation avec déclaration d'éligibilité ; reçus PDF conformes au modèle CERFA ; numéros
      continus ; envoi par email ; annulation tracée sans renumérotation.
- [ ] État annuel (nombre, montant) cohérent avec les reçus émis.

**US-C1 — Suivre le budget.** Le bureau saisit le budget N par poste et par projet et suit
l'exécution.
- [ ] Prévu / réalisé / écart par poste et par projet, à date, export tableur.
- [ ] CdR d'un projet sur une période, pour un financeur.

**US-D1 — Tenir une comptabilité simplifiée.** Une petite association saisit recettes et
dépenses par catégorie, importe son relevé et édite son compte de résultat simplifié.
- [ ] Aucun terme débit / crédit dans ce mode ; états recettes / dépenses et trésorerie N / N-1.
- [ ] Passage en partie double possible sans ressaisie.

**US-C2 — Anticiper la trésorerie.** Le trésorier voit le solde prévisionnel mois par mois sur
12 mois (banques et caisse).
- [ ] Prise en compte des factures non réglées, du budget restant et des saisies manuelles ;
      alerte si solde prévu négatif.

## 8. Risques et points d'attention

- **Conformité légale** : formats FEC et reçus fixés par les textes (LPF, CGI, modèle CERFA) ;
  vérifier les versions en vigueur au moment de l'implémentation et faire relire par l'expert-
  comptable. L'éligibilité aux reçus engage la structure (amende fiscale en cas de reçus indus).
- **Rôles et accès** (lot A, OA6) : passer de « tout utilisateur voit toutes les instances » à des
  accès par instance touche la session, le choix d'instance, l'API (contrôle de chaque écriture) et
  la palette de recherche ; une reprise des accès existants est nécessaire pour ne bloquer personne.
- **Comptabilité simplifiée** (lot D) : deux modes à maintenir côte à côte ; la reprise vers la
  partie double (FD5) conditionne la façon de stocker les opérations simplifiées.
- **Analytique** : ajouter un axe projet aux lignes touche la saisie, les règles, les factures
  d'achat et les états ; garder un modèle simple (un axe) pour commencer.
- **Données existantes** : exercices déjà « clôturés » (verrou seul) à reprendre dans le nouveau
  cycle (clôture provisoire) sans écritures d'à-nouveaux rétroactives non voulues.

## 9. Questions ouvertes

Toutes tranchées le 2026-10-22 (OA1–OA14). Points à préciser au design, sans décision
utilisateur attendue :

- format exact du FEC retenu (séparateur, encodage) et vérification avec « Test Compta Demat » ;
- modèles CERFA en vigueur (particuliers, entreprises) au moment de l'implémentation ;
- modèle de données de l'axe projet et du mode simplifié permettant le passage en partie double
  sans ressaisie (FD5) ;
- reprise des exercices déjà « clôturés » (verrou seul) et des accès utilisateurs existants.
