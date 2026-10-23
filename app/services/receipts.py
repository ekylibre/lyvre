"""Reçus fiscaux (lot B) — B.1 : paramètres de l'instance et signature ; B.2 : candidats, émission,
PDF.

- L'outil **n'évalue pas l'éligibilité** : l'administrateur déclare la situation de la structure
  (intérêt général, utilité publique, autre cas du CGI, rescrit éventuel) et **reconnaît sa
  responsabilité** à l'activation (date et auteur conservés ; à reconfirmer si l'éligibilité change).
- Activation refusée tant que les mentions obligatoires du reçu manquent : identité et adresse de
  la structure, objet, signataire, au moins un article du CGI, des comptes de dons existants.
- La signature (PNG ou JPEG, 500 Ko au plus) est rangée avec les pièces de l'instance (donc dans
  les sauvegardes) ; son chemin est sur `organization.signature_path`.
"""
import hashlib
import json
from datetime import date, datetime
from pathlib import Path

from sqlalchemy import update

from app.extensions import db
from app.models import (
    Account, BankTransaction, DonationReceipt, DonationReceiptItem, Entity, InKindDonation, JournalEntry, JournalLine,
    ReceiptCounter, ReceiptSettings,
)
from app.models.receipt import (
    CGI_ARTICLES, DEFAULT_DONATION_PREFIXES, ELIGIBILITY, FORMS, NATURES, PAYMENT_METHODS,
)
from app.services import organization
from app.services.attachments import instance_dir
from app.utils.money import euros, euros_in_words

SIGNATURE_MAX = 500 * 1024
SIGNATURE_TYPES = {b"\x89PNG\r\n\x1a\n": ".png", b"\xff\xd8\xff": ".jpg"}


class ReceiptError(Exception):
    def __init__(self, message, field=None, status=422):
        super().__init__(message)
        self.message, self.field, self.status = message, field, status


def get() -> ReceiptSettings:
    settings = db.session.query(ReceiptSettings).order_by(ReceiptSettings.id).first()
    if settings is None:
        settings = ReceiptSettings(enabled=False, default_mode="annual",
                                   cgi_articles_json=json.dumps(["200"]),
                                   donation_prefixes_json=json.dumps(DEFAULT_DONATION_PREFIXES))
        db.session.add(settings)
        db.session.commit()
    return settings


def articles(settings) -> list[str]:
    return json.loads(settings.cgi_articles_json or "[]")


def prefixes(settings) -> list[str]:
    return json.loads(settings.donation_prefixes_json or "[]")


def donation_accounts(codes) -> list[Account]:
    """Comptes utilisables couverts par les préfixes de dons (7541 → 7541, 75411…)."""
    if not codes:
        return []
    return (Account.query.filter(Account.is_header.is_(False), db.or_(*[Account.code.like(f"{c}%") for c in codes]))
            .order_by(Account.code).all())


def readiness(settings=None) -> list[dict]:
    """Mentions du reçu : chaque point est `ok` ou à compléter (avec l'écran où le faire)."""
    settings = settings or get()
    org = organization.get()
    structure = "/configuration/organization"
    items = [
        ("identity", "Raison sociale et SIREN ou RNA de la structure", bool(org.name and (org.siren or org.rna)), structure),
        ("address", "Adresse de la structure", bool(org.address_line1 and org.postal_code and org.city), structure),
        ("purpose", "Objet de la structure", bool(org.purpose), structure),
        ("signatory", "Nom et qualité du signataire", bool(org.signatory_name and org.signatory_title), structure),
        ("signature", "Image de la signature", bool(org.signature_path and _instance_file(org.signature_path)), None),
        ("eligibility", "Éligibilité déclarée", bool(settings.eligibility), None),
        ("articles", "Article(s) du CGI", bool(articles(settings)), None),
        ("accounts", "Comptes de dons présents dans le plan", bool(donation_accounts(prefixes(settings))), "/accounts/"),
    ]
    return [{"key": k, "label": label, "ok": ok, "url": url} for k, label, ok, url in items]


