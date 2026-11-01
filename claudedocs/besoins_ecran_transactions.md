# Besoins — Écran Banque › Transactions (lisibilité du tableau)

Demande du 01/11/2026 : améliorer le design de `/bank-accounts/<id>/transactions` (skill frontend-design) :
icônes à la place des types (`card`, `direct_debit`…), actions dans une colonne à part, statut remplacé par
des **feux** (vert, orange, rouge) avec le libellé en légende, badges (« Justificatif manquant »…) plus
visibles.

Statut : **besoins complets** (réponses du 01/11/2026, § 7 et § 8) — prêt pour `/sc:design`.

## 1. Constat (écran actuel, `TransactionsPage.tsx`)

Colonnes : Date · Libellé · Type · Montant · Tiers · Catégorie · Statut · Écriture.

- **Type** : code brut de la banque en texte gris (`card`, `direct_debit`, `transfer`, `income`,
  `qonto_fee` ; en OFX : `DEBIT`, `CHECK`, `XFER`…) — illisible pour un trésorier.
- **Libellé** : surchargé — texte, badge « Annulée », badge de justificatif, badges des factures liées,
  boutons « Créer la facture » et « Encaisser F-… » dans la même cellule ; les lignes n'ont pas la même
  hauteur et les actions se cherchent.
- **Statut** : deux badges texte (« Rapprochée » / « À rapprocher ») qui ne disent rien du justificatif
  ni des anomalies.
- **Badges** : petits, teinte claire sur fond clair (`paille-tint` / `paille-ink` pour « Justificatif
  manquant ») ; ils se confondent avec le texte du libellé.

Données de l'essai Ekylibre (123 transactions) : 101 carte, 14 prélèvements, 3 virements émis, 3 virements
reçus, 2 frais Qonto ; 101 non rapprochées, 104 sans justificatif alors qu'il est exigé.

## 2. Objectif

Lire une ligne d'un coup d'œil : **quoi** (type, libellé, tiers), **combien**, **où en est-elle**
(feu) et **que faire** (action) — chaque information à une place fixe.

## 3. Proposition (dans la charte Lyvre, sans nouvelle palette)

La charte est donnée : paper `#F6F4EE`, ink `#1E2421`, action `lichen #2F6B4F`, `paille #D9A441`
(jamais en texte sur paper), `brique #B5462F` réservé aux anomalies, `ardoise #3B5A78` info ; IBM Plex
Sans (UI), IBM Plex Mono (montants), icônes Lucide ; cartes bordées sans ombre. Le design reste dans ces
jetons : la nouveauté tient à **une** chose, le feu et sa légende, le reste devient plus calme.

### 3.1 Disposition

```
Légende-filtre (au-dessus du tableau)
 ● À jour 18   ● À traiter 101   ● Anomalie 4        ← pastilles cliquables = filtres, comptes à jour

┌──┬────────────┬──┬──────────────────────────────┬──────────────┬────────────┬───────────┬──────────────────┐
│● │ 21/07/2026 │⇄ │ BZIIIT — EKYLIBRE-SIA-26     │ bziiit       │ +3 600,00  │ OD-0043   │ [Encaisser F-…]  │
│  │            │  │ 📎 Justificatif manquant     │              │            │           │                  │
├──┼────────────┼──┼──────────────────────────────┼──────────────┼────────────┼───────────┼──────────────────┤
│● │ 26/07/2026 │▭ │ ANTHROPIC                    │ Anthropic    │   −90,00   │ AC-0011   │ [Créer la facture]│
│  │            │  │ 📎 Justificatif · Facture 6QZ…│              │            │           │                  │
└──┴────────────┴──┴──────────────────────────────┴──────────────┴────────────┴───────────┴──────────────────┘
 feu  date      type  libellé + pièces (ligne 2)    tiers          montant      écriture    actions
```

