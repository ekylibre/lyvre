"""Restauration d'une sauvegarde Ekylibre depuis l'interface (Imports › Sauvegarde Ekylibre, lot RE6).

Même moteur que le script `scripts/restore_ekylibre.py` (profil `standard`, référentiel de l'instance), mais dans
l'instance courante plutôt que dans une nouvelle :
- l'archive (jusqu'à plusieurs Go, pièces comprises) est **déposée sur disque**, dans le dossier de l'instance
  (`.reprise-ekylibre/`), jamais chargée en mémoire ;
- l'**analyse à blanc** et l'**import** tournent en tâche de fond (`SyncJob`), suivis à l'écran ;
- l'import exige une instance **vide** (ni écriture, ni achat, ni vente, ni transaction bancaire) et des contrôles
  bloquants passés ; il est **tout-ou-rien** : en cas d'échec, la base est annulée et les fichiers écrits retirés ;
- le rapport Markdown (le même que celui du script) est conservé à côté de l'archive ; l'archive est retirée après
  un import réussi.
"""
from __future__ import annotations

import dataclasses
import json
import shutil
from datetime import datetime
from pathlib import Path

from app.extensions import db

STAGING = ".reprise-ekylibre"
ARCHIVE = "archive.zip"
REPORT = "rapport.md"
STATE = "etat.json"
MAX_UPLOAD = 4 * 1024 ** 3          # 4 Go : sauvegardes avec pièces jointes
from app.models.sync_job import SYNC_KIND_EKYLIBRE_ANALYSIS as KIND_ANALYSE  # noqa: E402
from app.models.sync_job import SYNC_KIND_EKYLIBRE_RESTORE as KIND_IMPORT  # noqa: E402
CHUNK = 1024 * 1024


class RestoreError(ValueError):
    def __init__(self, message, field=None, status=422):
        super().__init__(message)
        self.message, self.field, self.status = message, field, status


def staging_dir() -> Path:
    from app.services import attachments
    return attachments.instance_dir() / STAGING


def _state() -> dict:
    path = staging_dir() / STATE
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except ValueError:
        return {}


def _save_state(**values) -> dict:
    state = {**_state(), **values}
    folder = staging_dir()
    folder.mkdir(parents=True, exist_ok=True)
    (folder / STATE).write_text(json.dumps(state, ensure_ascii=False, default=str), encoding="utf-8")
    return state


def archive_path() -> Path | None:
    path = staging_dir() / ARCHIVE
    return path if path.exists() else None


def report_path() -> Path | None:
    path = staging_dir() / REPORT
    return path if path.exists() else None


def store_upload(file_storage) -> dict:
    """Archive déposée : écrite par morceaux, vérifiée (zip contenant un fichier .sql), remplace la précédente."""
    import zipfile
    name = Path(file_storage.filename or "").name
    if not name.lower().endswith(".zip"):
        raise RestoreError("Sauvegarde Ekylibre attendue (fichier .zip).", "file")
    folder = staging_dir()
    folder.mkdir(parents=True, exist_ok=True)
    partial = folder / (ARCHIVE + ".part")
    size = 0
    with partial.open("wb") as out:
        while True:
            chunk = file_storage.stream.read(CHUNK)
            if not chunk:
                break
            size += len(chunk)
            if size > MAX_UPLOAD:
                out.close()
                partial.unlink(missing_ok=True)
                raise RestoreError("Archive trop volumineuse (4 Go au plus).", "file", 413)
            out.write(chunk)
    try:
        with zipfile.ZipFile(partial) as zf:
            if not any(n.endswith(".sql") for n in zf.namelist()):
                raise RestoreError("Archive sans base Ekylibre (aucun fichier .sql) : choisissez une sauvegarde "
                                   "téléchargée depuis Ekylibre.", "file")
    except zipfile.BadZipFile:
        partial.unlink(missing_ok=True)
        raise RestoreError("Fichier zip illisible.", "file") from None
    except RestoreError:
        partial.unlink(missing_ok=True)
        raise
    partial.replace(folder / ARCHIVE)
    (folder / REPORT).unlink(missing_ok=True)
    (folder / STATE).unlink(missing_ok=True)
    return _save_state(name=name, size=size, uploaded_at=datetime.utcnow().isoformat(timespec="seconds"))


def discard() -> None:
    shutil.rmtree(staging_dir(), ignore_errors=True)