def payload(settings=None) -> dict:
    settings = settings or get()
    return {
        "enabled": settings.enabled, "eligibility": settings.eligibility,
        "eligibility_detail": settings.eligibility_detail or "", "rescrit_ref": settings.rescrit_ref or "",
        "cgi_articles": articles(settings), "donation_prefixes": prefixes(settings),
        "donation_accounts": [{"code": a.code, "label": a.label} for a in donation_accounts(prefixes(settings))],
        "default_mode": settings.default_mode,
        "acknowledged_at": settings.acknowledged_at.isoformat() + "Z" if settings.acknowledged_at else None,
        "readiness": readiness(settings),
        "options": {"eligibility": [{"value": k, "label": v} for k, v in ELIGIBILITY.items()],
                    "cgi_articles": [{"value": k, "label": v} for k, v in CGI_ARTICLES.items()],
                    "modes": [{"value": "annual", "label": "Reçu annuel récapitulatif"},
                              {"value": "single", "label": "Un reçu par don"}]},
    }


def save(data: dict, user_id=None) -> ReceiptSettings:
    organization.get()  # créée (avec commit) avant toute modification des paramètres
    settings = get()
    eligibility = data.get("eligibility") or None
    if eligibility is not None and eligibility not in ELIGIBILITY:
        raise ReceiptError("Éligibilité inconnue.", "eligibility")
    chosen = data.get("cgi_articles") or []
    if not isinstance(chosen, list) or any(a not in CGI_ARTICLES for a in chosen):
        raise ReceiptError("Article du CGI inconnu.", "cgi_articles")
    codes = [str(c).strip() for c in (data.get("donation_prefixes") or []) if str(c).strip()]
    if any(not c.isdigit() or not c.startswith("7") for c in codes):
        raise ReceiptError("Comptes de dons : préfixes de comptes de produits (7…).", "donation_prefixes")
    mode = data.get("default_mode") or "annual"
    if mode not in ("annual", "single"):
        raise ReceiptError("Mode d'émission inconnu.", "default_mode")
    if eligibility == "other" and not (data.get("eligibility_detail") or "").strip():
        raise ReceiptError("Précisez le cas prévu par le CGI.", "eligibility_detail")
    changed_eligibility = eligibility != settings.eligibility
    settings.eligibility = eligibility
    settings.eligibility_detail = (data.get("eligibility_detail") or "").strip() or None
    settings.rescrit_ref = (data.get("rescrit_ref") or "").strip()[:100] or None
    settings.cgi_articles_json = json.dumps([a for a in CGI_ARTICLES if a in chosen])
    settings.donation_prefixes_json = json.dumps(list(dict.fromkeys(codes)))
    settings.default_mode = mode
    if changed_eligibility:
        settings.acknowledged_at = settings.acknowledged_by_user_id = None
    if data.get("acknowledged"):
        settings.acknowledged_at, settings.acknowledged_by_user_id = datetime.utcnow(), user_id
    enable = bool(data.get("enabled"))
    if enable:
        missing = [item["label"] for item in readiness(settings) if not item["ok"]]
        if missing:
            db.session.rollback()
            raise ReceiptError("Activation impossible, à compléter : " + " ; ".join(missing) + ".", "enabled")
        if settings.acknowledged_at is None:
            db.session.rollback()
            raise ReceiptError("Cochez la déclaration de responsabilité sur l'éligibilité.", "acknowledged")
    settings.enabled = enable
    db.session.commit()
    return settings


# ------------------------------------------------------------------ signature


def _instance_file(relative: str) -> Path | None:
    """Fichier rangé avec les pièces de l'instance (signature, PDF des reçus), s'il existe."""
    path = (instance_dir() / relative).resolve()
    return path if path.is_relative_to(instance_dir().resolve()) and path.is_file() else None


def signature_file() -> Path | None:
    org = organization.get()
    return _instance_file(org.signature_path) if org.signature_path else None


def save_signature(file_storage) -> None:
    if file_storage is None or not file_storage.filename:
        raise ReceiptError("Aucun fichier.", "signature")
    body = file_storage.stream.read(SIGNATURE_MAX + 1)
    if len(body) > SIGNATURE_MAX:
        raise ReceiptError("Image trop volumineuse (500 Ko au plus).", "signature")
    suffix = next((ext for magic, ext in SIGNATURE_TYPES.items() if body.startswith(magic)), None)
    if suffix is None:
        raise ReceiptError("Image PNG ou JPEG attendue.", "signature")
    folder = instance_dir() / "recus"
    folder.mkdir(parents=True, exist_ok=True)
    for old in folder.glob("signature.*"):
        old.unlink()
    (folder / f"signature{suffix}").write_bytes(body)
    org = organization.get()
    org.signature_path = f"recus/signature{suffix}"
    db.session.commit()


