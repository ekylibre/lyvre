"""Lot NV3 : soldes intermédiaires de gestion pour tous les référentiels et page d'accueil des éditions
(claudedocs/design_navigation.md § 4)."""
import pytest

from app.services import sig
from test_reports_charts import _fy, _post

LINES = [("707", 0, 100000), ("607", 40000, 0), ("6037", 5000, 0), ("706", 0, 50000), ("606", 10000, 0),
         ("74", 0, 20000), ("756", 0, 30000), ("63", 3000, 0), ("641", 25000, 0), ("512", 117000, 0)]


@pytest.mark.parametrize("chart, ebe", [("asso", 117000), ("sci", 87000), ("societe", 87000)])
def test_pcg_sig(session, chart, ebe):
    fy = _fy(session)
    _post(session, fy, LINES)
    rows = {r["key"]: r for r in sig.compute(fy, None, chart)}
    assert rows["marge_commerciale"]["n"] == 100000 - 45000
    assert rows["production"]["n"] == 50000
    assert rows["consommations"]["n"] == 10000
    assert rows["valeur_ajoutee"]["n"] == 55000 + 50000 - 10000
    assert ("ressources_associatives" in rows) is (chart == "asso")       # D-NV1 : dons et cotisations à part
    assert rows["ebe"]["n"] == ebe and rows["ebe"]["kind"] == "total"
    assert rows["resultat_net"]["n"] == 117000
    assert rows["ebe"]["p"] is None


def test_api_sig_and_editions_hub(app, login_as):
    client = login_as()
    body = client.get("/api/v1/reports/sig").get_json()                  # plan associatif : ouvert depuis NV3
    assert body["meta"]["method"].startswith("Tableau usuel") and body["meta"]["export_url"] is None
    hub = client.get("/api/v1/reports/").get_json()
    assert [i["key"] for i in hub["items"]] == ["balance", "grand_livre", "bilan", "compte_resultat", "sig"]
    assert hub["items"][4]["url"] == "/reports/sig"
    assert client.get("/reports/").status_code == 200
