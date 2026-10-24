"""Erreurs du grand livre, dans un module à part : la garde (`ledger_guard`) et `ledger` s'en servent
sans s'importer l'une l'autre."""


class LedgerError(Exception):
    pass


class LedgerGuardError(LedgerError):
    """Refus de la garde des écritures (API 409) ; `code` : `entry_validated`, `period_locked`."""

    def __init__(self, message, code="entry_validated", first_open_date=None):
        super().__init__(message)
        self.code = code
        self.first_open_date = first_open_date


def period_locked(fy, on_date=None):
    """Refus d'une écriture datée dans la période verrouillée de l'exercice (lot F2)."""
    first = fy.first_open_date
    when = f" ({on_date:%d/%m/%Y})" if on_date else ""
    advice = f" : utilisez une date à partir du {first:%d/%m/%Y}" if first else " : exercice entièrement verrouillé"
    return LedgerGuardError(f"Période verrouillée jusqu'au {fy.locked_until:%d/%m/%Y}{when}{advice}.",
                            code="period_locked", first_open_date=first)
