# Besoins — Qonto, lot 1 : comptes et transactions bancaires

> Statut : besoins validés (brainstorm du 2026-10-20), questions tranchées (§8). Design : `design_qonto_transactions.md`.
> Source : note [`qonto.md`](qonto.md) (périmètre complet Qonto) ; ce document couvre le **premier lot**.

## 1. Contexte

La facturation électronique devient obligatoire ; l'association a choisi **Qonto** (API Business,
authentification par **clé API**, pas d'OAuth). La note `qonto.md` prévoit plusieurs lots : tiers,
ventes, achats, catalogue, relevés bancaires, stockage Google Drive. Ce lot traite les **comptes et
transactions bancaires**, base de tout le reste (paiements et encaissements sont faits dans Qonto puis
récupérés dans l'application).

| Constat (état au commit `e6b9978`) | Valeur |
|------------------------------------|--------|
| Comptes bancaires | `bank_accounts` (libellé, IBAN, compte GL) ; aucun lien Qonto |
| Transactions | `bank_transactions` : dédoublonnage par `(bank_account_id, fitid)`, montant signé en centimes, `reconciled` / `journal_line_id`, `entity_id`, `category` |
| Alimentation actuelle | Import OFX manuel (`ofx_importer`) ; compte 5121 (185 transactions, toutes rapprochées) — **ce n'est pas un compte Qonto** : aucun recouvrement à gérer |
| Catégorisation | Moteur de règles (`rules_engine.apply_rules`) : entité, compte, écriture + rapprochement automatiques |
| Intégrations | Écran `Configuration › Intégrations` (activation, test, dernière synchro) ; Qonto absent |
| Tiers | `entities` (`entity_type` dont `FOURNISSEUR`, `account_code`) |

**API Qonto utilisée** (vérifiée sur docs.qonto.com) : base `https://thirdparty.qonto.com/v2` ;
en-tête `Authorization: {identifiant}:{clé secrète}` (pas du Basic) ; `GET /organization` (comptes),
`GET /transactions` (filtres `bank_account_id`, `status[]`, `updated_at_from/to`, `settled_at_from/to`,
`sort_by`, pagination `page`/`per_page`, `page × per_page ≤ 10 000`) ; montants `amount_cents` positifs
+ `side` (`credit`/`debit`) ; statuts `pending`, `declined`, `completed`, `reversed` (seuls les
`completed` par défaut) ; limites 1 000 requêtes / 10 s et 10 000 / 10 min par IP, **429** au-delà,
blocage temporaire après 200 réponses 401 en une heure ; bac à sable via l'en-tête `X-Qonto-Staging-Token`.

## 2. Objectifs

- **O1** — Les transactions Qonto arrivent dans l'application **sans export / import de fichier**.
- **O2** — Elles sont **immédiatement exploitables** : rapprochement, règles de catégorisation, tiers.
- **O3** — Synchronisation **fiable et rejouable** : jamais de doublon, jamais de perte, reprise après échec.
- **O4** — Qonto est une **intégration comme les autres** (activation, test, dernière synchronisation).

## 3. Utilisateurs

| Profil | Usage | Attentes |
|--------|-------|----------|
| Administrateur | Ponctuel : clé API, rattachement des comptes | Configuration guidée, test immédiat |
| Trésorier | Fréquent : synchroniser, rapprocher, catégoriser | Un bouton, un résumé clair (nouvelles, mises à jour, annulées, erreurs) |

## 4. Besoins fonctionnels

### Q1 — Intégration Qonto
- Q1.1 Nouvelle intégration **Qonto** dans `Configuration › Intégrations` : identifiant (login de
  l'organisation), clé secrète (secret, jamais réaffichée), jeton de bac à sable optionnel.
- Q1.2 Test de fonctionnement : lecture de l'organisation (`GET /organization`) ; succès = nom de
  l'organisation et nombre de comptes ; erreurs traduites comme les autres intégrations (401 → identifiants refusés…).
- Q1.3 Dernière synchronisation affichée sur la page de détail de l'intégration.
- Q1.4 Désactivation : comme les autres intégrations, plus aucune synchronisation possible.

### Q2 — Rattachement des comptes
- Q2.1 Écran de rattachement listant les comptes Qonto (nom, IBAN, statut, principal ou non).
- Q2.2 Un compte Qonto dont l'IBAN correspond à un compte bancaire existant est **rattaché automatiquement**.
- Q2.3 Pour les autres, l'administrateur **rattache** à un compte bancaire existant ou **crée** un
  compte bancaire en choisissant le compte comptable (classe 512…). Il peut aussi **ignorer** un compte.
- Q2.4 Seuls les comptes rattachés sont synchronisés. Un compte Qonto fermé n'est plus synchronisé
  mais ses transactions restent.

### Q3 — Synchronisation des transactions
- Q3.1 Déclenchement **manuel** (bouton), depuis l'écran du compte bancaire et/ou une page Qonto ;
  pas de synchronisation planifiée dans ce lot.
- Q3.2 **Incrémentale** : seules les transactions créées ou modifiées depuis la dernière
  synchronisation réussie (par compte) sont lues ; la première synchronisation part d'une **date de
  début** choisie par l'administrateur au rattachement (défaut : début de l'exercice en cours).
- Q3.3 **Statuts** : seules les transactions **`completed`** deviennent des transactions bancaires.
  Une transaction déjà importée qui passe en **`reversed`** est **signalée** : elle ne peut plus être
  rapprochée ; si elle l'était, le rapprochement est **signalé à revoir** (pas défait automatiquement).
- Q3.4 **Dédoublonnage** par l'identifiant Qonto stable de la transaction : relancer une
  synchronisation ne crée jamais de doublon ; une transaction modifiée dans Qonto (libellé, note,
  pièces) est **mise à jour** sans toucher à son rapprochement ni à sa catégorisation.
- Q3.5 Données reprises : date (règlement), date de valeur si disponible, montant signé (débit négatif),
  libellé lisible (contrepartie + référence), type d'opération, contrepartie normalisée, note, référence.
- Q3.6 **Résumé** après synchronisation : nouvelles, mises à jour, annulées (`reversed`), ignorées,
  erreurs, par compte ; trace dans la **dernière synchronisation** de l'intégration.
- Q3.7 **Reprise** : en cas d'échec (réseau, 429, erreur API), la date de dernière synchronisation
  n'avance pas ; la synchronisation suivante reprend sans perte ni doublon.

### Q4 — Règles de catégorisation
- Q4.1 Les règles existantes sont **appliquées automatiquement** aux transactions nouvellement
  importées (comme une application manuelle depuis l'écran Règles) : entité, catégorie, écriture et
  rapprochement automatiques quand la règle a un compte.
- Q4.2 Les règles peuvent cibler les champs propres à Qonto **au moins via le libellé** (qui inclut
  la contrepartie) ; l'ajout de conditions sur le type d'opération est hors périmètre (question ouverte QO3).

### Q5 — Contreparties → fournisseurs
- Q5.1 Pour une transaction **débit** sans entité après application des règles, la contrepartie
  normalisée (`clean_counterparty_name`, à défaut `label`) est rapprochée d'une entité existante
  (nom identique, insensible à la casse et aux espaces) ; sinon elle est **proposée** comme fournisseur
  dans une liste à valider (créer, rattacher à une entité existante, ignorer) — décision QO4.
- Q5.2 Les transactions **crédit** sont liées à une entité existante si le nom correspond, **sans
  création** (clients, adhérents et donateurs viennent d'autres sources).
- Q5.3 Les types d'opération sans fournisseur réel (frais Qonto, rémunération du compte, rejets…)
  ne créent pas d'entité.
- Q5.4 La fiche fournisseur reste modifiable dans l'application (compte comptable, notes…) ; la
  synchronisation ne la modifie plus ensuite.

### Q6 — Pièces jointes (métadonnées)
- Q6.1 Pour chaque transaction : nombre de pièces jointes, pièce **requise** / **perdue**
  (`attachment_required`, `attachment_lost`), identifiants des pièces.
- Q6.2 Visible dans la liste des transactions (icône « justificatif présent / manquant ») et filtrable
  (« justificatif manquant »).
- Q6.3 Le **téléchargement et le stockage** des fichiers sont hors périmètre (lot Google Drive) : les
  URL Qonto expirent en 30 minutes et ne doivent pas être conservées.

## 5. Besoins non fonctionnels

- NF1 **Sécurité** : clé secrète jamais affichée ni journalisée (masquage existant des intégrations) ;
  lecture seule côté Qonto (aucune écriture dans ce lot).
- NF2 **Limites d'API** : respecter 1 000 req / 10 s ; sur **429**, attendre et réessayer (borné) ;
  ne pas multiplier les 401 (arrêt à la première réponse 401).
- NF3 **Volume** : la première synchronisation doit fonctionner au-delà de la limite de pagination
  (`page × per_page ≤ 10 000`) en découpant par période.
- NF4 **Durée** : une synchronisation courante (quelques dizaines de transactions) < 10 s ; une
  première synchronisation longue ne bloque pas l'interface (progression visible).
- NF5 **Idempotence et atomicité** : une transaction est soit importée complètement, soit pas ;
  la date de dernière synchronisation n'avance qu'après succès complet du compte.
- NF6 **Testabilité** : aucun appel réseau en test (client Qonto simulé) ; bac à sable Qonto pour
  l'essai manuel.
- NF7 **Multi-instance** : configuration, rattachements et curseurs de synchronisation propres à
  chaque instance (base tenant).

## 6. Récits utilisateur et critères d'acceptation

**US1 — Configurer Qonto.** L'admin saisit l'identifiant et la clé dans Intégrations › Qonto.
- [ ] Le test affiche le nom de l'organisation et le nombre de comptes.
- [ ] Une clé erronée donne « Identifiants refusés par Qonto (HTTP 401) ».

**US2 — Rattacher les comptes.** L'admin ouvre le rattachement.
- [ ] Le compte dont l'IBAN existe déjà est rattaché d'office.
- [ ] Un autre compte peut être créé (compte 512x choisi), rattaché à un compte existant ou ignoré.
- [ ] Une date de début de synchronisation est demandée (défaut : début de l'exercice).

**US3 — Synchroniser.** Le trésorier clique « Synchroniser Qonto ».
- [ ] Les transactions `completed` depuis la date de début apparaissent dans le compte bancaire.
- [ ] Relancer immédiatement : 0 nouvelle, 0 doublon.
- [ ] Une note modifiée dans Qonto est mise à jour à la synchronisation suivante, rapprochement intact.
- [ ] Le résumé (nouvelles / mises à jour / annulées / erreurs) s'affiche et apparaît comme dernière synchronisation.

**US4 — Exploiter.** Après synchronisation :
- [ ] Les règles ont catégorisé (et rapproché) les transactions qui correspondent.
- [ ] Les débits sans règle sont liés à un fournisseur existant, ou proposés à la validation ; les frais Qonto non.
- [ ] Les transactions sans justificatif requis sont repérables et filtrables.
- [ ] Les transactions apparaissent dans l'espace de rapprochement comme celles importées par OFX.

**US5 — Incidents.** Coupure réseau ou 429 en cours de synchronisation.
- [ ] Message clair, aucune transaction partielle ; la synchronisation suivante récupère tout.
- [ ] Une transaction `reversed` est signalée et n'est plus proposée au rapprochement.

## 7. Hors périmètre (lots suivants de `qonto.md`)

- Clients, ventes et factures Factur-X ; fournisseurs et factures d'achat ; catalogue produits.
- Téléchargement des justificatifs et stockage Google Drive.
- Relevés de compte PDF (`/statements`), webhooks, synchronisation planifiée.
- Écriture dans Qonto (étiquettes, notes, pièces jointes).
- Transactions `pending` / `declined`.

## 8. Questions ouvertes (à trancher en `/sc:design`)

1. **QO1 — Identifiant Qonto** : réutiliser `bank_transactions.fitid` (UUID Qonto) avec une colonne
   d'origine (`ofx` / `qonto`), ou une colonne dédiée `qonto_id` ? Où ranger les données propres à
   Qonto (type d'opération, pièces, statut) : colonnes ou table annexe ?
2. **QO2 — Synchronisation longue** : réutiliser `SyncJob` + fil d'exécution comme Stancer
   (progression, non bloquant) ou synchrone comme Odoo ?
3. **QO3 — Conditions de règles** : ajouter « type d'opération » / « contrepartie » aux conditions
   des règles maintenant ou plus tard ?
4. **QO4 — Création de fournisseurs** : automatique (Q5.1) ou proposée dans une liste à valider ?
   Risque : beaucoup de petits fournisseurs carte (restauration, transport…).
5. **QO5 — Transaction `reversed` déjà rapprochée** : signaler seulement (Q3.3), ou défaire le
   rapprochement et marquer l'écriture à revoir ?
6. **QO6 — Point d'entrée** : bouton sur la page du compte bancaire, sur une page « Qonto »
   dédiée, ou dans le menu Imports/Exports ?

### Réponses (2026-10-20)

| # | Décision |
|---|----------|
| QO1 | Identifiants Qonto dans **Intégrations** ; le lien avec le compte Qonto (identifiant, date de début, dernière synchronisation) dans les **informations du compte bancaire**. Stockage au niveau transaction : voir `design_qonto_transactions.md`. |
| QO2 | Synchronisation **en arrière-plan avec progression**. |
| QO3 | Conditions de règles supplémentaires : **plus tard**. |
| QO4 | Fournisseurs **proposés** dans une liste à valider (pas de création automatique). |
| QO5 | Transaction `reversed` déjà rapprochée : **signaler** seulement. |
| QO6 | Bouton de synchronisation dans la **vue du compte bancaire** concerné. |
