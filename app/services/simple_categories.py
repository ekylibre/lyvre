"""Catégories de la comptabilité simplifiée (lot D.2, D21).

Pré-remplies au premier accès depuis le plan associatif (le compte le plus précis présent : code
exact, sinon premier sous-compte) ; modifiables (libellé, compte, ordre, activation). Une recette
ou une dépense saisie (lot D.3) génère une écriture sur le compte de sa catégorie.
"""
from app.extensions import db
from app.models import Account, JournalLine, SimpleCategory

# (code, libellé, sens, comptes possibles par ordre de préférence)
DEFAULTS = (
    ("cotisations", "Cotisations", "income", ("756",)),
    ("dons", "Dons", "income", ("7541", "754")),
    ("subventions", "Subventions", "income", ("74",)),
    ("ventes", "Ventes et prestations", "income", ("706", "707", "70")),
    ("manifestations", "Manifestations", "income", ("7083", "708")),
    ("produits_financiers", "Produits financiers", "income", ("768", "76")),
    ("autres_recettes", "Autres recettes", "income", ("758", "75")),
    ("achats", "Achats et fournitures", "expense", ("606", "60")),
    ("marchandises", "Achats de marchandises", "expense", ("607",)),
    ("locations", "Locations", "expense", ("613",)),
    ("entretien", "Entretien et réparations", "expense", ("615",)),
    ("assurances", "Assurances", "expense", ("616",)),
    ("honoraires", "Honoraires", "expense", ("622",)),
    ("communication", "Communication", "expense", ("623",)),
    ("deplacements", "Déplacements et réceptions", "expense", ("625",)),
    ("telecom", "Frais postaux et télécommunications", "expense", ("626",)),
    ("frais_bancaires", "Frais bancaires", "expense", ("627",)),
    ("impots", "Impôts et taxes", "expense", ("63",)),
    ("salaires", "Salaires", "expense", ("641", "64")),
    ("charges_sociales", "Charges sociales", "expense", ("645",)),
    ("autres_depenses", "Autres dépenses", "expense", ("658", "65")),
)


class CategoryError(Exception):
    def __init__(self, message, field=None, status=422):
        super().__init__(message)
        self.message, self.field, self.status = message, field, status


def _account_for(codes, taken=()):
    """Compte le plus précis présent pour ces codes, hors comptes déjà pris par une catégorie
    (« Autres recettes » ne doit pas retomber sur le 756 des cotisations)."""
    usable = Account.query.filter(Account.is_header.is_(False), Account.id.notin_(list(taken) or [0]))
    for code in codes:
        account = (usable.filter(Account.code == code).first()
                   or usable.filter(Account.code.like(f"{code}%")).order_by(Account.code).first())
        if account is not None:
            return account
    return None


def ensure_defaults() -> None:
    """Crée les catégories par défaut absentes (une catégorie sans compte du plan est omise)."""
    existing = {c.code for c in SimpleCategory.query}
    taken = {c.account_id for c in SimpleCategory.query}
    position = db.session.query(db.func.max(SimpleCategory.position)).scalar() or 0
    added = False
    for code, label, kind, accounts in DEFAULTS:
        if code in existing:
            continue
        account = _account_for(accounts, taken)
        if account is None:
            continue
        taken.add(account.id)
        position += 10
        db.session.add(SimpleCategory(code=code, label=label, kind=kind, account_id=account.id, position=position))
        added = True
    if added:
        db.session.commit()


def listing(include_inactive=True) -> list[SimpleCategory]:
    ensure_defaults()
    query = SimpleCategory.query
    if not include_inactive:
        query = query.filter_by(active=True)
    return query.order_by(SimpleCategory.kind.desc(), SimpleCategory.position, SimpleCategory.id).all()


def payload(category: SimpleCategory, usage: int | None = None) -> dict:
    return {"id": category.id, "code": category.code, "label": category.label, "kind": category.kind,
            "account": {"id": category.account.id, "code": category.account.code, "label": category.account.label},
            "position": category.position, "active": category.active,
            **({"usage": usage} if usage is not None else {})}


def usage_counts() -> dict[int, int]:
    """Nombre de lignes d'écriture sur le compte de chaque catégorie."""
    rows = (db.session.query(SimpleCategory.id, db.func.count(JournalLine.id))
            .outerjoin(JournalLine, JournalLine.account_id == SimpleCategory.account_id)
            .group_by(SimpleCategory.id))
    return dict(rows.all())


def save(category: SimpleCategory | None, data: dict) -> SimpleCategory:
    label = (data.get("label") or "").strip()[:120]
    if not label:
        raise CategoryError("Libellé obligatoire.", "label")
    kind = data.get("kind") if category is None else category.kind
    if kind not in ("income", "expense"):
        raise CategoryError("Recette ou dépense ?", "kind")
    account = db.session.get(Account, data.get("account_id")) if isinstance(data.get("account_id"), int) else None
    if account is None or account.is_header:
        raise CategoryError("Compte obligatoire (compte utilisable du plan).", "account_id")
    expected = "7" if kind == "income" else "6"
    if not account.code.startswith(expected):
        raise CategoryError(f"Une {'recette' if kind == 'income' else 'dépense'} se rattache à un compte {expected}….",
                            "account_id")
    if category is None:
        position = (db.session.query(db.func.max(SimpleCategory.position)).scalar() or 0) + 10
        code = f"custom_{(db.session.query(db.func.max(SimpleCategory.id)).scalar() or 0) + 1}"
        category = SimpleCategory(code=code, kind=kind, position=position)
        db.session.add(category)
    category.label, category.account_id = label, account.id
    category.active = bool(data.get("active", True))
    db.session.commit()
    return category


def move(category: SimpleCategory, direction: str) -> None:
    siblings = [c for c in listing() if c.kind == category.kind]
    index = siblings.index(category)
    other = index - 1 if direction == "up" else index + 1
    if 0 <= other < len(siblings):
        neighbour = siblings[other]
        category.position, neighbour.position = neighbour.position, category.position
        if category.position == neighbour.position:
            category.position += -1 if direction == "up" else 1
        db.session.commit()
