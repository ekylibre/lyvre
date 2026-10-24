"""Modèles et texte des baux (lot L2, décisions BX3, BF8–BF12).

Un modèle par type de bail (`lease_templates`), en HTML (éditeur Tiptap) avec des champs Jinja
(`{{ preneur.nom }}`, `{{ biens.tableau }}`…), rendu **en bac à sable** (pas d'accès aux objets
Python), variables échappées. Le modèle livré (`templates/leases/defaults/<kind>.html`) est recopié
dans la base au premier usage ; tant qu'il n'a pas été enregistré une fois, il est signalé « à relire ».

Le texte d'un bail est généré à la validation puis **figé** (`leases.document_html`) : modifier le
modèle ne change pas les baux déjà rédigés ; il reste retouchable pour ce bail seul (`save_document`)
et peut être régénéré. Tant qu'il n'est pas figé (brouillon), l'aperçu rend le modèle à la volée.

PDF : gabarit `leases/document.html` + texte, WeasyPrint, sans ressource extérieure (seules les images
`data:` et la carte figée du bail, `lease-map:carte-….png`, sont lues).
"""
from __future__ import annotations

import html
import re
from datetime import date, datetime, timedelta
from html.parser import HTMLParser
from pathlib import Path

from flask import current_app, render_template
from jinja2 import StrictUndefined, TemplateError, UndefinedError
from jinja2.sandbox import SandboxedEnvironment
from markupsafe import Markup, escape

from app.extensions import db
from app.models import Associate, Lease, LeaseTemplate
from app.models.sale import FREQUENCIES
from app.services import lease_map, leases, organization
from app.services.recurrence import MONTHS
from app.utils.money import euros, euros_in_words, number_in_words

DEFAULTS_DIR = Path(__file__).resolve().parents[1] / "templates" / "leases" / "defaults"
_SANDBOX = SandboxedEnvironment(autoescape=True, undefined=StrictUndefined)

# Champs proposés dans l'éditeur des modèles (le contexte complet est `context(lease)`).
FIELDS = [
    ("bailleur.nom", "Bailleur : nom"), ("bailleur.forme", "Bailleur : forme juridique"),
    ("bailleur.rcs", "Bailleur : SIREN et RCS"), ("bailleur.adresse", "Bailleur : siège"),
    ("bailleur.gerants_texte", "Bailleur : gérance"), ("bailleur.identite", "Bailleur : identité complète"),
    ("preneur.identite", "Preneur : identité complète"), ("biens.situation", "Biens : lieu-dit et adresse"),
    ("preneur.nom", "Preneur : nom"), ("preneur.identification", "Preneur : SIRET"),
    ("preneur.adresse", "Preneur : adresse"), ("preneur.email", "Preneur : e-mail"),
    ("biens.lieu", "Biens : lieu-dit"), ("biens.adresse", "Biens : adresse"),
    ("biens.tableau", "Biens : tableau"), ("biens.carte", "Biens : carte"), ("biens.lettres", "Biens : lettres"),
    ("biens.surface_batie", "Biens : surface bâtie"), ("biens.surface_sol", "Biens : surface de terres"),
    ("bail.type", "Bail : type"), ("bail.debut", "Bail : date d'effet"), ("bail.fin", "Bail : fin"),
    ("bail.duree", "Bail : durée"),
    ("loyer.annuel", "Loyer annuel"), ("loyer.annuel_lettres", "Loyer annuel en lettres"),
    ("loyer.detail", "Loyer : décomposition"), ("loyer.echeance", "Loyer d'une échéance"),
    ("loyer.frequence", "Loyer : périodicité"), ("charges.montant", "Provision sur charges"),
    ("depot.montant", "Dépôt de garantie"), ("depot.lettres", "Dépôt de garantie en lettres"),
    ("indice.nom", "Indice : nom"), ("indice.reference", "Indice de référence"),
    ("indice.periodicite", "Indice : périodicité (annuelle, triennale)"),
    ("indice.frequence_texte", "Indice : chaque année, tous les trois ans"),
    ("signature.lieu", "Fait à"), ("signature.date", "Date de signature"), ("signatures", "Bloc des signatures"),
]
BLOCK_FIELDS = ("biens.tableau", "biens.carte", "loyer.detail", "signatures")

