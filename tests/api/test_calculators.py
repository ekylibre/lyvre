"""Lot AG12.a : cadre des calculettes (registre, API, gabarit, copie) et pilotes 23 amortissement, 25 acomptes de
TVA, 08 micro-BA. Les calculettes du groupe A donnent le même résultat que le service existant (règle unique)."""
from datetime import date

import pytest

from app.extensions import db
from app.models import Account, Asset, FiscalYear
from app.services import assets, ba_regimes, calculators, reg_params, vat_installments
from app.services.calculators import CalculatorError

from test_agri_fixtures import _agri_instance

API = "/api/v1/calculators"

# Faux services géographiques (calculettes 04 et 07) : aucun appel réel à l'IGN ni au Sandre.
SQUARE = {"type": "MultiPolygon", "coordinates": [[[[-0.79, 45.82], [-0.78, 45.82], [-0.78, 45.84], [-0.79, 45.84],
                                                     [-0.79, 45.82]]]]}
SANDRE_IN = """<?xml version='1.0' encoding="UTF-8" ?><wfs:FeatureCollection xmlns:sa="http://xml.sandre.eaufrance.fr/"
 xmlns:wfs="http://www.opengis.net/wfs/2.0" numberMatched="1" numberReturned="1"><wfs:member>
 <sa:ZoneVuln_delimitation_FXX><sa:CdEuZoneVuln>FRF_38</sa:CdEuZoneVuln><sa:NomZoneVuln></sa:NomZoneVuln>
 <sa:NumTexteReglem>R76-2021-07-15-00023</sa:NumTexteReglem><sa:URLTexteReglem>https://example.org/arrete.pdf</sa:URLTexteReglem>
 </sa:ZoneVuln_delimitation_FXX></wfs:member></wfs:FeatureCollection>"""
SANDRE_OUT = """<?xml version='1.0' encoding="UTF-8" ?><wfs:FeatureCollection xmlns:wfs="http://www.opengis.net/wfs/2.0"
 numberMatched="0" numberReturned="0"></wfs:FeatureCollection>"""


def _fake_ign(layer, params):
    if layer == "RPG.LATEST:codes_cultures":
        return {"features": [{"properties": {"code_culture": "BTH", "libelle_culture": "Blé tendre d'hiver",
                                             "libelle_groupe_culture": "Blé tendre"}}]}
    if layer == "RPG.LATEST:parcelles_graphiques":
        return {"features": [{"type": "Feature", "geometry": SQUARE, "properties": {"code_cultu": "BTH", "surf_parc": 9.53}},
                             {"type": "Feature", "geometry": None, "properties": {"code_cultu": "MIS", "surf_parc": 4.84}}]}
    if layer == "patrinat_sic:sic":
        return {"features": [{"properties": {"nom_site": "Vallée de la Charente (basse vallée)", "id_mnhn": "FR5400430",
                                             "url_fiche": "https://inpn.mnhn.fr/site/natura2000/FR5400430"}}]}
    return {"features": []}


DDT_016 = """<?xml version='1.0' encoding="UTF-8" ?><wfs:FeatureCollection xmlns:ms="http://mapserver.gis.umn.edu/mapserver"
 xmlns:wfs="http://www.opengis.net/wfs/2.0"><wfs:member><ms:N_DEFAVORISEE_ZSUP_016><ms:TYPE_HANDI>ZSCS</ms:TYPE_HANDI>
 </ms:N_DEFAVORISEE_ZSUP_016></wfs:member></wfs:FeatureCollection>"""


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    from app.services import agri_geo
    monkeypatch.setattr(agri_geo, "_ign", _fake_ign)
    monkeypatch.setattr(agri_geo, "_sandre", lambda query: SANDRE_IN if "45.8" in query else SANDRE_OUT)
    monkeypatch.setattr(agri_geo, "department_at", lambda lat, lon: "016" if lat < 45.7 else "017")
    monkeypatch.setattr(agri_geo, "_ddt", lambda source, lat, lon: DDT_016)


