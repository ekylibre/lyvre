# Base d'échéances de l'exploitation (lot AG9a)

Une fiche par échéance, reprise de `claudedocs/compta_agricole/audit_calendrier.md` (§ 2), à relire par
l'expert-comptable avant la mise en production (AGD5). Schéma et règles : `app/services/deadlines.py` et
`claudedocs/design_echeancier_agricole.md` § 4. Les liens viennent de l'audit : n'en ajoutez pas sans source vérifiée.

Champs d'une fiche : `id`, `title`, `domain`, `organism`, `summary`, `applies`, `events`, `prepare`, `lyvre_data`,
`penalties`, `links`, `reliability` (V, R, A, I), `reminder_only` (démarche hors comptabilité, AGD9).

Règles de date (`events[].rule.type`) : `fixed`, `nth_working_day_after`, `after_close`, `in_fiscal_year`, `monthly`,
`once`, `annual_param` (avec `fallback`), `profile`, `leases`, `lyvre`.
