"""Import d'un export Isacompta `.ISA` (lot AG10.b, claudedocs/design_efacturation_agricole.md § 7, AGD27).

Le format n'a pas de description publique : la disposition ci-dessous a été **relevée sur des exports réels**, lus
sur place sans copie (Q-E5). Les tests n'utilisent que des extraits fictifs. Fichier texte à largeur fixe,
encodage DOS (cp850), une ligne par enregistrement, type en tête :

| Enregistrement | Contenu repris (colonnes, à partir de 0) |
|---|---|
| `VER`, `DOS` | version, dossier (non repris) |
| `EXO` | exercice : début [6:14], fin [14:22] (JJMMAAAA) |
| `ANA` (6 premiers caractères `ANA   `) | section analytique : code [3:12], libellé [12:54], unité [54:66], quantité [66:78] |
| `CPT` | compte : numéro [6:16] (10 caractères), libellé [16:46] |
| `ANACPT` | section par défaut du compte qui précède : code [6:12], part [55:70] (‰) |
| `TVA` | code de TVA : code [6:8], libellé [8:38], compte [38:48], taux [48:55] (information) |
| `JOU` | journal : code [6:8], libellé [8:44] |
| `ECR` | écriture : journal [6:8], date [8:16], pièce [16:24], libellé [24:54] ; sans mouvement : ignorée |
| `MVT` | ligne de l'écriture qui précède : compte [6:16], libellé [16:46], débit [46:59], crédit [59:72], lettrée [106] = 1 et lettre [107:110], date [143:151] |
| `ANAMVT` | ventilation de la ligne qui précède : section [6:12], part [55:70] (‰) |
| `ECHMVT` | échéance de la ligne qui précède (information) |
| `AFFLET`, `POINTI` | lettrages et pointages bancaires (le lettrage est lu sur la ligne ; pointages non repris) |

Les numéros de compte sur 10 caractères perdent leurs deux zéros de fin (`6262000000` → `62620000`, la forme des FEC
du même cabinet) : l'ancien plan agricole s'applique alors comme à l'import FEC (AG10.a). Les comptes de tiers
alphanumériques (`401DUPONT`) deviennent des comptes auxiliaires du collectif.

La reprise passe par l'import FEC (`fec_import`) : même analyse, même plan de correspondance, même import
tout-ou-rien ; puis, si demandé, les sections deviennent des ateliers et activités (AG8) avec leur surface, et les
ventilations des lignes et des comptes sont reprises.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from app.extensions import db
from app.services import fec_import
from app.services.fec_import import FecEntry, FecLine, ImportError_

@dataclass
class IsaSection:
    code: str
    label: str
    unit: str | None
    quantity: float | None


@dataclass
class IsaFile:
    start: date | None = None
    end: date | None = None
    sections: dict = field(default_factory=dict)          # code → IsaSection
    accounts: dict = field(default_factory=dict)          # numéro (10) → libellé
    account_sections: dict = field(default_factory=dict)  # numéro (10) → [(section, part ‰)]
    journals: dict = field(default_factory=dict)          # code → libellé
    vat_codes: list = field(default_factory=list)
    entries: list = field(default_factory=list)           # FecEntry
    line_sections: dict = field(default_factory=dict)     # id(FecLine) → [(section, part ‰)]
    due_dates: int = 0
    reconciliations: int = 0
    problems: list = field(default_factory=list)


def _day(text: str) -> date | None:
    try:
        return datetime.strptime(text.strip(), "%d%m%Y").date()
    except ValueError:
        return None


def _amount(text: str) -> int:
    return fec_import.amount(text) if text.strip() else 0


def _share(text: str) -> int | None:
    match = re.search(r"(\d+(?:\.\d+)?)\s*$", text.rstrip())
    return int(float(match.group(1))) if match else None


def account_code(raw: str) -> tuple[str, str]:
    """(compte, auxiliaire) : `6262000000` → (`62620000`, ``) ; `401DUPONT` → (`401`, `401DUPONT`)."""
    raw = raw.strip()
    if raw.isdigit():
        return (raw[:8] if len(raw) == 10 and raw.endswith("00") else raw), ""
    match = re.match(r"^(\d{3})", raw)
    return (match.group(1), raw) if match and raw[:1] == "4" else (raw, "")


def parse(content: bytes) -> IsaFile:
    if len(content) > fec_import.MAX_SIZE:
        raise ImportError_("Fichier trop volumineux (20 Mo au plus).")
    text = content.decode("cp850", errors="replace")
    rows = [r for r in re.split(r"\r\n|\n|\r", text) if r.strip()]
    if not rows or not rows[0].startswith("VER"):
        raise ImportError_("Ce n'est pas un export Isacompta (.ISA) : enregistrement VER attendu en tête.")
    isa = IsaFile()
    entry, line, last_account, number = None, None, None, 0
    for n, row in enumerate(rows, start=1):
        kind, sub = row[:3], row[:6]
        if sub == "ANACPT":
            share = _share(row[55:70])
            if last_account and share:
                isa.account_sections.setdefault(last_account, []).append((row[6:12].strip(), share))
        elif sub == "ANAMVT":
            share = _share(row[55:70])
            if line is not None and share:
                isa.line_sections.setdefault(id(line), []).append((row[6:12].strip(), share))
        elif sub == "ECHMVT":
            isa.due_dates += 1
        elif sub == "POINTI":
            isa.reconciliations += 1
        elif kind == "ANA":
            quantity = row[66:78].strip()
            try:
                value = float(quantity) if quantity else None
            except ValueError:
                value = None
            code = row[3:12].strip()
            isa.sections[code] = IsaSection(code, row[12:54].strip(), row[54:66].strip().lower() or None, value)
        elif kind == "EXO":
            isa.start, isa.end = _day(row[6:14]), _day(row[14:22])
        elif kind == "CPT":
            last_account = row[6:16].strip()
            isa.accounts[last_account] = row[16:46].strip()
        elif kind == "JOU":
            isa.journals[row[6:8].strip()] = row[8:44].strip()
        elif kind == "TVA":
            isa.vat_codes.append({"code": row[6:8].strip(), "label": row[8:38].strip(), "account": row[38:48].strip(),
                                  "rate": row[48:55].strip()})
        elif kind == "ECR":
            day, journal = _day(row[8:16]), row[6:8].strip()
            line = None
            if not journal or day is None:
                entry = None                                  # en-tête sans journal (relevé) : ignoré
                continue
            number += 1
            entry = FecEntry(journal, str(number), day, row[16:24].strip())
            entry.label = row[24:54].strip()
            isa.entries.append(entry)
        elif kind == "MVT":
            if entry is None:
                line = None
                continue
            account, aux = account_code(row[6:16])
            try:
                debit, credit = _amount(row[46:59]), _amount(row[59:72])
            except ValueError:
                isa.problems.append(f"Ligne {n} : montant illisible.")
                line = None
                continue
            if debit < 0 or credit < 0:
                debit, credit = max(debit, 0) + max(-credit, 0), max(credit, 0) + max(-debit, 0)
            label = row[16:46].strip() or entry.label
            letter = row[107:110].strip() if row[106:107] == "1" else ""
            raw = row[6:16].strip()
            line = FecLine(entry.journal, isa.journals.get(entry.journal, ""), entry.number,
                           _day(row[143:151]) or entry.day, account, isa.accounts.get(raw, ""), aux,
                           isa.accounts.get(raw, "") if aux else "", entry.piece, label, debit, credit, letter, None)
            entry.lines.append(line)
    isa.entries = [e for e in isa.entries if e.lines]
    for e in isa.entries:
        e.day = min(l.day for l in e.lines) if any(l.day != e.day for l in e.lines) else e.day
        if e.balance:
            isa.problems.append(f"Écriture {e.journal} {e.piece or e.number} du {e.day:%d/%m/%Y} déséquilibrée "
                                f"({e.balance / 100:.2f} €).")
    if not isa.entries:
        raise ImportError_("Aucune écriture dans le fichier.", isa.problems)
    return isa


# ------------------------------------------------------------------ analyse

def _parser(isa: IsaFile):
    return lambda _content: (isa.entries, isa.problems)


def _ancestors(isa: IsaFile, code: str) -> list[str]:
    """Sections dont le code est un préfixe strict de `code`, de la plus haute à la plus proche."""
    return sorted((c for c in isa.sections if c != code and code.startswith(c)), key=len)


def _activity_sections(isa: IsaFile) -> list[IsaSection]:
    """Sections sans section fille : les activités possibles."""
    codes = set(isa.sections)
    return [s for s in isa.sections.values() if not any(c != s.code and c.startswith(s.code) for c in codes)]


def _top(isa: IsaFile, section: IsaSection) -> IsaSection | None:
    """Section la plus haute au-dessus de la feuille (l'atelier) ; None pour une feuille sans parent."""
    above = _ancestors(isa, section.code)
    return isa.sections[above[0]] if above else None


def _used(isa: IsaFile) -> set[str]:
    return {c for parts in (*isa.line_sections.values(), *isa.account_sections.values()) for c, _s in parts}


def default_sections(isa: IsaFile) -> list[str]:
    """Feuilles proposées par défaut : ventilées, avec une surface, ou reconnues dans Lexicon."""
    from app.services.import_activities import match_production
    used = _used(isa)
    covered = {leaf.code for leaf in _activity_sections(isa) for u in used if leaf.code.startswith(u)}
    return [leaf.code for leaf in _activity_sections(isa)
            if leaf.code in covered or leaf.quantity or match_production(leaf.label)]


def analyze(content: bytes, filename: str = "", overrides: dict | None = None) -> dict:
    from app.services.import_activities import match_production
    isa = parse(content)
    result = fec_import.analyze(content, filename, overrides, parser=_parser(isa))
    if isa.start and isa.end:
        result["fiscal_year"] = {"start_date": isa.start.isoformat(), "end_date": isa.end.isoformat()}
    proposed = set(default_sections(isa))
    sections = []
    for leaf in _activity_sections(isa):
        top, production = _top(isa, leaf), match_production(leaf.label)
        sections.append({"code": leaf.code, "label": leaf.label, "unit": leaf.unit, "quantity": leaf.quantity,
                         "workshop": top.label if top else None, "lexicon_name": production["name"] if production else None,
                         "proposed": leaf.code in proposed})
    result["isa"] = {
        "sections": sections, "line_allocations": len(isa.line_sections),
        "account_allocations": len(isa.account_sections), "vat_codes": isa.vat_codes, "due_dates": isa.due_dates,
        "reconciliations": isa.reconciliations,
    }
    return result


# ------------------------------------------------------------------ import

FAMILY_WORDS = (("vigne", "vine_farming"), ("viti", "vine_farming"), ("vin", "wine_making"), ("lait", "animal_farming"),
                ("bovin", "animal_farming"), ("vache", "animal_farming"), ("porc", "animal_farming"),
                ("ovin", "animal_farming"), ("caprin", "animal_farming"), ("volaille", "animal_farming"),
                ("elevage", "animal_farming"), ("animal", "animal_farming"), ("culture", "plant_farming"),
                ("cereale", "plant_farming"), ("legume", "plant_farming"), ("maraich", "plant_farming"),
                ("fruit", "plant_farming"), ("arbori", "plant_farming"), ("fourrage", "plant_farming"),
                ("transform", "processing"), ("energie", "energy_production"))


def _family(top: IsaSection | None, leaves: list[IsaSection]) -> str:
    """Famille de l'atelier : celle de la première production Lexicon reconnue, sinon un mot du libellé de la
    section haute, sinon « Administration » (charges de structure, sections diverses)."""
    from app.services.import_activities import _words, match_production
    for leaf in leaves:
        production = match_production(leaf.label)
        if production:
            return production["family"]
    words = " ".join(_words(top.label if top else ""))
    return next((family for key, family in FAMILY_WORDS if key in words), "administering")


def _sections_to_activities(isa: IsaFile, fy, chosen: list[str] | None) -> tuple[dict, dict]:
    """Ateliers (sections hautes) et activités (feuilles choisies), retrouvés par leur code Isacompta ou créés ;
    surface de la campagne en cours au milieu de l'exercice, si elle n'est pas déjà saisie."""
    from app.models import Activity, ActivityProduction, Campaign, Workshop
    from app.models.analytic import ACTIVITY_FAMILIES
    from app.services import analytic
    from app.services.import_activities import _existing_activity, match_production
    wanted = set(default_sections(isa) if chosen is None else chosen)
    leaves = [leaf for leaf in _activity_sections(isa) if leaf.code in wanted]
    groups: dict[str, list[IsaSection]] = {}
    for leaf in leaves:
        top = _top(isa, leaf)
        groups.setdefault(top.code if top else "", []).append(leaf)
    by_code, stats = {}, {"workshops": 0, "activities": 0, "measures": 0}
    middle = fy.start_date + timedelta(days=(fy.end_date - fy.start_date).days // 2)
    for top_code, members in sorted(groups.items()):
        top = isa.sections.get(top_code) if top_code else None
        family = _family(top, members)
        workshop = Workshop.query.filter_by(isacompta_code=top_code).first() if top_code else None
        if workshop is None:
            name = (top.label if top and top.label else f"{ACTIVITY_FAMILIES[family]} (reprise)")[:120]
            workshop = Workshop.query.filter_by(name=name).first()
            if workshop is None:
                workshop = analytic.save_workshop(None, {"name": name, "family": family,
                                                         "isacompta_code": top_code or None})
                stats["workshops"] += 1
        for leaf in members:
            activity = Activity.query.filter_by(isacompta_code=leaf.code).first()
            if activity is None:
                production = match_production(leaf.label)
                name = (production["name"] if production else (leaf.label or f"Section {leaf.code}").capitalize())[:120]
                activity = _existing_activity(name, production["reference"] if production else None)
                if activity is None:
                    data = {"workshop_id": workshop.id, "name": name, "isacompta_code": leaf.code}
                    if production:
                        data["lexicon_reference"] = production["reference"]
                    if Activity.query.filter_by(workshop_id=workshop.id, name=name).first() is not None:
                        data["name"] = f"{name} ({leaf.code})"[:120]
                    activity = analytic.save_activity(None, data)
                    stats["activities"] += 1
                elif not activity.isacompta_code:
                    activity.isacompta_code = leaf.code
            by_code[leaf.code] = activity
            if leaf.quantity and leaf.unit == "ha" and activity.unit == "hectare":
                year = analytic.campaign_year(activity, middle)
                campaign = Campaign.query.filter_by(year=year).first()
                known = campaign and ActivityProduction.query.filter_by(activity_id=activity.id,
                                                                        campaign_id=campaign.id).first()
                if not known or known.measure is None:
                    analytic.set_measure(activity.id, year, {"measure": leaf.quantity})
                    stats["measures"] += 1
    return by_code, stats


def _key_for(isa: IsaFile, code: str, by_code: dict, keys: dict):
    """Section regroupant d'autres sections (atelier, famille de cultures) : clé « surface » sur les activités
    reprises de ses feuilles en hectares ; None s'il n'y en a pas."""
    from app.models import AnalyticKey
    from app.services import analytic_allocation
    if code in keys:
        return keys[code]
    members = list({a.id: a for leaf, a in sorted(by_code.items())
                    if leaf != code and leaf.startswith(code) and a.unit == "hectare"}.values())
    key = None
    if members:
        section = isa.sections[code]
        name = f"{section.label or 'Section'} ({code})"[:120]
        key = AnalyticKey.query.filter_by(name=name).first() or analytic_allocation.save_key(
            None, {"name": name, "basis": "surface", "note": "Reprise Isacompta : section regroupant des activités.",
                   "members": [{"activity_id": a.id} for a in members]})
    keys[code] = key
    return key


def _target(isa: IsaFile, code: str, by_code: dict, keys: dict):
    """(activité, clé) d'une section : activité reprise, ou clé de ses descendantes ; (None, None) sinon."""
    if code in by_code:
        return by_code[code], None
    if code in isa.sections and any(c != code and c.startswith(code) for c in isa.sections):
        return None, _key_for(isa, code, by_code, keys)
    return None, None


def _allocations(isa: IsaFile, pairs: list, by_code: dict, accounts: dict) -> dict:
    """Ventilations des lignes (ANAMVT) et règles de compte (ANACPT, une seule section à 100 %) ; une section non
    reprise (feuille non choisie, regroupement sans activité en hectares) laisse la ligne à ventiler."""
    from app.models import AnalyticAllocation, AnalyticRule
    from app.services import analytic_allocation
    stats, keys = {"lines": 0, "rules": 0, "skipped": 0}, {}
    for fec_line, model in pairs:
        parts = isa.line_sections.get(id(fec_line)) or []
        if not parts or not analytic_allocation.eligible_code(model.account.code):
            continue
        targets = [(*_target(isa, section, by_code, keys), share) for section, share in parts]
        if any(a is None and k is None for a, k, _s in targets) or sum(s for _a, _k, s in targets) != 1000:
            stats["skipped"] += 1
            continue
        for activity, key, share in targets:
            db.session.add(AnalyticAllocation(journal_line_id=model.id, activity_id=activity.id if activity else None,
                                              key_id=key.id if key else None, share_bp=share * 10, origin="import"))
        stats["lines"] += 1
    for raw, parts in isa.account_sections.items():
        account = accounts.get(raw)
        if account is None or not analytic_allocation.eligible_code(account.code):
            continue
        activity, key = _target(isa, parts[0][0], by_code, keys) if len(parts) == 1 and parts[0][1] == 1000 else (None, None)
        if activity is None and key is None:
            stats["skipped"] += 1
            continue
        if AnalyticRule.query.filter_by(account_prefix=account.code).first() is None:
            analytic_allocation.save_rule({"account_prefix": account.code, "activity_id": activity.id if activity else None,
                                           "key_id": key.id if key else None})
            stats["rules"] += 1
    return stats


def import_history(content: bytes, filename: str, start: date, end: date, overrides: dict | None = None,
                   user_id=None, sections: list[str] | None = None) -> dict:
    """Historique de l'exercice (comme un FEC), puis, dans une instance agricole, ateliers et activités des
    sections choisies (`sections`, défaut : `default_sections`), ventilations des lignes et règles de compte."""
    from app.services import analytic as analytic_service
    isa = parse(content)
    extra = {}

    def after(fy, pairs):
        if not analytic_service.enabled() or not isa.sections:
            return
        by_code, stats = _sections_to_activities(isa, fy, sections)
        accounts = {}
        for raw in isa.account_sections:
            code, aux = account_code(raw)
            if not aux:
                accounts[raw] = next((m.account for f, m in pairs if f.account == code), None)
        stats.update(_allocations(isa, pairs, by_code, accounts))
        extra.update(stats)

    result = fec_import.import_history(content, filename, start, end, overrides, user_id, parser=_parser(isa),
                                       after=after, source_label="isa_history")
    return {**result, "analytic": extra}


def import_opening(content: bytes, filename: str, fy, overrides: dict | None = None, user_id=None) -> dict:
    isa = parse(content)
    return fec_import.import_opening(content, filename, fy, overrides, user_id, parser=_parser(isa))
