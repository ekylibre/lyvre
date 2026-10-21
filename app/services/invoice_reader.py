"""Lecture d'une facture d'achat : Factur-X, texte du PDF, OCR (Tesseract).

`read(path, mime)` renvoie une `Extraction` : pour chaque champ trouvé, sa valeur,
son origine (`facturx`, `text`, `ocr`) et s'il est « à vérifier ». Rien n'est
enregistré ici : l'extraction sert à préremplir le formulaire de saisie.

Ordre de lecture : XML Factur-X / ZUGFeRD embarqué (valeurs exactes) ; sinon le
texte natif des premières pages ; une page sans texte (scan, photo) passe par
l'OCR français. Tesseract absent : avertissement, lecture texte conservée.

Les montants sont en centimes, les taux en points de base (2000 = 20 %).
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation

import pymupdf

PDF_MIME = "application/pdf"
IMAGE_MIMES = ("image/jpeg", "image/png")
FACTURX_NAMES = ("factur-x.xml", "zugferd-invoice.xml", "xrechnung.xml")
MAX_XML_SIZE = 1024 * 1024
MIN_PAGE_TEXT = 30       # en dessous : page scannée, OCR
OCR_MAX_WIDTH_PX = 2500  # résolution du rendu OCR (une photo n'est pas agrandie)
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

    def value(self, name, default=None):
        f = self.fields.get(name)
        return f.value if f is not None else default

    def set(self, name, value, origin, check=False):
        if value is not None and value != "":
            self.fields[name] = Field(value, origin, check)


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
}
_DATE_PATTERNS = (
    re.compile(r"\b(\d{1,2})(?:er)?\s+(" + "|".join(sorted(MONTHS, key=len, reverse=True))
               + r")\.?\s+(\d{4})\b", re.IGNORECASE),
    re.compile(r"\b(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{4}|\d{2})\b"),
    re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b"),
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
                else:
                    year, month, day = int(a), int(b), int(c)
                if 2000 <= year <= 2100:
                    found.append((m.start(), date(year, month, day)))
            except (ValueError, KeyError):
                continue
    return [d for _, d in sorted(found, key=lambda x: x[0])]


# ------------------------------------------------------------------ texte

_DUE_WORDS = re.compile(r"échéance|echeance|à payer le|a payer le|payable|date limite|prélev|"
                        r"prelev|exigible|due date", re.IGNORECASE)
_ISSUE_WORDS = re.compile(r"date (?:de (?:la )?)?(?:facture|facturation|d'émission|émission)|"
                          r"facture|invoice|émise|emise|\bdu\b|\ble\b|\bdate\b", re.IGNORECASE)
_TOTAL_WORDS = (  # par priorité
    re.compile(r"net\s+à\s+payer|net\s+a\s+payer|somme\s+à\s+payer|montant\s+à\s+payer|"
               r"total\s+à\s+payer|reste\s+à\s+payer", re.IGNORECASE),
    re.compile(r"total\s+t\.?t\.?c|montant\s+t\.?t\.?c|ttc\s+total|total\s+général|"
               r"total\s+facture|amount due|grand total", re.IGNORECASE),
    re.compile(r"^\s*total\b(?!.*\b(?:ht|h\.t|tva|hors)\b)", re.IGNORECASE),
)
_UNTAXED_WORDS = re.compile(r"total\s+h\.?t\b|montant\s+h\.?t\b|base\s+h\.?t\b|total hors tax|"
                            r"sous-total", re.IGNORECASE)
_TAX_TOTAL_WORDS = re.compile(r"total\s+t\.?v\.?a|montant\s+t\.?v\.?a|dont\s+t\.?v\.?a", re.IGNORECASE)
_RATE = re.compile(r"(?:t\.?v\.?a|vat)[^%\n]{0,20}?(\d{1,2}(?:[,.]\d{1,2})?)\s?%", re.IGNORECASE)
_NUMBER_LINE_SKIP = re.compile(r"carte|client|abonn|commande|t\.?v\.?a|siret|siren|t[ée]l|"
                               r"fid[ée]lit|rcs|compte|contrat|lot\b|devis|bon\b|iban|bic",
                               re.IGNORECASE)
_NUMBER_AFTER_INVOICE = re.compile(
    r"\b(?:facture|invoice|avoir)\s*(?:n[°ºo]\.?|num(?:[ée]ro)?\.?|#)?\s*:?\s*"
    r"([A-Z0-9][\w\-/.]*\d[\w\-/.]*)", re.IGNORECASE)
_NUMBER_AFTER_NO = re.compile(r"(?:\bn[°º]|\bnum[ée]ro\b|\bno\b\.?)\s*:?\s*([A-Z0-9][\w\-/.]*\d[\w\-/.]*)",
                              re.IGNORECASE)
_LEGAL_FORMS = r"SASU|SAS|SARL|EURL|SNC|SCOP|SELARL|GIE|SA|SCI"
_LEGAL_NAME = re.compile(
    r"^\s*([A-Z0-9][\w&'’.\- ]{0,60}?)[\s,]+(?:" + _LEGAL_FORMS + r")\b.{0,120}?"
    r"(?:capital|RCS|SIRE[NT])", re.IGNORECASE)
_WEBSITE = re.compile(r"www\.([a-z0-9-]{2,40})\.(?:fr|com|eu|net|org|be|ch)", re.IGNORECASE)
_SIRET = re.compile(r"\b(\d{3}[ .]?\d{3}[ .]?\d{3}[ .]?\d{5})\b")
_VAT_FR = re.compile(r"\bFR(?:[ .]?[0-9A-HJ-NP-Z]){2}(?:[ .]?\d){9}\b")
_IBAN = re.compile(r"\b[A-Z]{2}\d{2}(?:[ ]?[A-Z0-9]){11,30}\b")
_CREDIT_NOTE = re.compile(r"^\s*(?:facture\s+d'|)avoir\b|\bavoir\s+n[°º]|note\s+de\s+cr[ée]dit|"
                          r"credit\s+note", re.IGNORECASE | re.MULTILINE)
_DISCOUNT_WORDS = re.compile(r"fid[ée]lit|remise|r[ée]duction|bon d'achat|coupon|ristourne",
                             re.IGNORECASE)
_OCR_DIGIT_O = re.compile(r"(?<=\d)[Oo]|[Oo](?=\d)")


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


def _find_total(lines) -> tuple[int | None, int | None]:
    """(TTC, index de sa ligne)."""
    for pattern in _TOTAL_WORDS:
        for i, line in enumerate(lines):
            m = pattern.search(line)
            if m:
                amount = _keyword_amount(lines, i, m)
                if amount is not None and amount > 0:
                    return amount, i
    return None, None


def _find_discount(lines, total_index) -> int:
    """Remises déduites après le total d'un ticket (« Fidélité Pros -0,76 € »), en centimes."""
    if total_index is None:
        return 0
    discount = 0
    for line in lines[total_index + 1:]:
        if _DISCOUNT_WORDS.search(line):
            discount += sum(-a for a in amounts_in(line) if a < 0)
    return discount


