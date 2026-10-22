---
id: C-03
titre: Fonds dédiés
referentiels: [asso_2018_06]
comptes: ["19", "194", "195", "196", "689", "6894", "6895", "6896", "789", "7894", "7895", "7896"]
articles: ["2018-06 art. 132-1", "2018-06 art. 132-2", "2018-06 art. 132-3", "2018-06 art. 132-4", "2018-06 art. 431-6"]
sources: [REC-NL26]
mots_cles: [subvention non utilisée, report, reliquat, projet défini, fonds affectés, 689, 789]
risque: expert
statut: publie
verifie_le: 2026-10-22
verifie_par: doc/ref_compta/Base_compta.md (C-03)
regles:
  - asso_2018_06.controles.fonds_dedies_jamais_debiteurs
  - asso_2018_06.controles.fonds_dedies_avec_projet
  - asso_2018_06.schemas.fonds_dedies_report
  - asso_2018_06.schemas.fonds_dedies_reprise
ecrans: ["/fiscal-years/*/closing", "/projects/*"]
---

## Résumé

À la clôture, la part **non utilisée** des ressources qu'un tiers financeur a affectées à un **projet défini** est inscrite au passif en 19x, en contrepartie d'une charge 689x (art. 132-1, 132-2). Elle est ensuite reprise en 789x au rythme de réalisation du projet (art. 132-3).

| Origine de la ressource | Passif | Report (charge) | Utilisation (produit) |
|---|---|---|---|
| Subventions | 194 | 6894 | 7894 |
| Contributions financières | 195 | 6895 | 7895 |
| Générosité du public | 196 | 6896 | 7896 |

Un **projet défini** participe à une partie spécifique de l'objet social et ses charges sont individualisables. Une collecte dont l'objet se confond avec l'objet social ne peut pas aller en fonds dédiés.

Un transfert vers un autre projet exige l'accord du financeur (art. 132-4). L'annexe présente un tableau par projet (art. 431-6).

## Exemple

Subvention de 30 000 € pour le projet « Atelier réemploi », dont 18 000 € utilisés au 31/12/N.
(Comptes du plan de l'application : `Base_compta.md` écrit D 441 / C 741, mais le plan asso n'a ni 741 ni 441 en compte de détail.)

| Date | Compte | Débit | Crédit |
|---|---|---|---|
| N | 4417 Subventions d'exploitation à recevoir | 30 000 | |
| N | 74 Subventions de fonctionnement | | 30 000 |
| 31/12/N | 6894 Reports en fonds dédiés sur subventions | 12 000 | |
| 31/12/N | 194 Fonds dédiés sur subventions | | 12 000 |
| N+1 | 194 Fonds dédiés sur subventions | 12 000 | |
| N+1 | 7894 Utilisation des fonds dédiés | | 12 000 |

## Référence

Règlement ANC 2018-06, art. 132-1 à 132-4 et 431-6. Recueil des normes du secteur non lucratif 2026 [REC-NL26].

## Dans le logiciel

- Étape « fonds dédiés » de l'**assistant de clôture** (`/fiscal-years/<id>/closing`). Le reliquat (ressources − charges affectées) est calculé par le logiciel à partir de l'axe **Projet**.
- Contrôles :
  - un compte 194, 195 ou 196 débiteur est une anomalie ;
  - toute ligne 19x, 689x ou 789x doit porter un projet.
- Modèles d'écriture : « Report en fonds dédiés » et « Utilisation de fonds dédiés en N+1 ».
- ⚠️ Décider qu'un projet est « défini », et donc qu'il ouvre droit aux fonds dédiés, relève du **jugement**. Faites valider ce point par votre expert-comptable.