@pytest.fixture()
def farm(app, login_as):
    client = login_as(role="admin")
    _agri_instance()
    db.session.add(FiscalYear(label="2026", start_date=date(2026, 1, 1), end_date=date(2026, 12, 31), vat_liable=True))
    db.session.commit()
    return client


def test_registry_specs_and_examples(farm):
    modules = calculators.registry()
    assert {"amortissement", "acompte-tva", "micro-ba"} <= set(modules)
    for code, module in modules.items():
        spec = module.SPEC
        assert spec.method.strip() and spec.category in calculators.CATEGORIES and spec.charts
        assert set(spec.example) <= {i.key for i in spec.inputs}
        result = calculators.run(module, spec.example)                      # l'exemple se calcule
        assert result["headline"] and spec.title in result["text"] and "Méthode et limites" in result["text"]


def test_list_and_filter(farm):
    data = farm.get(API).get_json()
    assert data["meta"]["chart"] == "agri" and {i["code"] for i in data["items"]} >= {"micro-ba", "acompte-tva"}
    assert farm.get(f"{API}?chart=asso").get_json()["items"] == []
    assert len(farm.get(f"{API}?chart=all").get_json()["items"]) == len(calculators.registry())


def test_amortissement_equals_register(farm):
    account = Account.query.filter(Account.code.like("2154%"), Account.is_header.is_(False)).first() \
        or Account.query.filter(Account.code.like("215%"), Account.is_header.is_(False)).first()
    asset = Asset(label="Tracteur", account_id=account.id, acquired_on=date(2026, 3, 15), in_service_date=date(2026, 4, 1),
                  acquisition_cents=4500000, method="linear", duration_months=84, status="in_use")
    db.session.add(asset)
    db.session.commit()
    detail = farm.get(f"{API}/amortissement?choice={asset.id}").get_json()["item"]
    assert detail["prefill"]["base"] == {"value": "45000.00", "origin": "registre des immobilisations : Tracteur"}
    values = {k: v["value"] for k, v in detail["prefill"].items()}
    result = farm.post(f"{API}/amortissement", json={"values": values}).get_json()["result"]
    expected = [calculators.euros(r.amount_cents)
                for r in assets.schedule(asset)]
    assert [row[4] for row in result["table"]["rows"]] == expected
    regressive = farm.post(f"{API}/amortissement", json={"values": {**values, "method": "regressive", "duration_months": "24"}})
    assert any("3 ans" in w for w in regressive.get_json()["result"]["warnings"])
    assert farm.post(f"{API}/amortissement", json={"values": {**values, "duration_months": "0"}}).status_code == 422


def test_acompte_tva(farm):
    result = farm.post(f"{API}/acompte-tva", json={"values": {"year": "2027", "due": "8400", "assets_vat": "1200"}}).get_json()["result"]
    amount = vat_installments.proposed_amount(840000, date(2027, 12, 31))
    assert result["headline"][0]["value"] == calculators.euros(amount)
    assert len(result["table"]["rows"]) == 4
    assert result["table"]["rows"][0][2] == f"{vat_installments.due_date(date(2027, 3, 31)):%d/%m/%Y}"
    small = farm.post(f"{API}/acompte-tva", json={"values": {"year": "2027", "due": "500", "assets_vat": "200"}}).get_json()["result"]
    assert small["headline"][0]["value"] == "dispense"
    assert {p["key"] for p in result["params"]} == set(calculators.get("acompte-tva").SPEC.params)


