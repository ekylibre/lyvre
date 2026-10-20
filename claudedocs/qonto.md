# Contexte

Nous voulons ajouter une fonctionnalité pour gérer la facturation electronique qui devient obligatoire au 01/09/2026.
Nous avons choisi d'integrer la solution Qonto via son api pour :
- créer des tiers
- créer des factures clients et gérer les encaissements
- créer des factures fournisseurs et gérer les paiements
- gérer un catalogue de produits et services
- récupérer les relevés de comptes bancaires

# Gestion des tiers - client

Utilise le modele 'entities' et enrichi le des attributs necessaires pour Qonto en regardant l'api : https://docs.qonto.com/api-reference/business-api/clients/create-a-client

# Gestion des ventes

On doit pouvoir récupérer les ventes et clients saisie sur qonto.

Créer de nouveaus modeles (et tables) 'sale' et 'sale_lines' pour les ventes qonto

https://docs.qonto.com/get-started/business-api/use-cases/sync-client-invoices

On doit pouvoir saisir des ventes dans l'app et les envoyer sur qonto

https://docs.qonto.com/get-started/business-api/use-cases/generate-factur-x-invoice


# Gestion des tiers - fournisseurs (suppliers)

On ne peut pas créer de fournisseurs via l'api qonto. Les fournisseurs seront enregistrés dans l'app via la récupération des factures d'achats ou des releves de comptes.

On pourra ensuite modifier la fiche fournisseurs 'entities' (compte comptable et autres champs hors du périmètre qonto)

# Gestion des achats

On doit pouvoir récupérer les achats et fournisseurs saisie sur qonto.

Créer de nouveaus modeles (et tables) 'purchase' et 'purchase_lines' pour les achats qonto

https://docs.qonto.com/get-started/business-api/use-cases/sync-supplier-invoices#initialize-the-sync-timestamp


# Gestion des releves de comptes bancaires

Réutilise les modeles 'bank_accounts' et 'bank_transcations' en ajoutant eventuellement des attributs necessaires a qonto

https://docs.qonto.com/get-started/business-api/use-cases/sync-transactions

# authentification

on stockera et activera l'intégration qonto dans l'écran /configuration/external-connections/

https://docs.qonto.com/get-started/business-api/authentication/api-key

# gestion du stockage des documents - Google Drive

Tu créera un intégration Google Drive pour stocker les documents issue de Qonto.

Tu ajouteras dans l'écran /configuration/external-connections/ les id pour Google Drive

Tu feras une arborescence logique pour les achats, ventes, paiements, etc par mois.

# contraintes

On utilisera que les méthodes disponible en mode api (pas de Oauth 2.0)

Qonto est maitre dans la génération des factures de ventes et d'achats.

Tous les paiements sont fait directement dans Qonto et récupérer ensuite dans l'application

# ressources

api endpoint selon la méthode d'authentification : https://docs.qonto.com/get-started/business-api/authentication/introduction#endpoints-access

idempotent request : https://docs.qonto.com/get-started/general/idempotent-requests

gestion des erreurs : https://docs.qonto.com/get-started/general/errors

rate limits : https://docs.qonto.com/get-started/general/rate-limitations




