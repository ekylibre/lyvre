"""Lecture d'une facture d'achat : Factur-X, texte du PDF, OCR (Tesseract).

`read(path, mime)` renvoie une `Extraction` : pour chaque champ trouvé, sa valeur,
son origine (`facturx`, `text`, `ocr`) et s'il est « à vérifier ». Rien n'est
enregistré ici : l'extraction sert à préremplir le formulaire de saisie.

Ordre de lecture : XML Factur-X / ZUGFeRD embarqué (valeurs exactes) ; sinon le
texte natif des premières pages ; une page sans texte (scan, photo) passe par
l'OCR français. Tesseract absent : avertissement, lecture texte conservée.

Le texte est reconstruit d'après la position des mots (`layout_lines`), et les
montants retenus sont ceux qui se recoupent (HT + TVA = TTC, `_choose_amounts`).
Mesure sur un corpus de factures réelles : scripts/invoice_corpus.py.

Les montants sont en centimes, les taux en points de base (2000 = 20 %).
"""
from __future__ import annotations

import re
import unicodedata
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation

import numpy as np
import pymupdf
from PIL import Image, ImageFilter, ImageOps

PDF_MIME = "application/pdf"
IMAGE_MIMES = ("image/jpeg", "image/png")
FACTURX_NAMES = ("factur-x.xml", "zugferd-invoice.xml", "xrechnung.xml")
MAX_XML_SIZE = 1024 * 1024
MIN_PAGE_TEXT = 30       # en dessous : page scannée, OCR
OCR_MAX_WIDTH_PX = 2500  # résolution du rendu OCR (une photo n'est pas agrandie)
OCR_LANGUAGE = "fra"
AMOUNT_FIELDS = ("total", "untaxed", "tax")
COMMON_RATES_BP = (2000, 1000, 850, 550, 210)


@dataclass
class Field:
    value: object
    origin: str          # "facturx" | "text" | "ocr"
    check: bool = False  # à vérifier dans le formulaire


@dataclass
class Extraction:
    fields: dict[str, Field] = field(default_factory=dict)
    taxes: list[tuple[int, int | None, int]] = field(default_factory=list)  # (taux, HT, TVA)
    source: str = "none"  # "facturx" | "text" | "ocr" | "none"
    warnings: list[str] = field(default_factory=list)
    coherent: bool = False  # HT + TVA = TTC vérifié sur des montants lus (non déduits)

    def value(self, name, default=None):
        f = self.fields.get(name)
        return f.value if f is not None else default

    def set(self, name, value, origin, check=False):
        if value is not None and value != "":
            self.fields[name] = Field(value, origin, check)


@dataclass(frozen=True)
class SupplierHints:
    """Mémoire d'un fournisseur reconnu, tirée de ses factures déjà saisies : taux de TVA
    pratiqués, factures sans TVA, forme de ses numéros de facture."""
    rates: frozenset = frozenset()
    tax_free: bool = False
    number_shapes: frozenset = frozenset()


def number_shape(value: str) -> str:
    """« F-2026-010 » → « A-9999-999 » : forme d'un numéro de facture."""
    return re.sub(r"[A-Za-z]", "A", re.sub(r"\d", "9", value.replace(" ", "")))


# ------------------------------------------------------------------ identifiants

def _luhn_ok(digits: str) -> bool:
    total = 0
    for i, c in enumerate(reversed(digits)):
        n = int(c) * (2 if i % 2 else 1)
        total += n - 9 if n > 9 else n
    return total % 10 == 0


def valid_siret(value: str) -> bool:
    return len(value) == 14 and value.isdigit() and _luhn_ok(value)


def valid_fr_vat(value: str) -> bool:
    """N° de TVA français : FR + clé + SIREN ; la clé numérique est contrôlée."""
    if not re.fullmatch(r"FR[0-9A-HJ-NP-Z]{2}\d{9}", value):
        return False
    key, siren = value[2:4], int(value[4:])
    return not key.isdigit() or int(key) == (12 + 3 * (siren % 97)) % 97


def valid_iban(value: str) -> bool:
    if not re.fullmatch(r"[A-Z]{2}\d{2}[A-Z0-9]{11,30}", value):
        return False
    moved = value[4:] + value[:4]
    return int("".join(str(int(c, 36)) for c in moved)) % 97 == 1


# ------------------------------------------------------------------ montants, dates

_AMOUNT = re.compile(
    r"(?<![\d,.])(-?\s?(?:\d{1,3}(?:[   .]\d{3})+|\d+)(?:,\d{2}|\.\d{2}))(?![\d,.%])"
    r"\s?(?:€|EUR\b)?"
)


def parse_amount(text: str) -> int | None:
    """« 1 234,56 », « 1.234,56 », « 39,99€ », « 39.99 » → centimes."""
    raw = re.sub(r"[\s  €]|EUR", "", text)
    if "," in raw:
        raw = raw.replace(".", "").replace(",", ".")
    try:
        return int((Decimal(raw) * 100).quantize(Decimal("1")))
    except InvalidOperation:
        return None


def amounts_in(line: str) -> list[int]:
    found = (parse_amount(m.group(1)) for m in _AMOUNT.finditer(line))
    return [a for a in found if a is not None]


MONTHS = {
    "janvier": 1, "janv": 1, "fevrier": 2, "février": 2, "fevr": 2, "févr": 2, "mars": 3,
    "avril": 4, "avr": 4, "mai": 5, "juin": 6, "juillet": 7, "juil": 7, "aout": 8, "août": 8,
    "septembre": 9, "sept": 9, "octobre": 10, "oct": 10, "novembre": 11, "nov": 11,
    "decembre": 12, "décembre": 12, "dec": 12, "déc": 12,
    # factures en anglais (services en ligne)
    "january": 1, "jan": 1, "february": 2, "feb": 2, "march": 3, "mar": 3, "april": 4, "apr": 4,
    "may": 5, "june": 6, "jun": 6, "july": 7, "jul": 7, "august": 8, "aug": 8, "september": 9,
    "sep": 9, "october": 10, "november": 11, "december": 12,
}
_MONTH_NAMES = "|".join(sorted(MONTHS, key=len, reverse=True))
_DATE_PATTERNS = (
    re.compile(r"\b(\d{1,2})(?:er|st|nd|rd|th)?\s+(" + _MONTH_NAMES + r")\.?,?\s+(\d{4})\b",
               re.IGNORECASE),
    re.compile(r"\b(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{4}|\d{2})\b"),
    re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b"),
    re.compile(r"\b(" + _MONTH_NAMES + r")\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})\b",
               re.IGNORECASE),  # « August 3, 2026 »
)


