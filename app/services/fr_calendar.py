"""Jours fériés et jours ouvrés en France métropolitaine (lot AG2.a, claudedocs/design_tva_agricole.md § 2, V5) :
échéances fiscales « 2e jour ouvré après le 1er mai » (CA12A, liasse), report d'une échéance tombant un samedi,
un dimanche ou un jour férié au premier jour ouvré suivant. Repris par l'échéancier (AG9).

Jours fériés légaux (Code du travail, art. L3133-1) : 1er janvier, lundi de Pâques, 1er mai, 8 mai, Ascension,
lundi de Pentecôte, 14 juillet, 15 août, 1er novembre, 11 novembre, 25 décembre. Le lundi de Pentecôte est
compté férié (son traitement par la DGFiP n'est pas confirmé : audit_calendrier.md, conventions de calcul).
"""
from __future__ import annotations

from datetime import date, timedelta
from functools import lru_cache


def easter(year: int) -> date:
    """Dimanche de Pâques (algorithme grégorien de Meeus / Jones / Butcher)."""
    a, b, c = year % 19, year // 100, year % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7  # noqa: E741
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = (h + l - 7 * m + 114) % 31 + 1
    return date(year, month, day)


@lru_cache(maxsize=64)
def holidays(year: int) -> frozenset[date]:
    sunday = easter(year)
    return frozenset({
        date(year, 1, 1), sunday + timedelta(days=1), date(year, 5, 1), date(year, 5, 8),
        sunday + timedelta(days=39), sunday + timedelta(days=50), date(year, 7, 14), date(year, 8, 15),
        date(year, 11, 1), date(year, 11, 11), date(year, 12, 25),
    })


def is_working_day(day: date) -> bool:
    return day.weekday() < 5 and day not in holidays(day.year)


def next_working_day(day: date) -> date:
    """Le jour lui-même s'il est ouvré, sinon le premier jour ouvré suivant (report d'une échéance)."""
    while not is_working_day(day):
        day += timedelta(days=1)
    return day


def nth_working_day_after(day: date, n: int) -> date:
    """n-ième jour ouvré strictement après `day` : `nth_working_day_after(date(2026, 5, 1), 2)` = 5 mai 2026."""
    count = 0
    while count < n:
        day += timedelta(days=1)
        if is_working_day(day):
            count += 1
    return day
