"""Montants en centimes dans les messages destinés à l'utilisateur."""


def euros(cents: int) -> str:
    """1234567 → « 12 345,67 € »."""
    return f"{cents / 100:,.2f} €".replace(",", " ").replace(".", ",")
