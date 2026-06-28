"""Tests du rendu SVG des graphes (PDF serveur)."""
from app.services.chart_svg import option_to_svg


def _bar_option():
    return {
        "xAxis": {"type": "category", "data": ["Boutique", "Vinted", "Dons"]},
        "yAxis": {"type": "value"},
        "series": [{"type": "bar", "data": [120.0, 0, 35.5], "itemStyle": {"color": "#1c7a33"}}],
    }


def test_bar_chart_svg():
    svg = option_to_svg(_bar_option())
    assert svg.startswith("<svg") and svg.endswith("</svg>")
    assert "<rect" in svg                      # barres dessinées
    assert "Boutique" in svg and "Vinted" in svg
    # Valeur nulle : pas de barre ratée mais pas de crash.
    assert svg.count("<rect") == 2             # 120 et 35.5 (0 ignoré)


def test_line_area_chart_svg():
    option = {
        "xAxis": {"type": "category", "data": ["01/2025", "02/2025", "03/2025"]},
        "yAxis": {"type": "value"},
        "series": [{"type": "line", "data": [10, 40, 22], "areaStyle": {},
                    "lineStyle": {"color": "#1c7a33"}}],
    }
    svg = option_to_svg(option)
    assert "<polyline" in svg and "<polygon" in svg     # courbe + zone
    assert svg.count("<circle") == 3                    # un point par mois


def test_multi_series_bar_has_legend():
    option = {
        "xAxis": {"type": "category", "data": ["Meubles", "D3E"]},
        "yAxis": {"type": "value"},
        "series": [
            {"name": "Collecté", "type": "bar", "data": [10, 2], "itemStyle": {"color": "#5b5446"}},
            {"name": "Réemployé", "type": "bar", "data": [4, 1], "itemStyle": {"color": "#1c7a33"}},
        ],
    }
    svg = option_to_svg(option)
    assert "Collecté" in svg and "Réemployé" in svg     # légende
    assert svg.count("<rect") >= 4                       # 2 catégories × 2 séries


def test_empty_option_returns_blank():
    assert option_to_svg({}) == ""
    assert option_to_svg({"xAxis": {"data": []}, "series": []}) == ""


def test_handles_none_values_without_crash():
    option = {
        "xAxis": {"type": "category", "data": ["a", "b", "c"]},
        "series": [{"type": "line", "data": [None, 5, None]}],
    }
    svg = option_to_svg(option)
    assert "<svg" in svg and svg.count("<circle") == 1
