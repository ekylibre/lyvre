"""Jeu d'évaluation de l'assistant (lot AG9b.d). HORS CI : appelle l'API Claude (coût réel).

    python scripts/run_assistant_evals.py --instance <slug> [--cases tests/assistant_evals/cases.yaml]
                                          [--only id1,id2] [--repeat 3] [--out rapport.json]

L'instance doit être une exploitation agricole d'essai (données fictives) avec l'intégration « Assistant Claude »
active. Affiche, par cas, la réussite des contrôles déterministes sur chaque exécution, puis le taux de réussite et
le coût estimé ; seuil de passage conseillé : 90 %.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--instance", required=True)
    parser.add_argument("--cases", default=str(ROOT / "tests" / "assistant_evals" / "cases.yaml"))
    parser.add_argument("--only", default="")
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    from app import create_app
    from app.models import Instance
    from app.services.agenda_summary import _select
    from app.services.assistant import evals, settings

    cases = yaml.safe_load(Path(args.cases).read_text(encoding="utf-8"))
    only = {c for c in args.only.split(",") if c}
    app = create_app()
    report = {"instance": args.instance, "runs": []}
    with app.app_context():
        instance = Instance.query.filter_by(slug=args.instance).first()
        if instance is None or instance.chart != "agri":
            print(f"Instance agricole « {args.instance} » introuvable.")
            return 2
        with app.test_request_context():
            _select(instance)
            if not settings.available():
                print("Intégration « Assistant Claude » indisponible sur cette instance.")
                return 2
            report["model"] = settings.model()
            passed = total = 0
            cost = 0.0
            for case in cases:
                if only and case["id"] not in only:
                    continue
                for attempt in range(args.repeat):
                    run = evals.run_case(case)
                    problems = evals.score(case, run)
                    total += 1
                    passed += not problems
                    cost += run.get("cost_usd") or 0
                    status = "OK " if not problems else "ÉCHEC"
                    print(f"{status} {case['id']} #{attempt + 1} ({run.get('cost_usd', 0):.4f} $)"
                          + ("" if not problems else " — " + " ; ".join(problems)))
                    report["runs"].append({"id": case["id"], "attempt": attempt + 1, "problems": problems, **run})
            rate = 100 * passed / total if total else 0
            print(f"\n{passed}/{total} exécutions réussies ({rate:.0f} %), coût estimé {cost:.4f} $ — modèle {report['model']}")
            report.update(passed=passed, total=total, rate=rate, cost_usd=round(cost, 4))
    if args.out:
        Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0 if total and rate >= 90 else 1


if __name__ == "__main__":
    raise SystemExit(main())