def delete_signature() -> None:
    org = organization.get()
    path = signature_file()
    if path is not None:
        path.unlink()
    org.signature_path = None
    settings = get()
    if settings.enabled:
        settings.enabled = False  # plus de signature : plus d'émission possible
    db.session.commit()


# ------------------------------------------------------------------ B.2 : candidats, émission, PDF

PAYMENT_BY_PREFIX = (("53", "cash"), ("511", "check"), ("512", "transfer"), ("517", "transfer"))


def _year_bounds(year: int):
    return date(year, 1, 1), date(year, 12, 31)


def issued_line_ids() -> set[int]:
    rows = (db.session.query(DonationReceiptItem.journal_line_id)
            .join(DonationReceipt, DonationReceipt.id == DonationReceiptItem.receipt_id)
            .filter(DonationReceipt.status == "issued", DonationReceiptItem.journal_line_id.isnot(None)))
    return {line_id for (line_id,) in rows}


def issued_in_kind_ids() -> set[int]:
    rows = (db.session.query(DonationReceiptItem.in_kind_id)
            .join(DonationReceipt, DonationReceipt.id == DonationReceiptItem.receipt_id)
            .filter(DonationReceipt.status == "issued", DonationReceiptItem.in_kind_id.isnot(None)))
    return {item_id for (item_id,) in rows}


def donation_lines(year: int) -> list[JournalLine]:
    codes = prefixes(get())
    if not codes:
        return []
    start, end = _year_bounds(year)
    return (JournalLine.query.join(JournalEntry, JournalEntry.id == JournalLine.entry_id)
            .join(Account, Account.id == JournalLine.account_id)
            .filter(JournalEntry.entry_date.between(start, end),
                    db.or_(*[Account.code.like(f"{c}%") for c in codes]),
                    JournalLine.credit_cents > JournalLine.debit_cents)
            .order_by(JournalEntry.entry_date, JournalLine.id).all())


def resolve_donors(lines) -> dict[int, int | None]:
    """Donateur de chaque ligne : choisi sur la ligne, sinon tiers de la transaction bancaire
    rapprochée avec l'écriture, sinon tiers dont le compte figure dans l'écriture."""
    entry_ids = {line.entry_id for line in lines}
    by_bank = dict(db.session.query(JournalLine.entry_id, BankTransaction.entity_id)
                   .join(BankTransaction, BankTransaction.journal_line_id == JournalLine.id)
                   .filter(JournalLine.entry_id.in_(entry_ids or {0}), BankTransaction.entity_id.isnot(None)).all())
    by_code = {e.account_code: e.id for e in Entity.query.filter(Entity.account_code.isnot(None))}
    by_account = {}
    if by_code:
        for entry_id, code in (db.session.query(JournalLine.entry_id, Account.code)
                               .join(Account, Account.id == JournalLine.account_id)
                               .filter(JournalLine.entry_id.in_(entry_ids or {0}), Account.code.in_(list(by_code)))):
            by_account.setdefault(entry_id, by_code[code])
    return {line.id: line.entity_id or by_bank.get(line.entry_id) or by_account.get(line.entry_id) for line in lines}


def payment_method(line: JournalLine) -> str:
    for other in line.entry.lines:
        for prefix, method in PAYMENT_BY_PREFIX:
            if other.id != line.id and other.account.code.startswith(prefix):
                return method
    return "none"


def donor_problems(entity: Entity) -> list[str]:
    """Mentions du donateur manquantes pour son reçu."""
    problems = []
    if entity.person_kind not in ("individual", "company"):
        problems.append("nature (particulier ou entreprise)")
    if not (entity.address_line1 and entity.postal_code and entity.city):
        problems.append("adresse")
    if entity.person_kind == "company" and not entity.siret:
        problems.append("SIRET (SIREN de l'entreprise)")
    return problems