ALLOWED_TAGS = {"p", "br", "strong", "b", "em", "i", "u", "s", "h1", "h2", "h3", "h4", "ul", "ol", "li", "blockquote",
                "hr", "a", "table", "thead", "tbody", "tfoot", "tr", "th", "td", "div", "span"}
VOID_TAGS = {"br", "hr"}
DROPPED_TAGS = {"script", "style", "iframe", "object", "embed", "head", "title", "svg", "math", "template"}
SAFE_LINK = re.compile(r"^(https?:|mailto:|\{\{)", re.I)
SAFE_CLASS = re.compile(r"^[a-z0-9 _-]{1,60}$")
MAP_SRC = re.compile(r"^lease-map:(carte-[0-9a-f]{8,16}\.png)$")  # carte figée du bail (lot L3), seule image admise


class LeaseDocumentError(ValueError):
    def __init__(self, message, field=None, status=422):
        super().__init__(message)
        self.message, self.field, self.status = message, field, status


# ------------------------------------------------------------------ HTML des modèles

class _Sanitizer(HTMLParser):
    """Garde les balises de mise en forme de l'éditeur (et des tableaux), sans attribut sauf le
    lien d'un `<a>` et les classes (styles du PDF) ; retire scripts, styles, images et tout ce qui
    chargerait une ressource."""

    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.out, self.skipping = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in DROPPED_TAGS:
            self.skipping += 1
        elif not self.skipping and tag in ALLOWED_TAGS:
            values = dict(attrs)
            href, css = values.get("href") if tag == "a" else None, values.get("class")
            safe = f' href="{html.escape(href)}"' if href and SAFE_LINK.match(href.strip()) else ""
            safe += f' class="{css}"' if css and SAFE_CLASS.match(css) else ""
            self.out.append(f"<{tag}{safe}>")
        elif not self.skipping and tag == "img" and MAP_SRC.match(dict(attrs).get("src") or ""):
            self.out.append(f'<img class="map" src="{dict(attrs)["src"]}">')

    def handle_startendtag(self, tag, attrs):
        if not self.skipping and tag in VOID_TAGS:
            self.out.append(f"<{tag}>")
        elif tag == "img":
            self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag):
        if tag in DROPPED_TAGS:
            self.skipping = max(0, self.skipping - 1)
        elif not self.skipping and tag in ALLOWED_TAGS and tag not in VOID_TAGS:
            self.out.append(f"</{tag}>")

    def handle_data(self, data):
        if not self.skipping:
            self.out.append(html.escape(data, quote=False))

    def handle_entityref(self, name):
        if not self.skipping:
            self.out.append(f"&{name};")

    def handle_charref(self, name):
        if not self.skipping:
            self.out.append(f"&#{name};")


def sanitize(value: str) -> str:
    parser = _Sanitizer()
    parser.feed(value or "")
    parser.close()
    return "".join(parser.out).strip()


def _prepare(body: str) -> str:
    """Texte Jinja d'un modèle saisi dans l'éditeur : opérateurs des balises Jinja déséchappés
    (l'éditeur écrit `&gt;`), champs « bloc » (tableau, carte…) sortis de leur paragraphe."""
    body = re.sub(r"(\{\{.*?\}\}|\{%.*?%\})", lambda m: html.unescape(m.group(1)), body, flags=re.S)
    fields = "|".join(re.escape(f) for f in BLOCK_FIELDS)
    return re.sub(rf"<p>\s*(\{{\{{\s*(?:{fields})\s*\}}\}})\s*</p>", r"\1", body)


def render_body(body: str, lease: Lease) -> str:
    try:
        return _SANDBOX.from_string(_prepare(body)).render(**context(lease)).strip()
    except UndefinedError as exc:
        raise LeaseDocumentError(f"Champ inconnu dans le modèle : {exc.message}.") from None
    except TemplateError as exc:
        raise LeaseDocumentError(f"Modèle invalide : {exc.message or exc}.") from None


# ------------------------------------------------------------------ modèles

def default_body(kind: str) -> str:
    return (DEFAULTS_DIR / f"{kind}.html").read_text(encoding="utf-8")


def _check_kind(kind: str) -> None:
    if kind not in leases.KINDS:
        raise LeaseDocumentError("Type de bail inconnu.", status=404)


