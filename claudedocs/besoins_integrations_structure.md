# Besoins — intégrations selon le type de structure

> Statut : expression de besoins (`/sc:brainstorm`, 23/10/2026). Pas de conception ni de code.
> Étape suivante : `/sc:design`. Décisions du 23/10/2026 au § 3 (questions du § 8 tranchées le même jour).

## 1. Objectif

Les intégrations doivent correspondre à la structure et ne se manifester que si elles servent :

1. ne proposer que les intégrations utiles au type de structure (pas de HelloAsso, Google
   Analytics ni Facebook pour une SCI) ;
2. reconnaître chaque service d'un coup d'œil (logo) ;
3. faire taire une intégration désactivée : ni alerte, ni notification, ni bouton qui en dépend ;
4. proposer l'activation des intégrations recommandées (Qonto pour une SCI) au lieu d'afficher
   des erreurs « non configurée » ;
5. prévenir quand une action courante a besoin d'une intégration désactivée (envoyer un email
   sans SMTP).

## 2. Constat (code au 23/10/2026)

| Élément | Aujourd'hui |
|---|---|
| Services | 7 : Stancer, Odoo, HelloAsso, SMTP, GA4, Facebook, Qonto (`external_config.SERVICE_KEYS`) |
| Type de structure | `Instance.chart` : `asso` (association loi 1901) ou `sci` |
| Page Intégrations | Les 7 services pour toutes les instances, carte = nom, statut, description, dernier test ; pas de logo |
| État par défaut | **Activée** quand aucun interrupteur n'est enregistré (`is_enabled` : ligne absente = activée) |
| Repli `.env` | Les valeurs du `.env` (SMTP, HelloAsso, Odoo, Stancer présents) valent pour **toutes** les instances sans réglage en base |
| Bandeau `IntegrationNotice` | Affiché si l'intégration est désactivée **ou** non configurée : Achats, Transactions (Qonto), Versements (Stancer), Adhérents, Relances, Tiers (HelloAsso, SMTP), Odoo |
| Boutons dépendants | Grisés quand l'intégration est indisponible (« Synchroniser les factures Qonto », « Mettre à jour la fiche Odoo », etc.) |
| Notifications | Fin des tâches en arrière-plan (synchronisation Qonto, factures Qonto, Stancer, reçus) |
| Menus | Versements Stancer, Odoo, Adhérents, Reçus fiscaux : association seulement. Visibilité & Impact : toutes structures |

Conséquence actuelle : une SCI voit HelloAsso, GA4 et Facebook ; une instance sans Qonto voit
« Qonto indisponible » sur ses écrans d'achats et de banque.

## 3. Décisions prises (23/10/2026)

| # | Sujet | Décision |
|---|---|---|
| D1 | Intégrations par structure | Association seulement : **HelloAsso, Google Analytics (GA4), Facebook**. Toutes structures : **Qonto, SMTP, Stancer, Odoo** |
| D2 | État par défaut | **Désactivée**, et l'activation est **proposée** pour les intégrations recommandées selon la structure |
| D3 | Où proposer | **Page Intégrations**, **tableau de bord** (administrateur), **création d'instance** |
| D4 | Intégration désactivée | Ce qui n'existe que par elle est **masqué** (boutons, colonnes, filtres, bandeaux, notifications) ; les données déjà importées restent visibles |
| D5 | Repli `.env` (Q1) | **Développement seulement.** En production, les réglages de l'instance font foi. Un service utilisé pour toutes les instances (ex. envoi des emails de la plateforme) n'est pas une intégration |
| D6 | Recommandées pour une association (Q2) | **HelloAsso** |
| D7 | Notifications déjà reçues (Q3) | **Conservées** dans l'historique |
| D8 | Menus Stancer et Odoo (Q4) | Affichés **dès que l'intégration est activée**, quelle que soit la structure |
| D9 | Tuiles du tableau de bord (Q5) | « Versements Stancer », « Factures Odoo » **masquées** si l'intégration est désactivée |
| D10 | Activée mais non configurée (Q6) | Bandeau « non configurée » sur les écrans métier (F5.3) |
| D11 | Logos (Q7) | Fichiers **officiels** des marques, stockés dans l'application |

