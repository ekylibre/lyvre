"""Choix du plan comptable par seed_accounts.py (lancé sans argument au démarrage Docker)."""
import pytest

from seed_accounts import CHARTS, detect_chart, load_chart, resolve_chart

ASSO = [a["code"] for a in load_chart("asso")]
SCI = [a["code"] for a in load_chart("sci")]
COMMON = sorted(set(ASSO) & set(SCI))


@pytest.mark.parametrize("chart", list(CHARTS))
def test_detect_loaded_chart(chart):
    assert detect_chart([a["code"] for a in load_chart(chart)]) == chart


def test_detect_nothing_on_empty_or_shared_codes():
    assert detect_chart([]) is None
    assert detect_chart(COMMON) is None


def test_no_argument_completes_the_chart_already_loaded():
    assert resolve_chart(None, SCI) == "sci"
    assert resolve_chart(None, ASSO, default="sci") == "asso"  # la base prime


def test_no_argument_on_empty_database_uses_default():
    assert resolve_chart(None, []) == "asso"
    assert resolve_chart(None, [], default="SCI") == "sci"


def test_explicit_chart_conflicting_with_database_is_refused():
    with pytest.raises(SystemExit, match="déjà le plan « sci »"):
        resolve_chart("asso", SCI)
    assert resolve_chart("sci", SCI) == "sci"
    assert resolve_chart("sci", []) == "sci"


def test_unknown_chart_is_refused():
    with pytest.raises(SystemExit, match="inconnu"):
        resolve_chart("pcg", [])
    with pytest.raises(SystemExit, match="inconnu"):
        resolve_chart(None, [], default="pcg")
