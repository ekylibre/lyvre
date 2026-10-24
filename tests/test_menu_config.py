"""Tests du builder de navigation piloté par le plan comptable."""

from app.menu_config import MENUS, build_nav


def _labels(nav):
    return [m["label"] for m in nav]


def test_common_menus_shared_by_both_charts():
    asso = _labels(build_nav("asso", is_admin=True))
    sci = _labels(build_nav("sci", is_admin=True))
    for label in ("Tableau de bord", "Compta", "Banque", "Tiers", "Imports/Exports", "Configuration"):
        assert label in asso
        assert label in sci


def test_asso_only_menus_hidden_for_sci():
    sci = {m["key"]: m for m in build_nav("sci", is_admin=True)}
    assert "odoo" not in sci
    assert "indicateurs" not in sci
    tiers_items = [i.get("key") for i in sci["tiers"]["items"]]
    assert "members" not in tiers_items
    assert "work_times" not in tiers_items
    banque_items = [i.get("key") for i in sci["banque"]["items"]]
    assert "payouts" not in banque_items
    assert not sci["banque"]["items"][-1].get("divider")
    imports_items = [i.get("key") for i in sci["imports"]["items"]]
    assert imports_items == ["ofx", "reprise"]  # import de tonnages (associations) masqué


def test_asso_keeps_all_menus():
    asso = {m["key"]: m for m in build_nav("asso", is_admin=True, features={"odoo", "stancer"})}
    assert {"odoo", "indicateurs"} <= asso.keys()
    assert "payouts" in [i.get("key") for i in asso["banque"]["items"]]
    assert "members" in [i.get("key") for i in asso["tiers"]["items"]]


def test_integration_menus_follow_the_switch_not_the_structure():
    """Odoo et Versements Stancer : affichés si l'intégration est activée, quelle que soit la structure."""
    for chart in ("asso", "sci"):
        off = {m["key"]: m for m in build_nav(chart, is_admin=True)}
        assert "odoo" not in off and "payouts" not in [i.get("key") for i in off["banque"]["items"]]
        assert not off["banque"]["items"][-1].get("divider")
        on = {m["key"]: m for m in build_nav(chart, is_admin=True, features={"odoo", "stancer"})}
        assert "odoo" in on and "payouts" in [i.get("key") for i in on["banque"]["items"]]


def test_admin_only_menu_hidden_for_non_admin():
    nav = build_nav("asso", is_admin=False)
    assert "Configuration" not in _labels(nav)


def test_admin_only_item_hidden_for_non_admin():
    nav = {m["key"]: m for m in build_nav("asso", is_admin=False)}
    imports_items = [i["label"] for i in nav["imports"]["items"]]
    assert "Import de tonnages" not in imports_items
    assert "Fichier OFX" in imports_items


def test_admin_only_item_visible_for_admin():
    nav = {m["key"]: m for m in build_nav("asso", is_admin=True)}
    imports_items = [i["label"] for i in nav["imports"]["items"]]
    assert "Import de tonnages" in imports_items


def test_unknown_chart_falls_back_to_default():
    assert _labels(build_nav(None, is_admin=True)) == _labels(build_nav("asso", is_admin=True))


def test_no_orphan_or_consecutive_dividers():
    for menu in build_nav("asso", is_admin=True):
        items = menu.get("items")
        if not items:
            continue
        assert not items[0].get("divider"), f"séparateur en tête: {menu['label']}"
        assert not items[-1].get("divider"), f"séparateur en fin: {menu['label']}"
        for prev, cur in zip(items, items[1:]):
            assert not (prev.get("divider") and cur.get("divider"))


def test_chart_only_menu_is_filtered():
    # Simule un menu réservé à un plan comptable en restreignant à la volée.
    compta = next(m for m in MENUS if m["key"] == "compta")
    original = compta["charts"]
    try:
        compta["charts"] = ["sci"]
        assert "Compta" not in _labels(build_nav("asso", is_admin=True))
        assert "Compta" in _labels(build_nav("sci", is_admin=True))
    finally:
        compta["charts"] = original
