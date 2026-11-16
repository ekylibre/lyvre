"""Lot CG4 : fiches de méthode (data/kb/fiches), validation et corpus de l'assistant
(claudedocs/design_fiabilisation_cegara.md § 7)."""
from app.services import kb

GOOD = {"id": "MA-99", "titre": "Essai", "referentiels": ["agri"], "articles": ["CGI art. 73"],
        "liens": ["https://bofip.impots.gouv.fr/x"], "statut": "publie", "verifie_le": "2026-11-07",
        "verifie_par": "test", "risque": "aucun", "parametres": ["ba.dep.cap_cents"],
        "body": "## Résumé\nPlafond [ba.dep.cap_cents].\n## Exemple\nx\n## Référence\nx\n## Dans le logiciel\nx"}


def test_delivered_fiches_are_valid(app):
    with app.app_context():
        assert kb.validate() == []
        ids = [f["id"] for f in kb.method_fiches("agri")]
        assert set(ids) == {f"MA-{n:02d}" for n in range(1, 11)} and ids == sorted(ids)


def test_validation_rejects_bad_fiches(app):
    with app.app_context():
        assert kb.validate([GOOD]) == []
        bad = {**GOOD, "liens": ["https://www.example.com"], "parametres": ["ba.nope_cents"], "titre": "",
               "body": GOOD["body"].replace("## Exemple", "## Exemples") + " Barème du CEGARA [ba.inconnu]."}
        problems = " | ".join(kb.validate([bad]))
        for needle in ("clé(s) manquante(s) titre", "source primaire", "paramètre daté inconnu ba.nope_cents",
                       "paramètre cité inconnu [ba.inconnu]", "« Exemple » absente", "guide de tiers"):
            assert needle in problems, needle
        long = {**GOOD, "body": GOOD["body"] + " mot" * 800}
        assert any("mots" in p for p in kb.validate([long]))
        assert any("non conforme" in p for p in kb.validate([{**GOOD, "id": "X-1"}]))


def test_corpus_includes_method_fiches(app):
    with app.app_context():
        from app.services.assistant import corpus
        corpus.text.cache_clear()
        text = corpus.text()
        assert "## Fiches de méthode" in text and "[MA-04] Déduction pour épargne de précaution" in text
        assert "publiée" in text and text == corpus.text()
        assert "CEGARA" not in text.split("## Fiches de méthode")[1]