def _find_keyword(lines, pattern) -> int | None:
    for i, line in enumerate(lines):
        m = pattern.search(line)
        if m and (_RATE.search(line) is None or pattern is _TAX_TOTAL_WORDS):
            amount = _keyword_amount(lines, i, m)
            if amount is not None:
                return abs(amount)
    return None


def _find_taxes(lines) -> list[tuple[int, int | None, int]]:
    """Lignes de TVA « TVA 20 % … 28,53 … 142,63 » → (taux, HT ou None, TVA)."""
    taxes = []
    for i, line in enumerate(lines):
        m = _RATE.search(line)
        if not m:
            continue
        rate = int((Decimal(m.group(1).replace(",", ".")) * 100).quantize(Decimal("1")))
        if not 0 < rate <= 3000:
            continue
        found = [abs(a) for a in amounts_in(line[m.end():])]
        if not found and i + 1 < len(lines):
            found = [abs(a) for a in amounts_in(lines[i + 1])][:2]
        entry = None
        if len(found) >= 2:
            for tax, base in ((found[0], found[1]), (found[1], found[0])):
                if abs(round(base * rate / 10000) - tax) <= 1:
                    entry = (rate, base, tax)
                    break
        elif len(found) == 1:
            entry = (rate, None, found[0])
        if entry and entry not in taxes:
            taxes.append(entry)
    return taxes


