"""Données et services de démonstration pour les captures du README (`e2e_server.py --demo`).

Tout est fabriqué : aucune donnée réelle d'association, d'adhérent ou de locataire, aucun appel à
l'INSEE ni à Brevo.
- Instance « Les Jardins Partagés » (association) : structure, exercice, 12 adhérents (e-mails
  en @example.org) avec des adhésions HelloAsso à des dates variées, intégration Brevo activée.
- Sirene simulé : toute recherche ou fiche renvoie une unité légale fabriquée (« SCI DES TILLEULS »).
- Brevo simulé : un compte en mémoire qui connaît déjà une partie des adhérents, dont un désinscrit.
"""
from __future__ import annotations

import json
import os
from datetime import date, timedelta

from sqlalchemy import text

DEMO_INSTANCE = {"slug": "jardins-demo", "label": "Les Jardins Partagés", "chart": "asso"}
MEMBERS = [("Camille Martin", 20), ("Louis Bernard", 45), ("Inès Petit", 80), ("Hugo Robert", 120), ("Léa Richard", 150),
           ("Nathan Durand", 200), ("Chloé Dubois", 260), ("Jules Moreau", 300), ("Emma Laurent", 340),
           ("Lucas Simon", 355), ("Manon Michel", 380), ("Théo Lefebvre", 420)]


def email(name: str) -> str:
    return name.lower().replace(" ", ".").replace("é", "e").replace("è", "e").replace("ï", "i").replace("î", "i") \
        + "@example.org"


def seed(engine, tmpdir: str) -> None:
    today = date.today()
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO fiscal_years (label, start_date, end_date, closed, vat_liable) "
                          "VALUES (:l, :s, :e, 0, 0)"), {"l": str(today.year), "s": f"{today.year}-01-01",
                                                        "e": f"{today.year}-12-31"})
        conn.execute(text(
            "INSERT INTO organization (name, rna, address_line1, postal_code, city, country, purpose, signatory_name, "
            "signatory_title) VALUES ('Les Jardins Partagés', 'W351234567', '12 rue des Potagers', '35000', 'Rennes', "
            "'France', 'Jardins partagés et ateliers de jardinage', 'Camille Martin', 'Présidente')"))
        for i, (name, days) in enumerate(MEMBERS, 1):
            conn.execute(text("INSERT INTO entities (name, entity_type, email, is_member, is_benevole) "
                              "VALUES (:n, 'ADHERENT', :e, 1, :b)"), {"n": name, "e": email(name), "b": int(i % 4 == 0)})
            entity = conn.execute(text("SELECT id FROM entities WHERE name = :n"), {"n": name}).scalar()
            first, last = name.split(" ", 1)
            joined = today - timedelta(days=days)
            conn.execute(text("INSERT INTO helloasso_orders (helloasso_id, entity_id, date, amount_total_cents, amount_vat_cents, "
                              "form_slug, form_type, payer_first_name, payer_last_name) VALUES (:h, :e, :d, 2000, 0, "
                              "'adhesion', 'Membership', :f, :l)"), {"h": 9000 + i, "e": entity, "d": f"{joined} 10:00:00",
                                                         "f": first, "l": last})
            order = conn.execute(text("SELECT id FROM helloasso_orders WHERE helloasso_id = :h"), {"h": 9000 + i}).scalar()
            conn.execute(text("INSERT INTO helloasso_items (helloasso_id, order_id, entity_id, type, name, amount_cents, "
                              "user_first_name, user_last_name) VALUES (:h, :o, :e, 'Membership', 'Adhésion', 2000, :f, :l)"),
                         {"h": 19000 + i, "o": order, "e": entity, "f": first, "l": last})
        for key, value in (("api_key", "xkeysib-demo"), ("list_id", "7")):
            conn.execute(text("INSERT INTO external_connections (service, key, value, updated_at) "
                         "VALUES ('brevo', :k, :v, CURRENT_TIMESTAMP)"),
                         {"k": key, "v": value})