def blockers() -> list[str]:
    """Raisons d'un refus d'import tenant à l'instance (vide, partie double)."""
    from app.models import BankTransaction, JournalEntry, Purchase, Sale
    from app.services.rule_entries import simple_mode
    out = []
    if simple_mode():
        out.append("Instance en comptabilité simplifiée : la restauration demande la partie double.")
    for model, label in ((JournalEntry, "écriture(s)"), (Purchase, "facture(s) d'achat"), (Sale, "pièce(s) de vente"),
                         (BankTransaction, "transaction(s) bancaire(s)")):
        count = db.session.query(model).count()
        if count:
            out.append(f"L'instance contient déjà {count} {label} : restaurez dans une instance vide.")
    return out


def overview() -> dict:
    state = _state()
    archive = archive_path()
    return {"archive": {"name": state.get("name"), "size": state.get("size"), "uploaded_at": state.get("uploaded_at")}
            if archive else None,
            "analysis": state.get("analysis") if archive else None,
            "imported": state.get("imported"),
            "report": report_path() is not None,
            "blockers": blockers(), "max_upload": MAX_UPLOAD}


def _options(raw: dict) -> dict:
    from_year = raw.get("from_year")
    if from_year not in (None, ""):
        try:
            from_year = int(from_year)
        except (TypeError, ValueError):
            raise RestoreError("Année de début invalide.", "from_year") from None
    else:
        from_year = None
    return {"from_year": from_year, "all_history": bool(raw.get("all_history")),
            "attachments": raw.get("attachments", True) is not False}


def _profile_factory(options: dict, chart: str):
    from app.services.ekylibre import profile as profiles

    def make(data):
        start = None
        if options["from_year"]:
            years = sorted(data.rows["financial_years"], key=lambda fy: fy["started_on"])
            first = next((fy for fy in years if fy["started_on"][:4] >= str(options["from_year"])), None)
            if first is None:
                raise RestoreError(f"Aucun exercice à partir de {options['from_year']} dans la sauvegarde.", "from_year")
            from app.services.ekylibre.data import day
            start = day(first["started_on"])
        made = profiles.standard(data, chart=chart, start=start, all_history=options["all_history"] and start is None)
        return made if options["attachments"] else dataclasses.replace(made, attachments_from=None)
    return make


def analyse(source_path: Path, make_profile, chart_obj=None):
    """Lecture complète, profil, période, correspondances et contrôles (partagé avec le script)."""
    from app.services.ekylibre import checks, report
    from app.services.ekylibre.data import WIDE_START, WIDE_UNTIL, EkyData
    from app.services.ekylibre.mapping import Chart, chart_file
    from app.services.ekylibre.reader import open_source
    with open_source(source_path) as source:
        data = EkyData.load(source, WIDE_START, WIDE_UNTIL)
    profile = make_profile(data)
    data.set_period(profile.start, profile.until)
    chart = chart_obj or Chart.from_file(chart_file(profile.chart))
    mapping = report.plan(data, chart, profile)
    results = checks.run(data, profile, mapping["entities"])
    return data, mapping, results, profile


def _summary(data, mapping, results, profile) -> dict:
    from app.services.ekylibre.profile import detect_chart
    detected, _why = detect_chart(data)
    years = sorted({fy["started_on"][:4] for fy in data.rows["financial_years"]})
    return {
        "profile": profile.describe(), "chart": profile.chart, "detected_chart": detected,
        "period": {"start": data.start.isoformat(), "until": data.until.isoformat()},
        "years": [int(y) for y in years],
        "volumes": {"entries": len(data.entries()), "purchases": len(data.purchases()), "sales": len(data.sales()),
                    "statement_items": len(data.statement_items()), "fixed_assets": len(data.rows["fixed_assets"]),
                    "entities": len(mapping["entities"]), "accounts": len(mapping["accounts"]),
                    "activities": len(data.rows["activities"])},
        "checks": [{"label": c.label, "ok": c.ok, "blocking": c.blocking, "details": c.details[:12],
                    "more": max(len(c.details) - 12, 0)} for c in results],
        "blocking": sum(1 for c in results if not c.ok and c.blocking),
        "warnings": sum(1 for c in results if not c.ok and not c.blocking),
    }


def _instance_chart() -> str:
    from app.tenant import current_instance
    return getattr(current_instance(), "chart", None) or "agri"


