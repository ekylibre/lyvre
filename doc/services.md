

## cash_forecast.py — Prévisionnel de trésorerie (lot C.4)

`balances(today)` : par compte bancaire, solde comptable jusqu'à aujourd'hui **hors à-nouveaux**
(qui reprennent des soldes déjà comptés) plus les transactions bancaires non comptabilisées ;
comptes de caisse 53. `forecast(today)` : 12 mois glissants ; factures d'achat non réglées (montant
à payer à l'échéance ; avoir = encaissement), factures clients Odoo au reste dû, budget général
du mois (hors 68 / 78 ; mois en cours : prévu moins réalisé), saisies manuelles répétées ;
échéance dépassée → mois en cours ; `first_negative` (alerte). `save_item`, `item_payload` ;
erreurs `ForecastError(message, field)`.
