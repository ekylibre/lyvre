"""Score de la lecture des factures (app/services/invoice_reader.py) sur un corpus.

    python scripts/invoice_corpus.py DOSSIER [--scan] [-v]

DOSSIER contient les factures et `expected.json` (valeurs attendues, voir le
`_doc` du fichier). Par champ : juste, faux, absent ; un faux non signalé « à
vérifier » est une erreur silencieuse, la pire (rien n'alerte la saisie).
`--scan` relit chaque PDF converti en image (150 dpi, niveaux de gris, léger
pivotement) : simule un scan pour éprouver l'OCR. `--memory` simule la mémoire du
fournisseur (une facture précédente aux mêmes taux et à la même forme de numéro).
"""
from __future__ import annotations

import argparse
import io
import json
import sys
import tempfile
import time
import unicodedata
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pymupdf  # noqa: E402
from PIL import Image  # noqa: E402

from app.services import invoice_reader  # noqa: E402

FIELDS = ("supplier_name", "vat_number", "siret", "iban", "invoice_number", "issue_date",
          "due_date", "total", "untaxed", "tax", "taxes")


def _plain(text: str) -> str:
    text = unicodedata.normalize("NFKD", str(text)).encode("ascii", "ignore").decode()
    return "".join(c for c in text.lower() if c.isalnum())


def _same(name: str, expected, found) -> bool:
    if name == "supplier_name":
        got = _plain(found)
        return bool(got) and any(_plain(e) in got or got in _plain(e) for e in expected)
    if name == "invoice_number":
        return _plain(found) == _plain(expected)
    if name == "taxes":
        return sorted(map(tuple, expected)) == sorted(map(tuple, found))
    if isinstance(found, date):
        found = found.isoformat()
    return found == expected


def _as_scan(path: Path, workdir: Path) -> tuple[Path, str]:
    """Pages du PDF → une image PNG par page, réunies dans un PDF d'images (sans texte)."""
    out = pymupdf.open()
    with pymupdf.open(path) as doc:
        for page in list(doc)[:3]:
            pix = page.get_pixmap(dpi=150, colorspace=pymupdf.csGRAY)
            image = Image.frombytes("L", (pix.width, pix.height), pix.samples)
            image = image.rotate(0.7, resample=Image.BICUBIC, fillcolor=255)
            buffer = io.BytesIO()
            image.save(buffer, "PNG")
            img = out.new_page(width=page.rect.width, height=page.rect.height)
            img.insert_image(img.rect, stream=buffer.getvalue())
    target = workdir / (path.stem + ".scan.pdf")
    out.save(target)
    return target, invoice_reader.PDF_MIME


def _hints(expected) -> invoice_reader.SupplierHints:
    return invoice_reader.SupplierHints(
        rates=frozenset(rate for rate, _, tax in expected.get("taxes", ()) if rate),
        tax_free=expected.get("tax") == 0,
        number_shapes=frozenset({invoice_reader.number_shape(expected["invoice_number"])}
                                if expected.get("invoice_number") else ()),
    )


def score(folder: Path, scan: bool = False, verbose: bool = False, memory: bool = False) -> dict:
    spec = json.loads((folder / "expected.json").read_text())
    org = spec.get("organization", {})
    totals = {"ok": 0, "wrong": 0, "silent": 0, "missing": 0}
    per_field = {name: {"ok": 0, "wrong": 0, "missing": 0} for name in FIELDS}
    # Noms de fichiers comparés en NFC (les accents sont parfois décomposés sur le disque).
    files = {unicodedata.normalize("NFC", p.name): p for p in folder.iterdir()}
    with tempfile.TemporaryDirectory() as tmp:
        for filename, expected in spec["invoices"].items():
            path = files[unicodedata.normalize("NFC", filename)]
            mime = invoice_reader.PDF_MIME
            if scan:
                path, mime = _as_scan(path, Path(tmp))
            started = time.monotonic()
            ext = invoice_reader.read(path, mime, ignore_ibans=org.get("ibans", ()),
                                      ignore_sirens=[org["siren"]] if org.get("siren") else (),
                                      ignore_names=[org["name"]] if org.get("name") else (),
                                      hints_for=(lambda _, e=expected: _hints(e)) if memory else None)
            elapsed = time.monotonic() - started
            lines = []
            for name in FIELDS:
                if name not in expected:
                    continue
                want = expected[name]
                if name == "taxes":
                    found, check = ext.taxes, any(ext.fields[a].check for a in ("total", "tax")
                                                  if a in ext.fields)
                    found = found or None
                else:
                    f = ext.fields.get(name)
                    found, check = (f.value, f.check) if f else (None, False)
                if want is None:
                    status = "ok" if found is None else "wrong"
                elif found is None:
                    status = "missing"
                else:
                    status = "ok" if _same(name, want, found) else "wrong"
                per_field[name][status] += 1
                totals[status] += 1
                if status == "wrong" and not check:
                    totals["silent"] += 1
                if status != "ok":
                    flag = " (à vérifier)" if check else (" SILENCIEUX" if status == "wrong" else "")
                    lines.append(f"    {name:15} attendu {want!r:32} lu {found!r}{flag}")
            ok = sum(1 for name in FIELDS if name in expected) - len(lines)
            print(f"{filename[:60]:60} {ok:2}/{ok + len(lines):<2} {ext.source:8} {elapsed:4.1f}s")
            if verbose:
                print("\n".join(lines))
                for warning in ext.warnings:
                    print(f"    ! {warning}")
    graded = totals["ok"] + totals["wrong"] + totals["missing"]
    print(f"\nJustes {totals['ok']}/{graded} ({100 * totals['ok'] / graded:.0f} %) — faux {totals['wrong']}"
          f" dont silencieux {totals['silent']} — absents {totals['missing']}")
    print("Par champ : " + ", ".join(f"{n} {c['ok']}/{sum(c.values())}" for n, c in per_field.items()
                                     if sum(c.values())))
    return totals


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("folder", type=Path)
    parser.add_argument("--scan", action="store_true", help="relire chaque PDF converti en image")
    parser.add_argument("--memory", action="store_true", help="simuler la mémoire du fournisseur")
    parser.add_argument("-v", "--verbose", action="store_true", help="détail des écarts")
    args = parser.parse_args()
    score(args.folder, args.scan, args.verbose, args.memory)


if __name__ == "__main__":
    main()