def test_micro_ba_single_rule(farm):
    values = {"year": "2026", "receipts_n2": "61000", "receipts_n1": "68000", "receipts_n": "72000", "real_result": "21000"}
    result = farm.post(f"{API}/micro-ba", json={"values": values, "origins": {"receipts_n": "saisie"}}).get_json()["result"]
    expected = ba_regimes.micro_profit(6700000, date(2026, 12, 31))
    assert result["headline"][1] == {"label": "Bénéfice micro-BA", "value": calculators.euros(expected)}
    assert "Recettes N : 72000 € (saisie)" in result["text"]
    assert farm.post(f"{API}/micro-ba", json={"values": {**values, "receipts_n": ""}}).status_code == 422
    assert farm.post(f"{API}/micro-ba", json={"values": {**values, "receipts_n": "abc"}}).status_code == 422


def test_missing_param_blocks(farm, monkeypatch):
    real = reg_params.get
    monkeypatch.setattr(reg_params, "get", lambda key, on=None, default=None: None if key == "ba.micro.allowance_bp"
                        else real(key, on, default))
    resp = farm.post(f"{API}/micro-ba", json={"values": calculators.get("micro-ba").SPEC.example})
    assert resp.status_code == 409 and "ba.micro.allowance_bp" in resp.get_json()["error"]["message"]
    with pytest.raises(CalculatorError):
        calculators.require_params(calculators.get("micro-ba").SPEC, date(2026, 12, 31))


def test_unknown(farm):
    assert farm.get(f"{API}/inconnue").status_code == 404


def test_accountant_can_compute(app, login_as):
    accountant = login_as(role="accountant")
    _agri_instance()
    resp = accountant.post(f"{API}/acompte-tva", json={"values": {"year": "2027", "due": "8400"}})
    assert resp.status_code == 200                                          # un calcul n'écrit rien


# ------------------------------------------------------------------ lot AG12.b : reste du groupe A

def _run(farm, code, values):
    resp = farm.post(f"{API}/{code}", json={"values": values})
    assert resp.status_code == 200, resp.get_json()
    return resp.get_json()["result"]


def test_dep_single_rule(farm):
    from app.services import dep
    result = _run(farm, "dep", {"closing": "2026-12-31", "profit": "62000", "operators": "2", "months": "12", "pending": "15000"})
    expected = dep.ceiling_for(6200000, date(2026, 12, 31), 2, 12, 1500000)
    assert result["headline"][0]["value"] == calculators.euros(expected["ceiling_cents"])
    fy = FiscalYear.query.one()
    assert dep.ceiling(6200000, fy)["ceiling_cents"] == dep.ceiling_for(6200000, fy.end_date, dep.operators(fy), 12,
                                                                         dep.outstanding(fy, exclude_fy=fy))["ceiling_cents"]


def test_fermage(farm):
    from decimal import Decimal
    from app.services import rent_revision
    rent_revision.save_value("FERMAGES", "2025", "122.55")
    rent_revision.save_value("FERMAGES", "2026", "123.06")
    db.session.commit()
    result = _run(farm, "fermage", {"rent": "4800", "index_code": "FERMAGES", "old_period": "2025", "new_period": "2026"})
    expected = rent_revision.apply_ratio(480000, Decimal("123.06") / Decimal("122.55"))
    assert result["headline"][0]["value"] == calculators.euros(expected)
    missing = farm.post(f"{API}/fermage", json={"values": {"rent": "4800", "index_code": "FERMAGES", "old_period": "2019",
                                                           "new_period": "2026"}})
    assert missing.status_code == 409 and "2019" in missing.get_json()["error"]["message"]


def test_msa_single_rule(farm):
    from app.services import msa_estimate
    result = _run(farm, "msa", {"year": "2026", "base": "32000", "status": "principal", "atexa": "B"})
    expected = msa_estimate.estimate(3200000, 2026, "principal", "B")["totals"]["total_cents"]
    assert result["headline"][0]["value"] == calculators.euros(expected) and len(result["table"]["rows"]) > 8