# ------------------------------------------------------------------ Sirene simulé


def _unit(siren: str) -> dict:
    return {"siren": siren, "statutDiffusionUniteLegale": "O", "etatUniteLegale": "1",
            "denominationUniteLegale": "SCI DES TILLEULS", "categorieJuridiqueUniteLegale": "6540",
            "activitePrincipaleUniteLegale": "6820B", "nomenclatureActivitePrincipaleUniteLegale": "NAFRev2",
            "nicSiegeUniteLegale": "00014"}


def _establishment(siret: str) -> dict:
    return {"siren": siret[:9], "siret": siret, "statutDiffusionEtablissement": "O", "etatEtablissement": "1",
            "etablissementSiege": True, "activitePrincipaleEtablissement": "6820B",
            "nomenclatureActivitePrincipaleEtablissement": "NAFRev2",
            "adresseEtablissement": {"numeroVoieEtablissement": "8", "typeVoieEtablissement": "ALLEE",
                                     "libelleVoieEtablissement": "des Tilleuls", "codePostalEtablissement": "17100",
                                     "libelleCommuneEtablissement": "Saintes"}}


class _Response:
    def __init__(self, body, status=200):
        self.status_code, self._body, self.headers = status, body, {}
        self.ok, self.text = status < 400, json.dumps(body)

    def json(self):
        return self._body


def fake_sirene(method, url, params=None, json=None, headers=None, timeout=None):
    path = url.split("/api-sirene/4", 1)[-1]
    if path.startswith("/etat-courant/unites-legales/multicritere"):
        return _Response({"items": [{"item": _unit("123456782")}]})
    if path.startswith("/etat-courant/etablissements/multicritere"):
        sirens = (json or {}).get("siren") or [s[:9] for s in (json or {}).get("siret", [])]
        return _Response({"items": [{"item": _establishment(f"{s}00014")} for s in sirens]})
    if path.startswith("/etat-courant/unites-legales/"):
        return _Response(_unit(path.rsplit("/", 1)[-1]))
    if path.startswith("/etat-courant/etablissements/"):
        return _Response(_establishment(path.rsplit("/", 1)[-1]))
    return _Response({"message": "introuvable"}, 404)


# ------------------------------------------------------------------ Brevo simulé


class FakeBrevo:
    """Compte Brevo de démonstration : 9 des 12 adhérents y sont déjà (dont un désinscrit),
    plus deux anciens contacts de la liste inconnus de Lyvre."""

    def __init__(self):
        self.items = []
        for i, (name, _days) in enumerate(MEMBERS[:9], 1):
            self.items.append({"id": 500 + i, "email": email(name), "emailBlacklisted": i == 4, "listIds": [7],
                               "attributes": {"PRENOM": name.split(" ")[0]}})
        for i, address in enumerate(("ancien.membre@example.org", "contact.salon@example.org"), 1):
            self.items.append({"id": 600 + i, "email": address, "emailBlacklisted": False, "listIds": [7], "attributes": {}})

    def account(self):
        return {"companyName": "Les Jardins Partagés", "plan": [{"type": "free"}]}

    def lists(self):
        return [{"id": 7, "name": "Adhérents (Lyvre)", "uniqueSubscribers": len(self.items)}]

    def attributes(self):
        return [{"name": n, "category": "normal"} for n in
                ("PRENOM", "NOM", "DATE_ADH", "LYVRE_STATUT", "LYVRE_ECHEANCE", "LYVRE_BENEVOLE", "EXT_ID")]

    def contacts(self):
        return [dict(c) for c in self.items]


def install(app) -> None:
    """Branche les services simulés (à appeler avant de servir)."""
    from app.services import brevo_client, sirene

    app.config["SIRENE_API_KEY"] = "demo"
    sirene.requests.request = fake_sirene
    fake = FakeBrevo()
    brevo_client.Client.from_config = classmethod(lambda cls, timeout=15: fake)
    os.environ.setdefault("APP_COMMIT", "")