def candidates(year: int) -> dict:
    """Dons de l'année civile non encore repris sur un reçu émis, par donateur ; lignes sans donateur."""
    lines = [l for l in donation_lines(year) if l.id not in issued_line_ids()]
    donors = resolve_donors(lines)
    groups: dict[int, dict] = {}
    unassigned = []
    for line in lines:
        item = {"kind": "line", "id": line.id, "date": line.entry.entry_date.isoformat(), "reference": line.entry.reference,
                "entry_url": f"/entries/{line.entry_id}", "label": line.label or line.entry.description or "",
                "account": line.account.code, "amount_cents": line.credit_cents - line.debit_cents,
                "payment_method": payment_method(line)}
        entity_id = donors[line.id]
        if entity_id is None:
            unassigned.append(item)
            continue
        groups.setdefault(entity_id, {"items": []})["items"].append(item)
    start, end = _year_bounds(year)
    done = issued_in_kind_ids()
    for gift in InKindDonation.query.filter(InKindDonation.date.between(start, end)).order_by(InKindDonation.date):
        if gift.id in done:
            continue
        groups.setdefault(gift.entity_id, {"items": []})["items"].append({
            "kind": "in_kind", "id": gift.id, "date": gift.date.isoformat(), "reference": None, "entry_url": None,
            "label": gift.description, "account": None, "amount_cents": gift.valuation_cents, "payment_method": "none"})
    out = []
    for entity_id, group in groups.items():
        entity = db.session.get(Entity, entity_id)
        out.append({"entity_id": entity_id, "name": entity.name, "person_kind": entity.person_kind,
                    "email": entity.email, "problems": donor_problems(entity), "items": group["items"],
                    "total_cents": sum(i["amount_cents"] for i in group["items"])})
    out.sort(key=lambda g: g["name"].lower())
    return {"year": year, "donors": out, "unassigned": unassigned,
            "total_cents": sum(g["total_cents"] for g in out)}


def assign_donor(line_id: int, entity_id) -> JournalLine:
    line = db.session.get(JournalLine, line_id)
    codes = prefixes(get())
    if line is None or not any(line.account.code.startswith(c) for c in codes):
        raise ReceiptError("Ligne de don introuvable.", status=404)
    if line.id in issued_line_ids():
        raise ReceiptError("Don déjà repris sur un reçu émis.", status=409)
    entity = db.session.get(Entity, int(entity_id)) if entity_id not in (None, "") else None
    if entity_id not in (None, "") and entity is None:
        raise ReceiptError("Tiers inconnu.", "entity_id")
    line.entity_id = entity.id if entity else None
    db.session.commit()
    return line


# --- dons en nature


def save_in_kind(data: dict) -> InKindDonation:
    entity = db.session.get(Entity, data.get("entity_id")) if isinstance(data.get("entity_id"), int) else None
    if entity is None:
        raise ReceiptError("Donateur obligatoire.", "entity_id")
    try:
        when = date.fromisoformat(str(data.get("date") or ""))
    except ValueError:
        raise ReceiptError("Date invalide.", "date") from None
    description = (data.get("description") or "").strip()[:300]
    if not description:
        raise ReceiptError("Description du don obligatoire.", "description")
    value = data.get("valuation_cents")
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ReceiptError("Valorisation positive attendue.", "valuation_cents")
    gift = InKindDonation(entity_id=entity.id, date=when, description=description, valuation_cents=value,
                          valuation_method=(data.get("valuation_method") or "").strip()[:300] or None)
    db.session.add(gift)
    db.session.commit()
    return gift


def delete_in_kind(gift_id: int) -> None:
    gift = db.session.get(InKindDonation, gift_id)
    if gift is None:
        raise ReceiptError("Don en nature introuvable.", status=404)
    if gift.id in issued_in_kind_ids():
        raise ReceiptError("Don repris sur un reçu émis : annulez d'abord le reçu.", status=409)
    db.session.delete(gift)
    db.session.commit()


# --- émission


def _next_number(year: int) -> str:
    """Numéro suivant, réservé dans la transaction en cours (verrou d'écriture sur le compteur) :
    annulée avec elle si l'émission échoue, donc sans trou."""
    updated = db.session.execute(
        update(ReceiptCounter).where(ReceiptCounter.year == year).values(last_number=ReceiptCounter.last_number + 1))
    if updated.rowcount == 0:
        db.session.add(ReceiptCounter(year=year, last_number=1))
        db.session.flush()
    number = db.session.query(ReceiptCounter.last_number).filter(ReceiptCounter.year == year).scalar()
    return f"{year}-{number:05d}"