def test_marge_brute_and_cout_materiel(farm):
    result = _run(farm, "marge-brute", {"sales": "86000", "aids": "4200", "other": "-1500", "operational": "38500",
                                        "measure": "62", "unit": "ha"})
    assert result["headline"][0]["value"] == calculators.euros(5020000)
    assert result["headline"][1] == {"label": "Marge brute par ha", "value": calculators.euros(80968)}
    cost = _run(farm, "cout-materiel", {"depreciation": "9600", "financial": "1100", "insurance": "650", "maintenance": "2400",
                                        "hours": "480", "fuel_per_hour": "14", "fuel_price": "1.15", "hectares": "320"})
    # Fixes 11 350 € ÷ 480 h = 23,65 €/h ; variables : 2 400 ÷ 480 + 14 × 1,15 = 21,10 €/h.
    assert cost["headline"][0]["value"] == calculators.euros(2365 + 2110)
    assert cost["headline"][1]["value"] == calculators.euros(round((1135000 + 240000 + 1610 * 480) / 320))


def test_rfa_single_rule(farm):
    from app.services import rfa
    result = _run(farm, "rfa", {"year": "2026", "high_base": "38000", "low_base": "6500", "receipts_previous": "41000",
                                "receipts_year": "60000", "factor": "1"})
    on = date(2026, 12, 31)
    expected = rfa.flat_amount(3800000, 650000, reg_params.value("vat.rfa.rate_high_bp", on), reg_params.value("vat.rfa.rate_low_bp", on))
    assert result["headline"][0]["value"] == calculators.euros(expected)
    assert any("régime simplifié" in w for w in result["warnings"])         # moyenne 50 500 € > 46 000 €


# ------------------------------------------------------------------ lot AG12.c : groupe B (cas chiffrés à la main)

@pytest.mark.parametrize("code, values, expected", [
    ("calc-surfaces", {"value": "2.35", "unit": "ha"}, "2,3500 ha"),
    ("calc-parcelle", {"shape": "trapeze", "a": "210", "b": "95", "c": "180"}, "18 525,0 m²"),   # (210+180)/2×95
    ("calc-regle-de-trois", {"a": "12", "b": "540", "c": "17"}, "765,0000"),
    ("calc-pourcentage", {"start": "200", "end": "230"}, "+15,00 %"),
    ("calc-debit-chantier", {"width": "6", "speed": "8", "efficiency": "75"}, "3,60 ha/h"),
    ("calc-temps-chantier", {"surface": "48", "rate": "3.6"}, "13 h 20"),
    ("calc-dose-semis", {"grains": "300", "tgw": "45", "emergence": "90"}, "150,0 kg/ha"),
    ("calc-densite-plantation", {"row": "2.5", "spacing": "1"}, "4 000 plants/ha"),
    ("calc-prix-unite", {"price": "420", "content": "27"}, "1,556 €/unité"),
    ("calc-dose-apport", {"units": "60", "content": "30"}, "200,0 kg/ha"),
    ("calc-debit-buse", {"volume": "150", "speed": "8", "spacing": "0.5"}, "1,000 l/min"),
    ("calc-pluviometrie", {"mm": "25"}, "250,0 m³/ha"),
    ("calc-enrouleur", {"flow": "40", "width": "80", "speed": "25"}, "20,0 mm"),
    ("calc-rendement", {"weight": "182.4", "surface": "24"}, "76,0 q/ha"),
    ("calc-gmq", {"start": "280", "end": "400", "days": "120"}, "1 000 g/j"),
    ("calc-mise-bas", {"service": "2026-11-10", "gestation": "283"}, "20/08/2027"),
    ("calc-chargement", {"n1": "55", "c1": "1", "n2": "30", "c2": "0.5", "surface": "70"}, "1,00 UGB/ha"),
    ("calc-emprunt", {"capital": "100000", "rate": "3", "months": "120"}, "965,61 €"),
    ("refaction-humidite", {"gross": "28.4", "measured": "18.5", "base": "15", "drying": "1.9"}, "27,231 t"),
    ("prix-equilibre", {"costs": "1450", "aids": "180", "other": "60", "yield": "7.2"}, "168,06 €/t"),
    ("entraide", {"tool": "28", "tractor": "35", "driver": "22", "rate": "2.5"}, "34,00 €/ha"),
    ("solaire", {"power": "100", "yield": "1150", "tariff": "0.105"}, "115 000 kWh"),
])
def test_group_b_values(farm, code, values, expected):
    result = _run(farm, code, values)
    assert result["headline"][0]["value"] == expected


