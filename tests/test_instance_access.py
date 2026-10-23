"""Service des accès aux instances (E1, claudedocs/design_acces_instances.md §3) : validation des
lignes sans écriture, création des comptes et des accès, avertissements, membres et gardes."""
import os

import pytest

from app.extensions import db
from app.models import Instance, InstanceMembership, User
from app.services import instance_access as ia
from app.services.instance_access import AccessError


def _user(email, *, is_admin=False, is_active=True):
    user = User(email=email, is_admin=is_admin, is_active=is_active)
    user.set_password("x")
    db.session.add(user)
    db.session.commit()
    return user


def _instance(slug="asso-x"):
    inst = Instance(slug=slug, label=slug.title(), database_url=os.environ["DATABASE_URL"])
    db.session.add(inst)
    db.session.commit()
    return inst


def _refused(fn, *args, **kwargs) -> AccessError:
    with pytest.raises(AccessError) as info:
        fn(*args, **kwargs)
    return info.value


# ------------------------------------------------------------------ parse_grants


def test_parse_grants_existing_and_new(app):
    marie = _user("marie@asso.fr")
    grants = ia.parse_grants([{"user_id": marie.id, "role": "treasurer"},
                              {"email": " Paul@Asso.fr ", "full_name": " Paul ", "password": "motdepasse", "role": "admin"}])
    assert grants[0].user == marie and grants[0].role == "treasurer"
    assert (grants[1].email, grants[1].full_name, grants[1].password) == ("paul@asso.fr", "Paul", "motdepasse")
    assert ia.parse_grants(None) == [] and ia.parse_grants([]) == []


@pytest.mark.parametrize("items, field, message", [
    ("x", "members", "liste"),
    (["x"], "members.0", "Ligne invalide"),
    ([{"user_id": 999, "role": "admin"}], "members.0.user_id", "introuvable"),
    ([{"email": "a@b.fr", "password": "motdepasse", "role": "chef"}], "members.0.role", "Rôle inconnu"),
    ([{"email": "pas-un-email", "password": "motdepasse", "role": "admin"}], "members.0.email", "Email invalide"),
    ([{"email": "a@b.fr", "password": "court", "role": "admin"}], "members.0.password", "8 caractères"),
    ([{"email": "a@b.fr", "password": "motdepasse", "role": "admin"},
      {"email": "A@B.fr", "password": "motdepasse", "role": "treasurer"}], "members.1.email", "déjà dans la liste"),
])
def test_parse_grants_refusals(app, items, field, message):
    err = _refused(ia.parse_grants, items)
    assert err.field == field and message in err.message and err.status == 422


def test_parse_grants_refuses_global_admin_duplicates_and_known_email(app):
    boss = _user("boss@asso.fr", is_admin=True)
    marie = _user("marie@asso.fr")
    assert "Administrateur global" in _refused(ia.parse_grants, [{"user_id": boss.id, "role": "admin"}]).message
    err = _refused(ia.parse_grants, [{"user_id": marie.id, "role": "admin"}, {"user_id": marie.id, "role": "treasurer"}])
    assert err.field == "members.1.user_id"
    err = _refused(ia.parse_grants, [{"email": "MARIE@asso.fr", "password": "motdepasse", "role": "admin"}])
    assert err.field == "members.0.email" and "choisissez-le" in err.message
    # un compte choisi puis ressaisi comme nouveau : doublon
    err = _refused(ia.parse_grants, [{"user_id": marie.id, "role": "admin"},
                                     {"email": "marie@asso.fr", "password": "motdepasse", "role": "admin"}])
    assert err.field == "members.1.email"


def test_parse_grants_writes_nothing(app):
    before = User.query.count()
    _refused(ia.parse_grants, [{"email": "a@b.fr", "password": "motdepasse", "role": "admin"},
                               {"email": "c@d.fr", "password": "court", "role": "admin"}])
    assert User.query.count() == before


def test_warnings(app):
    sleeping = _user("dort@asso.fr", is_active=False)
    grants = ia.parse_grants([{"user_id": sleeping.id, "role": "treasurer"}])
    warnings = ia.grants_warnings(grants)
    assert any("Aucun administrateur" in w for w in warnings)
    assert any("dort@asso.fr désactivé" in w for w in warnings)
    assert ia.grants_warnings([]) == []
    admin_line = ia.parse_grants([{"email": "a@b.fr", "password": "motdepasse", "role": "admin"}])
    assert ia.grants_warnings(admin_line) == []


# ------------------------------------------------------------------ apply_grants