def dates_in(line: str) -> list[date]:
    found = []
    for index, pattern in enumerate(_DATE_PATTERNS):
        for m in pattern.finditer(line):
            a, b, c = m.groups()
            try:
                if index == 0:
                    day, month, year = int(a), MONTHS[b.lower()], int(c)
                elif index == 1:
                    day, month, year = int(a), int(b), int(c)
                    year += 2000 if year < 100 else 0
                elif index == 2:
                    year, month, day = int(a), int(b), int(c)
                else:
                    day, month, year = int(b), MONTHS[a.lower()], int(c)
                if 2000 <= year <= 2100:
                    found.append((m.start(), date(year, month, day)))
            except (ValueError, KeyError):
                continue
    return [d for _, d in sorted(found, key=lambda x: x[0])]


# ------------------------------------------------------------------ texte

# Dates : un libellé explicite l'emporte ; à défaut, les mots faibles de l'ancienne lecture.
_ISSUE_STRONG = re.compile(
    r"date\s+(?:de\s+(?:la\s+)?)?(?:facture|facturation|d'[ée]mission|[ée]mission|d'[ée]tablissement)|"
    r"date\s+facture|facture\b.{0,40}?\bdu\b|invoice\s+date|date\s+of\s+issue|issued?\s+(?:on|date)|"
    r"[ée]mise?\s+le", re.IGNORECASE)
_ISSUE_WORDS = re.compile(r"facture|invoice|émise|emise|\bdu\b|\ble\b|\bdate\b", re.IGNORECASE)
_NOT_ISSUE = re.compile(r"prochain|next|relev[ée]|souscrit|depuis|livraison|\bbl\b|intervention|"
                        r"arriv[ée]e|commande|p[ée]riode|naissance|valable|\bau\s+\d", re.IGNORECASE)
_DUE_STRONG = (  # par priorité
    re.compile(r"date\s+(?:d'|de\s+l')?[ée]ch[ée]ance|date\s+limite|due\s+date|payment\s+due|"
               r"[àa]\s+(?:payer|r[ée]gler)\s+(?:avant\s+)?le|[àa]\s+r[ée]gler\b.{0,40}?\bau\b|"
               r"payable\s+(?:le|avant|au)\b|^\s*[ée]ch[ée]ance", re.IGNORECASE),
    re.compile(r"pr[ée]lev[ée]e?s?\s+(?:automatiquement\s+)?le|[àa]\s+partir\s+du", re.IGNORECASE),
)
_DUE_WORDS = re.compile(r"échéance|echeance|à payer le|a payer le|payable|date limite|prélev|"
                        r"prelev|exigible|due date", re.IGNORECASE)
_NOT_DUE = re.compile(r"venant\s+[àa]\s+[ée]ch[ée]ance|contrat|souscrit|retard|p[ée]nalit", re.IGNORECASE)

_TOTAL_WORDS = (  # par priorité
    re.compile(r"net\s+[àa]\s+payer|(?:somme|montant)\s+[àa]\s+(?:payer|pr[ée]lever)|"
               r"total\s+[àa]\s+payer|reste\s+[àa]\s+payer|amount\s+due|total\s+due|balance\s+due",
               re.IGNORECASE),
    re.compile(r"total\s+t\.?t\.?c|montant\s+t\.?t\.?c|facture\s+ttc|ttc\s+total|total\s+g[ée]n[ée]ral|"
               r"total\s+facture|grand\s+total|total\s+incl|total\s+amount|invoice\s+total",
               re.IGNORECASE),
    re.compile(r"^\s*total\b(?!.*\b(?:ht|h\.t|tva|hors|lignes)\b)", re.IGNORECASE),
)
_UNTAXED_WORDS = re.compile(
    r"total\s+h\.?t\b|montant\s+h\.?t\b|base\s+h\.?t\b|total\s+hors\s+t|montant\s+hors\s+t|"
    r"base\s+taxe|sous-total|sub-?total|total\s+excl|total\s+before\s+tax|net\s+amount", re.IGNORECASE)
_TAX_TOTAL_WORDS = re.compile(
    r"total\s+t\.?v\.?a|montant\s+t\.?v\.?a|dont\s+t\.?v\.?a|montant\s+(?:de\s+la\s+)?taxe|"
    r"total\s+vat|vat\s+amount|total\s+tax|tax\s+amount", re.IGNORECASE)
_TAX_FREE = re.compile(r"tva\s+non\s+applicable|293\s*b\b|exon[ée]r[ée]e?\s+de\s+tva|"
                       r"vat\s+not\s+applicable", re.IGNORECASE)
_RATE = re.compile(r"(?:t\.?v\.?a|vat)[^%\n]{0,20}?(\d{1,2}(?:[,.]\d{1,2})?)\s?%", re.IGNORECASE)
_NUMBER_LINE_SKIP = re.compile(r"carte|client|abonn|commande|t\.?v\.?a|siret|siren|t[ée]l|"
                               r"fid[ée]lit|rcs|compte|contrat|lot\b|devis|bon\b|iban|bic|"
                               r"d[ée]cret|article|\bloi\b|\bart\b", re.IGNORECASE)
_NUMBER_REF = re.compile(  # « Réf. Facture : 25 150416 A du 25/02/2025 » (blancs dans le numéro)
    r"r[ée]f(?:[ée]rence)?\.?\s+(?:de\s+(?:la\s+)?)?facture\s*:?\s*"
    r"([A-Z0-9](?:[\w\-/.]| (?=\w))*?\d(?:[\w\-/.]| (?=\w))*?)(?=\s+du\b|\s{2,}|$)", re.IGNORECASE)
