"""Contenu public (site lyvre.org, lot L1) : sections générées du README, cohérence de data/features.yml,
liste noire des textes publiés."""
from datetime import date

import pytest

from app.version import STRUCTURES
from scripts import public_content as pc


def _features(**overrides):
    data = {"highlights": [{"emoji": "📒", "title": "Compta", "text": "Partie **double**."}],
            "audiences": [{"id": "asso", "emoji": "🌱", "title": "Une association", "points": ["Reçus `Cerfa`."]}],
            "overview": [],
            "domains": [{"id": "compta", "emoji": "📒", "title": "Comptabilité"}],
            "features": [{"id": "pd", "domain": "compta", "title": "Partie double", "text": "Au clavier."},
                         {"id": "x", "domain": "compta", "title": "Bientôt", "text": "Plus tard.", "status": "soon"}],
            "integrations": [{"name": "Qonto", "usage": "Banque", "structures": "toutes"}]}
    data.update(overrides)
    return data


VERSIONS = [{"version": "2026.11.2", "date": date(2026, 11, 3), "title": "Deux", "entries": [
    {"kind": "fixed", "text": "Correction mineure."},
    {"kind": "new", "structure": "agri", "text": "Banque › Soldes — colonne ajoutée. Détail en plus.", "tech": "SECRET_TECH"},
    {"kind": "action", "text": "Relancer la synchronisation."}]},
    {"version": "2026.11.1", "date": date(2026, 11, 1), "title": "Un", "entries": [{"kind": "fixed", "text": "Rien."}]}]


def test_repository_features_are_valid():
    from app.version import load
    published = {str(v["version"]) for v in load()["versions"]}
    assert pc.validate_features(pc.load_features(), published) == []


def test_render_replaces_only_tagged_sections():
    text = "Intro écrite à la main.\n<!-- features -->\nancien\n<!-- /features -->\nFin.\n<!-- news --><!-- /news -->"
    out = pc.render_readme(text, _features(), VERSIONS, STRUCTURES)
    assert out.startswith("Intro écrite à la main.\n") and out.rstrip().endswith("<!-- /news -->")
    assert "ancien" not in out
    assert "- **Partie double** : Au clavier." in out and "- **Bientôt** *(à venir)* : Plus tard." in out
    assert pc.render_readme(out, _features(), VERSIONS, STRUCTURES) == out  # stable


def test_news_keeps_actions_and_new_entries_without_tech():
    news = pc.news_section(VERSIONS, STRUCTURES)
    assert "**2026.11.2 — Deux** (03/11/2026)" in news
    assert "⚠️ Relancer la synchronisation." in news
    assert "[Exploitations agricoles] Banque › Soldes — colonne ajoutée." in news
    assert "Correction mineure" not in news  # une correction s'efface devant les nouveautés de la version
    assert "Rien." in news  # version sans nouveauté : ses corrections
    assert "SECRET_TECH" not in news and "Détail en plus" not in news


def test_inline_markdown_in_html_cells():
    assert "Partie <b>double</b>." in pc.highlights_section(_features())
    assert "Reçus <code>Cerfa</code>." in pc.audiences_section(_features())


@pytest.mark.parametrize("change, message", [
    ({"features": [{"id": "a", "domain": "inconnu", "title": "T", "text": "x"}]}, "domaine inconnu"),
    ({"features": [{"id": "a", "domain": "compta", "title": "T", "text": "x", "since": "2030.01.1"}]}, "non publiée"),
    ({"features": [{"id": "a", "domain": "compta", "title": "T", "text": "x", "structures": ["coop"]}]}, "structures parmi"),
    ({"features": [{"id": "a", "domain": "compta", "title": "T", "text": "x", "capture": "absente.png"}]}, "absente de doc/images"),
    ({"features": [{"id": "a", "domain": "compta", "title": "T", "text": "x"},
                   {"id": "a", "domain": "compta", "title": "T", "text": "y"}]}, "en double"),
])
def test_feature_errors(change, message):
    errors = "\n".join(pc.validate_features(_features(**change), {"2026.11.1"}))
    assert message in errors


def test_denylist_matches_normalized_word_sequences(tmp_path):
    hashes = {pc.fingerprint("SCI des Écureuils")}
    assert pc.denied("Reprise de la sci   des ecureuils en 2025", hashes)
    assert not pc.denied("Une SCI et des écureuils", hashes)
    assert not pc.denied("Écureuils", hashes)
    texts = pc.public_texts(_features(highlights=[{"title": "SCI des écureuils", "text": "", "emoji": ""}]), VERSIONS)
    assert pc.denylist_errors(texts, hashes) == ["features.yml › highlights : contient un terme de la liste noire (texte public)."]


def test_denylist_reads_fingerprints_and_local_terms(tmp_path):
    published = tmp_path / "deny.sha256"
    published.write_text(f"# commentaire\n{pc.fingerprint('Alpha')}\n")
    local = tmp_path / "local"
    local.write_text("Bravo Charlie\n")
    hashes = pc.denylist(published, local)
    assert pc.denied("alpha", hashes) and pc.denied("BRAVO, charlie !", hashes)
    assert pc.denylist(tmp_path / "absent", tmp_path / "absent") == set()


def test_check_fails_on_a_denied_published_text(monkeypatch):
    import scripts.release as release
    from app.version import load
    data = load()
    first = data["versions"][0]["entries"][0]["text"]
    monkeypatch.setattr(pc, "denylist", lambda *a, **k: {pc.fingerprint(" ".join(pc.normalize(first)[:2]))})
    assert any("liste noire" in e for e in release.public_errors(data))
