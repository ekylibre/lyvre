"""Projets / activités (lot C.1) : liste avec charges et produits, création, modification,
archivage ; affectation et ventilation des lignes d'écriture."""
from contextlib import contextmanager

from flask import jsonify, request

from app.extensions import db
from app.models import JournalLine, Project
from app.services import projects

from . import ApiError, bp, get_or_404, json_body, notice


@contextmanager
def _errors():
    """ProjectError → réponse d'API (champ en erreur si connu)."""
    try:
        yield
    except projects.ProjectError as exc:
        db.session.rollback()
        code = "validation_error" if exc.status == 422 else "conflict"
        raise ApiError(code, exc.message, exc.status, {exc.field: exc.message} if exc.field else None) from None


@bp.route("/projects")
def projects_list():
    """`?fiscal_year_id=` : charges et produits de cet exercice (sinon tous exercices)."""
    fy = projects.fiscal_year_or_none(request.args.get("fiscal_year_id"))
    figures = projects.totals(fy.id if fy else None)
    items = [projects.payload(p, figures.get(p.id)) for p in Project.query.order_by(Project.archived, Project.name)]
    return jsonify(items=items, meta={"fiscal_year_id": fy.id if fy else None})


@bp.route("/projects/options")
def projects_options():
    return jsonify(items=projects.options())


@bp.route("/projects", methods=["POST"])
def projects_create():
    with _errors():
        project = projects.save(None, json_body())
    return jsonify(item=projects.payload(project), notices=[notice(f"Projet « {project.name} » créé.")]), 201


@bp.route("/projects/<int:project_id>")
def projects_get(project_id):
    project = get_or_404(Project, project_id, "Projet introuvable.")
    return jsonify(item=projects.payload(project, projects.totals().get(project.id)))


@bp.route("/projects/<int:project_id>", methods=["PUT"])
def projects_update(project_id):
    project = get_or_404(Project, project_id, "Projet introuvable.")
    with _errors():
        projects.save(project, json_body())
    return jsonify(item=projects.payload(project), notices=[notice(f"Projet « {project.name} » enregistré.")])


@bp.route("/projects/<int:project_id>", methods=["DELETE"])
def projects_delete(project_id):
    project = get_or_404(Project, project_id, "Projet introuvable.")
    name = project.name
    with _errors():
        projects.delete(project)
    return jsonify(notices=[notice(f"Projet « {name} » supprimé.")])


@bp.route("/entries/<int:entry_id>/lines/<int:line_id>/project", methods=["PUT"])
def entry_line_project(entry_id, line_id):
    """`{project_id}` (null : aucun) ; possible sur une écriture rapprochée."""
    line = _line(entry_id, line_id)
    with _errors():
        projects.set_line_project(line, json_body().get("project_id"))
    return jsonify(notices=[notice("Projet de la ligne enregistré.")])


@bp.route("/entries/<int:entry_id>/lines/<int:line_id>/split", methods=["POST"])
def entry_line_split(entry_id, line_id):
    """Ventilation : `{parts: [{project_id, amount_cents}]}`, total = montant de la ligne."""
    line = _line(entry_id, line_id)
    with _errors():
        lines = projects.split_line(line, json_body().get("parts"))
    return jsonify(notices=[notice(f"Ligne ventilée en {len(lines)} parts.")])


def _line(entry_id, line_id):
    line = db.session.get(JournalLine, line_id)
    if line is None or line.entry_id != entry_id:
        raise ApiError("not_found", "Ligne d'écriture introuvable.", 404)
    return line