## 4. Exigences fonctionnelles

### F1 — Intégrations selon la structure

- F1.1 Chaque intégration déclare les structures auxquelles elle s'applique (D1).
- F1.2 La page Intégrations ne liste que les intégrations applicables à l'instance. L'adresse
  d'une intégration non applicable répond « introuvable ».
- F1.3 Une intégration non applicable est traitée comme désactivée partout (API, tâches,
  écrans), même si des réglages existent en base ou dans le `.env`.
- F1.5 Menus « Versements Stancer » et « Odoo » : visibles quand l'intégration est activée, quelle
  que soit la structure ; masqués sinon (D8).

### F0 — Réglages de l'instance seulement (D5)

- F0.1 Hors développement, une intégration n'utilise que les réglages enregistrés dans la base de
  l'instance ; le repli `.env` est ignoré (fiche : plus de mention « repli .env »).
- F0.2 En développement, le repli `.env` reste possible pour ne pas ressaisir les réglages.
- F0.3 Un service commun à toutes les instances (emails de la plateforme : mot de passe oublié,
  invitations…) relève de la configuration de l'application, pas des intégrations.
- F1.4 Changer la structure d'une instance (si un jour possible) ne supprime aucun réglage.

### F2 — Logos

- F2.1 Le logo du service s'affiche **à gauche** dans le bandeau de chaque intégration : carte de
  la page Intégrations et en-tête de la fiche.
- F2.2 SMTP n'a pas de marque : icône générique (enveloppe).
- F2.3 Logos servis par l'application (aucun chargement depuis un site tiers), lisibles en
  thème clair et sombre, avec un texte alternatif (nom du service).
- F2.4 Une intégration désactivée garde son logo (pas d'effet grisé imposé ; à voir en conception).

### F3 — Une intégration désactivée ne se manifeste pas

Pour une intégration désactivée (ou non applicable) :

- F3.1 Aucun bandeau `IntegrationNotice`, aucun message d'erreur ou d'information la concernant
  (ex. Factures d'achat : ni « Qonto indisponible », ni « factures à partir du… / dernière
  synchronisation », ni compteur « modifiées dans Qonto, à revoir »).
- F3.2 Les boutons, cases, colonnes et filtres qui n'existent que pour elle sont **masqués** :
  « Synchroniser les factures Qonto », « Synchroniser Qonto », colonne et filtre « Statut Qonto »,
  case et bouton « Envoyer à Qonto », « Comptes Qonto », « Mettre à jour la fiche Odoo », etc.
- F3.3 Aucune notification nouvelle n'est produite pour elle ; les notifications déjà reçues
  restent lisibles dans l'historique (D7).
- F3.6 Tableau de bord : les tuiles fondées sur une seule intégration (« Versements Stancer »,
  « Factures Odoo ») sont masquées (D9).
- F3.4 Les données déjà importées restent visibles et utilisables : factures venues de Qonto,
  versements Stancer, commandes HelloAsso d'un tiers. Leur origine reste affichée (ex. « Qonto »
  sur une facture), sans action vers le service.
- F3.5 Aucune tâche automatique ou appel au service n'a lieu (déjà le cas côté clients API ; à
  vérifier pour chaque tâche).

### F4 — Proposer l'activation

- F4.1 Recommandées par structure : SCI → **Qonto** ; association → **HelloAsso** (D6).
- F4.2 **Page Intégrations** : les intégrations recommandées non activées portent un badge
  « Recommandée » et un bouton **Activer** qui mène à la fiche (configuration puis test).