_NUMBER_AFTER_INVOICE = re.compile(
    r"\b(?:facture|invoice|avoir)\s*(?:n[°ºo]\.?|num(?:[ée]ro)?\.?|number|#)?\s*:?\s*"
    r"([A-Z0-9][\w\-/.]*\d[\w\-/.]*)", re.IGNORECASE)
_NUMBER_PIECE = re.compile(r"n[°º]\s*(?:de\s+)?(?:pi[eè]ce|document)\s*:?\s*([A-Z0-9][\w\-/.]*\d[\w\-/.]*)",
                           re.IGNORECASE)
_NUMBER_AFTER_NO = re.compile(r"(?:\bn[°º]|\bnum[ée]ro\b|\bno\b\.?)\s*:?\s*([A-Z0-9][\w\-/.]*\d[\w\-/.]*)",
                              re.IGNORECASE)
_LEGAL_FORMS = r"SASU|SAS|SARL|EURL|SNC|SCOP|SELARL|GIE|SA|SCI"
_LEGAL_NAME = (
    re.compile(r"^\s*([A-Z0-9][\w&'’.\- ]{0,60}?)[\s,\-]+(?:" + _LEGAL_FORMS + r")\b.{0,120}?"
               r"(?:capital|RCS|SIRE[NT])", re.IGNORECASE),
    # « HM France Bétons - 4 Place des Saisons, 92400 Courbevoie - SAS au capital … »
    re.compile(r"^\s*([A-Z][\w&'’. ]{1,60}?)\s+-\s+.{0,120}?\b(?:" + _LEGAL_FORMS + r")\s+au\s+capital",
               re.IGNORECASE),
)
_STREET = re.compile(r"^\d{1,4}\s*(?:bis|ter)?,?\s+(?:rue|avenue|av\.|bd|boulevard|cours|place|chemin|"
                     r"route|impasse|all[ée]e|quai|lieu-dit|zone|za|zi|parc)\b", re.IGNORECASE)
_WEBSITE = re.compile(r"www\.([a-z0-9-]{2,40})\.(?:fr|com|eu|net|org|be|ch)", re.IGNORECASE)
_SIRET = re.compile(r"\b(\d{3}[ .]?\d{3}[ .]?\d{3}[ .]?\d{5})\b")
_SIRET_LABELLED = re.compile(r"siret\W{0,5}((?:\d[ .]?){13}\d)\b", re.IGNORECASE)
_VAT_FR = re.compile(r"\bFR(?:[ .]?[0-9A-HJ-NP-Z]){2}(?:[ .]?\d){9}\b")
_IBAN = re.compile(r"\b[A-Z]{2}\d{2}(?:[ ]?[A-Z0-9]){11,30}\b")
_CREDIT_NOTE = re.compile(r"^\s*(?:facture\s+d'|)avoir\b|\bavoir\s+n[°º]|note\s+de\s+cr[ée]dit|"
                          r"credit\s+note", re.IGNORECASE | re.MULTILINE)
_DISCOUNT_WORDS = re.compile(r"fid[ée]lit|remise|r[ée]duction|bon d'achat|coupon|ristourne",
                             re.IGNORECASE)
_CUSTOMER = re.compile(r"client|acheteur|customer|destinataire|factur[ée]\s+[àa]|si[èe]ge\s*:",
                       re.IGNORECASE)
_NOT_SIRET = re.compile(r"r[ée]f|acheminement|\bpdl\b|\bprm\b|compteur|contrat|commande|mandat",
                        re.IGNORECASE)  # n° de point de livraison, de compteur… valides par hasard
_OCR_DIGIT_O = re.compile(r"(?<=\d)[Oo]|[Oo](?=\d)")
_OCR_THOUSANDS_ONE = re.compile(r"(?<![\w,.])[lIL|]\s(?=\d{3},\d{2}\b)")  # « L 905,00 » → « 1 905,00 »
_OCR_GLUED_A = re.compile(r"\b(somme|montant|reste|net|total)à\s*", re.IGNORECASE)  # « Sommeà payer »
MAX_RATE_BP = 2000