- **Feu** : première colonne étroite, pastille de 10 px ; libellé du feu en infobulle et en
  `aria-label` (la couleur ne porte jamais seule l'information).
- **Type** : icône Lucide 16 px, gris `ink-muted`, infobulle en français ; plus de texte.
- **Libellé** : ligne 1 le libellé de la banque ; ligne 2 les pièces (justificatif, factures liées,
  « Annulée ») — plus aucun bouton dans cette cellule.
- **Actions** : dernière colonne, alignée à droite, une action principale visible.
- **Montant** : inchangé (mono, à droite, « − »).

### 3.2 Icônes de type (Lucide)

| Code Qonto / OFX | Libellé (infobulle) | Icône |
|---|---|---|
| `card`, `POS` | Paiement par carte | `CreditCard` |
| `direct_debit`, `DIRECTDEBIT` | Prélèvement | `Repeat` |
| `transfer`, `XFER` (débit) | Virement émis | `ArrowUpRight` |
| `income`, `transfer` / `XFER` (crédit), `CREDIT` | Virement reçu | `ArrowDownLeft` |
| `qonto_fee`, `FEE`, `SRVCHG` | Frais bancaires | `Landmark` |
| `cheque`, `CHECK` | Chèque | `PenLine` |
| `atm`, `ATM`, `CASH` | Retrait d'espèces | `Banknote` |
| autre / vide | code brut en infobulle | `CircleDot` |

### 3.3 Feux (proposition à valider, Q1)

| Feu | Couleur | Libellé | Quand |
|---|---|---|---|
| Vert | `lichen` | À jour | rapprochée **et** justificatif présent ou non exigé |
| Orange | `paille` | À traiter | non rapprochée, **ou** rapprochée sans justificatif exigé, **ou** passée par une règle avec le tiers par défaut |
| Rouge | `brique` | Anomalie | annulée par la banque mais encore rapprochée, **ou** justificatif déclaré perdu |

Le motif précis (« À rapprocher », « Justificatif manquant », « Tiers par défaut »…) apparaît dans
l'infobulle du feu.

### 3.4 Badges plus visibles

- Badge de justificatif avec icône (`Paperclip` présent, `FileX` manquant, `FileQuestion` perdu), taille
  supérieure, texte en `ink` sur la teinte (contraste AA), bordure fine de la couleur du ton.
- Factures liées : badge `ardoise` avec icône `FileText`, cliquable.
- « Annulée » : badge `brique`, icône `Ban`.

## 4. Exigences fonctionnelles

- **E1** Icône de type avec infobulle française, correspondance Qonto et OFX, repli lisible pour un
  code inconnu.
- **E2** Colonne « Actions » : « Créer la facture », « Encaisser F-… », « Attribuer / Changer » le tiers
  (aujourd'hui dans la colonne Tiers), visibles selon les mêmes règles qu'aujourd'hui (droit d'écriture).
- **E3** Feu par ligne, calculé par le serveur (un seul endroit pour la règle), avec motif.
- **E4** Légende des feux au-dessus du tableau, avec le libellé de chaque couleur (et, selon Q2, les
  comptes et le filtre).
- **E5** Badges de pièces plus lisibles (icône, contraste AA), regroupés sous le libellé.
- **E6** Rien ne disparaît : catégorie, écriture, tiers, filtres et tri restent accessibles (colonnes
  masquables du `DataGrid`).

## 5. Exigences non fonctionnelles

- Accessibilité : couleur jamais seule (infobulle, `aria-label`, légende), contraste AA, focus visible,
  navigation au clavier dans les actions.
- Mode sombre : mêmes jetons (`--lv-*` sombres déjà définis).
- Mobile : feu, date, libellé, montant, actions ; les autres colonnes repliées.
- Performance : aucun appel en plus par ligne (feu et motif dans la réponse de la liste).

## 6. Questions ouvertes

1. **Règle des feux** : la table du § 3.3 te convient-elle ? En particulier, une transaction rapprochée
   **sans justificatif** est-elle orange (à traiter) ? Et « justificatif perdu » rouge, ou orange ?
2. **Légende** : simple légende, ou légende **cliquable** qui filtre le tableau avec le nombre de lignes
   par couleur (elle remplacerait alors en partie les filtres « À rapprocher » / « Justificatif manquant ») ?
3. **Actions** : toutes les actions visibles côte à côte, ou une action principale plus un menu « … » pour
   les autres ? Ajouter « Nouvelle écriture » et « Rapprocher » pour une ligne à rapprocher ?
4. **Justificatif** : badge sous le libellé (proposition), ou colonne dédiée avec une icône (trombone vert /
   barré orange) ?
5. **Colonnes** : garder « Catégorie » visible par défaut, ou la masquer (affichable) ?
6. **Périmètre** : appliquer les mêmes icônes, feux et badges à l'écran **Rapprochement** pour la cohérence ?

Suite : réponses, puis `/sc:design` (maquette précise et contrat de l'API) avant `/sc:implement`.

## 7. Décisions (réponses du 01/11/2026)

| # | Décision |
|---|---|
| D1 | Règle des feux du § 3.3 **validée** (rapprochée sans justificatif exigé = orange ; justificatif perdu = rouge) |
| D2 | Légende **cliquable** : nombre de lignes par couleur, un clic filtre le tableau (un second clic retire le filtre) |
| D3 | **Une action principale** visible + menu « … » pour les autres |
| D4 | Justificatif dans une **colonne dédiée avec icône** (et non plus en badge sous le libellé) |
| D5 | Colonne **Catégorie visible**, alimentée par la **catégorie Qonto** |
| D6 | Mêmes icônes, feux et pièces sur l'écran **Rapprochement** |

Conséquences :
- E5 devient : colonne « Pièce » étroite — `Paperclip` (lichen) justificatif présent, `PaperclipOff`
  (paille) manquant, `FileQuestion` (brique) perdu, vide si la banque ne gère pas les justificatifs (OFX) ;
  libellé en infobulle et `aria-label`. Sous le libellé ne restent que les factures liées et « Annulée ».
- E2 : action principale choisie par priorité (Encaisser F-… › Créer la facture › Attribuer le tiers ›
  Nouvelle écriture), les autres dans le menu « … » ; menu masqué s'il est vide, rien pour le comptable.
- E4 : la légende-filtre reprend le rôle des filtres « À rapprocher » / « Justificatif manquant » ; les
  filtres « Toutes » et « Débit sans facture » restent.

## 8. Catégorie Qonto (D5)

Constat : la synchronisation ne stocke aucune catégorie Qonto (`bank_transactions.category` est vide sur
l'essai ; ce champ sert aux **règles** de Lyvre). Lecture réelle de 3 transactions (01/11/2026) :

| Champ Qonto | Exemple | Remarque |
|---|---|---|
| `category` | `online_service`, `other_service` | code anglais, toujours présent |
| `cashflow_category.name` | « Dépenses liées aux technologies » | en français, choisi dans Qonto, parfois nul |
| `cashflow_subcategory.name` | « Licences logicielles », « Services d'hébergement web » | plus précis, parfois nul |

Proposition : stocker la catégorie Qonto **à part** (sans écraser la catégorie des règles), afficher dans la
colonne la sous-catégorie de trésorerie, sinon la catégorie de trésorerie, sinon le code traduit en français
(`online_service` → « Services en ligne ») ; la catégorie posée par une règle Lyvre reste prioritaire si elle
existe. Les transactions déjà importées se complètent à la prochaine synchronisation complète (date de début
reculée) ou par une reprise ponctuelle.

**D7 (01/11/2026)** : la **catégorie Lyvre** (posée par une règle) s'affiche d'abord ; à défaut, la
catégorie Qonto (sous-catégorie, catégorie de trésorerie, code traduit). L'origine Qonto se distingue
discrètement (infobulle « Catégorie Qonto »).

Suite : `/sc:design`.