def template_for(kind: str) -> LeaseTemplate:
    """Modèle de l'instance pour ce type, recopié du modèle livré au premier usage (sans commit)."""
    _check_kind(kind)
    row = LeaseTemplate.query.filter_by(kind=kind).first()
    if row is None:
        row = LeaseTemplate(kind=kind, title=leases.KINDS[kind], body_html=default_body(kind), version=1, reviewed=False)
        db.session.add(row)
        db.session.flush()
    return row


def templates() -> list[LeaseTemplate]:
    rows = [template_for(kind) for kind in leases.KINDS]
    db.session.commit()
    return rows


def check_syntax(body: str) -> None:
    try:
        _SANDBOX.parse(_prepare(body))
    except TemplateError as exc:
        raise LeaseDocumentError(f"Modèle invalide : {exc.message or exc}.", "body_html") from None


def save_template(kind: str, body_html: str, user_id=None) -> LeaseTemplate:
    body = sanitize(body_html)
    if not body:
        raise LeaseDocumentError("Le modèle est vide.", "body_html")
    check_syntax(body)
    row = template_for(kind)
    row.body_html, row.version, row.reviewed, row.updated_by_id = body, row.version + 1, True, user_id
    db.session.commit()
    return row


def reset_template(kind: str, user_id=None) -> LeaseTemplate:
    row = template_for(kind)
    row.body_html, row.version, row.reviewed, row.updated_by_id = default_body(kind), row.version + 1, False, user_id
    db.session.commit()
    return row


# ------------------------------------------------------------------ champs

def long_date(value: date | None) -> str:
    if value is None:
        return "[date]"
    return f"{'1er' if value.day == 1 else value.day} {MONTHS[value.month - 1]} {value.year}"


def _area(m2: int) -> str:
    return f"{m2:,}".replace(",", " ") + " m²"


def _hectares(m2: int) -> str:
    return f"{leases.hectares(m2)}".replace(".", ",") + " ha"


def duration(start: date, end: date | None) -> str:
    """« trois années » (1er octobre 2025 – 30 septembre 2028), « dix-huit mois », sinon en jours ;
    sans fin, un repère à compléter."""
    if end is None:
        return "[durée]"
    after = end + timedelta(days=1)
    months = (after.year - start.year) * 12 + after.month - start.month
    if after.day != start.day or months <= 0:
        return f"{number_in_words((end - start).days + 1)} jours"
    if months % 12 == 0:
        years = months // 12
        return "une année" if years == 1 else f"{number_in_words(years)} années"
    return f"{number_in_words(months)} mois"


def _address(*parts) -> str:
    return ", ".join(p for p in (" ".join(x for x in part if x) if isinstance(part, tuple) else part
                                 for part in parts) if p)


def _period(value: str | None) -> str:
    match = re.fullmatch(r"(\d{4})-[QT]([1-4])", value or "")
    if match:
        quarter = int(match.group(2))
        return f"{quarter}{'er' if quarter == 1 else 'e'} trimestre {match.group(1)}"
    return value or "[période]"


def _decimal(value) -> str:
    return f"{value}".replace(".", ",") if value is not None else "[valeur]"


def _table(lease: Lease) -> Markup:
    rows = "".join(
        f"<tr><td class='letter'>{escape(i.letter or '')}</td><td>{escape(i.label)}"
        f"{' (partie)' if i.partial else ''}</td><td class='num'>{escape(_area(i.area_m2)) if i.area_m2 else '—'}</td>"
        f"<td>{escape(', '.join(i.cadastral_refs or []))}</td>"
        f"<td class='num'>{escape(_area(i.built_m2)) if i.built_m2 else '—'}</td></tr>"
        for i in lease.items)
    total_area, total_built = sum(i.area_m2 for i in lease.items), sum(i.built_m2 for i in lease.items)
    return Markup(
        "<table class='premises'><thead><tr><th></th><th>Désignation</th><th>Superficie</th>"
        "<th>Références cadastrales</th><th>Dont bâtiments</th></tr></thead>"
        f"<tbody>{rows}</tbody><tfoot><tr><td></td><td>Total</td><td class='num'>{escape(_area(total_area))}</td>"
        f"<td></td><td class='num'>{escape(_area(total_built))}</td></tr></tfoot></table>")


