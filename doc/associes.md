# Associés

Pour une **société** (SCI, entreprise) : qui détient le capital, en pleine propriété, en usufruit ou
en nue-propriété, et ce que la société doit à chaque associé sur son **compte courant**. Le module
n'est pas proposé aux associations.

Menu **Associés** : Associés, Registre des parts, Notes de frais, Importer (CSV).

## Mise en place

1. **Activer le module** — Configuration › Structure, case **Société avec associés**
   (administrateur de l'instance). Elle est cochée d'office pour une instance créée au plan SCI.
   Désactiver le module masque le menu sans rien effacer ; un avertissement liste les comptes
   courants qui ne sont pas soldés.
2. **Taux d'intérêt des comptes courants** — même page, 0 % par défaut (pas d'intérêts). Un taux
   propre à un associé se saisit sur sa fiche.
3. **Associés** — Associés › **Nouvel associé** : un tiers existant ou un nouveau nom (le tiers est
   créé). Chaque associé reçoit un **compte courant**, sous-compte 455 : le prochain libre de 4551001
   à 4551999 est proposé, ou indiquez un compte 455 existant (reprise). Le compte ne change plus dès
   qu'il porte des écritures.
4. **Reprise d'une situation existante** — Associés › Importer (CSV) : voir [Import](#import-csv).

## Registre des parts

Associés › **Registre des parts** (`/share-movements/`). Le registre est **hors comptabilité** : il
décrit qui détient quoi, à quelle date. Le capital se passe en écritures comme d'habitude ; un écart
entre le capital du registre (parts × valeur nominale) et le solde des comptes 101 est signalé.

Chaque **mouvement** est daté et porte des lignes « associé, reçoit ou cède, parts, nature », avec une
pièce facultative (acte, statuts). Pendant la saisie, la **situation après le mouvement** s'affiche,
calculée sans rien enregistrer.

| Mouvement | Règle |
|---|---|
| Reprise, souscription | Parts reçues ; valeur nominale d'une part obligatoire |
| Réduction de capital | Parts cédées (annulées) ; valeur nominale |
| Cession, succession | Autant de parts cédées que reçues, nature par nature |
| Donation | Le capital ne change pas. Avec **réserve d'usufruit** : le donateur cède N parts en pleine propriété et reçoit N parts en usufruit ; les donataires reçoivent N parts en nue-propriété au total |
| Réunion de l'usufruit | L'usufruitier cède N parts en usufruit, le nu-propriétaire cède N parts en nue-propriété et reçoit N parts en pleine propriété |

Pour tous les mouvements : la nue-propriété et l'usufruit portent toujours sur le même nombre de
parts, et aucun associé ne peut avoir un nombre de parts négatif, à la date du mouvement ni après. Un
mouvement dont un mouvement postérieur dépend ne se supprime pas.

La **situation à une date** (filtre « Situation au ») recalcule les parts de chacun et le
pourcentage du capital : une part démembrée compte une fois (pleine propriété + nue-propriété).

## Comptes courants

