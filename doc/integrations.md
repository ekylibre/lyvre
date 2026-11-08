# Intégrations

Services externes qu'une instance peut utiliser : **Qonto** (banque, factures d'achat), **SMTP**
(emails), **Stancer** (paiements par carte), **Odoo** (caisse, factures clients), **Documenso**
(signature électronique des baux), **SUPER PDP** (plateforme agréée de facturation électronique), et pour une
association seulement **HelloAsso** (adhésions), **Brevo** (liste de contacts des adhérents),
**Google Analytics** et **Facebook** (Visibilité & Impact).

Configuration › **Intégrations** (administrateur de l'instance) : une carte par intégration, avec
son logo, son état et son dernier test.

## Proposées selon la structure

| Intégration | Association | SCI / société |
|---|---|---|
| Qonto | ✔ | ✔ **recommandée** |
| SMTP (emails) | ✔ | ✔ |
| Stancer | ✔ | ✔ |
| Odoo | ✔ | ✔ |
| Documenso | ✔ | ✔ |
| SUPER PDP | ✔ | ✔ |
| HelloAsso | ✔ **recommandée** | — |
| Google Analytics (GA4), Facebook (Page) | ✔ | — |
| Brevo | ✔ | — |

Une intégration d'une autre structure n'apparaît pas (son adresse répond « introuvable »).

## Activer, configurer, tester

Une intégration est **désactivée** tant que l'administrateur ne l'active pas. Sur sa fiche :

1. **Activer** ;
2. renseigner la **configuration** (un secret enregistré n'est jamais réaffiché) ;
3. **Enregistrer et tester**, ou **Tester maintenant**.

Les intégrations recommandées sont proposées :

- sur la page Intégrations (badge **Recommandée**, en tête de liste après les activées) ;
- sur le **tableau de bord** de l'administrateur, tant qu'elles ne sont ni activées ni écartées :
  **Configurer** ou **Ne plus proposer** ;
- à la **création d'une instance** (Administration › Instances) : cases pré-cochées selon le plan
  comptable.

Les réglages sont ceux **de l'instance**. Le fichier `.env` ne sert de repli qu'en développement
(`INTEGRATIONS_ENV_FALLBACK`) ; un service commun à toutes les instances n'est pas une intégration.
**Documenso n'a pas de repli `.env`** : une copie de base servie en local ne peut pas envoyer de bail
à la signature tant que son intégration n'est pas configurée.

**Documenso** (édition communautaire, auto-hébergée ; l'édition libre de Docuseal ne permet pas
d'envoyer un PDF par l'API) : URL du serveur et **jeton d'API** d'équipe (Documenso › Paramètres de
l'équipe › Jetons d'API, `api_…`). Chaque instance a les siens ; plusieurs instances peuvent viser le
même serveur. Le test lit la liste des envois (lecture seule). Installation du serveur :
[Signature électronique des baux : serveur Documenso](signature_documenso.md).

**Brevo** : **clé API** (Brevo › Paramètres › SMTP et API › Clés API, `xkeysib-…`) et **liste des
adhérents**, choisie parmi les listes du compte une fois la clé enregistrée. Le compte peut limiter
l'API à des **adresses IP autorisées** : le test l'indique (« L'adresse IP du serveur (…) n'est pas
autorisée dans Brevo ») ; ajouter l'adresse du serveur Lyvre dans Brevo › Sécurité › IP autorisées.
La fiche montre les attributs attendus par la synchronisation des adhérents : `PRENOM` et `NOM`
(complétés seulement s'ils sont vides dans Brevo), `DATE_ADH`, `LYVRE_STATUT`, `LYVRE_ECHEANCE`,
`LYVRE_BENEVOLE` (tenus par Lyvre). Les manquants se créent par le bouton « Créer les attributs
manquants », jamais automatiquement. Repli `.env` de développement : `BREVO_API_KEY`. Conception :
`claudedocs/design_brevo.md`.

**Synchronisation des adhérents vers Brevo** (`services/brevo_sync.py`, tâche `brevo_sync`) : un
adhérent = un contact Brevo, lié une fois pour toutes (table `brevo_links`) puis retrouvé par
l'identifiant du contact. Chaque passage lit tout le compte et classe chaque adhérent : rattacher
(contact existant, même e-mail ou `EXT_ID` Lyvre), créer, mettre à jour, inchangé (aucun appel),
conflit, retirer de la liste. Règles : jamais de fusion ni de doublon ; jamais de changement d'e-mail
d'un contact désinscrit (Brevo le réinscrirait) ; un adhérent sorti est retiré de la liste, jamais
supprimé ; les contacts de la liste inconnus de Lyvre ne sont pas touchés. La première
synchronisation commence par un **aperçu** sans écriture (`dry_run`).

Écran **Adhérents** › bouton **Brevo** : « Aperçu (sans rien écrire) », « Synchroniser avec Brevo »
(possible une fois un aperçu abouti), dernier passage. Le rapport (`/entities/members/brevo/<n°>`,
lien de la notification de fin) donne les compteurs (créés, rattachés, mis à jour, inchangés, retirés
de la liste), les **conflits à traiter** avec leur motif, les désinscrits (restés désinscrits), les
adhérents sans e-mail et les erreurs ; celui d'un aperçu propose « Synchroniser ». Après chaque
synchronisation HelloAsso, les adhérents touchés sont renvoyés vers Brevo en arrière-plan, dès que
la première synchronisation a eu lieu. API : `GET /api/v1/brevo/status`, `POST /api/v1/brevo/sync`
`{dry_run, entity_ids?}`, `GET /api/v1/brevo/sync/<n°>`.

## Périmètre (Qonto)

La fiche de Qonto a trois cases : **Relevés de compte** (synchronisation des transactions),
**Achats** (factures fournisseurs, dépôt de pièces) et **Ventes** (émission des factures, avoirs et
devis par Qonto, synchronisation des ventes). Par défaut : relevés et achats. Une partie décochée se
comporte comme une intégration désactivée : ni bouton, ni bandeau, et une action qui en a besoin le
dit.

## SUPER PDP et plateforme agréée unique

**SUPER PDP** est une plateforme agréée de facturation électronique : client OAuth « client credentials », dont
l'identifiant et le secret sont créés dans SUPER PDP, un par entreprise. Elle a deux parties :

- **Envoi des factures de vente** : bouton « Transmettre (SUPER PDP) » sur une facture ou un avoir émis, au PDF
  Factur-X conforme, jamais d'envoi automatique ; le dernier statut (`api:*`, `fr:200` à `fr:213`) s'affiche sur la
  pièce ;
- **Réception des factures d'achat** : bouton « Recevoir (SUPER PDP) » dans Achats, en tâche de fond ; chaque facture
  reçue est lue (Factur-X, CII, UBL) et devient une facture d'achat (badge « SUPER PDP »), fichier rangé avec les
  pièces. Une autofacture reçue est signalée, pas importée.

Une entreprise n'a **qu'une plateforme agréée à un instant donné** : SUPER PDP et la partie « Ventes » de Qonto
(émission Factur-X par Qonto) ne peuvent pas être actives ensemble ; l'activation de l'une, ou le cochage de la partie
concernée de l'autre, est refusé avec le motif (409). Qonto garde ses relevés et ses achats. Le test de la fiche
affiche l'entreprise, le mode (bac à sable ou production) et l'état des adresses de réception (une adresse « en
erreur » signale en général une portabilité depuis une autre plateforme). Conception : `claudedocs/design_superpdp.md`.

## Intégration désactivée

Rien de ce qui n'existe que par elle ne s'affiche : ni bandeau d'alerte, ni notification, ni bouton
de synchronisation, ni colonne ou filtre qui lui est propre. Par exemple, sans Qonto, les factures
d'achat n'ont ni « Synchroniser les factures Qonto », ni « Statut Qonto », ni « Envoyer à Qonto ».
Les menus **Versements Stancer** et **Odoo** n'apparaissent que si l'intégration est activée ; les
tuiles du tableau de bord qui en dépendent aussi.

Les **données déjà importées restent** visibles (factures venues de Qonto, versements Stancer,
commandes HelloAsso d'un adhérent), ainsi que les notifications déjà reçues.

## Action qui a besoin d'une intégration

Une action courante qui passe par une intégration reste visible. Si l'intégration est désactivée, le
clic n'exécute rien et ouvre une fenêtre, par exemple « L'envoi des relances par email nécessite
l'intégration SMTP (emails), désactivée. », avec **Activer l'intégration** pour l'administrateur
(« Contactez un administrateur » sinon). Concerné : relances d'adhésion et reçus fiscaux par email.

Une intégration **activée mais non configurée** (ou en erreur) affiche un bandeau sur les écrans qui
en dépendent et grise leurs boutons, avec le lien vers sa fiche.

## Mise en place sur une instance existante

À sa première ouverture, une instance active les intégrations de sa structure dont les réglages
requis sont **enregistrés dans sa base** (et que l'ancien interrupteur ne désactivait pas) ; les
autres sont désactivées. Une intégration qui fonctionnait grâce au `.env` passe donc désactivée :
avant la mise en production, lancer le constat (lecture seule, aucune valeur affichée)

```
.venv/bin/python scripts/integrations_report.py
```

puis saisir dans la fiche de chaque intégration les réglages signalés « fournis par le .env,
absents de la base », et l'activer.

L'activation est enregistrée avec l'instance (base des instances), pas dans sa sauvegarde : après
une restauration, vérifier la page Intégrations.