def test_apply_grants_creates_accounts_and_access(app):
    me = _user("moi@asso.fr", is_admin=True)
    marie = _user("marie@asso.fr")
    inst = _instance()
    grants = ia.parse_grants([{"user_id": marie.id, "role": "treasurer"},
                              {"email": "paul@asso.fr", "password": "motdepasse", "role": "admin"}])
    counts = ia.apply_grants(inst, grants, me)
    db.session.commit()
    assert counts == {"created": 1, "granted": 2}
    assert ia.grants_summary(counts) == "1 compte créé, 2 accès donnés"
    assert ia.grants_summary({"created": 0, "granted": 0}) == ""
    paul = User.query.filter_by(email="paul@asso.fr").one()
    assert paul.check_password("motdepasse") and paul.must_change_password and not paul.is_admin
    assert not marie.must_change_password
    rows = {m.user_id: m for m in InstanceMembership.query.filter_by(instance_id=inst.id)}
    assert rows[paul.id].role == "admin" and rows[marie.id].role == "treasurer"
    assert {m.created_by_user_id for m in rows.values()} == {me.id}


# ------------------------------------------------------------------ membres


def test_members_and_guards_on_any_instance(app):
    me = _user("moi@asso.fr", is_admin=True)
    inst = _instance()
    inst.is_active = False  # une instance désactivée se prépare aussi
    db.session.commit()
    paul, created = ia.add_member(inst, {"email": "paul@asso.fr", "password": "motdepasse", "role": "admin"}, me)
    assert created and paul.must_change_password
    marie = _user("marie@asso.fr")
    user, created = ia.add_member(inst, {"user_id": marie.id, "role": "accountant"}, me)
    assert user == marie and not created
    err = _refused(ia.add_member, inst, {"user_id": marie.id, "role": "accountant"}, me)
    assert err.field == "user_id" and "déjà accès" in err.message
    err = _refused(ia.add_member, inst, {"email": "moi@asso.fr", "role": "admin"}, me)
    assert err.status == 409

    rows = {m["email"]: m for m in ia.members(inst, me.id)}
    assert rows["moi@asso.fr"]["global_admin"] and rows["moi@asso.fr"]["is_me"]
    assert rows["paul@asso.fr"]["role"] == "admin" and rows["marie@asso.fr"]["role_label"] == "Expert-comptable"

    assert _refused(ia.set_role, inst, paul.id, "treasurer").status == 409  # dernier administrateur
    assert _refused(ia.remove_member, inst, paul.id).status == 409
    assert _refused(ia.set_role, inst, me.id, "treasurer").status == 409    # administrateur global
    assert _refused(ia.remove_member, inst, 999).status == 404
    ia.set_role(inst, marie.id, "admin")
    ia.set_role(inst, paul.id, "treasurer")
    assert ia.remove_member(inst, paul.id) == "paul@asso.fr"
    assert InstanceMembership.query.filter_by(instance_id=inst.id).count() == 1


# ------------------------------------------------------------------ mot de passe à changer (page Utilisateurs)


def test_users_screen_flags_password_set_for_someone_else(login_as):
    client = login_as(is_admin=True)
    item = client.post("/api/v1/users", json={"email": "membre@asso.fr", "password": "motdepasse"}).get_json()["item"]
    assert item["must_change_password"] is True
    user = db.session.get(User, item["id"])
    user.must_change_password = False
    db.session.commit()
    client.patch(f"/api/v1/users/{user.id}", json={"email": "membre@asso.fr", "is_active": True})
    db.session.expire_all()
    assert not db.session.get(User, user.id).must_change_password  # sans mot de passe : inchangé
    client.patch(f"/api/v1/users/{user.id}", json={"email": "membre@asso.fr", "is_active": True, "password": "autre-mdp"})
    db.session.expire_all()
    assert db.session.get(User, user.id).must_change_password


def test_users_screen_own_password_is_not_flagged(login_as):
    client = login_as(is_admin=True)
    me = User.query.filter_by(email="admin@example.org").one()
    client.patch(f"/api/v1/users/{me.id}", json={"email": me.email, "is_admin": True, "is_active": True,
                                                  "password": "nouveau-mdp"})
    db.session.expire_all()
    assert not db.session.get(User, me.id).must_change_password


def test_seed_meta_adds_the_column(app):
    import seed_meta
    from sqlalchemy import inspect

    seed_meta._ensure_user_must_change_password_column()  # idempotent sur une base qui l'a déjà
    columns = {c["name"] for c in inspect(db.engines["meta"]).get_columns("users")}
    assert "must_change_password" in columns
