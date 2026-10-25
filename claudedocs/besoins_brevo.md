# Besoins — intégration Brevo : synchronisation des adhérents vers une liste de contacts

Brainstorm du 25/10/2026. Réservé aux associations (lot G1 : `is_association()`).

## Constat

### Côté Lyvre (Seconde Nature, production, lecture seule, agrégats)

- 331 adhérents (`entities.entity_type = ADHERENT`), **tous avec un e-mail**, aucun e-mail partagé par
  deux adhérents, aucun e-mail mal formé (majuscules, espaces). Les doublons ne viendront donc pas
  de Lyvre, mais de Brevo (contacts existants) et des changements d'e-mail dans le temps.
- Statut d'adhésion calculé par `services/membership_status.py` à partir des dernières adhésions
  HelloAsso et caisse : `ok` (à jour, HelloAsso), `asha` (caisse seulement), `?` (inconnu), date
  anniversaire. Le nom du tiers est un seul champ (`name`).
- Les intégrations sont déclarées par instance (`external_config` : réglages en base, interrupteur,
  test, structures concernées). HelloAsso est déjà réservée aux associations.

### Côté Brevo (documentation et appel réel)

- **L'e-mail est l'identifiant unique d'un contact.** Créer un contact dont l'e-mail existe renvoie
  400, sauf avec `updateEnabled: true` (création ou mise à jour en un appel, réponse 204).
- Identifiants possibles : e-mail, `ext_id` (identifiant fourni par l'appelant), SMS, WhatsApp.
  `forceMerge: true` fusionne deux contacts qui partagent un identifiant **en supprimant l'un des
  deux** (le plus ancien) : dangereux, à ne jamais activer d'office.
- Listes : ajout par `listIds`, retrait par `unlinkListIds`, sans supprimer le contact.
- Attributs : noms en majuscules (FNAME, LNAME…), **ils doivent exister dans le compte** ; une valeur
  au mauvais type est ignorée silencieusement.
- Désinscription : `emailBlacklisted` sur le contact. Rien n'oblige l'appelant à la respecter :
  c'est à Lyvre de ne jamais la défaire.
- **Le compte limite l'API aux adresses IP autorisées** : l'appel de lecture fait depuis le poste de
  développement a été refusé (401 « unrecognised IP address »). L'adresse du serveur Lyvre devra
  être autorisée dans Brevo (Sécurité › IP autorisées) ; Lyvre doit afficher ce cas clairement.
- Clés dans le `.env` de développement : `BREVO_API_KEY` (API v3, `xkeysib-…`) et `BREVO_MCP`
  (jeton du serveur MCP du compte, en-tête `Authorization: Bearer`). En production, comme les
  autres intégrations, la clé se saisit dans Configuration › Intégrations, pas dans le `.env`.
- Serveur MCP de **documentation** Brevo (`brevo-docs`, lecture seule, sans clé) ajouté à Claude Code
  (portée utilisateur) pour la conception. Le serveur MCP du **compte** n'est pas connecté (décision
  ci-dessous) : l'application utilise l'API REST, le MCP n'est qu'un outil de développement.

## Décisions de l'utilisateur

- **D1 — Périmètre** : tous les adhérents dans **une** liste Brevo, avec des attributs de statut et
  d'échéance pour segmenter dans Brevo. Un adhérent échu reste dans la liste.
- **D2 — Déclencheur** : bouton « Synchroniser avec Brevo » sur l'écran Adhérents, et passage
  automatique après chaque synchronisation HelloAsso.
- **D3 — Existant** : le compte Brevo contient déjà beaucoup d'adhérents. La première
  synchronisation doit les rattacher, sans doublon et sans défaire leurs désinscriptions.
- **D4 — Outils** : pas de connexion du serveur MCP du compte à Claude Code ; documentation (MCP
  `brevo-docs`) et API suffisent.

## Workflow proposé contre les doublons

Principe : **un adhérent Lyvre = un contact Brevo, lié une fois pour toutes**, retrouvé ensuite par
son identifiant Brevo et jamais recréé.

1. **Clé de rapprochement.** E-mail normalisé (minuscules, sans espaces) comme Brevo, plus un
   `ext_id` posé par Lyvre (`lyvre-<instance>-<id du tiers>`) : il survit à un changement d'e-mail.
   Lyvre garde de son côté l'identifiant Brevo du contact lié (et la date du dernier envoi).
2. **Rattachement initial, à blanc d'abord** (D3). Pour chaque adhérent : contact par `ext_id`, sinon
   par e-mail, sinon « à créer ». Rapport avant toute écriture : à créer, à rattacher, déjà liés,
   désinscrits, **conflits** (un `ext_id` Lyvre sur un contact dont l'e-mail ne correspond plus ; un
   e-mail déjà lié à un autre adhérent). L'utilisateur valide, puis Lyvre écrit.
