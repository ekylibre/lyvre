"""Version et changelog de Lyvre (lot R1), à partir de data/changelog.yml.

    python scripts/release.py check                  # fichier valide, fichiers générés à jour
    python scripts/release.py build                  # régénère CHANGELOG.md, package.json, badge du README
    python scripts/release.py publish [--title "…"]  # « next » devient la version AAAA.MM.N du jour, puis build

`publish` ne commite et ne pousse rien : il affiche les commandes git à lancer (commit, tag
v<version>). Le numéro n'est écrit à la main nulle part : il est celui de la première version de
data/changelog.yml.
"""
import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.version import CHANGELOG_FILE, ChangelogError, load, markdown, next_version, validate  # noqa: E402

CHANGELOG_MD = ROOT / "CHANGELOG.md"
PACKAGE_JSON = ROOT / "frontend" / "package.json"
PACKAGE_LOCK = ROOT / "frontend" / "package-lock.json"
README = ROOT / "README.md"
BADGE = re.compile(r"(<!-- version -->).*?(<!-- /version -->)", re.S)


def badge(version: str) -> str:
    return (f"[![Version {version}](https://img.shields.io/badge/version-{version.replace('-', '--')}-2f6b4f)]"
            f"(CHANGELOG.md)")


def _package(version: str) -> str:
    text = PACKAGE_JSON.read_text(encoding="utf-8")
    return re.sub(r'("version":\s*")[^"]*(")', rf"\g<1>{version}\g<2>", text, count=1)


def _lock(version: str) -> str:
    """Version du paquet racine dans package-lock.json (en tête et sous packages[""])."""
    data = json.loads(PACKAGE_LOCK.read_text(encoding="utf-8"))
    data["version"] = version
    if "" in data.get("packages", {}):
        data["packages"][""]["version"] = version
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def _readme(version: str) -> str | None:
    if not README.exists():
        return None
    text = README.read_text(encoding="utf-8")
    return BADGE.sub(lambda m: f"{m.group(1)}{badge(version)}{m.group(2)}", text)


def expected(data: dict) -> dict[Path, str]:
    """Contenu attendu de chaque fichier généré."""
    version = data["versions"][0]["version"] if data["versions"] else "0.0.0"
    out = {CHANGELOG_MD: markdown(data), PACKAGE_JSON: _package(version), PACKAGE_LOCK: _lock(version)}
    readme = _readme(version)
    if readme is not None:
        out[README] = readme
    return out


def check() -> list[str]:
    data = load()
    errors = validate(data)
    if not errors:
        for path, content in expected(data).items():
            if not path.exists() or path.read_text(encoding="utf-8") != content:
                errors.append(f"{path.relative_to(ROOT)} n'est pas à jour : lancer `python scripts/release.py build`.")
    return errors


def build() -> str:
    data = load()
    errors = validate(data)
    if errors:
        raise ChangelogError("\n".join(errors))
    for path, content in expected(data).items():
        path.write_text(content, encoding="utf-8")
    return data["versions"][0]["version"] if data["versions"] else "0.0.0"


def publish(title: str | None, today: date | None = None) -> str:
    data = load()
    if not data["next"]:
        raise ChangelogError("Rien à publier : la liste « next » de data/changelog.yml est vide.")
    today = today or date.today()
    previous = data["versions"][0]["version"] if data["versions"] else None
    number = next_version(previous, today)
    data["versions"].insert(0, {"version": number, "date": today, "title": title or "Nouveautés",
                                "entries": data["next"]})
    data["next"] = []
    errors = validate(data)
    if errors:
        raise ChangelogError("\n".join(errors))
    CHANGELOG_FILE.write_text(dump(data), encoding="utf-8")
    build()
    return number


def dump(data: dict) -> str:
    header = ("# Nouveautés de Lyvre : source unique du numéro de version, de CHANGELOG.md et de la page\n"
              "# « Nouveautés ». Ajouter les entrées sous « next », puis `python scripts/release.py publish`.\n"
              "# kind : new | improved | fixed | action ; structure : asso | sci (absent : toutes) ;\n"
              "# text : pour l'utilisateur ; tech : précision pour CHANGELOG.md seulement.\n")
    return header + yaml.safe_dump({"next": data["next"], "versions": data["versions"]}, allow_unicode=True,
                                   sort_keys=False, width=110)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("check")
    sub.add_parser("build")
    pub = sub.add_parser("publish")
    pub.add_argument("--title")
    args = parser.parse_args(argv)
    try:
        if args.command == "check":
            errors = check()
            for e in errors:
                print(e, file=sys.stderr)
            return 1 if errors else 0
        if args.command == "build":
            print(f"Version {build()} : CHANGELOG.md, package.json et README régénérés.")
            return 0
        number = publish(args.title)
        print(f"Version {number} publiée dans data/changelog.yml ; fichiers régénérés. À lancer :\n"
              f"  git add data/changelog.yml CHANGELOG.md frontend/package.json frontend/package-lock.json README.md\n"
              f"  git commit -m \"Release {number}\"\n"
              f"  git tag v{number}\n"
              f"  git push && git push origin v{number}")
        return 0
    except ChangelogError as exc:
        print(exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