def _find_dates(lines) -> tuple[date | None, date | None, bool]:
    """(date de facture, échéance, date de facture devinée)."""
    issue = due = None
    guessed = False
    for i, line in enumerate(lines):
        found = dates_in(line) or (dates_in(lines[i + 1]) if i + 1 < len(lines)
                                   and not dates_in(line) else [])
        if not found:
            continue
        if _DUE_WORDS.search(line):
            due = due or found[0]
        elif _ISSUE_WORDS.search(line) and issue is None:
            issue = found[0]
    if issue is None:
        first = next((d for line in lines if not _DUE_WORDS.search(line) for d in dates_in(line)),
                     None)
        issue, guessed = first, first is not None
    return issue, due, guessed


def _find_number(lines) -> str | None:
    for pattern in (_NUMBER_AFTER_INVOICE, _NUMBER_AFTER_NO):
        for line in lines:
            if pattern is _NUMBER_AFTER_NO and _NUMBER_LINE_SKIP.search(line):
                continue
            m = pattern.search(line)
            if m:
                return m.group(1).rstrip(".-/")[:100]
    return None


def _find_siret(text: str) -> str | None:
    candidates = []
    for m in _SIRET.finditer(text):
        digits = re.sub(r"\D", "", m.group(1))
        if valid_siret(digits):
            labelled = re.search(r"siret\W{0,5}$", text[max(0, m.start() - 12):m.start()], re.IGNORECASE)
            candidates.append((not labelled, m.start(), digits))
    return min(candidates)[2] if candidates else None


def _find_vat(text: str) -> str | None:
    for m in _VAT_FR.finditer(text):
        value = re.sub(r"[ .]", "", m.group(0))
        if valid_fr_vat(value):
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


def _find_supplier_name(lines, text) -> tuple[str | None, bool]:
    """(nom, deviné) : forme juridique suivie du capital / RCS, sinon site web."""
    for line in lines:
        m = _LEGAL_NAME.search(line)
        if m:
            name = re.sub(r"\s+", " ", m.group(1)).strip(" -,.")
            if len(name) >= 2:
                return name[:200], False
    compact = re.sub(r"\s*\n\s*", "", text)
    m = _WEBSITE.search(compact)
    if m:
        return m.group(1).replace("-", " ").title()[:200], True
    return None, True


def parse_text(text: str, origin: str = "text", ignore_ibans=()) -> Extraction:
    """Champs d'une facture à partir de son texte (natif ou OCR)."""
    ext = Extraction(source=origin)
    if origin == "ocr":
        text = _OCR_DIGIT_O.sub("0", text)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    ocr = origin == "ocr"

    name, guessed = _find_supplier_name(lines, text)
    ext.set("supplier_name", name, origin, check=guessed or ocr)
    ext.set("vat_number", _find_vat(text), origin, check=ocr)
    ext.set("siret", _find_siret(text), origin, check=ocr)
    ext.set("iban", _find_iban(text, set(ignore_ibans)), origin, check=True)
    ext.set("invoice_number", _find_number(lines), origin, check=ocr)
    issue, due, issue_guessed = _find_dates(lines)
    ext.set("issue_date", issue, origin, check=ocr or issue_guessed)
    ext.set("due_date", due, origin, check=ocr)
    if _CREDIT_NOTE.search(text):
        ext.set("is_credit_note", True, origin, check=True)

    ext.taxes = _find_taxes(lines)
    total, total_index = _find_total(lines)
    untaxed = _find_keyword(lines, _UNTAXED_WORDS)
    tax = _find_keyword(lines, _TAX_TOTAL_WORDS)
    if ext.taxes:
        tax = sum(t[2] for t in ext.taxes)
        bases = [t[1] for t in ext.taxes]
        if None not in bases and (untaxed is None or untaxed != sum(bases)):
            if total is None or sum(bases) + tax == total:
                untaxed = sum(bases)
    _complete_amounts(ext, total, untaxed, tax, origin)
    discount = _find_discount(lines, total_index)
    if discount and total and discount < total:
        ext.set("discount", discount, origin, check=True)
    return ext