def _detail(lease: Lease) -> Markup:
    """Décomposition du loyer : un total par prix au m² et par prix à l'hectare, puis les forfaits."""
    lines, groups = [], {}
    for item in lease.items:
        if item.billing_unit in ("m2", "ha") and item.annual_cents:
            groups.setdefault((item.billing_unit, item.unit_price_cents), []).append(item)
    for (unit, price), items in sorted(groups.items(), key=lambda g: (g[0][0] != "m2", -g[0][1])):
        amount = sum(i.annual_cents for i in items)
        if unit == "m2":
            quantity, label = _area(sum(i.area_m2 for i in items)), f"{euros(price)} / m² / an"
        else:
            quantity = f"{sum(leases.hectares(i.area_m2) for i in items)}".replace(".", ",") + " ha"
            label = f"{euros(price)} / ha / an"
        lines.append(f"Prix de base de {label} : {quantity} × {euros(price)} = {euros(amount)}")
    lines += [f"{item.letter + ' ' if item.letter else ''}{item.label} : forfait annuel de {euros(item.annual_cents)}"
              for item in lease.items if item.billing_unit == "flat" and item.annual_cents]
    return Markup("<ul class='rent'>" + "".join(f"<li>{escape(line)}</li>" for line in lines) + "</ul>")


def _map(lease: Lease) -> Markup:
    """Carte figée des biens (image rendue une fois par jeu de zones), vide sans géométrie."""
    name = lease_map.render(lease)
    return Markup(f'<img class="map" src="lease-map:{name}">') if name else Markup("")


def _letters(lease: Lease) -> str:
    letters = [i.letter for i in lease.items if i.letter]
    if len(letters) <= 1:
        return "".join(letters)
    return ", ".join(letters[:-1]) + " et " + letters[-1]


def _managers() -> list[str]:
    return [a.name for a in Associate.query.filter_by(is_manager=True).order_by(Associate.id)]


def _signatures(org, managers: list[str], tenant: str) -> Markup:
    landlord = "".join(f"<div class='signer'>{escape(name)}</div>" for name in managers) or \
        f"<div class='signer'>{escape(org.signatory_name or '')}</div>"
    return Markup(
        "<table class='signatures'><tr>"
        f"<td><b>Le Bailleur</b><br>{escape(org.name)}{landlord}</td>"
        f"<td><b>Le Preneur</b><br>{escape(tenant)}<div class='signer'></div></td>"
        "</tr></table>")


