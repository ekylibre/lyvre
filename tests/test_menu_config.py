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


# ---------------------------------------------------------------- lot NV1 (claudedocs/design_navigation.md)

def _keys(items):
    return [i.get("key") for i in items if not i.get("divider")]


def test_every_endpoint_is_a_spa_route():
    import json
    from pathlib import Path

    from app.menu_config import endpoints
    routes = {r["endpoint"] for r in json.loads((Path(__file__).parents[1] / "app" / "spa_routes.json").read_text())["routes"]}
    missing = [e for e in endpoints() if e not in routes]
    assert missing == []


def test_farm_compta_has_three_submenus_and_gestion_menu():
    nav = {m["key"]: m for m in build_nav("agri", is_admin=True, features={"vat_returns"})}
    compta = {i["key"]: i for i in nav["compta"]["items"] if not i.get("divider")}
    assert _keys(nav["compta"]["items"]) == ["entries", "editions", "fixed_and_stock", "tax_social",
                                             "accounting_settings"]
    assert compta["entries"]["also"] == ["lettering.index"]              # lot NV2 : onglet
    assert _keys(compta["editions"]["items"]) == ["balance", "grand_livre", "bilan", "compte_resultat", "sig"]
    assert _keys(compta["fixed_and_stock"]["items"]) == ["assets", "stock"]
    assert "vat_returns" in _keys(compta["tax_social"]["items"]) and "msa" in _keys(compta["tax_social"]["items"])
    assert _keys(nav["gestion"]["items"]) == ["projects", "budgets", "budget_tracking", "agenda", "activities",
                                              "analytic", "activity_margins"]
    sales = {i["key"]: i for i in nav["sales"]["items"] if not i.get("divider")}
    assert _keys(sales["cooperatives"]["items"]) == ["sales_self_billed", "sales_coop_statements"]
    assert "rent_indices" not in sales and sales["leases"]["also"] == ["rent_indices.index"]
    assert list(nav)[:4] == ["dashboard", "compta", "gestion", "banque"]


def test_single_entry_submenu_collapses_and_empty_one_disappears():
    nav = {m["key"]: m for m in build_nav("asso", is_admin=True)}
    keys = _keys(nav["compta"]["items"])
    assert "fixed_and_stock" not in keys and "assets" in keys          # une seule entrée : remontée
    assert "tax_social" not in keys and "vat_returns" not in keys      # TVA désactivée : sous-menu vide
    with_vat = {m["key"]: m for m in build_nav("asso", is_admin=True, features={"vat_returns"})}
    assert "vat_returns" in _keys(with_vat["compta"]["items"])         # une seule entrée : remontée
    assert _keys(nav["gestion"]["items"]) == ["projects", "budgets", "budget_tracking"]
    assert "cooperatives" not in _keys(nav["sales"]["items"])


def test_top_level_menus_have_icons():
    assert all(m.get("icon") for m in MENUS)


def test_session_nav_is_nested_with_icons(app, login_as):
    client = login_as(role="admin")
    nav = {m["key"]: m for m in client.get("/api/v1/session").get_json()["nav"]}
    compta = {i.get("key"): i for i in nav["compta"]["items"]}
    assert nav["compta"]["icon"] == "calculator" and compta["entries"]["url"].endswith("/entries/")
    editions = compta["editions"]
    assert "url" not in editions and editions["items"][0]["key"] == "balance" and editions["items"][0]["icon"] == "scale"
    assert compta["entries"]["also_urls"] == ["/lettering/"]


def test_every_icon_is_in_the_frontend_table():
    import re
    from pathlib import Path
    table = (Path(__file__).parents[1] / "frontend" / "src" / "app" / "navIcons.tsx").read_text()
    known = set(re.findall(r'"([a-z0-9-]+)":', table)) | set(re.findall(r"\b([a-z]+): [A-Z]", table))

    def icons(entries):
        for e in entries:
            if e.get("icon"):
                yield e["icon"]
            yield from icons(e.get("items", []))
    assert sorted(set(icons(MENUS)) - known) == []