def _donor_snapshot(entity: Entity) -> dict:
    return {"name": entity.name, "address_line1": entity.address_line1, "address_line2": entity.address_line2,
            "postal_code": entity.postal_code, "city": entity.city, "country": entity.country or "France",
            "siren": (entity.siret or "")[:9] or None, "email": entity.email}


def check_issue(year: int, mode=None) -> str:
    """Contrôles préalables à une émission (avant de lancer le job) ; renvoie le mode retenu."""
    settings = get()
    if not settings.enabled:
        raise ReceiptError("Reçus fiscaux non activés (Configuration › Reçus fiscaux).", status=409)
    missing = [r["label"] for r in readiness(settings) if not r["ok"]]
    if missing:
        raise ReceiptError("Mentions manquantes : " + " ; ".join(missing) + ".", status=409)
    if year > date.today().year:
        raise ReceiptError("Année à venir.", "year")
    mode = mode or settings.default_mode
    if mode not in ("annual", "single"):
        raise ReceiptError("Mode d'émission inconnu.", "mode")
    return mode


def issue(year: int, entity_ids, mode=None, user_id=None, progress=None) -> tuple[list[DonationReceipt], list[dict]]:
    """Émet les reçus de l'année pour les donateurs choisis (tous si `entity_ids` est vide) :
    un reçu annuel récapitulatif par donateur, ou un reçu par don (`mode='single'`).
    Renvoie (reçus émis, refus par donateur). `progress(done, total, message)` : avancement."""
    mode = check_issue(year, mode)
    wanted = set(entity_ids or [])
    groups = [g for g in candidates(year)["donors"] if not wanted or g["entity_id"] in wanted]
    issued, refused = [], []
    for index, group in enumerate(groups, start=1):
        if group["problems"]:
            refused.append({"entity_id": group["entity_id"], "name": group["name"],
                            "reason": "À compléter dans la fiche du tiers : " + ", ".join(group["problems"]) + "."})
            continue
        batches = [group["items"]] if mode == "annual" else [[item] for item in group["items"]]
        for items in batches:
            try:
                issued.append(_issue_one(year, group["entity_id"], items, mode, user_id))
            except Exception as exc:  # noqa: BLE001 — un refus n'arrête pas le lot
                db.session.rollback()
                refused.append({"entity_id": group["entity_id"], "name": group["name"], "reason": f"Émission impossible : {exc}"})
        if progress:
            progress(index, len(groups), f"{len(issued)} reçu(s) émis")
    return issued, refused


def _issue_one(year, entity_id, items, mode, user_id) -> DonationReceipt:
    entity = db.session.get(Entity, entity_id)
    receipt = DonationReceipt(number=_next_number(year), year=year, entity_id=entity.id, person_kind=entity.person_kind,
                              mode=mode, total_cents=sum(i["amount_cents"] for i in items), status="issued",
                              donor_json=json.dumps(_donor_snapshot(entity), ensure_ascii=False),
                              issued_at=datetime.utcnow(), issued_by_user_id=user_id)
    for item in items:
        receipt.items.append(DonationReceiptItem(
            journal_line_id=item["id"] if item["kind"] == "line" else None,
            in_kind_id=item["id"] if item["kind"] == "in_kind" else None,
            date=date.fromisoformat(item["date"]), amount_cents=item["amount_cents"],
            nature="in_kind" if item["kind"] == "in_kind" else "cash", form="manual",
            payment_method=item["payment_method"]))
    db.session.add(receipt)
    db.session.flush()
    pdf = render_pdf(receipt)
    folder = instance_dir() / "recus" / str(year)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{receipt.number}.pdf").write_bytes(pdf)
    receipt.pdf_path = f"recus/{year}/{receipt.number}.pdf"
    receipt.pdf_sha256 = hashlib.sha256(pdf).hexdigest()
    db.session.commit()
    return receipt


def receipt_file(receipt: DonationReceipt) -> Path | None:
    return _instance_file(receipt.pdf_path) if receipt.pdf_path else None