def context(lease: Lease) -> dict:
    org, tenant = organization.get(), lease.entity
    managers = _managers()
    if org.siren and org.rcs_city:
        rcs = f"{org.siren[:3]} {org.siren[3:6]} {org.siren[6:]} RCS {org.rcs_city}"
    else:
        rcs = f"SIREN {org.siren}" if org.siren else ""
    rec = lease.recurrence
    frequency = rec.frequency if rec else "monthly"
    per_period = sum(amount for _i, amount in leases.period_amounts(lease, frequency))
    annual = leases.annual_total(lease)
    triennial = lease.revision_months == 36
    landlord_address = _address(org.address_line1, org.address_line2, (org.postal_code, org.city)) or "[siège]"
    managers_text = ("sa gérance, " + (" et ".join(managers) if len(managers) <= 2
                                       else ", ".join(managers[:-1]) + " et " + managers[-1])) if managers else ""
    tenant_address = _address(tenant.address_line1, tenant.address_line2, (tenant.postal_code, tenant.city)) or "[adresse]"
    individual = tenant.person_kind == "individual"
    identification = f"SIRET {tenant.siret}" if tenant.siret else ""
    premises_address = _address(lease.address_line1, lease.address_line2, (lease.postal_code, lease.city))
    situation = (f" au lieu-dit « {lease.premises_label} »" if lease.premises_label else "") + \
        (f", {premises_address}" if premises_address else "")
    return {
        "bailleur": {
            "nom": org.name, "forme": org.legal_form or "", "siren": org.siren or "", "rcs": rcs,
            "adresse": landlord_address, "gerants": managers, "gerants_texte": managers_text or (org.signatory_name or ""),
            "identite": ", ".join(p for p in (org.name, org.legal_form, rcs) if p) + f", dont le siège est {landlord_address}"
            + (f", représentée par {managers_text or org.signatory_name}" if managers_text or org.signatory_name else ""),
        },
        "preneur": {
            "nom": tenant.name, "identification": identification, "adresse": tenant_address,
            "email": tenant.email or "", "particulier": individual,
            "identite": ", ".join(p for p in (tenant.name, identification) if p)
            + (f", demeurant {tenant_address}" if individual else f", dont le siège est {tenant_address}"),
        },
        "biens": {
            "lieu": lease.premises_label or "", "adresse": premises_address, "situation": situation,
            "tableau": _table(lease), "carte": _map(lease), "lettres": _letters(lease),
            "surface_batie": _area(sum(i.built_m2 for i in lease.items)),
            "surface_sol": _hectares(sum(i.area_m2 for i in lease.items if i.nature == "land")),
        },
        "bail": {
            "type": leases.KINDS.get(lease.kind, ""), "designation": lease.unit_label,
            "debut": long_date(lease.start_date), "fin": long_date(lease.end_date) if lease.end_date else "[date de fin]",
            "duree": duration(lease.start_date, lease.end_date),
        },
        "loyer": {
            "annuel": euros(annual), "annuel_lettres": euros_in_words(annual), "detail": _detail(lease),
            "echeance": euros(per_period), "frequence": FREQUENCIES[frequency].lower(),
        },
        "charges": {"montant": euros(lease.charges_cents) if lease.charges_cents else ""},
        "depot": {"montant": euros(lease.deposit_cents) if lease.deposit_cents else "",
                  "lettres": euros_in_words(lease.deposit_cents) if lease.deposit_cents else ""},
        "indice": {
            "code": lease.index_code or "",
            "nom": leases.INDEXES[lease.index_code][0].lower() + leases.INDEXES[lease.index_code][1:]
            if lease.index_code else "",
            "reference": f"{_period(lease.index_reference_period)} : {_decimal(lease.index_reference_value)}",
            "periodicite": "triennale" if triennial else "annuelle",
            "frequence_texte": "tous les trois ans" if triennial else "chaque année",
        },
        "signature": {"lieu": lease.signed_on_place or org.city or "[lieu]", "date": long_date(date.today())},
        "signatures": _signatures(org, managers, tenant.name),
    }


# ------------------------------------------------------------------ texte d'un bail

def _kind(lease: Lease) -> str:
    if not lease.kind:
        raise LeaseDocumentError("Choisissez le type du bail (étape 1 de l'assistant) pour rédiger son texte.", "kind")
    return lease.kind


def generate(lease: Lease) -> None:
    """(Re)génère le texte du bail depuis le modèle de son type et le fige (sans commit)."""
    lease.document_html = render_body(template_for(_kind(lease)).body_html, lease)
    lease.document_generated_at, lease.document_edited = datetime.utcnow(), False


def save_document(lease: Lease, body_html: str) -> None:
    body = sanitize(body_html)
    if not body:
        raise LeaseDocumentError("Le texte du bail est vide.", "document_html")
    lease.document_html, lease.document_edited = body, True
    db.session.commit()


def current_html(lease: Lease) -> str:
    """Texte figé du bail, sinon le modèle de son type rendu à la volée (brouillon)."""
    if lease.document_html:
        return lease.document_html
    return render_body(template_for(_kind(lease)).body_html, lease)


def _url_fetcher(lease: Lease):
    """Aucune ressource extérieure dans un bail : images `data:` et carte figée du bail seulement."""
    def fetch(url, *args, **kwargs):
        from weasyprint import default_url_fetcher
        if url.startswith("data:"):
            return default_url_fetcher(url, *args, **kwargs)
        match = MAP_SRC.match(url)
        if match:
            path = lease_map.folder(lease) / match.group(1)
            if path.is_file():
                return {"string": path.read_bytes(), "mime_type": "image/png"}
        raise ValueError(f"Ressource refusée dans un bail : {url[:80]}")
    return fetch


def render_pdf(lease: Lease, body_html: str | None = None) -> bytes:
    """PDF du bail : texte figé (ou rendu à la volée), ou `body_html` (aperçu d'un modèle)."""
    from weasyprint import HTML
    body = render_body(body_html, lease) if body_html is not None else current_html(lease)
    page = render_template("leases/document.html", body=Markup(body), lease=lease, org=organization.get(),
                           title=leases.KINDS.get(lease.kind, "Bail"))
    return HTML(string=page, url_fetcher=_url_fetcher(lease), base_url=str(current_app.root_path)).write_pdf()