def _work_analyse(options: dict, chart: str):
    def work(job_id):
        from app.services.ekylibre import report
        from app.services.ekylibre.mapping import Chart
        archive = archive_path()
        if archive is None:
            raise RuntimeError("Aucune sauvegarde déposée.")
        data, mapping, results, profile = analyse(archive, _profile_factory(options, chart), Chart.from_database())
        text = report.render(data, mapping, results, _state().get("name") or ARCHIVE, dry_run=True, profile=profile)
        (staging_dir() / REPORT).write_text(text, encoding="utf-8")
        summary = {**_summary(data, mapping, results, profile), "options": options}
        _save_state(analysis=summary)
        return {"blocking": summary["blocking"], "warnings": summary["warnings"], "entries": summary["volumes"]["entries"]}
    return work


def _files(root: Path) -> set[Path]:
    return {p for p in root.rglob("*") if p.is_file() and STAGING not in p.parts} if root.exists() else set()


def _work_import(options: dict, chart: str, user_id: int | None):
    def work(job_id):
        from app.services import attachments
        from app.services.ekylibre import importer, report
        from app.services.ekylibre.mapping import Chart
        from app.services.ekylibre.reader import open_source
        from app.tenant import current_instance
        archive = archive_path()
        if archive is None:
            raise RuntimeError("Aucune sauvegarde déposée.")
        problems = blockers()
        if problems:
            raise RuntimeError(" ".join(problems))
        root = attachments.instance_dir()
        before = _files(root)
        try:
            chart_obj = Chart.from_database()
            data, mapping, results, profile = analyse(archive, _profile_factory(options, chart), chart_obj)
            failed = [c.label for c in results if not c.ok and c.blocking]
            if failed:
                raise RuntimeError("Contrôles bloquants en échec : " + " ; ".join(failed[:5]))
            with open_source(archive) as source:
                ctx = importer.run(data, mapping["accounts"], mapping["entities"], chart_obj, source=source,
                                   attachments_from=profile.attachments_from, profile=profile)
            inst = current_instance()
            if inst is not None and ctx.stats.get("associates") and not inst.has_associates:
                inst.has_associates = True
            db.session.commit()
        except BaseException:
            db.session.rollback()
            for path in _files(root) - before:
                path.unlink(missing_ok=True)
            raise
        name = _state().get("name") or ARCHIVE
        text = report.render(data, mapping, results, name, dry_run=False, imported=ctx, profile=profile)
        folder = staging_dir()
        (folder / REPORT).write_text(text, encoding="utf-8")
        (folder / ARCHIVE).unlink(missing_ok=True)
        stats = {k: int(v) for k, v in ctx.stats.items()}
        _save_state(analysis=None, imported={"name": name, "at": datetime.utcnow().isoformat(timespec="seconds"),
                                             "period": {"start": data.start.isoformat(), "until": data.until.isoformat()},
                                             "stats": stats, "notes": len(ctx.notes)})
        return {**stats, "notes": len(ctx.notes)}
    return work


def start_analysis(app, raw: dict):
    from app.services import sync_jobs
    if archive_path() is None:
        raise RestoreError("Déposez d'abord une sauvegarde Ekylibre.", "file", 409)
    if sync_jobs.running_job(KIND_IMPORT) or sync_jobs.running_job(KIND_ANALYSE):
        raise RestoreError("Une analyse ou un import est déjà en cours.", status=409)
    options = _options(raw)
    return sync_jobs.start(app, KIND_ANALYSE, _work_analyse(options, _instance_chart()),
                           message="Lecture de la sauvegarde…")


def start_import(app, raw: dict, user_id: int | None = None):
    from app.services import sync_jobs
    if archive_path() is None:
        raise RestoreError("Déposez d'abord une sauvegarde Ekylibre.", "file", 409)
    problems = blockers()
    if problems:
        raise RestoreError(" ".join(problems), status=409)
    analysis = _state().get("analysis")
    if not analysis:
        raise RestoreError("Analysez d'abord la sauvegarde.", status=409)
    if analysis.get("blocking"):
        raise RestoreError("Des contrôles bloquants sont en échec : voir l'analyse.", status=409)
    if sync_jobs.running_job(KIND_IMPORT) or sync_jobs.running_job(KIND_ANALYSE):
        raise RestoreError("Une analyse ou un import est déjà en cours.", status=409)
    options = _options({**analysis.get("options", {}), **raw})
    return sync_jobs.start(app, KIND_IMPORT, _work_import(options, _instance_chart(), user_id),
                           message="Restauration en cours…")

