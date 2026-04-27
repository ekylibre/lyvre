from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required
from app.extensions import db
from app.models import Entity
from app.models.entity import ENTITY_TYPES

bp = Blueprint("entities", __name__, url_prefix="/entities")


@bp.route("/")
@login_required
def index():
    entities = Entity.query.order_by(Entity.name).all()
    return render_template("entities/index.html", entities=entities, entity_types=dict(ENTITY_TYPES))


@bp.route("/new", methods=["GET", "POST"])
@login_required
def new():
    if request.method == "POST":
        name = request.form["name"].strip()
        if not name:
            flash("Le nom est obligatoire.", "danger")
        elif Entity.query.filter_by(name=name).first():
            flash(f"Une entité nommée « {name} » existe déjà.", "danger")
        else:
            entity = Entity(
                name=name,
                entity_type=request.form.get("entity_type", "AUTRE"),
                account_code=request.form.get("account_code", "").strip() or None,
                notes=request.form.get("notes", "").strip() or None,
            )
            db.session.add(entity)
            db.session.commit()
            flash(f"Entité « {name} » créée.", "success")
            return redirect(url_for("entities.index"))

    return render_template("entities/form.html", entity=None, entity_types=ENTITY_TYPES)


@bp.route("/<int:entity_id>/edit", methods=["GET", "POST"])
@login_required
def edit(entity_id):
    entity = Entity.query.get_or_404(entity_id)
    if request.method == "POST":
        name = request.form["name"].strip()
        if not name:
            flash("Le nom est obligatoire.", "danger")
        else:
            existing = Entity.query.filter(Entity.name == name, Entity.id != entity_id).first()
            if existing:
                flash(f"Une autre entité nommée « {name} » existe déjà.", "danger")
            else:
                entity.name = name
                entity.entity_type = request.form.get("entity_type", "AUTRE")
                entity.account_code = request.form.get("account_code", "").strip() or None
                entity.notes = request.form.get("notes", "").strip() or None
                db.session.commit()
                flash("Entité mise à jour.", "success")
                return redirect(url_for("entities.index"))

    return render_template("entities/form.html", entity=entity, entity_types=ENTITY_TYPES)


@bp.route("/<int:entity_id>/delete", methods=["POST"])
@login_required
def delete(entity_id):
    entity = Entity.query.get_or_404(entity_id)
    count = entity.transactions.count()
    if count > 0:
        flash(
            f"Impossible de supprimer « {entity.name} » : {count} transaction(s) liée(s).",
            "danger",
        )
        return redirect(url_for("entities.index"))
    db.session.delete(entity)
    db.session.commit()
    flash(f"Entité « {entity.name} » supprimée.", "success")
    return redirect(url_for("entities.index"))
