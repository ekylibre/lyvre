"""Reçus fiscaux (lot B) — phase B.1 : paramètres de l'instance et image de signature.

- L'outil **n'évalue pas l'éligibilité** : l'administrateur déclare la situation de la structure
  (intérêt général, utilité publique, autre cas du CGI, rescrit éventuel) et **reconnaît sa
  responsabilité** à l'activation (date et auteur conservés ; à reconfirmer si l'éligibilité change).
- Activation refusée tant que les mentions obligatoires du reçu manquent : identité et adresse de
  la structure, objet, signataire, au moins un article du CGI, des comptes de dons existants.
- La signature (PNG ou JPEG, 500 Ko au plus) est rangée avec les pièces de l'instance (donc dans
  les sauvegardes) ; son chemin est sur `organization.signature_path`.
"""
import json
from datetime import datetime
from pathlib import Path

from app.extensions import db
from app.models import Account, ReceiptSettings
from app.models.receipt import CGI_ARTICLES, DEFAULT_DONATION_PREFIXES, ELIGIBILITY
from app.services import organization
from app.services.attachments import instance_dir

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
        ("signature", "Image de la signature", bool(org.signature_path and _signature_file(org.signature_path)), None),
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


def _signature_file(relative: str) -> Path | None:
    path = (instance_dir() / relative).resolve()
    return path if path.is_relative_to(instance_dir().resolve()) and path.is_file() else None


def signature_file() -> Path | None:
    org = organization.get()
    return _signature_file(org.signature_path) if org.signature_path else None


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
