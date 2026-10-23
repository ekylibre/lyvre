"""Montants en centimes dans les messages destinés à l'utilisateur."""


def euros(cents: int) -> str:
    """1234567 → « 12 345,67 € »."""
    return f"{cents / 100:,.2f} €".replace(",", " ").replace(".", ",")


_UNITS = ("zéro", "un", "deux", "trois", "quatre", "cinq", "six", "sept", "huit", "neuf", "dix", "onze", "douze",
          "treize", "quatorze", "quinze", "seize", "dix-sept", "dix-huit", "dix-neuf")
_TENS = {2: "vingt", 3: "trente", 4: "quarante", 5: "cinquante", 6: "soixante"}


def _below_100(n: int) -> str:
    if n < 20:
        return _UNITS[n]
    tens, unit = divmod(n, 10)
    if tens in (7, 9):  # soixante-dix…, quatre-vingt-dix…
        base = "soixante" if tens == 7 else "quatre-vingt"
        return f"{base}-{_UNITS[10 + unit]}" if not (tens == 7 and unit == 1) else "soixante et onze"
    if tens == 8:
        return "quatre-vingts" if unit == 0 else f"quatre-vingt-{_UNITS[unit]}"
    if unit == 0:
        return _TENS[tens]
    return f"{_TENS[tens]} et un" if unit == 1 else f"{_TENS[tens]}-{_UNITS[unit]}"


def _below_1000(n: int, final: bool) -> str:
    """`final` : le nombre termine l'expression (« deux cents » mais « deux cent mille »)."""
    hundreds, rest = divmod(n, 100)
    words = []
    if hundreds:
        if hundreds == 1:
            words.append("cent")
        else:
            words.append(f"{_UNITS[hundreds]} cent" + ("s" if rest == 0 and final else ""))
    if rest:
        text = _below_100(rest)
        if not final and text.endswith("quatre-vingts"):
            text = text[:-1]
        words.append(text)
    return " ".join(words)


def number_in_words(n: int) -> str:
    """Nombre entier en toutes lettres (orthographe traditionnelle) : 1 234 → « mille deux cent
    trente-quatre »."""
    if n == 0:
        return "zéro"
    parts = []
    millions, rest = divmod(n, 1_000_000)
    thousands, units = divmod(rest, 1000)
    if millions:
        parts.append(f"{_below_1000(millions, True)} million" + ("s" if millions > 1 else ""))
    if thousands:
        parts.append("mille" if thousands == 1 else f"{_below_1000(thousands, False)} mille")
    if units:
        parts.append(_below_1000(units, True))
    return " ".join(parts)


def euros_in_words(cents: int) -> str:
    """Montant en toutes lettres pour un reçu : 123456 → « mille deux cent trente-quatre euros et
    cinquante-six centimes »."""
    whole, rest = divmod(cents, 100)
    text = f"{number_in_words(whole)} euro" + ("s" if whole > 1 else "")
    if whole % 1_000_000 == 0 and whole:
        text = text.replace(" euros", " d'euros")
    if rest:
        text += f" et {number_in_words(rest)} centime" + ("s" if rest > 1 else "")
    return text
