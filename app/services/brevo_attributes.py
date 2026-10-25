"""Attributs Brevo attendus par la synchronisation des adhérents (lot B1, conception §2.4).

Deux familles : les attributs **partagés** (PRENOM, NOM), que l'association entretient aussi dans
Brevo et que Lyvre ne fait que compléter quand ils sont vides ; les attributs **gérés par Lyvre**,
toujours écrits. Un attribut absent du compte n'est pas envoyé (Brevo l'ignorerait sans rien dire) :
il se crée par une action explicite (`create_missing`), jamais automatiquement.
"""
from __future__ import annotations

# nom → (type Brevo, libellé, partagé)
EXPECTED: dict[str, tuple[str, str, bool]] = {
    "PRENOM":         ("text", "Prénom", True),
    "NOM":            ("text", "Nom", True),
    "DATE_ADH":       ("date", "Dernière adhésion (HelloAsso ou caisse)", False),
    "LYVRE_STATUT":   ("text", "Statut d'adhésion", False),
    "LYVRE_ECHEANCE": ("date", "Date anniversaire de l'adhésion", False),
    "LYVRE_BENEVOLE": ("boolean", "Bénévole", False),
}
SHARED = {name for name, (_kind, _label, shared) in EXPECTED.items() if shared}


def missing(attributes: list[dict]) -> list[str]:
    """Attributs attendus absents du compte (attributs « normaux » de Brevo)."""
    present = {a.get("name") for a in attributes if a.get("category", "normal") == "normal"}
    return [name for name in EXPECTED if name not in present]


def status(attributes: list[dict]) -> list[dict]:
    present = {a.get("name"): a.get("type") for a in attributes if a.get("category", "normal") == "normal"}
    return [{"name": name, "type": kind, "label": label, "shared": shared, "present": name in present}
            for name, (kind, label, shared) in EXPECTED.items()]


def create_missing(client) -> list[str]:
    """Crée les attributs manquants ; renvoie leurs noms."""
    created = []
    for name in missing(client.attributes()):
        client.create_attribute(name, EXPECTED[name][0])
        created.append(name)
    return created