def test_group_b_refusals(farm):
    assert farm.post(f"{API}/calc-debit-chantier", json={"values": {"width": "0", "speed": "8", "efficiency": "75"}}).status_code == 422
    assert farm.post(f"{API}/calc-pourcentage", json={"values": {"start": "0", "end": "5"}}).status_code == 422
    assert farm.post(f"{API}/refaction-humidite", json={"values": {"gross": "10", "measured": "120", "base": "15"}}).status_code == 422
    vat = _run(farm, "calc-tva", {"amount": "1055", "kind": "ttc", "rate": "5.5"})
    assert [h["value"] for h in vat["headline"]] == [calculators.euros(100000), calculators.euros(5500), calculators.euros(105500)]
    gnr = _run(farm, "gnr", {"litres": "12000", "gnr_price": "1.12", "road_price": "1.62"})
    assert gnr["headline"][1]["value"] == calculators.euros(600000) and "attestation" in gnr["warnings"][0]
    listing = farm.get(f"{API}?chart=agri").get_json()
    assert len(listing["items"]) == len(calculators.registry())



# ------------------------------------------------------------------ lot AG12.d : groupe C (paramètres sourcés)

def test_certiphyto(farm):
    dea = _run(farm, "certiphyto", {"expiry": "2024-10-11", "category": "dea"})
    assert dea["headline"][0]["value"] == "10/10/2026"                       # exemple officiel (service-public)
    other = _run(farm, "certiphyto", {"expiry": "2024-10-11", "category": "other"})
    assert other["headline"][0]["value"] == "11/10/2024" and "expiré" in other["warnings"][0]
    late = _run(farm, "certiphyto", {"expiry": "2030-03-15", "category": "dea"})
    assert late["headline"] == [{"label": "Valide jusqu'au", "value": "15/03/2030"},
                                {"label": "Renouveler à partir du", "value": "15/03/2029"}]


def test_duer(farm):
    small = _run(farm, "duer", {"staff": "4", "last_update": "2024-01-10"})
    assert small["headline"][0]["value"] == "non obligatoire"
    big = _run(farm, "duer", {"staff": "11", "last_update": "2024-01-10"})
    assert big["headline"][0]["value"] == "10/01/2025" and "retard" in big["warnings"][0]


@pytest.mark.parametrize("pay, expected_rate", [("2000", "28,000 %"), ("2900", "0,000 %")])
def test_tode_bounds(farm, pay, expected_rate):
    result = _run(farm, "tode", {"pay": pay, "smic": "1800", "rate": "28"})
    assert result["headline"][1]["value"] == expected_rate                  # ≤ 1,25 SMIC : total ; ≥ 1,6 : nul


def test_tode_degressive(farm):
    from decimal import Decimal
    result = _run(farm, "tode", {"pay": "2520", "smic": "1800", "rate": "28"})   # 1,4 SMIC
    rate = Decimal("1.25") * Decimal("0.28") / Decimal("0.35") * (Decimal("1.6") * 1800 / 2520 - 1)
    assert result["headline"][0]["value"] == calculators.euros(int((Decimal(252000) * rate).quantize(Decimal(1))))


