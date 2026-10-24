"""Erreurs du grand livre, dans un module à part : la garde (`ledger_guard`) et `ledger` s'en servent
sans s'importer l'une l'autre."""


class LedgerError(Exception):
    pass


class LedgerGuardError(LedgerError):
    """Refus de la garde des écritures (API 409) ; `code` : `entry_validated`."""

    def __init__(self, message, code="entry_validated"):
        super().__init__(message)
        self.code = code
