---
id: S-02
titre: Loyers et charges refacturées (SCI)
referentiels: [sci]
comptes: ["411", "7083", "7085"]
articles: []
sources: [PLAN-SCI]          # + notice 2072 de l'année, à ajouter à sources.yml
mots_cles: [loyer, quittance, charges locatives, refacturation, 2072, ligne 1, ligne 2]
risque: attention
statut: brouillon            # NON injecté dans l'assistant tant qu'il n'est pas validé (doc 6 §6.3)
verifie_le: 2026-10-23
verifie_par: plan SCI uniquement — à faire valider par un expert-comptable
regles:
  - sci.schemas.loyer_appele
  - sci.schemas.charges_refacturees
ecrans: ["/entries/new"]
---

## Résumé (à valider)

Dans le plan SCI de l'application :
- les **loyers encaissés** vont en **7083** « Fermages ou loyers encaissés », repris en **ligne 1** de la 2072 ;
- les **dépenses** qui incombent normalement à la SCI mais que le bail met à la charge du locataire vont en **7085**, repris en **ligne 2**.

Le loyer est constaté à l'appel, au crédit du compte de produit et au débit du locataire (411). L'encaissement solde ensuite le 411.

## Exemple

Loyer de 900 € et provision sur charges de 80 € appelés le 01/04, encaissés le 05/04.

| Date | Compte | Débit | Crédit |
|---|---|---|---|
| 01/04 | 411 Locataire Dupont | 980 | |
| 01/04 | 7083 Loyers encaissés | | 900 |
| 01/04 | 7085 Charges refacturées | | 80 |
| 05/04 | 512 Banque | 980 | |
| 05/04 | 411 Locataire Dupont | | 980 |

## Référence

Plan comptable SCI (`doc/plan-comptable-SCI.pdf`), libellés « (ligne 1) » et « (ligne 2) ». **À compléter** : notice de la déclaration 2072 de l'année en cours.

## Dans le logiciel

- Modèles d'écriture « Loyer appelé » et « Charges récupérables refacturées ».
- Correspondance 2072 : `regles/sci/correspondance_2072.yml`.
- ⚠️ Points à valider :
  - régime de la SCI (IR ou IS) ;
  - traitement de la régularisation annuelle des charges ;
  - ventilation par immeuble si la SCI en détient plusieurs.
