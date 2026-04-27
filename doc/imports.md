# Guide des imports

## Import bancaire OFX

### Qu'est-ce que l'OFX ?

OFX (Open Financial Exchange) est le format standard d'export de relevés bancaires. La plupart des banques françaises proposent l'export dans ce format (parfois appelé `.qfx`).

Il existe deux variantes :
- **OFX 1.x** (SGML) — format le plus courant pour les banques françaises (CIC, Crédit Agricole, BNP, etc.)
- **OFX 2.x** (XML) — format plus récent, parfois proposé par les banques en ligne

Les deux sont supportés par `ofxtools`.

### Prérequis

Avant d'importer un fichier OFX, il faut qu'un **compte bancaire** soit créé en base (table `bank_accounts`), lié à un compte GL `512xxx` du plan comptable.

Voir [Installation — Configuration des comptes bancaires](installation.md#configuration-des-comptes-bancaires).

### Procédure

1. Aller sur **Imports → Fichier OFX**
2. Sélectionner le compte bancaire dans la liste
3. Choisir le fichier `.ofx` ou `.qfx` exporté depuis votre banque
4. Cliquer sur **Importer**

### Résultat

L'import affiche :
- **Nouvelles transactions** : lignes insérées dans `bank_transactions`
- **Doublons ignorés** : transactions dont le `FITID` est déjà présent (réimport sans effet)
- **Erreurs** : lignes non parsées (format inattendu)

### Déduplication

Le champ `FITID` (Financial Transaction ID) est unique par transaction dans un fichier OFX. L'application utilise la contrainte `UNIQUE(bank_account_id, fitid)` pour garantir qu'un même relevé peut être réimporté plusieurs fois sans créer de doublons.

### Ce qui est importé

Pour chaque transaction OFX :

| Champ OFX | Champ base | Description |
|-----------|-----------|-------------|
| `<FITID>` | `fitid` | Identifiant unique |
| `<DTPOSTED>` | `transaction_date` | Date de l'opération |
| `<DTAVAIL>` | `value_date` | Date de valeur (optionnelle) |
| `<TRNAMT>` | `amount_cents` | Montant signé (négatif = débit) |
| `<MEMO>` ou `<NAME>` | `label` | Libellé de l'opération |
| `<TRNTYPE>` | `raw_type` | Type : DEBIT, CREDIT, INT, etc. |

### Important

**L'import OFX ne crée pas d'écritures comptables.** Les transactions atterrissent dans la table `bank_transactions` en attente de rapprochement. C'est le workflow correct : les relevés bancaires *confirment* les écritures, ils ne les *génèrent* pas.

---

## Import Odoo (lignes de vente)

### Format attendu

L'application attend un CSV correspondant à l'export **"Lignes de facturation"** d'Odoo (menu Comptabilité → Clients → Factures → Exporter).

### Colonnes attendues

| Colonne CSV Odoo | Obligatoire | Description |
|-----------------|-------------|-------------|
| `name` | oui | Numéro de facture (ex : `INV/2024/001`) |
| `invoice_date` | oui | Date de la facture |
| `partner_id/name` | non | Nom du client |
| `product_id/name` | non | Désignation du produit |
| `price_subtotal` | oui | Montant HT |
| `price_total` | oui | Montant TTC |
| `account_id/code` | non | Code compte comptable Odoo |

> Les colonnes supplémentaires sont ignorées. Les colonnes manquantes sont traitées comme vides.

### Encodage

Le fichier est lu en `UTF-8`. En cas d'erreur d'encodage, l'application bascule automatiquement sur `latin-1` (Windows-1252).

### Procédure

1. Dans Odoo : Comptabilité → Clients → Factures → sélectionner les factures → **Exporter** → choisir les colonnes listées ci-dessus → télécharger en CSV
2. Dans l'application : aller sur **Imports → Export Odoo**
3. Saisir un nom de lot (ou laisser vide pour un nom automatique)
4. Uploader le fichier CSV
5. Vérifier l'aperçu des 5 premières lignes
6. Cliquer sur **Voir toutes les lignes du lot** pour contrôler l'import complet

### Table de staging

Les lignes importées arrivent dans `odoo_import_lines` avec le statut **"En attente"**. Elles ne sont pas encore dans la comptabilité.

Cette étape permet :
- De contrôler le mapping des codes compte (`account_code`)
- De corriger d'éventuelles erreurs avant comptabilisation
- De regrouper plusieurs imports en lots distincts

### Comptabilisation

> La comptabilisation automatique (conversion des lignes Odoo en écritures `JournalEntry`) est prévue dans une prochaine version. En attendant, les lignes servent de référence pour la saisie manuelle dans le journal des ventes.

### Lots

Chaque import porte un **nom de lot** (ex : `odoo-2024-11`). La page de liste Odoo affiche tous les lots avec leur nombre de lignes. On peut consulter le détail de chaque lot.

### Exemple de fichier CSV Odoo valide

```csv
name,invoice_date,partner_id/name,product_id/name,price_subtotal,price_total,account_id/code
INV/2024/001,2024-01-15,Association Dupont,Cotisation annuelle,100.00,100.00,756
INV/2024/002,2024-01-20,Fondation ABC,Formation Python,800.00,960.00,706
INV/2024/002,2024-01-20,Fondation ABC,TVA 20%,0.00,160.00,44571
```

---

## Après les imports : le rapprochement

Une fois les transactions OFX importées et les écritures saisies (manuellement ou via Odoo), procéder au [rapprochement bancaire](reports.md#rapprochement-bancaire).