def receipt_payload(receipt: DonationReceipt) -> dict:
    donor = json.loads(receipt.donor_json)
    return {"id": receipt.id, "number": receipt.number, "year": receipt.year, "entity_id": receipt.entity_id,
            "donor": donor["name"], "person_kind": receipt.person_kind, "mode": receipt.mode,
            "total_cents": receipt.total_cents, "status": receipt.status, "items": len(receipt.items),
            "issued_at": receipt.issued_at.isoformat() + "Z", "sent_at": receipt.sent_at.isoformat() + "Z" if receipt.sent_at else None,
            "pdf_url": f"/receipts/{receipt.id}.pdf", "email": receipt.entity.email or donor.get("email"),
            "sent_to": receipt.sent_to, "cancel_reason": receipt.cancel_reason,
            "replaced_by": receipt.replaced_by.number if receipt.replaced_by_id else None}


# --- PDF


def render_pdf(receipt: DonationReceipt) -> bytes:
    from flask import render_template
    from weasyprint import HTML

    settings, org = get(), organization.get()
    signature = _instance_file(org.signature_path) if org.signature_path else None
    items = [{"date": i.date, "amount_cents": i.amount_cents, "nature": NATURES[i.nature], "form": FORMS[i.form],
              "payment": PAYMENT_METHODS[i.payment_method],
              "description": (db.session.get(InKindDonation, i.in_kind_id).description if i.in_kind_id else None)}
             for i in receipt.items]
    html = render_template(
        "receipts/receipt.html", receipt=receipt, donor=json.loads(receipt.donor_json), org=org, items=items,
        # Particuliers : articles 200 / 978 ; entreprises : 238 bis.
        settings=settings, eligibility=ELIGIBILITY.get(settings.eligibility, ""),
        articles=[a for a in articles(settings) if (a == "238bis") == (receipt.person_kind == "company")],
        amount=euros(receipt.total_cents), amount_words=euros_in_words(receipt.total_cents),
        forms={i["form"] for i in items}, natures={i["nature"] for i in items},
        payments={i["payment"] for i in items if i["payment"]},
        signature_src=signature.as_uri() if signature else None,
        cerfa="16216*01" if receipt.person_kind == "company" else "11580*05",
        issued_on=date.today())  # date locale du jour d'émission (issued_at est en UTC)
    return HTML(string=html).write_pdf()


# ------------------------------------------------------------------ B.3 : envoi, annulation, état annuel

EMAIL_SUBJECT = "Votre reçu fiscal n° {number} — {org}"
EMAIL_BODY = """<p>Bonjour,</p>
<p>Nous vous remercions pour votre soutien. Vous trouverez ci-joint le reçu fiscal n° <strong>{number}</strong>
correspondant à vos dons de {year} à {org}, d'un montant de <strong>{amount}</strong>, à conserver pour votre
déclaration d'impôt.</p>
<p>Bien cordialement,<br>{signatory}<br>{org}</p>"""


def send(receipt_ids, progress=None) -> dict:
    """Envoie chaque reçu émis à l'adresse email du donateur (PDF joint) ; sans adresse : ignoré.
    Une erreur sur un reçu n'arrête pas l'envoi des autres."""
    from app.services.membership_reminders import _build_message, _open_smtp, smtp_configured, smtp_settings

    if not smtp_configured():
        raise ReceiptError("Envoi impossible : SMTP non configuré (Configuration › Intégrations).", status=409)
    rows = DonationReceipt.query.filter(DonationReceipt.id.in_(list(receipt_ids) or [0]),
                                        DonationReceipt.status == "issued").order_by(DonationReceipt.number).all()
    org = organization.get()
    settings = smtp_settings()
    sent = skipped = 0
    errors = []
    server = _open_smtp(settings)
    try:
        for index, receipt in enumerate(rows, start=1):
            email = receipt.entity.email or json.loads(receipt.donor_json).get("email")
            path = receipt_file(receipt)
            if not email or path is None:
                skipped += 1
                continue
            try:
                values = {"number": receipt.number, "org": org.name, "year": receipt.year,
                          "amount": euros(receipt.total_cents), "signatory": org.signatory_name or ""}
                message = _build_message(settings["sender"], email, EMAIL_SUBJECT.format(**values), EMAIL_BODY.format(**values))
                message.add_attachment(path.read_bytes(), maintype="application", subtype="pdf",
                                       filename=f"recu-fiscal-{receipt.number}.pdf")
                server.send_message(message)
                receipt.sent_at, receipt.sent_to = datetime.utcnow(), email
                db.session.commit()
                sent += 1
            except Exception as exc:  # noqa: BLE001 — on isole l'échec par reçu
                db.session.rollback()
                errors.append(f"{receipt.number} <{email}> : {exc}")
            if progress:
                progress(index, len(rows), f"{sent} reçu(s) envoyé(s)")
    finally:
        try:
            server.quit()
        except Exception:  # noqa: BLE001 — fermeture best-effort
            pass
    return {"sent": sent, "skipped": skipped, "errors": errors}