- F4.3 **Tableau de bord** (administrateur de l'instance seulement) : encart « Activez Qonto pour
  synchroniser vos comptes et factures » tant que l'intégration recommandée n'est ni activée ni
  écartée ; action **Configurer** et **Ne plus proposer** (mémorisé pour l'instance).
- F4.4 **Création d'instance** : cases des intégrations applicables, pré-cochées selon la
  structure. Cochée = activée dès la création, puis à configurer (l'intégration activée non
  configurée affiche alors son bandeau « non configurée », voir F5.3).
- F4.5 Aucun bandeau d'erreur sur les écrans métier pour une intégration seulement proposée.

### F5 — Prévenir quand une action a besoin d'une intégration

Distinction : une **fonction propre** à l'intégration (synchroniser Qonto) est masquée (F3) ; une
**fonction courante** qui a besoin d'une intégration pour s'exécuter reste visible et prévient.

- F5.1 Fonctions courantes concernées (au moins) : envoyer des relances d'adhésion par email,
  envoyer les reçus fiscaux par email (SMTP).
- F5.2 Si l'intégration est désactivée : le bouton reste visible ; un message dit que l'action a
  besoin de l'intégration, par exemple « L'envoi par email nécessite l'intégration SMTP,
  désactivée. » Administrateur : lien **Activer l'intégration** ; autres rôles : « Contactez un
  administrateur ». L'action n'est pas lancée.
- F5.3 Si l'intégration est activée mais non configurée ou en erreur : comportement actuel
  conservé (bandeau `IntegrationNotice` et bouton grisé), car l'administrateur a choisi de s'en
  servir.
- F5.4 Le serveur refuse toujours l'action (409) avec le même message, si l'écran est contourné.

### F6 — Reprise des instances existantes

- F6.1 Une intégration **paramétrée en base** (champs requis dans `external_connections`) et non
  désactivée reste **activée** (ex. Qonto de la SCI).
- F6.2 Une intégration sans paramètres en base passe **désactivée**, y compris si le `.env` la
  rendait « configurée » (D5). Les valeurs du `.env` utilisées en production par une instance
  sont à saisir dans sa fiche avant la mise à jour (liste fournie à la migration).
- F6.3 Une intégration explicitement désactivée le reste.
- F6.4 La reprise est appliquée par migration ; elle ne touche aucune base réelle sans accord
  (règle du projet).

## 5. Exigences non fonctionnelles

- N1 Aucun appel réseau à un service désactivé ou non applicable.
- N2 Aucun secret exposé par les nouveaux écrans (règles actuelles inchangées).
- N3 Accessibilité : logo avec texte alternatif, contraste en thème sombre, encart du tableau de
  bord fermable au clavier.
- N4 Les tests existants des bandeaux et boutons grisés sont adaptés ; nouveaux tests sur la
  liste par structure, le masquage, la proposition et le message « nécessaire ».

## 6. Récits utilisateur et critères d'acceptation

**U1 — Liste par structure.** En tant qu'administrateur d'une SCI, je ne vois que Qonto, SMTP,
Stancer et Odoo dans Intégrations.
- `GET /integrations` d'une SCI ne contient ni `helloasso`, ni `ga4`, ni `facebook`.
- `/configuration/integrations/helloasso` sur une SCI → introuvable.

**U2 — Logos.** Chaque carte et l'en-tête de chaque fiche montrent le logo à gauche du nom.

**U3 — Silence d'une intégration désactivée.** Sur une instance où Qonto est désactivée, la page
Factures d'achat n'affiche ni bandeau, ni bouton de synchronisation, ni colonne/filtre « Statut
Qonto », ni case « Envoyer à Qonto » à la saisie ; les factures déjà importées de Qonto restent
listées.

**U4 — Proposition.** Une nouvelle SCI a Qonto pré-cochée à la création ; si elle est décochée,
l'administrateur voit l'encart Qonto sur le tableau de bord et le badge « Recommandée » sur la page
Intégrations ; « Ne plus proposer » retire l'encart, pas le badge.

**U5 — Action nécessitant une intégration.** SMTP désactivée : « Envoyer les relances » reste
visible ; au clic, message « nécessite l'intégration SMTP » avec lien d'activation pour
l'administrateur ; aucun email n'est envoyé ; l'API répond 409.

**U6 — Reprise.** Après migration : la SCI garde Qonto activée ; une association sans Qonto en base
n'affiche plus « Qonto indisponible ».

## 7. Hors périmètre

- Nouvelles intégrations ; changement des écrans de configuration des champs.
- Changer la structure d'une instance existante.

## 8. Questions ouvertes

Toutes tranchées le 23/10/2026 : voir D5 à D11 au § 3.
