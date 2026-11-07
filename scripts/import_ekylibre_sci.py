"""Reprise de la SCI Chênes Verts depuis un export de tenant Ekylibre (voir
`claudedocs/design_import_ekylibre_sci.md`).

Analyse à blanc (rien n'est écrit) :
  .venv/bin/python scripts/import_ekylibre_sci.py ARCHIVE.zip --dry-run [--report rapport.md]

Import (base neuve, tout-ou-rien) :
  .venv/bin/python scripts/import_ekylibre_sci.py ARCHIVE.zip --meta-url sqlite:////chemin/meta.db \\
      [--slug sci-chenes-verts] [--label "SCI Chênes Verts"] [--replace] [--report rapport.md]

La base est construite dans `<dossier de la méta-base>/tenants/<slug>.db.part`, provisionnée comme
une instance neuve (plan SCI), remplie par les services de Lyvre, contrôlée (balance = Ekylibre,
corrections comprises), puis renommée et inscrite dans la méta-base ; en cas d'erreur, rien ne reste.
`--meta-url` est obligatoire pour l'import : jamais la méta-base par défaut sans le vouloir.
Aucun accès réseau, aucun identifiant Qonto.

Depuis le lot RE1 (claudedocs/design_restauration_ekylibre.md), ce script applique le profil
`sci-chenes-verts` du moteur commun (`_ekylibre_restore.py`) ; `restore_ekylibre.py` restaure les autres.
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
    parser.add_argument("source", help="archive .zip de l'export Ekylibre, ou dossier extrait")
    parser.add_argument("--start", default="2025-01-01", help="début de la reprise (AAAA-MM-JJ)")
    parser.add_argument("--until", default="2026-06-30", help="date limite incluse (AAAA-MM-JJ)")
    parser.add_argument("--dry-run", action="store_true", help="analyse à blanc : rapport seulement")
    parser.add_argument("--meta-url", help="méta-base visée (sqlite:////chemin/meta.db), obligatoire pour l'import")
    parser.add_argument("--slug", default="sci-chenes-verts")
    parser.add_argument("--label", default="SCI Chênes Verts")
    parser.add_argument("--copy-access-from", default="chenes-verts", help="instance dont les accès sont repris")
    parser.add_argument("--attachments-from", type=int, default=2026,
                        help="année à partir de laquelle les pièces des achats sont reprises (EK5)")
    parser.add_argument("--replace", action="store_true", help="recrée l'instance si elle existe (sauvegarde gardée)")
    parser.add_argument("--report", help="fichier du rapport Markdown")
    args = parser.parse_args(argv)
    start, until = date.fromisoformat(args.start), date.fromisoformat(args.until)

    def make_profile(_data):
        from app.services.ekylibre import profile
        return profile.sci(start, until, args.attachments_from, args.copy_access_from)

    if args.dry_run:
        text, code = restore.dry_run(args.source, make_profile)
    else:
        if not args.meta_url:
            parser.error("--meta-url est obligatoire pour l'import (ou --dry-run pour l'analyse à blanc).")
        text, code = restore.run_import(args.source, make_profile, args.meta_url, args.slug, args.label, args.replace)
    if args.report:
        Path(args.report).write_text(text, encoding="utf-8")
        print(f"Rapport : {args.report}")
    print(text.split("## Journaux")[0])
    return code


if __name__ == "__main__":
    sys.exit(main())