def cancel(receipt_id: int, reason, reissue=False, user_id=None) -> tuple[DonationReceipt, DonationReceipt | None]:
    """Annule un reçu émis (jamais supprimé ni renuméroté) ; ses dons redeviennent disponibles.
    `reissue` : émet aussitôt un reçu de remplacement pour les mêmes dons (donateur tel qu'il est
    aujourd'hui), relié par `replaced_by_id`."""
    receipt = db.session.get(DonationReceipt, receipt_id)
    if receipt is None:
        raise ReceiptError("Reçu introuvable.", status=404)
    if receipt.status != "issued":
        raise ReceiptError("Reçu déjà annulé.", status=409)
    reason = (reason or "").strip()
    if len(reason) < 5:
        raise ReceiptError("Motif d'annulation obligatoire (5 caractères au moins).", "reason")
    items = [{"kind": "line" if i.journal_line_id else "in_kind", "id": i.journal_line_id or i.in_kind_id,
              "date": i.date.isoformat(), "amount_cents": i.amount_cents, "payment_method": i.payment_method}
             for i in receipt.items if i.journal_line_id or i.in_kind_id]
    if reissue:
        check_issue(receipt.year, receipt.mode)
        problems = donor_problems(receipt.entity)
        if problems:
            raise ReceiptError("Réémission impossible, à compléter dans la fiche du tiers : " + ", ".join(problems) + ".",
                               status=409)
    receipt.status, receipt.cancel_reason = "cancelled", reason[:1000]
    db.session.flush()
    replacement = None
    if reissue:
        replacement = _issue_one(receipt.year, receipt.entity_id, items, receipt.mode, user_id)
        receipt = db.session.get(DonationReceipt, receipt_id)
        receipt.replaced_by_id = replacement.id
    db.session.commit()
    return receipt, replacement


def annual_summary(year: int) -> dict:
    """État annuel : reçus émis et annulés (nombre, montant) par type de donateur et nature, et
    rapprochement avec les dons comptabilisés de l'année."""
    rows = DonationReceipt.query.filter_by(year=year).all()
    issued = [r for r in rows if r.status == "issued"]
    by_kind = {kind: {"count": sum(1 for r in issued if r.person_kind == kind),
                      "amount_cents": sum(r.total_cents for r in issued if r.person_kind == kind)}
               for kind in ("individual", "company")}
    by_nature = {}
    for receipt in issued:
        for item in receipt.items:
            bucket = by_nature.setdefault(item.nature, {"label": NATURES[item.nature], "amount_cents": 0})
            bucket["amount_cents"] += item.amount_cents
    booked = sum(line.credit_cents - line.debit_cents for line in donation_lines(year))
    receipted_lines = sum(i.amount_cents for r in issued for i in r.items if i.journal_line_id)
    pending = candidates(year)
    return {
        "year": year,
        "issued": {"count": len(issued), "amount_cents": sum(r.total_cents for r in issued)},
        "cancelled": {"count": len(rows) - len(issued), "amount_cents": sum(r.total_cents for r in rows if r.status != "issued")},
        "by_kind": by_kind, "by_nature": by_nature,
        "sent": sum(1 for r in issued if r.sent_at), "unsent": sum(1 for r in issued if not r.sent_at),
        "booked_donations_cents": booked, "receipted_donations_cents": receipted_lines,
        # Dons comptabilisés = déjà sur un reçu + encore à reprendre (lignes ; les dons en nature sont à part).
        "pending_donations_cents": sum(i["amount_cents"] for d in pending["donors"] for i in d["items"] if i["kind"] == "line")
        + sum(u["amount_cents"] for u in pending["unassigned"]),
        "numbers": [r.number for r in sorted(rows, key=lambda r: r.number)],
    }

