"""Pages servies par la SPA React (claudedocs/design_front_mantine.md §4).

``app/spa_routes.json`` liste les pages migrées : chaque règle est enregistrée
en GET avec le **même nom d'endpoint** que l'ancienne vue Jinja, si bien que
``url_for`` (menus, liens et redirections des pages encore en Jinja) continue de
fonctionner. Une ancienne vue GET encore présente sur le même endpoint fait
échouer le démarrage (Flask refuse d'écraser un endpoint) : la bascule d'un
écran supprime donc sa vue HTML.
"""
import json
import os

from flask import render_template
from flask_login import login_required

ROUTES_FILE = os.path.join(os.path.dirname(__file__), "spa_routes.json")


def load_routes() -> list[dict]:
    with open(ROUTES_FILE, encoding="utf-8") as fh:
        return json.load(fh)["routes"]


def spa_shell(**_kwargs):
    """Coquille HTML de la SPA : le routeur React affiche la page selon l'URL."""
    return render_template("spa.html")


_private_shell = login_required(spa_shell)


def register_spa(app):
    for route in load_routes():
        view = spa_shell if route.get("public") else _private_shell
        app.add_url_rule(route["rule"], endpoint=route["endpoint"], view_func=view, methods=["GET"])