def _complete_amounts(ext: Extraction, total, untaxed, tax, origin) -> None:
    """Déduit le montant manquant de HT + TVA = TTC ; signale une incohérence."""
    if total is None and untaxed is not None and tax is not None:
        total = untaxed + tax
    elif untaxed is None and total is not None and tax is not None:
        untaxed = total - tax
    elif tax is None and total is not None and untaxed is not None:
        tax = total - untaxed
    if len(ext.taxes) == 1 and ext.taxes[0][1] is None and untaxed is not None:
        rate, _, vat = ext.taxes[0]
        ext.taxes[0] = (rate, untaxed, vat)
    consistent = None not in (total, untaxed, tax) and abs(untaxed + tax - total) <= 1
    if None not in (total, untaxed, tax) and not consistent:
        ext.warnings.append("HT + TVA ≠ TTC : montants à vérifier.")
    if total is None:
        ext.warnings.append("Montant TTC introuvable.")
    check = origin == "ocr" or not consistent
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
            _complete_amounts(ext, total, untaxed, tax, origin)
    return ext


def read_facturx(pdf) -> Extraction | None:
    """XML Factur-X embarqué dans le PDF, s'il y en a un."""
    try:
        names = pdf.embfile_names()
    except Exception:  # noqa: BLE001 — PDF sans table des fichiers joints
        return None
    for name in names:
        if name.lower() in FACTURX_NAMES:
            info = pdf.embfile_info(name)
            if (info.get("size") or 0) > MAX_XML_SIZE:
                continue
            ext = parse_facturx(pdf.embfile_get(name))
            if ext is not None:
                return ext
    return None


# ------------------------------------------------------------------ lecture

def _ocr_page(page) -> str:
    dpi = max(72, min(300, int(OCR_MAX_WIDTH_PX * 72 / max(page.rect.width, 1))))
    textpage = page.get_textpage_ocr(language="fra", dpi=dpi, full=True)
    return page.get_text(textpage=textpage)


def _open(path, mime):
    if mime in IMAGE_MIMES:
        with pymupdf.open(path) as image:
            return pymupdf.open("pdf", image.convert_to_pdf())
    return pymupdf.open(path, filetype="pdf")


def read(path, mime: str = PDF_MIME, max_pages: int = 3, ignore_ibans=()) -> Extraction:
    """Lit une facture (PDF, JPEG, PNG). `ignore_ibans` : IBAN propres à l'organisation."""
    try:
        doc = _open(path, mime)
    except Exception as exc:  # noqa: BLE001 — fichier corrompu ou chiffré
        return Extraction(warnings=[f"Fichier illisible : {exc}"])
    with doc:
        facturx = read_facturx(doc) if mime == PDF_MIME else None
        texts, used_ocr, warnings = [], False, []
        for page in list(doc)[:max_pages]:
            text = page.get_text()
            if len(text.strip()) < MIN_PAGE_TEXT:
                try:
                    text = _ocr_page(page)
                    used_ocr = True
                except Exception as exc:  # noqa: BLE001 — Tesseract absent ou en échec
                    if not warnings:
                        warnings.append(f"OCR indisponible ({exc}) : saisissez les champs.")
            texts.append(text)
    origin = "ocr" if used_ocr else "text"
    from_text = parse_text("\n".join(texts), origin, ignore_ibans)
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
