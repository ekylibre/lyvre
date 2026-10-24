"""Lecture d'un export de tenant Ekylibre sans PostgreSQL : blocs `COPY … FROM stdin;` du dump SQL,
lus en flux depuis l'archive `.zip` (ou un dossier extrait), et pièces `files/…`."""
import io
import re
import zipfile
from contextlib import contextmanager
from pathlib import Path

COPY = re.compile(r'^COPY (?:"?[^"\s.]+"?\.)?"?(\w+)"? \((.*)\) FROM stdin;$')
_ESCAPES = {"t": "\t", "n": "\n", "r": "\r", "b": "\b", "f": "\f", "v": "\v", "\\": "\\"}


class ReaderError(Exception):
    pass


def unescape(value: str):
    """Valeur d'une colonne au format texte de COPY (`\\N` : NULL)."""
    if value == r"\N":
        return None
    if "\\" not in value:
        return value
    return re.sub(r"\\(.)", lambda m: _ESCAPES.get(m.group(1), m.group(1)), value)


def iter_copy(lines, tables=None):
    """`(table, ligne)` de chaque bloc COPY ; `tables` : tables à lire (les autres sont sautées)."""
    current, columns = None, None
    for raw in lines:
        line = raw.rstrip("\n")
        if current is None:
            match = COPY.match(line)
            if match:
                current = match.group(1)
                columns = [c.strip().strip('"') for c in match.group(2).split(",")]
            continue
        if line == "\\.":
            current = None
            continue
        if tables is not None and current not in tables:
            continue
        yield current, dict(zip(columns, (unescape(v) for v in line.split("\t"))))


class Source:
    """Archive `.zip` ou dossier de l'export : dump SQL et pièces."""

    def __init__(self, path):
        self.path = Path(path)
        if not self.path.exists():
            raise ReaderError(f"Introuvable : {self.path}")
        self._zip = zipfile.ZipFile(self.path) if self.path.is_file() else None

    def close(self):
        if self._zip is not None:
            self._zip.close()

    def _sql_name(self) -> str:
        names = self._zip.namelist() if self._zip else [p.name for p in self.path.glob("*.sql")]
        sql = [n for n in names if n.endswith(".sql") and "/" not in n]
        if len(sql) != 1:
            raise ReaderError("Dump SQL introuvable à la racine de l'export.")
        return sql[0]

    @contextmanager
    def sql_lines(self):
        name = self._sql_name()
        if self._zip is not None:
            with self._zip.open(name) as raw:
                yield io.TextIOWrapper(raw, encoding="utf-8")
        else:
            with open(self.path / name, encoding="utf-8") as fh:
                yield fh

    def read_file(self, relative: str) -> bytes | None:
        """Contenu d'un fichier de `files/` (chemin relatif à la racine de l'export), ou None."""
        if self._zip is not None:
            try:
                return self._zip.read(relative)
            except KeyError:
                return None
        path = self.path / relative
        return path.read_bytes() if path.is_file() else None

    def document_file(self, document_id, extension: str | None = None) -> tuple[str, bytes] | None:
        """Fichier d'origine d'un document (`files/attachments/documents/000/000/<id>/original.<ext>`)."""
        padded = f"{int(document_id):09d}"
        folder = f"files/attachments/documents/{padded[0:3]}/{padded[3:6]}/{padded[6:9]}/"
        candidates = [f"{folder}original.{extension}"] if extension else []
        if self._zip is not None:
            candidates += [n for n in self._zip.namelist() if n.startswith(folder + "original.")]
        else:
            candidates += [str(p.relative_to(self.path)) for p in (self.path / folder).glob("original.*")]
        for name in candidates:
            content = self.read_file(name)
            if content is not None:
                return name.rsplit("/", 1)[-1], content
        return None


@contextmanager
def open_source(path):
    source = Source(path)
    try:
        yield source
    finally:
        source.close()
