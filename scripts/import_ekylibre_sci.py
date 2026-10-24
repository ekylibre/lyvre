"""Reprise de la SCI Chênes Verts depuis un export de tenant Ekylibre (voir
`claudedocs/design_import_ekylibre_sci.md`).

Usage :
  .venv/bin/python scripts/import_ekylibre_sci.py ARCHIVE.zip --dry-run [--until 2026-06-30] [--report rapport.md]

Lot K1 : analyse à blanc seulement (lecture, contrôles, correspondances, rapport) ; rien n'est écrit.
Aucun accès réseau, aucun identifiant Qonto.
"""
import argparse
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.ekylibre import checks, report  # noqa: E402
from app.services.ekylibre.data import EkyData  # noqa: E402
from app.services.ekylibre.mapping import Chart  # noqa: E402
from app.services.ekylibre.reader import open_source  # noqa: E402


def analyse(source_path, start: date, until: date):
    with open_source(source_path) as source:
        data = EkyData.load(source, start, until)
    results = checks.run(data)
    mapping = report.plan(data, Chart.from_file())
    return data, mapping, results


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("source", help="archive .zip de l'export Ekylibre, ou dossier extrait")
    parser.add_argument("--start", default="2025-01-01", help="début de la reprise (AAAA-MM-JJ)")
    parser.add_argument("--until", default="2026-06-30", help="date limite incluse (AAAA-MM-JJ)")
    parser.add_argument("--dry-run", action="store_true", help="analyse à blanc : rapport seulement")
    parser.add_argument("--report", help="fichier du rapport Markdown")
    args = parser.parse_args(argv)
    if not args.dry_run:
        parser.error("Lot K1 : seule l'analyse à blanc (--dry-run) est disponible.")
    data, mapping, results = analyse(args.source, date.fromisoformat(args.start), date.fromisoformat(args.until))
    text = report.render(data, mapping, results, str(args.source), dry_run=True)
    if args.report:
        Path(args.report).write_text(text, encoding="utf-8")
        print(f"Rapport : {args.report}")
    failed = [c for c in results if not c.ok]
    for check in results:
        print(f"{'OK ' if check.ok else 'KO '} {check.label}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
