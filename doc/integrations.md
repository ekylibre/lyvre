# Intégrations

Services externes qu'une instance peut utiliser : **Qonto** (banque, factures d'achat), **SMTP**
(emails), **Stancer** (paiements par carte), **Odoo** (caisse, factures clients), **Docuseal**
(signature électronique des baux), et pour une
association seulement **HelloAsso** (adhésions), **Google Analytics** et **Facebook** (Visibilité &
Impact).

Configuration › **Intégrations** (administrateur de l'instance) : une carte par intégration, avec
son logo, son état et son dernier test.

## Proposées selon la structure

| Intégration | Association | SCI / société |
|---|---|---|
| Qonto | ✔ | ✔ **recommandée** |
| SMTP (emails) | ✔ | ✔ |
| Stancer | ✔ | ✔ |
| Odoo | ✔ | ✔ |
| Docuseal | ✔ | ✔ |
| HelloAsso | ✔ **recommandée** | — |
| Google Analytics (GA4), Facebook (Page) | ✔ | — |

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
**Docuseal n'a pas de repli `.env`** : une copie de base servie en local ne peut pas envoyer de bail
à la signature tant que son intégration n'est pas configurée.

**Docuseal** : URL du serveur (auto-hébergé, par exemple `https://docuseal.seconde-nature.net`, ou
`https://api.docuseal.com` / `https://api.docuseal.eu`) et **clé d'API** (Docuseal › Paramètres ›
API). Chaque instance a les siens ; plusieurs instances peuvent viser le même serveur. Le test lit
la liste des modèles (lecture seule).

## Périmètre (Qonto)

La fiche de Qonto a trois cases : **Relevés de compte** (synchronisation des transactions),
**Achats** (factures fournisseurs, dépôt de pièces) et **Ventes** (émission des factures, avoirs et
devis par Qonto, synchronisation des ventes). Par défaut : relevés et achats. Une partie décochée se
comporte comme une intégration désactivée : ni bouton, ni bandeau, et une action qui en a besoin le
dit.

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
