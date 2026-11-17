"""Lot R1 : version de Lyvre et changelog. Le dépôt doit être cohérent (fichiers générés à jour),
la numérotation calendaire correcte, la publication sans effet sur git."""
import json
from datetime import date

import pytest
import yaml

import scripts.release as release
from app import version


def test_repository_is_consistent():
    """data/changelog.yml valide, CHANGELOG.md, package.json et README régénérés (sinon : release.py build)."""
    assert release.check() == []


def test_version_is_the_first_published_entry():
    data = version.load()
    assert version.version() == data["versions"][0]["version"]
    assert json.loads(release.PACKAGE_JSON.read_text())["version"] == version.version()


@pytest.mark.parametrize("previous, today, expected", [
    ("2026.10.18", date(2026, 10, 27), "2026.10.19"),
    ("2026.10.18", date(2026, 11, 2), "2026.11.1"),
    ("2026.12.4", date(2027, 1, 5), "2027.01.1"),
    (None, date(2026, 10, 27), "2026.10.1"),
])
def test_next_version(previous, today, expected):
    assert version.next_version(previous, today) == expected


def test_next_version_refuses_a_future_month():
    with pytest.raises(version.ChangelogError):
        version.next_version("2026.11.1", date(2026, 10, 27))


def test_validation_errors():
    data = {"next": [{"kind": "bogus", "text": ""}], "versions": [
        {"version": "2026.10.2", "date": date(2026, 10, 3), "title": "B", "entries": [{"kind": "new", "text": "x"}]},
        {"version": "2026.10.3", "date": date(2026, 11, 1), "title": "", "entries": [{"kind": "new", "structure": "x", "text": "y"}]},
        {"version": "26.1", "date": date(2026, 1, 1), "title": "C"},
    ]}
    errors = "\n".join(version.validate(data))
    for expected in ("plus récente à la plus ancienne", "n'est pas dans le mois", "titre manquant",
                     "structure parmi asso, sci", "format AAAA.MM.N", "next, entrée 1 : type", "next, entrée 1 : texte"):
        assert expected in errors, expected


def test_markdown_groups_actions_first_with_structure_tags():
    data = {"versions": [{"version": "2026.10.2", "date": date(2026, 10, 26), "title": "Brevo", "entries": [
        {"kind": "new", "structure": "asso", "text": "Synchronisation Brevo.", "tech": "Lot B2."},
        {"kind": "action", "text": "Autoriser l'IP."},
        {"kind": "fixed", "structure": "sci", "text": "Carte du bail."}]}]}
    md = version.markdown(data)
    assert "## 2026.10.2 — Brevo (26/10/2026)" in md
    assert md.index("Action requise") < md.index("### Nouveautés") < md.index("### Corrections")
    assert "- [Associations] Synchronisation Brevo. — *Lot B2.*" in md and "- [SCI] Carte du bail." in md


def test_publish_turns_next_into_a_version_without_touching_git(tmp_path, monkeypatch):
    changelog = tmp_path / "changelog.yml"
    changelog.write_text(yaml.safe_dump({"next": [{"kind": "new", "text": "Page Nouveautés."}], "versions": [
        {"version": "2026.10.18", "date": date(2026, 10, 26), "title": "Brevo",
         "entries": [{"kind": "new", "text": "Brevo."}]}]}, allow_unicode=True), encoding="utf-8")
    package = tmp_path / "package.json"
    package.write_text('{\n  "name": "x",\n  "version": "2026.10.18"\n}\n')
    lock = tmp_path / "package-lock.json"
    lock.write_text(json.dumps({"name": "x", "version": "2026.10.18", "packages": {"": {"version": "2026.10.18"}}}, indent=2) + "\n")
    readme = tmp_path / "README.md"
    readme.write_text("Badge : <!-- version -->old<!-- /version --> fin\n")
    for name, value in (("CHANGELOG_FILE", changelog), ("PACKAGE_JSON", package), ("PACKAGE_LOCK", lock),
                        ("README", readme), ("CHANGELOG_MD", tmp_path / "CHANGELOG.md")):
        monkeypatch.setattr(release, name, value)
    monkeypatch.setattr(release, "load", lambda: version.load(changelog))
    calls = []
    monkeypatch.setattr("subprocess.run", lambda *a, **k: calls.append(a))

    number = release.publish("Nouveautés", today=date(2026, 10, 27))
    assert number == "2026.10.19"
    data = version.load(changelog)
    assert data["next"] == [] and data["versions"][0]["entries"] == [{"kind": "new", "text": "Page Nouveautés."}]
    assert data["versions"][0]["date"] == date(2026, 10, 27)
    assert '"version": "2026.10.19"' in package.read_text()
    assert json.loads(lock.read_text())["packages"][""]["version"] == "2026.10.19"
    assert "badge/version-2026.10.19-" in readme.read_text()
    assert "## 2026.10.19 — Nouveautés (27/10/2026)" in (tmp_path / "CHANGELOG.md").read_text()
    assert calls == []  # ni commit ni tag
    with pytest.raises(version.ChangelogError):
        release.publish(None, today=date(2026, 10, 27))  # « next » vide


def test_session_reports_the_version(app, login_as, monkeypatch):
    monkeypatch.setenv("APP_COMMIT", "a1b2c3d4e5f6a7b8")
    # Connecté d'abord : le contexte d'application des tests, partagé, garderait l'anonyme en mémoire.
    assert login_as().get("/api/v1/session").get_json()["app"]["version"] == version.version()
    anonymous = app.test_client().get("/api/v1/version")
    assert anonymous.status_code == 200
    assert anonymous.get_json() == {"version": version.version(), "commit": "a1b2c3d4e5f6"}


def test_published_hides_next_and_technical_notes():
    items = version.published()
    assert items[0]["version"] == version.version()
    assert all("tech" not in e for v in items for e in v["entries"])
    assert all(isinstance(v["date"], str) for v in items)



# ------------------------------------------------------------------ page « Nouveautés » (lot R2)


def test_changelog_route_for_signed_in_users(app, login_as):
    client = login_as()
    body = client.get("/api/v1/changelog").get_json()
    assert body["version"] == version.version() and body["items"][0]["version"] == version.version()
    assert all("tech" not in e for v in body["items"] for e in v["entries"])
    assert any(e.get("structure") == "asso" for v in body["items"] for e in v["entries"])


def test_changelog_requires_login(app):
    assert app.test_client().get("/api/v1/changelog").status_code == 401


def test_first_session_marks_the_current_version_as_seen(app, login_as):
    from app.models import User
    client = login_as()
    assert client.get("/api/v1/session").get_json()["preferences"]["changelog_seen"] == version.version()
    user = User.query.filter_by(email="user@example.org").one()
    assert json.loads(user.preferences)["changelog_seen"] == version.version()
    # Une préférence déjà enregistrée (version plus ancienne) est conservée : la pastille s'affiche.
    user.preferences = json.dumps({"changelog_seen": "2026.10.1"})
    from app.extensions import db
    db.session.commit()
    assert client.get("/api/v1/session").get_json()["preferences"]["changelog_seen"] == "2026.10.1"
