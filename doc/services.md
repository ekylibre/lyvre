

## budget.py — Budget (lot C.2)

`months(fy)` (mois de l'exercice, libellés courts), `spread(annual, n)` (douzièmes entiers),
`grid(fy, project)` (lignes annuelles ou mensuelles du périmètre), `totals(rows)`, `save(fy,
project, rows)` (remplace le périmètre ; refuse doublons et comptes imbriqués, qui fausseraient le
réalisé), `copy_rows(fy, project, source)` (budget ou réalisé de l'exercice précédent, réalisé
regroupé au compte à 3 chiffres s'il existe ; mensuel si les deux exercices ont autant de mois,
sinon annuel), `account_options()`. Erreurs : `BudgetError(message, field)`.

**Suivi (lot C.3)** — `tracking(fy, project=None, as_of=None)` : pour chaque poste du budget, prévu
de l'année, prévu à date (somme des mois entamés au `as_of`), réalisé à date (comptes commençant par
le code du poste ; seulement les lignes du projet si un projet est choisi), écart et taux ; le
réalisé non couvert par un poste remonte en lignes « hors budget » (compte à 3 chiffres) ; synthèse
charges / produits / résultat.
