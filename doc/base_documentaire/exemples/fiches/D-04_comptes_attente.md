---
id: D-04
titre: Comptes d'attente (471 à 473)
referentiels: [pcg2026]
comptes: ["47", "471", "472", "473"]
articles: ["PCG 2026 art. 1214-47"]
sources: [PCG26]
mots_cles: [prélèvement inconnu, opération non identifiée, compte d'attente, reclassement, 471]
risque: aucun
statut: publie               # art. 1214-47 vérifié dans le texte du PCG 2026 (arrhes/PCG, l. 7559)
verifie_le: 2026-10-23
verifie_par: doc/ref_compta/Base_compta.md (D-04, FAQ n° 4)
regles:
  - pcg2026.controles.suspense
  - pcg2026.schemas.attente_reclassement
ecrans: ["/reconciliation/*", "/fiscal-years/*/closing"]
---

## Résumé

Une opération bancaire dont on ne connaît pas encore la nature (prélèvement inconnu, virement sans libellé) peut être **provisoirement** enregistrée dans un compte d'attente 47x. Ce compte doit être **reclassé au plus vite** vers le bon compte. Il doit être **soldé avant la clôture** : un compte d'attente ne figure pas aux comptes annuels.

## Exemple

Prélèvement inconnu de 120 € le 12/03, identifié le 20/03 comme une prime d'assurance.

| Date | Compte | Débit | Crédit |
|---|---|---|---|
| 12/03 | 471 Compte d'attente | 120 | |
| 12/03 | 512 Banque | | 120 |
| 20/03 | 616 Primes d'assurance | 120 | |
| 20/03 | 471 Compte d'attente | | 120 |

## Référence

PCG 2026, art. 1214-47 [PCG26] : les opérations « qui ne peuvent pas être imputées de façon certaine » sont inscrites provisoirement en 471 à 473. Ce procédé n'est utilisé « qu'à titre exceptionnel », l'opération est imputée au compte définitif « dans les moindres délais possibles », et ces comptes sont « reclassés en fin d'exercice ». FAQ utilisateurs n° 4.

## Dans le logiciel

- **Rapprochement** : une transaction sans écriture peut être affectée au 471 en attendant la pièce.
- **Clôture, étape 1** : tout compte 47x non soldé est signalé comme anomalie (contrôle `suspense_<compte>`). Le bouton « Expliquer » liste les lignes concernées et propose un reclassement pour chacune.
- **Modèle d'écriture** : « Reclassement d'une opération passée en compte d'attente ».
- La numérotation des comptes d'attente diffère selon le plan : asso « 471 (jusqu'à 474) », SCI « 471 à 475 ». Pour le PCG, seuls **471 à 473** sont des comptes d'attente. Le 474 enregistre des différences d'évaluation, et les 476 / 477 des écarts de conversion : ils ne doivent pas être signalés comme « attente non soldée ».