def test_aides_pac(farm):
    result = _run(farm, "aides-pac", {"campaign": "2026", "dpb_value": "11500", "hectares": "95", "ecoregime": "base",
                                      "hedges": "yes", "young_farmer": "yes", "bovines": "40", "bovine_level": "base",
                                      "ewes": "600", "goats": ""})
    details = {d["label"]: d["value"] for d in result["details"]}
    assert details["Aide redistributive (52,00 ha)"] == calculators.euros(52 * 4850)
    assert details["Écorégime"] == calculators.euros(95 * 4546) and details["Bonus haies"] == calculators.euros(95 * 2000)
    assert details["Aide ovine"] == calculators.euros(600 * 2054 + 500 * 200)
    expected = 1150000 + 52 * 4850 + 95 * 4546 + 95 * 2000 + 370000 + 40 * 5100 + 600 * 2054 + 500 * 200
    assert result["headline"][0]["value"] == calculators.euros(expected)
    assert farm.post(f"{API}/aides-pac", json={"values": {"campaign": "2025", "hectares": "10", "ecoregime": "base",
                                                         "hedges": "no", "young_farmer": "no", "bovine_level": "base"}}
                     ).status_code == 409                                     # campagne sans arrêté enregistré


def test_gnr_crisis_aid(farm):
    base = {"litres": "12000", "gnr_price": "1.12", "road_price": "1.62"}
    september = _run(farm, "gnr", {**base, "aid_month": "2026-09-15", "aid_litres": "1800"})
    assert september["headline"][2]["value"] == calculators.euros(27000)    # 1 800 l × 15 c€
    assert "energy.gnr.crisis_aid_cents_per_hl" in {p["key"] for p in september["params"]}
    april = _run(farm, "gnr", {**base, "aid_month": "2026-04-10", "aid_litres": "2000000000"})
    assert april["headline"][2]["value"] == calculators.euros(5000000)      # plafond d'avril
    none = _run(farm, "gnr", {**base, "aid_month": "2025-09-01", "aid_litres": "1000"})
    assert len(none["headline"]) == 2 and any(d["value"] == "aucune pour ce mois" for d in none["details"])



# ------------------------------------------------------------------ lot AG12.d : 04 carte RPG, 07 zonages

def test_rpg(farm):
    result = _run(farm, "rpg", {"point": "45.8295,-0.7870", "radius": "300"})
    assert result["headline"][0]["value"] == "Blé tendre d'hiver (9.53 ha)"
    assert result["headline"][2]["value"] == "14,37 ha" and len(result["table"]["rows"]) == 2
    assert result["map"]["center"] == [45.8295, -0.787] and len(result["map"]["features"]["features"]) == 2
    assert farm.post(f"{API}/rpg", json={"values": {"point": "60,20"}}).status_code == 422          # hors de France
    assert farm.post(f"{API}/rpg", json={"values": {"point": "45.8,-0.78", "radius": "5000"}}).status_code == 422


def test_zonages(farm):
    result = _run(farm, "zonages", {"point": "45.8295,-0.7870"})
    rows = {r[0]: r for r in result["table"]["rows"]}
    assert rows["Zone vulnérable aux nitrates"][1] == "oui" and "FRF_38" in rows["Zone vulnérable aux nitrates"][2]
    natura = rows["Natura 2000 — site d'importance communautaire (directive Habitats)"]
    assert natura[1] == "oui" and "FR5400430" in natura[2]
    assert result["headline"] == [{"label": "Zonages au point", "value": "2"},
                                  {"label": "Zone vulnérable aux nitrates", "value": "oui"}]
    outside = _run(farm, "zonages", {"point": "45.0,6.3"})
    assert outside["headline"][1]["value"] == "non"


def test_geo_unavailable(farm, monkeypatch):
    from app.services import agri_geo
    from app.services.geodata import GeoUnavailable

    def down(*a, **k):
        raise GeoUnavailable("Le service cartographique de l'IGN")
    monkeypatch.setattr(agri_geo, "_ign", down)
    resp = farm.post(f"{API}/rpg", json={"values": {"point": "45.8,-0.78"}})
    assert resp.status_code == 503 and "IGN" in resp.get_json()["error"]["message"]


