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

### Factures d'achat réglées par l'import

Après un import qui amène de nouvelles transactions, l'application cherche le paiement des
**factures d'achat saisies** comptabilisées et pas encore réglées : un débit unique du montant TTC
entre la date de facture − 5 jours et l'échéance + 60 jours règle la facture (écriture 401 / banque
rapprochée) ; le message de l'import indique le nombre de factures réglées. Plusieurs débits
possibles : choix sur la fiche de la facture. Voir [Factures d'achat](achats.md#factures-payées-hors-qonto-relevé-ofx).

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

## Synchronisation Qonto

Pour un compte Qonto, plus besoin de fichier OFX : les transactions sont lues par l'API (clé API,
lecture seule). Guide d'utilisation :

1. **Configurer** (admin) : Configuration › Intégrations › Qonto — identifiant (login), clé secrète ;
   le jeton de bac à sable est réservé aux essais. Le test affiche l'organisation et son nombre de comptes.
   Saisir les identifiants **dans l'instance concernée** : le repli `.env` vaut pour toutes les instances.
2. **Rattacher** (admin) : Comptes bancaires › Comptes Qonto. Chaque compte Qonto est rattaché à un
   compte bancaire existant (même IBAN proposé) ou créé sur un compte `512…`, avec une date de début.
3. **Synchroniser** : bouton « Synchroniser Qonto » dans la vue du compte bancaire. La synchro tourne en
   arrière-plan ; le résumé indique les transactions nouvelles, mises à jour, annulées et les erreurs.
   - Première synchro : toutes les transactions réglées depuis la date de début (lecture mois par mois).
   - Ensuite : seulement ce qui a changé dans Qonto (marge de 10 minutes, sans doublon).
   - Une synchro relancée ne crée jamais de doublon ; une note ou un justificatif ajouté dans Qonto
     est repris, mais jamais le montant, la date, le rapprochement, le tiers ni la catégorie.
   - Date : la date de règlement en heure de Paris. Montant : négatif pour un débit.
4. **Après la synchro**, automatiquement : règlement des transactions qui paient une **facture
   d'achat** comptabilisée (401 / banque, voir [Factures d'achat](achats.md)), puis règles de
   catégorisation sur les autres nouvelles transactions (le type d'opération Qonto est dans « Type »,
   utilisable par les règles), puis rattachement aux tiers de même nom.
5. **Contreparties à valider** : les débits restés sans tiers sont regroupés ; créer le fournisseur,
   rattacher à un tiers existant ou ignorer. Les frais Qonto, rémunérations et encaissements ne sont
   pas proposés.
6. **Contrôles** : filtres « Justificatif manquant » et « Débit sans facture » ; une transaction **annulée** par Qonto est
   marquée « Annulée » et ne peut plus être rapprochée ; si elle l'était déjà, un bandeau rouge le signale
   (rapprochement et écriture à revoir à la main).

## Après les imports : le rapprochement

Une fois les transactions importées (OFX ou Qonto) et les écritures saisies (manuellement ou via Odoo), procéder au [rapprochement bancaire](reports.md#rapprochement-bancaire).

---

## Reprise d'historique (FEC, tableur)

**Imports › Reprise d'historique** (administrateur de la structure, comptabilité en partie double).
Rien n'est importé tant qu'une anomalie subsiste (tout-ou-rien).

### FEC d'un autre logiciel

1. Déposer le fichier (tabulation ou barre verticale ; UTF-8, ISO-8859-15 ou Windows-1252 ;
   montants `Debit` / `Credit` ou `Montant` / `Sens`). L'analyse donne le nombre d'écritures, la
   période, les lettrages et les anomalies (écriture déséquilibrée, date illisible).
2. **Comptes** : un compte de même code est repris ; sinon il est créé, rattaché à son compte de
   regroupement. Les comptes **auxiliaires** (`CompAuxNum`) deviennent des sous-comptes de tiers
   (401NNN, 411NNN…) avec leur fiche de tiers. Chaque compte peut être mis en **correspondance**
   avec un compte existant ; les correspondances sont mémorisées pour les imports suivants.
3. **Que reprendre ?**
   - **Historique complet** : l'exercice (dates proposées d'après le fichier) est créé, ses
     écritures importées et **validées**, les lettrages repris, l'exercice clôturé
     provisoirement et verrouillé. Les à-nouveaux de l'exercice suivant se génèrent ensuite avec
     l'assistant de clôture. Refusé si l'exercice existe déjà avec des écritures.
   - **Soldes d'ouverture** : seuls les soldes de fin (classes 1 à 5) sont repris en à-nouveaux au
     premier jour de l'exercice choisi ; les comptes lettrables ligne par ligne (lignes non lettrées),
     le résultat en 120 / 129.

Contrôle : un FEC produit par Lyvre, réimporté, redonne la même balance et le même fichier.

### Écritures d'un tableur (CSV, XLSX)

Une ligne de fichier par ligne d'écriture. Les colonnes (date, journal, pièce, compte, libellé,
débit, crédit — ou un montant signé) sont reconnues d'après leur en-tête et se corrigent ; on peut
les **mémoriser** sous un nom (profil). Les lignes d'une même pièce (sinon même date et même
libellé) forment une écriture ; elles sont importées **en brouillard** dans l'exercice ouvert de
leur date (journal OD si la colonne manque).

---

## Reprise de la SCI Chênes Verts depuis Ekylibre (ponctuel, avant la mise en production)

Script : `scripts/import_ekylibre_sci.py` (besoins et conception : `claudedocs/besoins_import_ekylibre_sci.md`,
`claudedocs/design_import_ekylibre_sci.md`). Lit l'export du tenant Ekylibre (archive `.zip` : dump SQL et
pièces) sans PostgreSQL.

```bash
# Analyse à blanc : contrôles, correspondances de comptes et de tiers, rapport ; rien n'est écrit
.venv/bin/python scripts/import_ekylibre_sci.py EXPORT.zip --dry-run --report rapport.md
# Import dans une nouvelle instance (tout-ou-rien), à côté de la méta-base indiquée
.venv/bin/python scripts/import_ekylibre_sci.py EXPORT.zip --meta-url sqlite:////chemin/meta.db \
    [--until 2026-06-30] [--attachments-from 2026] [--replace] --report rapport.md
```

Repris : exercices 2025 et 2026 (jusqu'à `--until`), à-nouveaux, écritures (brouillard, validées si
confirmées dans Ekylibre ; TVA des achats intégrée à la charge), lettrages, registre et comptes courants
des associés, compte bancaire, relevés rapprochés, factures d'achat et règlements (banque, compte
courant d'associé), pièces de vente et encaissements, immobilisations (terrains reclassés en 211),
pièces des achats à partir de `--attachments-from`, fiche de la structure ; règles : identifiants des
fournisseurs lus dans les pièces, compte par défaut par fournisseur, règles bancaires (motif ≥ 6
caractères, ≥ 2 paiements, un seul fournisseur). Le rapport liste contrôles, corrections, règles et
remarques ; la balance de Lyvre est comparée compte par compte à celle d'Ekylibre (échec sinon).