def _plain(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", text.lower())


_NAME_NOISE = {"sci", "sas", "sasu", "sarl", "eurl", "les", "des", "the", "association", "asso", "ste",
               "societe"}


def _name_words(name: str) -> set[str]:
    plain = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    return {w for w in re.findall(r"[a-z0-9]+", plain) if len(w) >= 3 and w not in _NAME_NOISE}


def same_name(a: str, b: str) -> bool:
    """« LES CHENES VERTS » et « SCI des Chênes Verts » : mêmes mots significatifs."""
    wa, wb = _name_words(a), _name_words(b)
    return bool(wa and wb) and (wa <= wb or wb <= wa)


def _keyword_amount(lines, i, match) -> int | None:
    """Montant après le mot-clé sur la ligne, sinon premier montant des 2 lignes suivantes."""
    after = amounts_in(lines[i][match.end():])
    if after:
        return after[-1] if len(after) > 1 and _RATE.search(lines[i]) is None else after[0]
    for line in lines[i + 1:i + 3]:
        found = amounts_in(line)
        if found:
            return found[0]
    return None


def _candidates(lines, patterns, skip_rate_lines=False) -> list[tuple[int, int]]:
    """(montant, index de ligne) après chaque mot-clé, par priorité du motif puis ordre du texte."""
    found = []
    for pattern in patterns:
        for i, line in enumerate(lines):
            m = pattern.search(line)
            if m is None or (skip_rate_lines and _RATE.search(line)):
                continue
            amount = _keyword_amount(lines, i, m)
            if amount is not None and (abs(amount), i) not in found:
                found.append((abs(amount), i))
    return found


def _row_triples(lines) -> list[tuple[int, int, int, int]]:
    """Lignes de total portant HT, TVA et TTC côte à côte (« TOTAL A PAYER 119,72 6,58 126,30 »)."""
    triples = []
    for i, line in enumerate(lines):
        if not re.search(r"total|t\.?t\.?c|payer", line, re.IGNORECASE):
            continue
        amounts = [abs(a) for a in amounts_in(line)]
        for c in sorted(set(amounts), reverse=True):
            for a in amounts:
                b = c - a
                if 0 <= b < a and b in amounts and _plausible(a, b):
                    triples.append((c, a, b, i))
    return triples


def _plausible(untaxed, tax) -> bool:
    """TVA au plus 20 % du HT (taux normal français), HT positif."""
    return untaxed > 0 and 0 <= tax <= untaxed * MAX_RATE_BP / 10000 + 1


def common_rate(untaxed, tax) -> int | None:
    """Taux usuel (points de base) qui donne cette TVA sur ce HT, au centime près."""
    for rate in COMMON_RATES_BP:
        if untaxed and abs(round(untaxed * rate / 10000) - tax) <= 1:
            return rate
    return None


def _find_discount(lines, total_index) -> int:
    """Remises déduites après le total d'un ticket (« Fidélité Pros -0,76 € »), en centimes."""
    if total_index is None:
        return 0
    discount = 0
    for line in lines[total_index + 1:]:
        if _DISCOUNT_WORDS.search(line):
            discount += sum(-a for a in amounts_in(line) if a < 0)
    return discount


def _find_taxes(lines) -> list[tuple[int, int | None, int]]:
    """Lignes de TVA « TVA 20 % … 28,53 … 142,63 » → (taux, HT ou None, TVA)."""
    taxes = []
    for i, line in enumerate(lines):
        m = _RATE.search(line)
        if not m:
            continue
        rate = int((Decimal(m.group(1).replace(",", ".")) * 100).quantize(Decimal("1")))
        if not 0 <= rate <= 3000:
            continue
        found = [abs(a) for a in amounts_in(line[m.end():])]
        if not found and i + 1 < len(lines):
            found = [abs(a) for a in amounts_in(lines[i + 1])][:2]
        entry = None
        if rate == 0:  # « TVA à 0 % 8,00 € 0,00 € » : base exonérée
            if len(found) >= 2 and 0 in found[:2] and max(found[:2]) > 0:
                entry = (0, max(found[:2]), 0)
        elif len(found) >= 2:
            for tax, base in ((found[0], found[1]), (found[1], found[0])):
                if abs(round(base * rate / 10000) - tax) <= 1:
                    entry = (rate, base, tax)
                    break
        elif len(found) == 1:
            entry = (rate, None, found[0])
        if entry and entry not in taxes:
            taxes.append(entry)
    return taxes


def _choose_amounts(lines, taxes, tax_free, hints: SupplierHints | None = None):
    """(TTC, HT, TVA, index de la ligne du TTC, cohérent).

    Les montants trouvés après chaque libellé sont des candidats ; on retient le premier trio
    où HT + TVA = TTC et TVA ≤ 20 % du HT. L'ordre du texte ne décide plus seul : un tableau
    de totaux en colonnes ou les en-têtes d'un tableau d'articles ne trompent plus la lecture.
    """
    totals = _candidates(lines, _TOTAL_WORDS)
    untaxeds = _candidates(lines, (_UNTAXED_WORDS,), skip_rate_lines=True)
    tax_amounts = _candidates(lines, (_TAX_TOTAL_WORDS,))
    if taxes:
        tax_amounts.append((sum(t[2] for t in taxes), None))
        if None not in (t[1] for t in taxes):
            untaxeds.append((sum(t[1] for t in taxes), None))
    triples = _row_triples(lines)
    for total, untaxed, tax, i in triples:
        totals.append((total, i))
        untaxeds.append((untaxed, i))
        tax_amounts.append((tax, i))
    known_rates = hints.rates if hints is not None else frozenset()
    # Taux habituels du fournisseur d'abord, puis tout trio cohérent.
    for wanted in ((lambda u, x: common_rate(u, x) in known_rates),) * bool(known_rates) + (None,):
        for total, total_index in totals:
            for untaxed, _ in untaxeds:
                for tax, _ in tax_amounts:
                    if abs(untaxed + tax - total) <= 1 and _plausible(untaxed, tax) and (
                            wanted is None or wanted(untaxed, tax)):
                        return total, untaxed, tax, total_index, True
    if totals and tax_free:
        total, total_index = totals[0]
        return total, total, 0, total_index, True
    if totals and hints is not None and hints.tax_free:
        total, total_index = totals[0]  # fournisseur sans TVA jusqu'ici : à vérifier
        return total, total, 0, total_index, False
    total, total_index = totals[0] if totals else (None, None)
    untaxed = untaxeds[0][0] if untaxeds else None
    tax = tax_amounts[0][0] if tax_amounts else None
    rates = {t[0] for t in taxes} or set(known_rates)
    if total is not None and untaxed is None and tax is None and len(rates) == 1:
        rate = rates.pop()  # seul le taux est lu : HT déduit du TTC, à vérifier
        untaxed = (2 * total * 10000 + 10000 + rate) // (2 * (10000 + rate))  # arrondi au plus proche, ½ vers le haut
        return total, untaxed, total - untaxed, total_index, False
    return total, untaxed, tax, total_index, None


def _reconcile_taxes(taxes, untaxed, tax) -> list[tuple[int, int | None, int]]:
    """Ventilation par taux accordée aux montants retenus ; à défaut, déduite du taux usuel."""
    if untaxed is None or tax is None:
        return taxes
    if taxes and abs(sum(t[2] for t in taxes) - tax) <= 1:
        if len(taxes) == 1 and taxes[0][1] is None:
            return [(taxes[0][0], untaxed, tax)]
        return taxes
    rate = common_rate(untaxed, tax) if tax else None
    return [(rate, untaxed, tax)] if rate else []


def _date_after(lines, pattern, exclude=None) -> date | None:
    """Première date qui suit le libellé (sur la ligne, ou seule sur la ligne suivante)."""
    for i, line in enumerate(lines):
        m = pattern.search(line)
        if m is None:
            continue
        start, end = line.rfind("   ", 0, m.start()), line.find("   ", m.end())
        cell = line[start + 3 if start >= 0 else 0:end if end >= 0 else len(line)]
        if exclude is not None and exclude.search(cell):
            continue
        found = dates_in(line[m.start():])
        if not found and not dates_in(line) and i + 1 < len(lines):
            found = dates_in(lines[i + 1])
        if found:
            return found[0]
    return None


def _find_dates(lines) -> tuple[date | None, date | None, bool]:
    """(date de facture, échéance, date de facture devinée)."""
    due = None
    for pattern in _DUE_STRONG:
        due = due or _date_after(lines, pattern, _NOT_DUE)
    due = due or _date_after(lines, _DUE_WORDS, _NOT_DUE)
    issue = _date_after(lines, _ISSUE_STRONG, _NOT_ISSUE)
    if issue is None:
        for i, line in enumerate(lines):
            if _DUE_WORDS.search(line) or _NOT_ISSUE.search(line) or not _ISSUE_WORDS.search(line):
                continue
            found = dates_in(line) or (dates_in(lines[i + 1]) if i + 1 < len(lines) else [])
            if found and found[0] != due:
                issue = found[0]
                break
    guessed = False
    if issue is None:
        first = next((d for line in lines if not _DUE_WORDS.search(line) for d in dates_in(line)),
                     None)
        issue, guessed = first, first is not None
    return issue, due, guessed


def _find_number(lines, shapes=frozenset()) -> str | None:
    """N° de facture ; parmi les candidats, la forme des numéros déjà reçus du fournisseur l'emporte."""
    candidates = []
    for pattern in (_NUMBER_REF, _NUMBER_AFTER_INVOICE, _NUMBER_PIECE, _NUMBER_AFTER_NO):
        for line in lines:
            if pattern is _NUMBER_AFTER_NO and _NUMBER_LINE_SKIP.search(line):
                continue
            for m in pattern.finditer(line):
                value = m.group(1).rstrip(".-/ ")
                if not dates_in(value) and not amounts_in(value):
                    candidates.append(value[:100])
    known = next((c for c in candidates if number_shape(c) in shapes), None)
    return known or (candidates[0] if candidates else None)


def _customer_side(text: str, start: int, other=None) -> bool:
    """Identifiant précédé d'un libellé « client » sur sa ligne (bloc de l'acheteur), ou d'un
    autre libellé exclu (`other`)."""
    before = text[max(text.rfind("\n", 0, start) + 1, start - 30):start]
    return _CUSTOMER.search(before) is not None or (other is not None and other.search(before) is not None)


def _find_siret(text: str, ignore_sirens=(), prefer_siren=None) -> str | None:
    candidates = []
    for pattern in (_SIRET, _SIRET_LABELLED):
        for m in pattern.finditer(text):
            digits = re.sub(r"\D", "", m.group(1))
            if not valid_siret(digits) or digits[:9] in ignore_sirens or _customer_side(
                    text, m.start(), _NOT_SIRET):
                continue
            labelled = pattern is _SIRET_LABELLED or re.search(
                r"siret\W{0,5}$", text[max(0, m.start() - 12):m.start()], re.IGNORECASE)
            candidates.append((digits[:9] != prefer_siren, not labelled, m.start(), digits))
    return min(candidates)[3] if candidates else None


def _find_vat(text: str, ignore_sirens=()) -> str | None:
    for m in _VAT_FR.finditer(text):
        value = re.sub(r"[ .]", "", m.group(0))
        if valid_fr_vat(value) and value[4:] not in ignore_sirens and not _customer_side(text, m.start()):
            return value
    return None


def _find_iban(text: str, ignore) -> str | None:
    for m in _IBAN.finditer(text):
        value = m.group(0).replace(" ", "")
        # L'expression déborde parfois sur le mot suivant : on raccourcit jusqu'à un IBAN valide.
        for end in range(len(value), 14, -1):
            if valid_iban(value[:end]):
                if value[:end] not in ignore:
                    return value[:end]
                break
    return None


def _address_name(lines, ignore_names) -> str | None:
    """Nom en tête d'un bloc d'adresse (« COUTANT LOCATION » puis « 5 rue du champs fleuri »),
    hors bloc de l'organisation elle-même."""
    for i in range(len(lines) - 1):
        name = lines[i].split("   ")[0].strip()
        street = lines[i + 1].split("   ")[0].strip()
        if not _STREET.match(street) or not 2 <= len(name) <= 60 or re.search(r"[\d:@/]", name):
            continue
        if _CUSTOMER.search(name) or any(same_name(name, own) for own in ignore_names):
            continue
        if i > 0 and _CUSTOMER.search(lines[i - 1].split("   ")[0]):
            continue
        return name.title() if name.isupper() else name
    return None


def _find_supplier_name(lines, text, ignore_names=()) -> tuple[str | None, bool]:
    """(nom, deviné) : forme juridique suivie du capital / RCS, sinon bloc d'adresse, sinon site web."""
    for pattern in _LEGAL_NAME:
        for line in lines:
            m = pattern.search(line)
            if m:
                name = re.sub(r"\s+", " ", m.group(1)).strip(" -,.")
                if len(name) >= 2:
                    return name[:200], False
    name = _address_name(lines, ignore_names)
    if name:
        return name[:200], True
    compact = re.sub(r"\s*\n\s*", "", text)
    m = _WEBSITE.search(compact)
    if m:
        return m.group(1).replace("-", " ").title()[:200], True
    return None, True


def parse_text(text: str, origin: str = "text", ignore_ibans=(), ignore_sirens=(),
               ignore_names=(), hints: SupplierHints | None = None) -> Extraction:
    """Champs d'une facture à partir de son texte (natif ou OCR). `ignore_*` : identifiants et nom
    de l'organisation elle-même (bloc client de la facture) ; `hints` : mémoire du fournisseur."""
    ext = Extraction(source=origin)
    if origin == "ocr":
        text = _OCR_DIGIT_O.sub("0", text)
        text = _OCR_THOUSANDS_ONE.sub("1 ", text)
        text = _OCR_GLUED_A.sub(r"\1 à ", text)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    ocr = origin == "ocr"
    ignore_sirens = {s for s in ignore_sirens if s}

    name, guessed = _find_supplier_name(lines, text, ignore_names)
    ext.set("supplier_name", name, origin, check=guessed or ocr)
    vat = _find_vat(text, ignore_sirens)
    ext.set("vat_number", vat, origin, check=ocr)
    ext.set("siret", _find_siret(text, ignore_sirens, vat[4:] if vat else None), origin, check=ocr)
    ext.set("iban", _find_iban(text, set(ignore_ibans)), origin, check=True)
    ext.set("invoice_number", _find_number(lines, hints.number_shapes if hints else frozenset()),
            origin, check=ocr)
    issue, due, issue_guessed = _find_dates(lines)
    ext.set("issue_date", issue, origin, check=ocr or issue_guessed)
    ext.set("due_date", due, origin, check=ocr)
    if _CREDIT_NOTE.search(text):
        ext.set("is_credit_note", True, origin, check=True)

    taxes = _find_taxes(lines)
    total, untaxed, tax, total_index, coherent = _choose_amounts(lines, taxes, bool(_TAX_FREE.search(text)),
                                                                  hints)
    ext.taxes = taxes
    _complete_amounts(ext, total, untaxed, tax, origin, coherent)
    discount = _find_discount(lines, total_index)
    if discount and total and discount < total:
        ext.set("discount", discount, origin, check=True)
    return ext


def _complete_amounts(ext: Extraction, total, untaxed, tax, origin, coherent=None) -> None:
    """Déduit le montant manquant de HT + TVA = TTC ; signale une incohérence ou un montant
    invraisemblable (HT nul, TVA ≥ TTC, TVA au-delà de 20 %, taux qui ne colle pas)."""
    if total is None and untaxed is not None and tax is not None:
        total = untaxed + tax
    elif untaxed is None and total is not None and tax is not None:
        untaxed = total - tax
    elif tax is None and total is not None and untaxed is not None:
        tax = total - untaxed
    ext.taxes = _reconcile_taxes(ext.taxes, untaxed, tax)
    complete = None not in (total, untaxed, tax)
    consistent = complete and abs(untaxed + tax - total) <= 1
    if complete and not consistent:
        ext.warnings.append("HT + TVA ≠ TTC : montants à vérifier.")
    elif consistent and not _plausible(untaxed, tax):
        consistent = False
        ext.warnings.append("Montants peu vraisemblables (HT nul ou TVA trop élevée) : à vérifier.")
    elif consistent and coherent is None and tax and not ext.taxes:
        consistent = False  # trio déduit d'un seul montant, sans taux pour le confirmer
    if total is None:
        ext.warnings.append("Montant TTC introuvable.")
    ext.coherent = bool(consistent and coherent)
    check = origin == "ocr" or not consistent or coherent is False
    for name, value in (("total", total), ("untaxed", untaxed), ("tax", tax)):
        if value is not None:
            ext.set(name, value, origin, check=check)


# ------------------------------------------------------------------ Factur-X

def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _first(root, *path):
    """Premier élément du chemin (noms locaux, espaces de noms ignorés)."""
    return root.find(".//" + "/".join(f"{{*}}{p}" for p in path))


def _text(root, *path) -> str | None:
    node = _first(root, *path)
    return node.text.strip() if node is not None and node.text else None


def _xml_amount(value) -> int | None:
    if value is None:
        return None
    try:
        return abs(int((Decimal(value) * 100).quantize(Decimal("1"))))
    except InvalidOperation:
        return None


def _xml_date(node) -> date | None:
    if node is None:
        return None
    raw = "".join(node.itertext()).strip()
    try:
        return date(int(raw[:4]), int(raw[4:6]), int(raw[6:8]))
    except ValueError:
        return None


def parse_facturx(xml_bytes: bytes) -> Extraction | None:
    """XML CII (Factur-X, ZUGFeRD) → Extraction ; None si illisible ou non CII."""
    if len(xml_bytes) > MAX_XML_SIZE or b"<!DOCTYPE" in xml_bytes[:2048].upper():
        return None
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return None
    if _local(root.tag) != "CrossIndustryInvoice":
        return None
    ext = Extraction(source="facturx")
    origin = "facturx"
    doc = _first(root, "ExchangedDocument")
    if doc is not None:
        ext.set("invoice_number", (_text(doc, "ID") or "")[:100], origin)
        type_code = _text(doc, "TypeCode")
        ext.set("is_credit_note", type_code in ("381", "261", "396") or None, origin)
        ext.set("issue_date", _xml_date(_first(doc, "IssueDateTime")), origin)
    seller = _first(root, "SellerTradeParty")
    if seller is not None:
        name = next((c.text.strip() for c in seller if _local(c.tag) == "Name" and c.text), None)
        ext.set("supplier_name", (name or "")[:200], origin)
        for reg in seller.iter():
            if _local(reg.tag) == "ID" and reg.get("schemeID") == "VA" and reg.text:
                ext.set("vat_number", reg.text.replace(" ", "").upper()[:30], origin)
        legal = _first(seller, "SpecifiedLegalOrganization", "ID")
        if legal is not None and legal.text:
            digits = re.sub(r"\D", "", legal.text)
            if valid_siret(digits):
                ext.set("siret", digits, origin)
    iban = _text(root, "PayeePartyCreditorFinancialAccount", "IBANID")
    ext.set("iban", (iban or "").replace(" ", "").upper()[:34], origin)
    ext.set("due_date", _xml_date(_first(root, "SpecifiedTradePaymentTerms", "DueDateDateTime")),
            origin)
    settlement = _first(root, "ApplicableHeaderTradeSettlement")
    if settlement is not None:
        for tax in (c for c in settlement if _local(c.tag) == "ApplicableTradeTax"):
            rate = _text(tax, "RateApplicablePercent")
            ext.taxes.append((
                int((Decimal(rate or "0") * 100).quantize(Decimal("1"))),
                _xml_amount(_text(tax, "BasisAmount")),
                _xml_amount(_text(tax, "CalculatedAmount")) or 0,
            ))
        summary = _first(settlement, "SpecifiedTradeSettlementHeaderMonetarySummation")
        if summary is not None:
            total = _xml_amount(_text(summary, "GrandTotalAmount"))
            untaxed = _xml_amount(_text(summary, "TaxBasisTotalAmount"))
            tax = _xml_amount(_text(summary, "TaxTotalAmount"))
            _complete_amounts(ext, total, untaxed, tax, origin, coherent=True)
    return ext


def read_facturx(pdf) -> Extraction | None:
    """XML Factur-X embarqué dans le PDF, s'il y en a un."""
    try:
        names = pdf.embfile_names()
    except Exception:  # noqa: BLE001 — PDF sans table des fichiers joints
        return None
    for name in names:
        if name.lower() in FACTURX_NAMES:
            # Pas d'embfile_info : PyMuPDF y décode la somme MD5 binaire en texte et échoue sur
            # certains PDF (ceux de la bibliothèque factur-x notamment). Taille contrôlée après lecture.
            try:
                content = pdf.embfile_get(name)
            except Exception:  # noqa: BLE001 — pièce jointe illisible
                continue
            if len(content) > MAX_XML_SIZE:
                continue
            ext = parse_facturx(content)
            if ext is not None:
                return ext
    return None


# ------------------------------------------------------------------ mise en page

@dataclass
class _Box:
    x0: float
    y0: float
    x1: float
    y1: float
    text: str

    @property
    def height(self) -> float:
        return max(self.y1 - self.y0, 1.0)


def _page_words(page, textpage=None) -> tuple[list[_Box], list[str]]:
    """Mots des lignes horizontales, et texte des lignes pivotées (mentions légales en marge)."""
    words, rotated = [], []
    data = page.get_text("rawdict", textpage=textpage)
    for block in data["blocks"]:
        for line in block.get("lines", ()):
            chars = [c for span in line["spans"] for c in span["chars"]]
            dx, dy = line["dir"]
            if abs(dy) > 0.1 or dx < 0:
                text = "".join(c["c"] for c in chars).strip()
                if text:
                    rotated.append(re.sub(r"\s+", " ", text))
                continue
            current: list = []
            for c in chars + [None]:
                if c is None or not c["c"].strip():
                    if current:
                        xs0, ys0, xs1, ys1 = zip(*(ch["bbox"] for ch in current))
                        words.append(_Box(min(xs0), min(ys0), max(xs1), max(ys1),
                                          "".join(ch["c"] for ch in current)))
                    current = []
                else:
                    current.append(c)
    return words, rotated


def _rows(words: list[_Box]) -> list[list[_Box]]:
    """Mots regroupés en lignes visuelles : recouvrement vertical d'au moins la moitié, sans
    chevauchement horizontal (deux lignes empilées face à une cellule haute restent distinctes)."""
    rows: list[tuple[float, float, list[_Box]]] = []
    for w in sorted(words, key=lambda w: (w.y0 + w.y1) / 2):
        for i, (top, bottom, members) in enumerate(rows):
            overlap = min(bottom, w.y1) - max(top, w.y0)
            if overlap >= 0.5 * min(w.height, bottom - top) and all(
                    w.x0 >= m.x1 - 0.5 or w.x1 <= m.x0 + 0.5 for m in members):
                members.append(w)
                rows[i] = (min(top, w.y0), max(bottom, w.y1), members)
                break
        else:
            rows.append((w.y0, w.y1, [w]))
    rows.sort(key=lambda r: r[0])
    return [sorted(members, key=lambda w: w.x0) for _, _, members in rows]


def _cells(row: list[_Box]) -> list[_Box]:
    """Mots d'une ligne → cellules : un blanc plus large que 0,6 hauteur de ligne les sépare."""
    cells: list[_Box] = []
    for w in row:
        last = cells[-1] if cells else None
        if last is not None and w.x0 - last.x1 < 0.6 * min(w.height, last.height):
            cells[-1] = _Box(last.x0, min(last.y0, w.y0), w.x1, max(last.y1, w.y1),
                             f"{last.text} {w.text}")
        else:
            cells.append(w)
    return cells


_MAPPED_LABEL = re.compile(
    r"total|montant|\bnet\b|t\.?t\.?c|\bh\.?t\b|hors|t\.?v\.?a|\bvat\b|\btax|base|taux|date|"
    r"[ée]ch[ée]ance|facture|invoice|n[°º]|pi[eè]ce|r[ée]f|\bdue\b|amount|subtotal|payer",
    re.IGNORECASE)


def _is_value(text: str) -> bool:
    digits = sum(c.isdigit() for c in text)
    alnum = sum(c.isalnum() for c in text)
    return digits > 0 and (bool(amounts_in(text)) or bool(dates_in(text)) or digits >= 0.3 * alnum)


def _column_values(rows: list[list[_Box]]) -> dict[int, list[str]]:
    """En-têtes de colonne suivis de leur valeur sur une ligne suivante (tableau des totaux :
    « Total HT | Taux TVA | Total TTC » puis les montants dessous) → lignes « libellé : valeur »,
    à insérer après la ligne des valeurs."""
    extra: dict[int, list[str]] = {}
    for r, row in enumerate(rows):
        for k, label in enumerate(row):
            right = row[k + 1] if k + 1 < len(row) else None
            if len(label.text) > 40 or _is_value(label.text) or not _MAPPED_LABEL.search(label.text) or (
                    right is not None and _is_value(right.text)):
                continue
            for below_index in range(r + 1, min(r + 3, len(rows))):
                below = [c for c in rows[below_index]
                         if min(c.x1, label.x1 + label.height) - max(c.x0, label.x0 - label.height) > 0]
                if not below:
                    continue
                center = (label.x0 + label.x1) / 2
                cell = min(below, key=lambda c: abs((c.x0 + c.x1) / 2 - center))
                if _is_value(cell.text) and len(cell.text) <= 40:
                    extra.setdefault(below_index, []).append(f"{label.text} : {cell.text}")
                break
    return extra


def layout_lines(page, textpage=None) -> list[str]:
    """Texte d'une page ligne visuelle par ligne visuelle, cellules séparées par trois blancs ;
    valeurs des tableaux d'en-têtes reportées sous leur libellé ; lignes pivotées à la fin."""
    words, rotated = _page_words(page, textpage)
    return lines_from_words(words, rotated)


def lines_from_words(words: list[_Box], rotated=()) -> list[str]:
    # Cellules sans lettre ni chiffre écartées (filets et marques de scan lus « | », « = »).
    rows = [[c for c in _cells(row) if any(ch.isalnum() or ch in "€%" for ch in c.text)]
            for row in _rows(words)]
    rows = [row for row in rows if row]
    extra = _column_values(rows)
    lines = []
    for i, row in enumerate(rows):
        lines.append("   ".join(c.text for c in row))
        lines.extend(extra.get(i, ()))
    return lines + list(rotated)


# ------------------------------------------------------------------ lecture

def _ocr_dpi(page) -> int:
    return max(72, min(300, int(OCR_MAX_WIDTH_PX * 72 / max(page.rect.width, 1))))


def _ocr_textpage(page):
    return page.get_textpage_ocr(language=OCR_LANGUAGE, dpi=_ocr_dpi(page), full=True)


def _dark_runs(dark, length: int):
    """Pixels pris dans une suite verticale d'au moins `length` pixels sombres."""
    counts = np.vstack([np.zeros((1, dark.shape[1]), np.int32), np.cumsum(dark, axis=0, dtype=np.int32)])
    starts = (counts[length:] - counts[:-length]) == length
    mark = np.zeros_like(dark)
    for k in range(length):
        mark[k:k + starts.shape[0]] |= starts
    return mark


def _clean_scan(page) -> "pymupdf.Pixmap":
    """Image de la page pour une seconde lecture OCR : contraste étiré, bandeaux sombres inversés
    (texte clair sur fond foncé), filets de tableau effacés (Tesseract ignore souvent une ligne
    encadrée, comme le « TOTAL A PAYER » d'une facture d'eau)."""
    pix = page.get_pixmap(dpi=_ocr_dpi(page), colorspace=pymupdf.csGRAY)
    image = ImageOps.autocontrast(Image.frombytes("L", (pix.width, pix.height), pix.samples), cutoff=1)
    pixels = np.asarray(image).copy()
    background = np.asarray(image.filter(ImageFilter.BoxBlur(40)))
    pixels = np.where(background < 100, 255 - pixels, pixels).astype(np.uint8)
    dark = pixels < 140
    pixels[_dark_runs(dark, 60) | _dark_runs(dark.T, 120).T] = 255
    return pymupdf.Pixmap(pymupdf.csGRAY, pix.width, pix.height, pixels.tobytes(), 0)


def _ocr_clean_lines(page) -> list[str]:
    with pymupdf.open("pdf", _clean_scan(page).pdfocr_tobytes(language=OCR_LANGUAGE)) as ocr:
        return layout_lines(ocr[0])


def _open(path, mime):
    if mime in IMAGE_MIMES:
        with pymupdf.open(path) as image:
            return pymupdf.open("pdf", image.convert_to_pdf())
    return pymupdf.open(path, filetype="pdf")


def read(path, mime: str = PDF_MIME, max_pages: int = 3, ignore_ibans=(), ignore_sirens=(),
         ignore_names=(), hints_for=None) -> Extraction:
    """Lit une facture (PDF, JPEG, PNG). `ignore_*` : IBAN, SIREN et nom de l'organisation ;
    `hints_for(extraction)` : mémoire du fournisseur reconnu (`SupplierHints` ou None), la
    lecture est alors refaite avec elle."""
    try:
        doc = _open(path, mime)
    except Exception as exc:  # noqa: BLE001 — fichier corrompu ou chiffré
        return Extraction(warnings=[f"Fichier illisible : {exc}"])
    with doc:
        facturx = read_facturx(doc) if mime == PDF_MIME else None
        texts, scanned, warnings = [], [], []
        for page in list(doc)[:max_pages]:
            lines = layout_lines(page)
            if len("".join(lines).strip()) < MIN_PAGE_TEXT:
                try:
                    lines = layout_lines(page, _ocr_textpage(page))
                    scanned.append(page.number)
                except Exception as exc:  # noqa: BLE001 — Tesseract absent ou en échec
                    if not warnings:
                        warnings.append(f"OCR indisponible ({exc}) : saisissez les champs.")
            texts.append("\n".join(lines))
        origin = "ocr" if scanned else "text"
        from_text = parse_text("\n".join(texts), origin, ignore_ibans, ignore_sirens, ignore_names)
        if scanned and not from_text.coherent:
            # Montants non confirmés : seconde lecture des pages scannées, image nettoyée ; les
            # lignes des deux lectures sont réunies, la cohérence HT + TVA = TTC fait le tri.
            extra = [line for number in scanned for line in _ocr_clean_lines(doc[number])]
            second = parse_text("\n".join(texts + extra), origin, ignore_ibans, ignore_sirens,
                                ignore_names)
            if second.coherent or len(second.fields) > len(from_text.fields):
                from_text, texts = second, texts + extra
        hints = hints_for(from_text) if hints_for is not None and facturx is None else None
        if hints is not None:
            from_text = parse_text("\n".join(texts), origin, ignore_ibans, ignore_sirens,
                                   ignore_names, hints)
    from_text.warnings[:0] = warnings
    if facturx is None:
        if not any(t.strip() for t in texts) and not warnings:
            from_text.warnings.insert(0, "Aucun texte lisible dans le fichier.")
        if not from_text.fields:
            from_text.source = "none"
        return from_text
    # Factur-X fait foi ; le texte ne complète que les champs absents du XML.
    for name, f in from_text.fields.items():
        if name not in facturx.fields and name not in AMOUNT_FIELDS:
            facturx.fields[name] = Field(f.value, f.origin, True)
    return facturx
