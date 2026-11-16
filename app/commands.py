"""Commandes `flask …` d'exploitation (lancées par le serveur, hors requête).

- `flask agenda send-weekly [--date AAAA-MM-JJ] [--dry-run]` : résumé du lundi de l'échéancier aux abonnés des
  exploitations (lot AG9a.d) ; une ligne par envoi sur la sortie ; à planifier chaque lundi à 7 h
  (`doc/agenda.md`).
"""
from datetime import date

import click
from flask.cli import AppGroup

agenda_cli = AppGroup("agenda", help="Échéancier des exploitations.")


@agenda_cli.command("send-weekly")
@click.option("--date", "day", default=None, help="Jour de référence (AAAA-MM-JJ), aujourd'hui par défaut.")
@click.option("--dry-run", is_flag=True, help="Calcule et liste les envois sans rien envoyer ni enregistrer.")
def send_weekly_command(day, dry_run):
    """Envoie le résumé de la semaine (un envoi au plus par utilisateur et par semaine)."""
    from app.services import agenda_summary

    try:
        on = date.fromisoformat(day) if day else date.today()
    except ValueError:
        raise click.BadParameter("date attendue au format AAAA-MM-JJ", param_hint="--date") from None
    stats = agenda_summary.send_weekly(on, dry_run=dry_run, log=click.echo)
    click.echo(f"{stats['instances']} exploitation(s), {stats['sent']} envoi(s), {stats['skipped']} ignoré(s), "
               f"{stats['failed']} échec(s), {stats['notifications']} notification(s).")
    if stats["failed"]:
        raise SystemExit(1)


def register_commands(app):
    app.cli.add_command(agenda_cli)