3. **Mises à jour suivantes** par l'identifiant Brevo enregistré : attributs et appartenance à la
   liste. Un contact déjà à jour (empreinte du dernier envoi identique) n'est pas renvoyé.
4. **Changement d'e-mail dans Lyvre** : l'e-mail du contact lié est modifié (pas de nouveau contact).
   Si le nouvel e-mail appartient déjà à un autre contact Brevo : **conflit signalé, rien n'est
   fusionné** (`forceMerge` jamais activé par Lyvre) ; l'utilisateur tranche dans Brevo.
5. **Désinscriptions** : Lyvre n'envoie jamais `emailBlacklisted` ; un contact désinscrit reste
   désinscrit, il est seulement compté dans le rapport.
6. **Sortie** : un tiers qui n'est plus adhérent, supprimé, ou sans e-mail est retiré de la liste
   (`unlinkListIds`), jamais supprimé de Brevo.
7. **Sens unique** : Lyvre → Brevo. Les modifications faites dans Brevo (attributs Lyvre) sont
   écrasées au passage suivant ; les autres attributs du contact ne sont pas touchés.

## Exigences

### Intégration (Configuration › Intégrations)

- **R1** — Intégration « Brevo », proposée aux associations seulement, désactivée par défaut,
  silencieuse quand elle est désactivée (comme les autres).
- **R2** — Réglages : clé API (secrète, jamais renvoyée au navigateur), liste cible choisie parmi les
  listes du compte (liste déroulante lue dans Brevo), correspondance des attributs (voir R6).
- **R3** — Bouton « Tester » : lecture du compte et des listes. Messages clairs pour une clé invalide
  et pour une **adresse IP non autorisée** (avec la marche à suivre dans Brevo).

### Synchronisation

- **R4** — Tâche de fond (`sync_jobs`) avec progression, notification de fin et rapport : créés,
  mis à jour, inchangés, retirés de la liste, désinscrits, conflits, erreurs.
- **R5** — Aperçu à blanc obligatoire avant la **première** synchronisation (D3), puis disponible à
  tout moment.
- **R6** — Attributs envoyés : e-mail, nom (FNAME/LNAME si le nom se découpe, sinon un attribut de
  nom), statut d'adhésion, date anniversaire (échéance), dernière adhésion HelloAsso et caisse,
  bénévole. Les attributs absents du compte sont signalés au test (R3) ; à trancher en conception :
  Lyvre les crée ou l'utilisateur les crée.
- **R7** — Lancement : bouton sur l'écran Adhérents (D2) ; après chaque synchronisation HelloAsso,
  synchronisation des seuls adhérents modifiés.
- **R8** — Quota de l'API Brevo respecté (attente plutôt qu'échec) ; volumétrie actuelle : 331
  adhérents.

### Non fonctionnel

- **R9** — Données minimales : seuls les adhérents, seuls les champs de R6. Aucune donnée d'un tiers
  non adhérent.
- **R10** — Tests sans réseau (réponses Brevo simulées) ; la clé n'apparaît ni dans les journaux ni
  dans les réponses de l'API.
- **R11** — Expert-comptable : consultation du rapport seulement.

## Critères d'acceptation

- Une SCI ne voit pas l'intégration Brevo, et ses routes lui sont refusées.
- Première synchronisation sur un compte qui contient déjà les adhérents : **aucun contact créé
  pour un e-mail existant**, rapport de rattachement validé avant écriture.
- Deux synchronisations de suite : la seconde n'envoie rien (tout « inchangé »).
- Un adhérent change d'e-mail dans Lyvre : le même contact Brevo est mis à jour, aucun nouveau.
- Un contact désinscrit dans Brevo le reste après synchronisation.
- Un adhérent supprimé dans Lyvre sort de la liste ; le contact existe toujours dans Brevo.
- Clé invalide, IP non autorisée, Brevo injoignable : message clair, rien d'écrit à moitié.

## Questions ouvertes (pour la conception)

1. Attributs Brevo : Lyvre les crée-t-il au premier test, ou l'utilisateur les crée-t-il ? Lesquels
   existent déjà dans le compte (lecture impossible d'ici tant que l'IP n'est pas autorisée) ?
2. Le nom (`name`, un seul champ) se découpe-t-il en prénom et nom de façon fiable, ou garde-t-on
   les prénoms et noms des commandes HelloAsso quand ils existent ?
3. Appels unitaires (331 contacts, simple et traçable) ou import par lot de Brevo (plus rapide, mais
   asynchrone et rapproché par e-mail seulement) ?
4. Adresse IP de sortie du serveur Lyvre à autoriser dans Brevo, et IP du poste de développement
   (pour lire le compte pendant la conception).
