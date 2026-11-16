"""Restauration d'une sauvegarde Ekylibre dans une nouvelle instance Lyvre (claudedocs/design_restauration_ekylibre.md).

Profil `standard`, réglé d'après la sauvegarde (§ 2) :
- référentiel détecté (plan agricole si Ekylibre suit le PCGA ou le régime BA) ;
- TVA conservée si la structure est assujettie ;
- départ au premier exercice ouvert dans Ekylibre ;
- noms de tiers rendus uniques ;
- écritures validées si leur exercice est verrouillé dans Ekylibre.

Analyse à blanc (rien n'est écrit) :
  .venv/bin/python scripts/restore_ekylibre.py ARCHIVE.zip --dry-run [--report rapport.md]

Import (base neuve, tout-ou-rien, méta-base explicite) :
  .venv/bin/python scripts/restore_ekylibre.py ARCHIVE.zip --meta-url sqlite:////chemin/meta.db \\
      --slug SLUG --label "Nom" [--chart agri] [--from-year 2024 | --all-history] [--until AAAA-MM-JJ] \\
      [--replace] [--report rapport.md]

Aucun accès réseau ; les jetons bancaires d'Ekylibre (Nordigen) ne sont pas repris. Seuls les administrateurs
voient l'instance créée.
"""
import argparse
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import _ekylibre_restore as restore  # noqa: E402


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("source", help="archive .zip de la sauvegarde Ekylibre, ou dossier extrait")
    parser.add_argument("--chart", choices=("agri", "sci", "societe", "asso"), help="référentiel (sinon détecté)")
    period = parser.add_mutually_exclusive_group()
    period.add_argument("--from-year", type=int, help="premier exercice repris (année de début)")
    period.add_argument("--all-history", action="store_true", help="tous les exercices d'Ekylibre")
    parser.add_argument("--until", help="date limite incluse (AAAA-MM-JJ) ; défaut : fin du dernier exercice")
    parser.add_argument("--dry-run", action="store_true", help="analyse à blanc : rapport seulement")
    parser.add_argument("--meta-url", help="méta-base visée (sqlite:////chemin/meta.db), obligatoire pour l'import")
    parser.add_argument("--slug", help="identifiant de l'instance créée (obligatoire pour l'import)")
    parser.add_argument("--label", help="nom de l'instance (défaut : nom de la structure dans Ekylibre)")
    parser.add_argument("--replace", action="store_true", help="recrée l'instance si elle existe (sauvegarde gardée)")
    parser.add_argument("--report", help="fichier du rapport Markdown")
    args = parser.parse_args(argv)
    until = date.fromisoformat(args.until) if args.until else None

    def make_profile(data):
        from app.services.ekylibre import profile
        from app.services.ekylibre.data import day
        start = None
        if args.from_year:
            year = next((fy for fy in data.rows["financial_years"] if day(fy["started_on"]).year == args.from_year), None)
            if year is None:
                raise SystemExit(f"--from-year {args.from_year} : aucun exercice d'Ekylibre ne commence cette année-là.")
            start = day(year["started_on"])
        return profile.standard(data, chart=args.chart, start=start, until=until, all_history=args.all_history)

    if args.dry_run:
        text, code = restore.dry_run(args.source, make_profile)
    else:
        if not args.meta_url or not args.slug:
            parser.error("--meta-url et --slug sont obligatoires pour l'import (ou --dry-run pour l'analyse à blanc).")
        text, code = restore.run_import(args.source, make_profile, args.meta_url, args.slug, args.label or args.slug,
                                        args.replace)
    if args.report:
        Path(args.report).write_text(text, encoding="utf-8")
        print(f"Rapport : {args.report}")
    print(text.split("## Journaux")[0])
    return code


if __name__ == "__main__":
    sys.exit(main())