def test_point_in_and_sandre_parse():
    from app.services import agri_geo
    assert agri_geo.point_in(SQUARE, 45.83, -0.785) and not agri_geo.point_in(SQUARE, 45.85, -0.785)
    assert agri_geo.parse_vulnerable(SANDRE_IN)["code"] == "FRF_38" and agri_geo.parse_vulnerable(SANDRE_OUT) is None



# ------------------------------------------------------------------ zones défavorisées (ICHN), données des DDT

def test_zonages_ichn(farm):
    covered = _run(farm, "zonages", {"point": "45.65,0.16"})                # Charente : DDT publiée
    rows = {r[0]: r for r in covered["table"]["rows"]}
    assert rows["Zone défavorisée (ICHN)"][1] == "oui" and "ZSCS" in rows["Zone défavorisée (ICHN)"][2]
    assert "DDT Charente" in rows["Zone défavorisée (ICHN)"][2]
    other = _run(farm, "zonages", {"point": "45.8295,-0.7870"})             # Charente-Maritime : pas de données
    row = next(r for r in other["table"]["rows"] if r[0] == "Zone défavorisée (ICHN)")
    assert row[1] == "à vérifier" and "017" in row[2]


def test_parse_ddt_filters():
    from app.services import agri_geo
    rhone = agri_geo.less_favoured_sources()["069"]
    text = """<wfs:FeatureCollection xmlns:ms="http://mapserver.gis.umn.edu/mapserver" xmlns:wfs="http://www.opengis.net/wfs/2.0">
     <wfs:member><ms:n_defavorisee_zinf_s_069><ms:lib_zone>Piémont</ms:lib_zone><ms:annee>2015</ms:annee></ms:n_defavorisee_zinf_s_069></wfs:member>
     <wfs:member><ms:n_defavorisee_zinf_s_069><ms:lib_zone>Plaine</ms:lib_zone><ms:annee>2019</ms:annee></ms:n_defavorisee_zinf_s_069></wfs:member>
     <wfs:member><ms:n_defavorisee_zinf_s_069><ms:lib_zone>Zone défavorisée simple</ms:lib_zone><ms:annee>2022</ms:annee></ms:n_defavorisee_zinf_s_069></wfs:member>
    </wfs:FeatureCollection>"""
    assert agri_geo.parse_ddt(text, rhone) == ["Zone défavorisée simple"]      # 2015 écarté, « Plaine » non classée
    assert agri_geo._repair("DÃ©favorisÃ©e simple") == "Défavorisée simple"
    assert len(agri_geo.less_favoured_sources()) == 13


def test_under_activity_cg5e(farm):
    """Lot CG5.e (PCG art. 213-32, 618-13 ; BOI-BIC-PDSTK-20-20-10-10 § 240) : production normale, taux d'activité,
    charge de sous-activité. Productions 62, 71, 48, 69, 66 ; année 41 ; frais fixes 18 000 €."""
    def head(result):
        return {h["label"]: h["value"].replace("\u202f", " ") for h in result["headline"]}
    module = calculators.get("sous-activite")
    result = head(calculators.run(module, module.SPEC.example))            # moyenne 63,2 → taux 64,87 %
    assert result["Frais fixes imputables au stock"] == "11 677,22 €" and result["Charge de sous-activité"] == "6 322,78 €"
    median = calculators.run(module, {**module.SPEC.example, "method": "median3"})   # 62, 66, 69 → 65,67
    assert head(median)["Frais fixes imputables au stock"] == "11 238,58 €"
    assert any("valider" in w for w in median["warnings"])
    full = calculators.run(module, {**module.SPEC.example, "current": "80"})
    assert head(full)["Charge de sous-activité"] == "0,00 €"
    with pytest.raises(calculators.CalculatorError):
        calculators.run(module, {"y1": "60", "y2": "62", "current": "40", "fixed": "1000"})


