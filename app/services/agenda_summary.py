"""Résumé du lundi de l'échéancier (lot AG9a.d, claudedocs/design_echeancier_agricole.md § 7).

- `weekly_summary(jour)` : quatre blocs — en retard (avec la pénalité de la fiche), cette semaine (montant, action),
  à préparer (avec ce qui manque), à vérifier (détections) ; les paiements reconnus sont rattachés d'abord.
- `send_weekly(jour)` : parcourt les instances agricoles actives ; pour chacune, une notification dans
  l'application (une par semaine) et un e-mail à chaque abonné, par le SMTP du serveur (`MAIL_*`, relais Brevo,
  Q-E1). Idempotent : un envoi au plus par utilisateur et par semaine (`agenda_subscriptions.last_sent_week`).
  Lancé chaque lundi par `flask agenda send-weekly` (timer systemd ou cron, `doc/agenda.md`).
- Destinataires (Q-E4) : administrateurs et trésoriers de l'instance, abonnés par défaut ; un administrateur global
  sans rôle sur l'instance seulement s'il s'est abonné ; jamais l'expert-comptable (lecture seule).
- Lien de désabonnement signé (`SECRET_KEY`), sans expiration, propre à l'utilisateur et à l'instance.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from flask import current_app, g
from itsdangerous import BadSignature, URLSafeSerializer

from app.extensions import db
from app.models import AgendaSubscription, Instance, InstanceMembership, Notification, User
from app.models.instance_membership import ROLE_ADMIN, ROLE_TREASURER

NOTIFICATION_KIND = "agenda_weekly"
UNSUBSCRIBE_SALT = "agenda-unsubscribe"
WRITER_ROLES = (ROLE_ADMIN, ROLE_TREASURER)
BLOCK_TITLES = {"late": "En retard", "this_week": "Cette semaine", "to_prepare": "À préparer (d'ici 45 jours)",
                "to_check": "À vérifier"}


def monday_of(day: date) -> date:
    return day - timedelta(days=day.weekday())


def week_key(day: date) -> str:
    year, week, _ = day.isocalendar()
    return f"{year}-W{week:02d}"


def _missing(item: dict) -> list[str]:
    out = []
    if item["managed"] and item["status"] != "ready":
        out.append("déclaration à préparer dans Lyvre")
    if item["amount_proposed"]:
        out.append("montant calculé par Lyvre, à valider")
    if item["to_confirm"]:
        out.append("date à confirmer")
    return out


def _line(item: dict, fiches: dict) -> dict:
    fiche = fiches[item["fiche_id"]]
    action = item.get("action") or {}
    return {"key": item["key"], "label": item["label"], "title": item["title"], "organism": item["organism"],
            "date": item["date"].isoformat(), "period": item["period"], "status": item["status"],
            "amount_cents": item["amount_cents"], "amount_proposed": item["amount_proposed"],
            "link": item.get("link") or action.get("route") or "/agenda/", "action_label": action.get("label"),
            "penalties": fiche.get("penalties"), "missing": _missing(item)}


def weekly_summary(day: date | None = None) -> dict:
    """Résumé de la semaine du jour `day` (défaut : aujourd'hui), lu dans l'instance courante (sans commit)."""
    from app.services import agenda, agenda_checks, deadlines

    day = day or date.today()
    ctx = deadlines.context()
    agenda.match_payments(day, ctx)
    start, end = agenda.window(day)
    items = agenda.occurrences(start, end, day, ctx)["items"]
    fiches = {f["id"]: f for f in deadlines.fiches()}
    blocks = {"late": [], "this_week": [], "to_prepare": []}
    for item in items:
        if item["status"] == "this_week":
            blocks["this_week"].append(_line(item, fiches))
        elif item["quiet"]:
            continue
        elif item["status"] == "late":
            blocks["late"].append(_line(item, fiches))
        elif item["status"] in ("to_prepare", "ready"):
            blocks["to_prepare"].append(_line(item, fiches))
    checks = agenda_checks.detections(day, ctx, items)
    counts = {name: len(rows) for name, rows in blocks.items()} | {"to_check": len(checks)}
    return {"day": day.isoformat(), "week": week_key(day), "monday": monday_of(day).isoformat(), **blocks,
            "to_check": checks, "counts": counts, "empty": not any(counts.values())}


# ------------------------------------------------------------------ abonnements

def subscription_of(user_id: int) -> AgendaSubscription | None:
    return AgendaSubscription.query.filter_by(user_id=user_id).first()


def is_subscribed(user: User, instance: Instance) -> bool:
    """Abonné par défaut s'il écrit sur l'instance ; administrateur global sans rôle : seulement s'il s'est abonné."""
    row = subscription_of(user.id)
    if _membership_role(user, instance) in WRITER_ROLES:
        return row is None or row.subscribed
    return bool(user.is_admin and row is not None and row.subscribed)


def set_subscribed(user_id: int, subscribed: bool) -> AgendaSubscription:
    row = subscription_of(user_id)
    if row is None:
        row = AgendaSubscription(user_id=user_id)
        db.session.add(row)
    row.subscribed = bool(subscribed)
    db.session.flush()
    return row


def _membership_role(user: User, instance: Instance) -> str | None:
    membership = db.session.query(InstanceMembership).filter_by(user_id=user.id, instance_id=instance.id).first()
    return membership.role if membership else None


def recipients(instance: Instance) -> list[User]:
    """Utilisateurs actifs qui écrivent sur l'instance et n'ont pas refusé le résumé, plus les administrateurs
    globaux abonnés."""
    rows = {row.user_id: row for row in AgendaSubscription.query}
    members = (db.session.query(User).join(InstanceMembership, InstanceMembership.user_id == User.id)
               .filter(InstanceMembership.instance_id == instance.id, InstanceMembership.role.in_(WRITER_ROLES),
                       User.is_active.is_(True)).all())
    out = [u for u in members if u.email and (u.id not in rows or rows[u.id].subscribed)]
    known = {u.id for u in members}
    opted = [uid for uid, row in rows.items() if row.subscribed and uid not in known]
    if opted:
        out += [u for u in db.session.query(User).filter(User.id.in_(opted), User.is_admin.is_(True),
                                                         User.is_active.is_(True)) if u.email]
    return sorted(out, key=lambda u: u.id)


def _serializer() -> URLSafeSerializer:
    return URLSafeSerializer(current_app.config["SECRET_KEY"], salt=UNSUBSCRIBE_SALT)


def unsubscribe_token(instance_id: int, user_id: int) -> str:
    return _serializer().dumps({"i": instance_id, "u": user_id})


def read_unsubscribe_token(token: str) -> tuple[int, int] | None:
    try:
        data = _serializer().loads(token or "")
    except BadSignature:
        return None
    if not isinstance(data, dict) or not isinstance(data.get("i"), int) or not isinstance(data.get("u"), int):
        return None
    return data["i"], data["u"]


# ------------------------------------------------------------------ e-mail

def _euros(cents: int) -> str:
    return f"{cents / 100:,.2f}".replace(",", " ").replace(".", ",") + " €"


def _fr(iso: str) -> str:
    return date.fromisoformat(iso).strftime("%d/%m")


def render_text(summary: dict, name: str, base_url: str, unsubscribe_url: str) -> tuple[str, str]:
    """(objet, texte) de l'e-mail du lundi ; `name` : nom de l'exploitation."""
    monday = date.fromisoformat(summary["monday"])
    counts = summary["counts"]
    subject = f"Lyvre — {name} : échéancier de la semaine du {monday:%d/%m}"
    if counts["late"] or counts["this_week"]:
        subject += f" ({counts['late']} en retard, {counts['this_week']} cette semaine)"
    lines = ["Bonjour,", "", f"Voici l'échéancier de {name} pour la semaine du {monday:%d/%m/%Y}.", ""]
    for name in ("late", "this_week", "to_prepare"):
        rows = summary[name]
        if not rows:
            continue
        lines += [f"{BLOCK_TITLES[name]} ({len(rows)})", ""]
        for row in rows:
            text = f"- {_fr(row['date'])} · {row['label']} ({row['organism']}, {row['period']})"
            if row["amount_cents"]:
                text += f" : {_euros(row['amount_cents'])}" + (" calculés par Lyvre" if row["amount_proposed"] else "")
            lines.append(text)
            if name == "late" and row["penalties"]:
                lines.append(f"  Pénalités : {row['penalties']}")
            if name != "late" and row["missing"]:
                lines.append(f"  À faire : {', '.join(row['missing'])}")
            lines.append(f"  {base_url}{row['link']}")
        lines.append("")
    if summary["to_check"]:
        lines += [f"{BLOCK_TITLES['to_check']} ({len(summary['to_check'])})", ""]
        for check in summary["to_check"]:
            lines.append(f"- {check['title']} : {check['detail']}")
            if check["link"]:
                lines.append(f"  {base_url}{check['link']}")
        lines.append("")
    lines += [f"Tout l'échéancier : {base_url}/agenda/", "",
              "Lyvre rappelle et prépare les échéances ; il ne télédéclare pas et ne paie pas à votre place.", "",
              f"Ne plus recevoir ce résumé pour {name} : {unsubscribe_url}", ""]
    return subject, "\n".join(lines)


# ------------------------------------------------------------------ envoi

def _select(instance: Instance | None) -> None:
    from app.tenant import get_tenant_engine

    g.current_instance = instance
    g.tenant_engine = get_tenant_engine(instance) if instance is not None else None


def _notify(summary: dict) -> bool:
    """Notification de la semaine pour tous les utilisateurs de l'instance (une seule par semaine)."""
    title = f"Échéancier — semaine du {date.fromisoformat(summary['monday']):%d/%m}"
    if Notification.query.filter_by(kind=NOTIFICATION_KIND, title=title).first() is not None:
        return False
    counts = summary["counts"]
    parts = [f"{counts[name]} {label.lower()}" for name, label in
             (("late", "En retard"), ("this_week", "Cette semaine"), ("to_prepare", "À préparer"),
              ("to_check", "À vérifier")) if counts[name]]
    level = "warning" if counts["late"] else "info"
    db.session.add(Notification(user_id=None, kind=NOTIFICATION_KIND, level=level, title=title,
                                message=", ".join(parts) + "." if parts else "Rien à signaler cette semaine.",
                                url="/agenda/"))
    return True


def send_weekly(day: date | None = None, dry_run: bool = False, deliver=None, log=None) -> dict:
    """Envoie le résumé de la semaine à chaque abonné des instances agricoles actives. Retourne les compteurs.
    `deliver(to, objet, texte)` : envoi (défaut : SMTP du serveur) ; `log(texte)` : une ligne par envoi."""
    from app.services import organization, password_reset

    day = day or date.today()
    week = week_key(day)
    deliver = deliver or password_reset.deliver
    log = log or current_app.logger.info
    base_url = (current_app.config.get("APP_BASE_URL") or "").rstrip("/")
    stats = {"instances": 0, "sent": 0, "skipped": 0, "failed": 0, "notifications": 0}
    if not base_url and not dry_run:
        raise RuntimeError("APP_BASE_URL non configurée : les liens du résumé ne peuvent pas être construits.")
    previous = (getattr(g, "current_instance", None), getattr(g, "tenant_engine", None))
    try:
        for instance in Instance.query.filter(Instance.is_active.is_(True), Instance.chart == "agri").order_by(Instance.id):
            stats["instances"] += 1
            _select(instance)
            try:
                summary = weekly_summary(day)
                name = organization.get().name or instance.label
                if dry_run:
                    db.session.rollback()          # essai : ni paiement rattaché ni notification
                else:
                    stats["notifications"] += _notify(summary)
                    db.session.commit()
            except Exception:  # une instance en échec n'arrête pas les autres
                db.session.rollback()
                current_app.logger.exception("Résumé du lundi : instance %s en échec", instance.slug)
                stats["failed"] += 1
                continue
            for user in recipients(instance):
                row = subscription_of(user.id)
                if row is not None and row.last_sent_week == week:
                    stats["skipped"] += 1
                    log(f"agenda weekly {week} {instance.slug} user={user.id} déjà envoyé")
                    continue
                if summary["empty"]:
                    stats["skipped"] += 1
                    log(f"agenda weekly {week} {instance.slug} user={user.id} rien à signaler")
                    continue
                link = f"{base_url}/agenda/unsubscribe?token={unsubscribe_token(instance.id, user.id)}"
                subject, text = render_text(summary, name, base_url, link)
                if dry_run:
                    stats["sent"] += 1
                    log(f"agenda weekly {week} {instance.slug} user={user.id} essai (non envoyé)")
                    continue
                try:
                    deliver(user.email, subject, text)
                except Exception as exc:  # noqa: BLE001 — journalisé, l'envoi suivant continue
                    stats["failed"] += 1
                    log(f"agenda weekly {week} {instance.slug} user={user.id} échec : {exc!r}")
                    continue
                row = row or AgendaSubscription(user_id=user.id)
                row.last_sent_week, row.last_sent_at = week, datetime.utcnow()
                db.session.add(row)
                db.session.commit()
                stats["sent"] += 1
                log(f"agenda weekly {week} {instance.slug} user={user.id} envoyé")
    finally:
        g.current_instance, g.tenant_engine = previous
    return stats
