# Clôturer un exercice

L'assistant de clôture guide le trésorier de la fin d'un exercice (N) jusqu'à l'ouverture du
suivant (N+1). On l'ouvre depuis **Compta › Exercices**, bouton **Clôturer…** (ou **Assistant**
pour un exercice déjà clôturé). L'assistant se reprend là où on l'a laissé ; chaque action est
inscrite dans son **historique**.

| Rôle | Ce qu'il peut faire |
|---|---|
| Trésorier | Étapes 1 à 5, clôture provisoire, étapes 7 et 8 |
| Administrateur de l'instance | Tout, plus la **clôture définitive** et la **réouverture** |
| Expert-comptable | Consulter l'assistant, télécharger le FEC ; aucune action |

## Avant la clôture (exercice ouvert)

Les étapes 1 à 5 se font dans l'ordre que l'on veut. Chacune est **faite**, ou **ignorée avec un
motif** (5 caractères au moins), qui reste visible dans la liste des étapes.

1. **Contrôles** — Recalculés à chaque affichage, avec un lien vers l'écran à corriger :
   transactions bancaires non rapprochées, écritures déséquilibrées ou datées hors exercice,
   factures d'achat non comptabilisées, comptes d'attente (47x) non soldés, banque ou caisse
   créditrice. Les factures non réglées sont une simple information (dettes au bilan). L'étape
   ne peut être « faite » qu'une fois les anomalies corrigées ; sinon, l'ignorer en expliquant.
2. **Écritures d'inventaire** — Charges à payer (408 / 4686), produits à recevoir (4687 / 418 /
   441), charges constatées d'avance (486), produits constatés d'avance (487). Passées en journal
   OD au dernier jour de l'exercice, elles seront **extournées** automatiquement à l'ouverture de
   N+1.
3. **Fonds dédiés** — Pour une subvention, une contribution d'un autre organisme ou un don
   affecté à un projet et non entièrement utilisé : créer la ressource (nature, montant reçu,
   compte de produit facultatif), puis **doter** la part non utilisée (689x / 19x). Les années
   suivantes, l'assistant présente le solde du fonds : enregistrer l'**utilisation** (19x /
   789x). Si la ressource finance un **projet** (Compta › Projets), l'assistant **propose** le
   montant d'après les charges du projet : dotation de la part non dépensée l'année de la
   ressource, utilisation à hauteur des dépenses du projet ensuite ; un clic l'enregistre. Sans
   ressource affectée, ignorer l'étape avec « sans objet ».
4. **Résultat** — Produits, charges et excédent ou déficit, écritures d'inventaire et de fonds
   dédiés comprises.
5. **Contrôle du FEC** — Le fichier des écritures comptables est produit « à blanc » et relu (18
   champs, équilibre, numérotation). Le SIREN doit être renseigné (Configuration › Structure).
   Les contrôles de l'étape 1 indiquent aussi le nombre d'écritures en brouillard (information).

## Clôture (étape 6)

- **Clôture provisoire** — Possible quand les étapes 1 à 5 sont faites ou ignorées. Les écritures
  sont verrouillées ; celles encore en brouillard sont **validées** (lot « Clôture provisoire »),
  numérotées **à la suite** des écritures déjà validées de leur journal (voir
  [Validation des écritures](saisie_rapprochement.md#validation-et-contrepassation)) : les numéros
  déjà attribués ne changent jamais ; l'exercice est verrouillé jusqu'à son dernier jour (voir
  [Verrouillage des périodes](saisie_rapprochement.md#verrouillage-des-périodes)). Le FEC est alors téléchargeable (liste des exercices, colonne
  FEC) pour l'expert-comptable.
- **Réouverture** (administrateur, motif obligatoire) — Pour corriger un oubli : le lot de
  validation de la clôture est annulé (ses écritures repassent en brouillard ; celles validées
  avant la clôture le restent), la date de verrouillage d'avant la clôture est rétablie, les à-nouveaux et extournes de N+1 supprimés (à regénérer).
  Impossible une fois le résultat affecté (annuler d'abord l'affectation), si N+1 est clôturé ou si
  ses à-nouveaux sont validés.
- **Clôture définitive** (administrateur) — Le FEC est figé avec son empreinte SHA-256.
  **Irréversible.**

Le contrôle officiel du FEC se fait avec l'outil « Test Compta Demat » de la DGFiP.

## Après la clôture

7. **Ouverture de l'exercice suivant** — L'assistant présente les à-nouveaux : soldes des comptes
   de bilan (classes 1 à 5) et résultat en 120 (excédent) ou 129 (déficit) — compte 12 pour une
   SCI. Un clic crée N+1 s'il n'existe pas (il doit commencer le lendemain de la clôture) et
   passe les à-nouveaux (journal AN, 1er jour) et les extournes. On peut les regénérer tant que le
   résultat n'est pas affecté.
8. **Affectation du résultat** — Souvent des mois plus tard, après l'assemblée : date de la
   décision (dans N+1), organe (assemblée générale, assemblée des associés…), répartition sur des
   comptes 10x (réserves), 11x (report à nouveau) ou 455x (comptes courants des associés d'une
   SCI). L'écriture est passée en OD à la date de la décision ; l'affectation peut être annulée.

**Après une comptabilité simplifiée.** Une association qui passe en partie double (Administration ›
Instances) garde ses opérations, déjà en partie double. Pour la première clôture en partie double,
les à-nouveaux reprennent les soldes cumulés des comptes de banque et de caisse depuis l'origine,
et les résultats des exercices tenus en simplifié passent en report à nouveau (110 / 119).

Les écritures produites par l'assistant (inventaire, fonds dédiés, à-nouveaux, extournes,
affectation) ne se modifient pas depuis l'écran des écritures : on les reprend dans l'assistant.

> À valider avec l'expert-comptable : l'affectation du résultat d'une SCI sur les comptes
> d'associés (455x) et la répartition entre associés.