def test_mutual_aid_per_hectare_and_capital_cost_cg6(farm):
    """Lot CG6 : calculette 14 avec un outil au barème à l'hectare ; calculette 22 avec rémunération du capital
    (taux saisi sur le capital moyen) et coût hors chauffeur."""
    def head(result):
        return {h["label"]: h["value"].replace("\\u202f", " ") for h in result["headline"]}
    aid = calculators.get("entraide")
    per_ha = calculators.run(aid, {"tool": "18", "tool_unit": "ha", "tractor": "35", "driver": "22", "rate": "2.5",
                                   "surface": "40"})
    assert head(per_ha)["Coût par hectare"] == "40,80 €/ha"                    # 18 + (35 + 22) ÷ 2,5
    hourly = calculators.run(aid, {"tool": "28", "tractor": "35", "driver": "22", "rate": "2.5"})
    assert head(hourly)["Coût par hectare"] == "34,00 €/ha"                    # (28 + 35 + 22) ÷ 2,5
    cost = calculators.get("cout-materiel")
    base = {"depreciation": "9600", "hours": "480", "driver_per_hour": "20"}
    plain = head(calculators.run(cost, base))
    assert plain["Coût par heure"] == "40,00 €" and plain["Coût par heure hors chauffeur"] == "20,00 €"
    with_capital = calculators.run(cost, {**base, "capital": "60000", "residual": "12000", "capital_rate": "3.2"})
    assert head(with_capital)["Coût par heure"] == "42,40 €"                   # + 3,2 % × 36 000 ÷ 480 h
    assert any(d["label"] == "dont rémunération du capital" for d in with_capital["details"])
    with pytest.raises(calculators.CalculatorError):
        calculators.run(cost, {**base, "capital_rate": "3"})


def test_trial_prefills_offset_year_msa_fallback_and_empty_hint(farm, monkeypatch):
    """Essai de l'interface (10/11/2026) : simulation micro-BA d'un exercice décalé sur l'exercice clos dans l'année ;
    assiette MSA reprise de l'écran MSA sans historique ; calculette « préremplie » sans rien à reprendre."""
    from app.models import Journal, MsaPerson
    from app.services import msa
    from app.services.ledger import post_entry
    fy = FiscalYear(label="2024-2025", start_date=date(2024, 2, 1), end_date=date(2025, 1, 31), vat_liable=True)
    od = Journal(code="OD", label="OD")
    db.session.add_all([fy, od])
    db.session.commit()
    ids = {c: Account.query.filter_by(code=c).one().id for c in ("512", "7011")}
    for day, cents in ((date(2024, 3, 1), 10000000), (date(2025, 1, 15), 2000000)):
        post_entry(fy.id, od.id, day, "vente", [
            {"account_id": ids["512"], "label": "x", "debit_cents": cents, "credit_cents": 0},
            {"account_id": ids["7011"], "label": "x", "debit_cents": 0, "credit_cents": cents}])
    rows = {r["year"]: r for r in ba_regimes.simulation(fy)["receipts"]}
    assert rows[2025]["receipts_cents"] == 12000000 and rows[2025]["label"] == "exercice 2024-2025"
    assert rows[2024]["receipts_cents"] is None and rows[2024]["label"] == "clos en 2024"
    person = MsaPerson(status="principal", base_option="annual")
    db.session.add(person)
    db.session.commit()
    monkeypatch.setattr(msa, "compute", lambda f: {"year": 2025, "people": [
        {"person": {"id": person.id}, "base_cents": 261136, "income_cents": 261136}]})
    pre = farm.get(f"{API}/msa?choice={person.id}").get_json()["item"]["prefill"]
    assert pre["year"]["value"] == "2026" and pre["base"]["value"] == "2611.36"
    assert "écran MSA" in pre["base"]["origin"]
    item = farm.get(f"{API}/marge-brute").get_json()["item"]
    assert item["prefill_options"] == [] and "aucune activité" in item["prefill_empty"]
    assert farm.get(f"{API}/micro-ba").get_json()["item"]["prefill_empty"] is None
