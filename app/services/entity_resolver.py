"""Helpers de résolution / création d'`Entity` à partir d'un email.

Mutualisé entre la synchro HelloAsso et la synchro Odoo POS.
"""
from app.extensions import db
from app.models import Entity


def entity_by_email(cache, email):
    """Cherche une Entity par email (insensible à la casse), avec cache local.

    `cache` : dict {email_lower: Entity|None} mémoire, partagé pour la durée d'un sync.
    """
    if not email:
        return None
    key = email.strip().lower()
    if key in cache:
        return cache[key]
    ent = Entity.query.filter(db.func.lower(Entity.email) == key).first()
    cache[key] = ent
    return ent


def unique_entity_name(base_name, email=None):
    """Garantit l'unicité de Entity.name : ajoute l'email puis un suffixe numérique."""
    if not Entity.query.filter_by(name=base_name).first():
        return base_name
    if email:
        with_email = f"{base_name} ({email})"
        if not Entity.query.filter_by(name=with_email).first():
            return with_email
    n = 2
    while True:
        candidate = f"{base_name} #{n}"
        if not Entity.query.filter_by(name=candidate).first():
            return candidate
        n += 1