Le solde d'un compte courant se lit dans le grand livre : **créditeur, la société doit à l'associé**
(« dû à l'associé ») ; débiteur, l'associé doit à la société (« dû par l'associé », signalé). La
fiche d'un associé montre le **relevé** (origine de chaque ligne, solde progressif) ; la liste des
associés a une vue **Comptes courants par exercice** (soldes empilés à la fin de chaque exercice).

Les opérations du module passent au journal **AS « Associés »**, créé à la première écriture.

### Facture payée par un associé

- **Fiche d'une facture d'achat** comptabilisée et non réglée : **Réglée par un associé** (associé,
  date). Écriture : 401 du fournisseur au débit, 455 de l'associé au crédit ; la facture est réglée.
  **Défaire** supprime l'écriture.
- **À la saisie** d'une facture : **Payée par un associé** (associé, date), appliqué après
  l'enregistrement si la facture est comptabilisée.
- Rien n'est écrit dans Qonto : une facture déposée dans Qonto y reste « à payer ».

### Note de frais

Associés › **Notes de frais** : dépense avancée par un associé sans facture fournisseur (associé,
date, libellé, compte de charge, HT, taux ou montant de TVA, justificatif). Écriture : charge et TVA
déductible au débit, 455 de l'associé au crédit. Supprimer la note supprime son écriture.

### Apport et remboursement

**Rapprochement**, sur une transaction : **Compte courant d'associé** → l'associé. L'éditeur
d'écriture s'ouvre prérempli (apport : 512 au débit, 455 au crédit ; remboursement : l'inverse) ;
l'écriture est enregistrée et rapprochée dans le journal de la banque. Une règle de catégorisation
peut aussi viser le compte 455 d'un associé.

## Clôture

- **Intérêts** — Clôture, étape *Écritures d'inventaire*, panneau **Intérêts des comptes courants** :
  taux, solde créditeur moyen et intérêts de chaque associé (Σ des soldes créditeurs de fin de journée
  × taux / 365). **Passer les intérêts** crée une écriture par associé au dernier jour de
  l'exercice : 6615 au débit (créé s'il manque), 455 de l'associé au crédit. Relancer remplace les
  écritures. Administrateur, exercice ouvert.
- **Affectation du résultat** — Clôture, étape *Affectation du résultat* : **Répartir entre les
  associés** remplit les lignes au prorata des parts en **pleine propriété et en usufruit** à la date
  de clôture (les nus-propriétaires n'y ont pas droit), centimes au plus fort reste. Les lignes restent
  modifiables avant d'enregistrer la décision.

## Import CSV

Associés › **Importer (CSV)** (administrateur). Le modèle se télécharge depuis la page.

```
nom;compte;nature;parts;date;nominal;solde;taux
Pascal Exemple;4551001;US;300;01/01/2026;10,00;86963,08;0
Barbara Exemple;4551002;NP;300;01/01/2026;10,00;500,00;
Barbara Exemple;4551002;PP;700;01/01/2026;10,00;;
```

- Une ligne par associé **et par nature** (un associé démembré a plusieurs lignes) ; nature PP, US
  ou NP ; séparateur « ; » ou « , » ; UTF-8 ou fichier Excel (Windows-1252).
- **Analyse d'abord**, sans rien écrire : associés créés ou repris (même nom), comptes, parts,
  soldes, erreurs ligne par ligne. **Importer** est refusé tant qu'il reste une erreur, et importe tout
  ou rien.
- Une **reprise** au registre par date. Choisissez une date où la situation est complète (par
  exemple le début de l'exercice de reprise) : une date d'entrée ancienne où l'usufruit existerait sans
  ses nus-propriétaires est refusée.
- **Solde** : solde du compte courant à la date de reprise, créditeur positif. Il est passé au
  journal AN contre le **compte de contrepartie** choisi (à voir avec l'expert-comptable), seulement si
  le compte courant n'a encore aucune écriture ; sinon il est ignoré (réimport sans doublon).

## Droits

| Action | Administrateur | Trésorier | Expert-comptable |
|---|---|---|---|
| Activer le module, taux, associés, registre, import, intérêts | ✔ | lecture | lecture |
| Facture réglée par un associé, notes de frais, apports et remboursements | ✔ | ✔ | lecture |

## Limites

- Le registre ne passe pas les écritures de capital (souscription, libération, réduction).
- Hors périmètre : déclaration 2072 et son annexe, dividendes (457), assemblées et procès-verbaux,
  valorisation des parts.
- Une écriture du journal AS reste modifiable depuis l'écran des écritures, comme les autres
  règlements : la supprimer de là détache la facture ou la note de frais de son règlement, à défaire et
  refaire depuis le module.
- L'option d'activation est enregistrée avec l'instance (base des instances), pas dans sa sauvegarde :
  après une restauration, recochez-la.
