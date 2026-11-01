# Conception — Écran Banque › Transactions (feux, icônes, pièces, actions, catégorie Qonto)

Besoins : `claudedocs/besoins_ecran_transactions.md` (E1–E6, décisions D1–D7).
Statut : **réalisé** (TX1–TX3, 01/11/2026). `PaperclipOff` absent de Lucide : justificatif manquant = `FileX`. Une transaction annulée n'attend pas de justificatif.

## 1. Direction visuelle (skill frontend-design, dans la charte Lyvre)

La charte est imposée (`reference_design_system_lyvre`) : pas de nouvelle palette ni de nouvelle police.

| Jeton | Valeur | Rôle ici |
|---|---|---|
| `paper` / `ink` | #F6F4EE / #1E2421 | fond, texte du libellé |
| `lichen` | #2F6B4F | feu vert, justificatif présent, action principale |
| `paille` | #D9A441 (texte : `paille-ink` #6B4A0E) | feu orange, justificatif manquant — jamais en texte sur paper |
| `brique` | #B5462F (texte : `brique-ink` #8A2F1C) | feu rouge, justificatif perdu, « Annulée » |
| `ardoise` | #3B5A78 | factures liées, focus |
| `ink-muted` | variable existante | icônes de type, catégorie Qonto |

Typographie inchangée : IBM Plex Sans (libellés), IBM Plex Mono (date, montant, référence d'écriture).

**Le seul élément marquant** : la **légende-filtre des feux** au-dessus du tableau — trois pastilles
larges (point coloré de 10 px, libellé, nombre en mono) qui se lisent comme un tableau de bord du compte
et filtrent d'un clic. Tout le reste s'efface : icônes grises de 16 px, pas de badge pour le type, une
seule action visible par ligne.

Revue contre les réflexes génériques : pas de pastilles « pill » colorées pour chaque statut (le feu est
un simple point, la couleur ne porte rien seule), pas de libellés en capitales, pas de puces numérotées,
pas de séparateurs à points médians dans les cellules (deux lignes à la place).

### Maquette

```
Qonto — Compte principal                                   [Retour] [Règles] [Rapprocher]
512 — Banque · FR76 …
┌ carte Qonto ────────────────────────────────────────────────────────────────────────────┐
┌ carte Relevés de compte ────────────────────────────────────────────────────────────────┐

 ┌────────────────┐ ┌──────────────────┐ ┌───────────────┐    [Toutes|Débit sans facture]  [Mois ▾]
 │ ● À jour    18 │ │ ● À traiter  101 │ │ ● Anomalie  4 │
 └────────────────┘ └──────────────────┘ └───────────────┘
   (pastille choisie : fond teinté + bordure de sa couleur ; un second clic retire le filtre)

 ●  Date        Type  Libellé                         Pièce  Tiers      Catégorie              Montant    Écriture  Actions
 ── ─────────── ───── ─────────────────────────────── ───── ────────── ────────────────────── ────────── ───────── ─────────────────────
 ●  21/07/2026   ↙   BZIIIT — EKYLIBRE-SIA-26          ⊘    bziiit     Ventes                 +3 600,00  —         [Encaisser F-2026-0001] ⋯
 ●  26/07/2026   ▭   ANTHROPIC                         📎   Anthropic  Licences logicielles   −90,00     AC-0011   [Créer la facture] ⋯
                     Facture 6QZE78GF-0005 (lien)
 ●  02/08/2026   ⟳   URSSAF                             ⊘   Tiers par  Cotisations            −512,00    BQ-0031   [Attribuer le tiers] ⋯
                                                            défaut
```

## 2. Serveur

### 2.1 Feu d'une transaction (`app/services/bank_lights.py`, nouveau)

`light(bt, *, rule_default_tiers: bool) -> tuple[str, list[str]]` — couleur et motifs, dans cet ordre :

| Couleur | Motifs (un ou plusieurs) |
|---|---|
| `red` | « Annulée par la banque mais encore rapprochée » (`is_reversed` et `reconciled`) ; « Justificatif perdu » (`attachment_lost`) |
| `orange` | « À rapprocher » (non rapprochée, non annulée) ; « Justificatif manquant » (exigé, absent) ; « Tiers par défaut » (passée par une règle, sans tiers) |
| `green` | « Rapprochée » ; « Annulée par la banque » (annulée, non rapprochée : rien à faire) |
| `green` (prioritaire, ajout du 01/11/2026) | « Facture liée et écriture passée » : facture d'achat ou de vente liée **et** écriture comptable — la facture tient lieu de justificatif ; seule « annulée encore rapprochée » reste rouge |

Le rouge l'emporte sur l'orange, l'orange sur le vert ; les motifs de la couleur retenue sont renvoyés
(les motifs orange s'ajoutent aux rouges pour l'infobulle). `LIGHT_LABELS = {"green": "À jour",
"orange": "À traiter", "red": "Anomalie"}`.

### 2.2 Liste des transactions (`GET /api/v1/bank-accounts/<id>/transactions`)

- Chaque transaction gagne `light` (`green|orange|red`), `light_reasons` (liste) et
  `category_display` (`{label, source: "lyvre"|"qonto"} | null`) — les champs existants restent
  (`category`, `attachment_status`, `rule_tiers`… : l'écran Rapprochement et les tests s'en servent).
- Nouveau paramètre `light=green|orange|red` : filtre appliqué **après** le calcul des feux.
- Nouvelle clé `lights: {green, orange, red}` : comptes des lignes **avant** le filtre `light` (mais
  après mois / statut / « Débit sans facture »), pour la légende.
- Paramètres `status`, `missing`, `no_invoice`, `month`, `sort` inchangés (compatibilité).
- Coût : calcul en Python sur les lignes déjà chargées (la liste n'est pas paginée côté serveur).

### 2.3 Catégorie Qonto (D5, D7)

- Migration : `bank_transactions` + `qonto_category` (texte 60, code `online_service`…),
  `qonto_cashflow_category` (texte 120), `qonto_cashflow_subcategory` (texte 120), tous nuls.
- `qonto_sync._fields` lit `category`, `cashflow_category.name`, `cashflow_subcategory.name`. Un code
  absent est stocké `""` (lu mais vide) : **nul = jamais lu**.
- **Reprise des transactions déjà importées** : si le compte a des transactions Qonto à `qonto_category`
  nul, la synchronisation relit toute la période depuis `qonto_sync_from` (comme quand la date de début
  recule) ; la comparaison champ par champ de `upsert_transaction` complète les catégories, sans doublon.
  Une seule fois : ensuite toutes les lignes ont une valeur (au pire `""`).
- Affichage (`category_display`) : catégorie Lyvre (règle) si présente → sinon sous-catégorie de
  trésorerie → sinon catégorie de trésorerie → sinon code traduit par `data/qonto_categories.json`
  (`online_service` → « Services en ligne » ; code inconnu : soulignés remplacés par des espaces,
  majuscule initiale) → sinon nul.

### 2.4 Écran Rapprochement

Même API (`status=unreconciled`) : `light`, `light_reasons` arrivent sans changement serveur.

## 3. Interface

### 3.1 Composants partagés (`frontend/src/components/bank/`)

| Composant | Rôle |
|---|---|
| `TransactionLight` | point de 10 px de la couleur du feu, `role="img"`, `aria-label` « À traiter : À rapprocher, Justificatif manquant », infobulle des motifs |
| `LightLegend` | trois boutons bascule (`aria-pressed`) point + libellé + nombre ; `value` / `onChange` ; mode statique (sans nombre ni clic) pour le Rapprochement |
| `TransactionTypeIcon` | icône Lucide 16 px `ink-muted` selon `raw_type` et le sens du montant, infobulle française, `aria-label` |
| `AttachmentIcon` | `Paperclip` (lichen) présent, `PaperclipOff` (paille) manquant, `FileQuestion` (brique) perdu, rien si `null` ; infobulle et `aria-label` |
| `RowActions` | action principale (bouton compact `light`) + `Menu` « … » (`ActionIcon`, `aria-label` « Autres actions ») ; rien si aucune action |

Correspondance des types (`lib/transactionTypes.ts`) : `card`/`POS` carte (`CreditCard`) ;
`direct_debit`/`DIRECTDEBIT` prélèvement (`Repeat`) ; `transfer`/`XFER`/`DEBIT`/`CREDIT` virement émis
(`ArrowUpRight`, débit) ou reçu (`ArrowDownLeft`, crédit) ; `income` virement reçu ; `qonto_fee`/`FEE`/
`SRVCHG` frais bancaires (`Landmark`) ; `cheque`/`CHECK` chèque (`PenLine`) ; `atm`/`ATM`/`CASH` retrait
(`Banknote`) ; autre : `CircleDot` avec le code brut en infobulle.

### 3.2 Banque › Transactions

- Colonnes : Feu (fixe) · Date · Type · Libellé · Pièce · Tiers · Catégorie · Montant · Écriture ·
  Actions (fixe). Type, Pièce, Tiers, Catégorie, Écriture masquables (préférences existantes du
  `DataGrid`). Colonnes « Statut » et texte du type supprimées.
- Libellé : ligne 1 le libellé ; ligne 2 (si besoin) factures liées (lien `ardoise` avec icône
  `FileText`), « Annulée » (`brique`, icône `Ban`), note Qonto en gris.
- Catégorie : `category_display.label` ; origine Qonto en `ink-muted` avec infobulle « Catégorie Qonto ».
- Tiers : nom ou « Tiers par défaut » ; le bouton « Attribuer / Changer » passe dans les actions.
- **Actions** (ordre de priorité, la première visible, les autres dans « … ») :
  1. « Encaisser F-… » (une entrée par facture proposée, confirmation inchangée) ;
  2. « Créer la facture » (`purchase_from_attachment`) ;
  3. « Attribuer le tiers » / « Changer le tiers » (`rule_tiers`) ;
  4. « Nouvelle écriture » (non rapprochée, non annulée) ;
  5. « Rapprocher » (non rapprochée : ouvre le Rapprochement sur ce compte).
  Rien pour le comptable (lecture seule).
- Filtres : légende-filtre (paramètre d'URL `light`) + `SegmentedControl` « Toutes » / « Débit sans
  facture » + mois. Les anciens filtres « À rapprocher » et « Justificatif manquant » disparaissent de
  l'écran (une ancienne URL `filter=unreconciled|missing` est lue comme `light=orange`).

### 3.3 Rapprochement

- Tableau : Feu · Date · Type · Libellé · Pièce · Montant ; badges de justificatif remplacés par
  l'icône de la colonne Pièce ; étoile de suggestion unique et « Annulée » conservés.
- `LightLegend` en mode statique sous le titre du tableau (libellés, sans filtre : la liste ne montre que
  le non-rapproché).

## 4. Tests

- Serveur : règle des feux (chaque motif, priorité rouge › orange › vert, annulée non rapprochée verte) ;
  liste : `light`, `light_reasons`, `lights` (comptes avant filtre), filtre `light` ; catégorie
  (`category_display` : Lyvre d'abord, sous-catégorie, catégorie, code traduit, inconnu) ; synchro :
  champs Qonto lus, `""` si absent, relecture complète déclenchée une fois par des catégories nulles.
- Interface (Vitest) : icône et infobulle de type (Qonto, OFX, inconnu, sens du virement) ; icône de
  pièce ; légende (comptes, clic → paramètre `light`, second clic → retrait) ; actions (priorité, menu,
  rien pour le comptable, confirmation d'encaissement conservée) ; Rapprochement (feu et pièce).
- Tests existants de `TransactionsPage` et `ReconcilePage` mis à jour (badges devenus icônes).

## 5. Découpage

| Lot | Contenu |
|---|---|
| **TX1** | Serveur : `bank_lights`, champs `light` / `light_reasons` / `lights` / filtre `light`, catégorie Qonto (migration, synchro, reprise unique, `category_display`, `data/qonto_categories.json`) |
| **TX2** | Banque › Transactions : composants partagés, légende-filtre, colonnes, actions principale + menu |
| **TX3** | Rapprochement : feu, type, pièce, légende statique |

Essai sur le 5003 après TX2 : légende attendue à peu près 18 / 101 / 4 (à confirmer avec les vraies
règles), catégories Qonto visibles après une synchronisation.

## 6. Points à valider

1. **Annulée non rapprochée = vert** (rien à faire) — ou gris neutre hors feux ?
2. **« Rapprocher » dans le menu** ouvre l'écran Rapprochement du compte (pas un rapprochement en ligne).
3. **Anciennes URL** `filter=unreconciled|missing` redirigées vers `light=orange`.
4. **Reprise des catégories** par une relecture complète automatique à la première synchronisation.
