# Déclarations de TVA (CA3 mensuelle)

Lyvre prépare la déclaration de TVA du régime réel normal (formulaire **3310-CA3-SD**) à partir des
écritures. Vous la recopiez ensuite sur **TeleDEC** (ou impots.gouv), puis vous la marquez déposée.
Conception : `claudedocs/design_societe_tva.md` (lots T2 et T3).

## Mise en place

1. **Compta › Exercices** : « Déclarer soumis » à la TVA, choisir l'exigibilité des prestations
   (à l'encaissement par défaut, ou option sur les débits), puis **« Déclaration mensuelle (CA3) »**.
   Le menu **Compta › Déclarations de TVA** apparaît.
2. **Configuration › Structure** : n° de TVA intracommunautaire et **échéance** (jour du mois suivant
   fixé par votre SIE, de 15 à 24 ; vide : le 24).
3. **Tiers** : le **régime TVA** des fournisseurs et clients étrangers (Union européenne, hors UE) est
   proposé d'après leur n° de TVA ; vérifiez-le, il décide de l'autoliquidation et des ventes sans TVA.
   Pour un fournisseur **non établi en France** dont vous devez la TVA française (article 283-1 du CGI,
   par exemple un bien installé en France), choisissez « Non établi en France, TVA due par l'acheteur ».

## Ce que Lyvre déclare

Chaque ligne de TVA d'une écriture porte un **code de TVA** et sa base HT, posés par Lyvre à la
comptabilisation (achats, ventes, encaissements) ou choisis dans la saisie (lignes 445…) :

| Code | Opération | Cases de la CA3 |
|---|---|---|
| `V20`, `V10`, `V55`, `V21` | Vente imposable en France (TVA encaissée pour les prestations à l'encaissement) | A1 ; 08, 9B, 09 ou T6 (base et taxe) |
| `V_UE_S` / `V_EXO` | Prestation à un assujetti de l'UE / hors de France | E2 |
| `V_UE_B` | Livraison intracommunautaire | F2 |
| `V_EXP` | Exportation | E1 |
| `D20`… | TVA déductible | 19 (compte 44562, immobilisations) ou 20 |
| `AL_S` | Achat de services à un prestataire non établi en France (autoliquidation) | A3 ; 08 ; 20 (ou 19) |
| `AL_B` | Acquisition intracommunautaire de biens | B2 ; 08 dont 17 ; 20 (ou 19) |
| `AL_I`, `AL_I10`, `AL_I55`, `AL_I21` | Bien importé hors UE : TVA à l'importation autoliquidée (compte 4453) | A4 ; I1, I2, I4 ou I5 ; 20 (ou 19) dont 24 |
| `AL_FR` | Achat à un assujetti non établi en France, TVA due par l'acheteur (art. 283-1) | B4 ; 08 ; 20 (ou 19) |

La nature de l'article (**bien** ou **service**) départage `AL_S`, `AL_B` et `AL_I` ; une ligne sans
article est un service. Sous les lignes 08 / I… et 19 / 20, une mention rappelle la **TVA autoliquidée** :
due d'un côté, déduite de l'autre, elle est sans effet sur la TVA nette.

**Importations** : la douane préremplit A4 et I1 à I6 ; comparez-les aux montants de Lyvre (contrôle
affiché). La base comprend la valeur en douane, les **droits de douane** et les frais jusqu'au premier
lieu de destination : s'ils ne sont pas sur la facture du fournisseur, ajoutez-les en ligne de la
facture d'import (compte d'achat ou 6353). Les droits eux-mêmes se paient à la douane (ou au
transitaire), sans TVA.

**Avoirs reçus des fournisseurs** : leur TVA déduite est **reversée en ligne 15** (comprise dans le
total 16), comme le demande la notice, au lieu de réduire les lignes 19 / 20.
La correspondance est dans `data/ca3/2026.json` (numéros et codes des cases du formulaire 2026) ;
un nouveau millésime s'ajoute par un nouveau fichier.

**Un mois** reprend les lignes codées de ses écritures, plus celles des mois précédents saisies après
leur déclaration (régularisation). La TVA des prestations à l'encaissement (44574) n'est déclarée qu'au
mois de l'encaissement. Les cases sont arrondies à l'euro ; le **crédit** d'un mois (ligne 27) se
reporte en ligne 22 du mois suivant ; le premier mois reprend le solde débiteur de 44567 des
à-nouveaux.

## Au quotidien

**Compta › Déclarations de TVA** liste les mois de l'exercice : statut, échéance, retard, TVA à payer
ou crédit. Dans un mois :

- les **cases** dans l'ordre du formulaire, avec leur code de saisie ; cliquer un montant montre les
  lignes d'écriture qui le composent ;
- les **contrôles** : déclaration du mois précédent à valider d'abord (bloquant), mois en cours,
  écritures en brouillard, lignes de TVA sans code (non déclarées), taxe différente de base × taux,
  pièces de mois précédents ;
- **PDF** et **XLSX** de la déclaration (projet tant qu'elle n'est pas validée).

**Valider** : les écritures en brouillard jusqu'à la fin du mois sont validées, les cases figées, et
l'écriture de **liquidation** est passée au dernier jour du mois (journal OD) : comptes de TVA du mois
soldés, TVA à décaisser en **44551** ou crédit à reporter en **44567**, écart d'arrondi en 658 / 758
(Configuration › Comptes par défaut). Seule la **dernière** déclaration validée et non déposée
s'annule.

**Marquer déposée** (date, référence TeleDEC facultative) : la liquidation est validée et le mois
**verrouillé** ; les mois se déposent dans l'ordre. Une erreur se corrige ensuite par une écriture de
régularisation, reprise par la déclaration suivante. Le prélèvement de la DGFiP se rapproche sur 44551.

## Limites

Pas de télédéclaration (EDI-TVA), pas de CA12 ni de déclaration trimestrielle, pas de demande de
remboursement de crédit (3519, ligne 26 à zéro), pas de taxes assimilées (ligne 29), taux DOM et
Corse non gérés. Les pénalités de retard se calculent hors de Lyvre.
