"""Vocabulaire autorisé dans le jeu d'essai agricole (lot AG1.f) : rien d'autre ne sort des dossiers réels.

- ``CROPS`` : productions reconnues dans les libellés d'origine (expression → libellé générique). C'est la seule
  information reprise d'un libellé réel ; aucun nom propre n'y figure.
- ``GENERIC`` : gabarits des tiers, journaux et libellés d'écriture.
Les intitulés des comptes viennent du plan agri (data/plan_comptable_agri.json).
"""
import re
import unicodedata

CROPS = [
    (r"MAIS\s*DOUX", "maïs doux"), (r"MAIS\s*SEMENCE", "maïs semence"), (r"MAIS", "maïs"),
    (r"BLE\b|BLE\s*TENDRE", "blé"), (r"\bBLE\s*DUR", "blé dur"), (r"ORGE", "orge"), (r"AVOINE", "avoine"),
    (r"TRITICALE", "triticale"), (r"SEIGLE", "seigle"), (r"SARRASIN", "sarrasin"), (r"SORGHO", "sorgho"),
    (r"TOURNESOL", "tournesol"), (r"COLZA", "colza"), (r"SOJA", "soja"), (r"\bPOIS\b|PROTEAGINEUX", "pois"),
    (r"FEVEROLE", "féverole"), (r"LUZERNE", "luzerne"), (r"TREFLE", "trèfle"), (r"PRAIRIE", "prairie"),
    (r"ASPERGE", "asperges"), (r"HARICOT", "haricots verts"), (r"POMMES?\s*DE\s*TERRE", "pommes de terre"),
    (r"CAROTTE", "carottes"), (r"POIREAU", "poireaux"), (r"OIGNON", "oignons"), (r"TOMATE", "tomates"),
    (r"KIWI", "kiwis"), (r"NOIX", "noix"), (r"\bVIN\b|VINS\b", "vin"), (r"SEMENCE", "semences"),
    (r"PORCELET", "porcelets"), (r"COCHETTE", "cochettes"), (r"TRUIE", "truies de réforme"), (r"VERRAT", "verrats"),
    (r"PORCS?\b|CHARCUTIER", "porcs charcutiers"), (r"VEAU", "veaux"), (r"GENISSE", "génisses"), (r"VACHE", "vaches"),
    (r"BROUTARD", "broutards"), (r"BOVIN", "bovins"), (r"AGNEAU", "agneaux"), (r"BREBIS", "brebis"),
    (r"VOLAILLE|POULET", "volailles"), (r"CANARD", "canards"), (r"\bLAIT\b", "lait"), (r"OEUFS?\b", "œufs"),
    (r"ENGRAIS", "engrais"), (r"ALIMENT", "aliments"), (r"PHYTO", "phytos"), (r"FIOUL|GNR|CARBURANT", "carburant"),
]
_CROPS = [(re.compile(pattern), label) for pattern, label in CROPS]
# Familles d'ateliers (exports Isacompta), lues avant les productions.
FAMILIES = [
    (r"GRANDES\s*CULTURES", "grandes cultures"), (r"CEREALES", "céréales"), (r"PROTEAGINEUX", "protéagineux"),
    (r"OLEAGINEUX", "oléagineux"), (r"FOURRAGE", "fourrages"), (r"LEGUMES", "légumes"), (r"ANIMAUX", "animaux"),
    (r"NON\s*AFFECT", "produits et charges non affectés"), (r"MELANGE", "mélanges"),
]
_FAMILIES = [(re.compile(pattern), label) for pattern, label in FAMILIES]


def family_or_crop(text: str) -> str | None:
    value = plain(text)
    for pattern, label in _FAMILIES:
        if pattern.search(value):
            return label
    return crop_of(text)

GENERIC = {
    "supplier": "Fournisseur {n:03d}", "customer": "Client {n:03d}", "associate": "Associé {n}",
    "debtor": "Débiteur divers {n:03d}", "cooperative": "Coopérative ou négoce {letter}", "bank": "Banque {n}",
    "opening": "À-nouveau", "payment": "Règlement", "receipt": "Encaissement", "vat": "TVA", "unknown": "Opération",
}
JOURNALS = {"AC": "Achats", "VE": "Ventes", "AN": "À-nouveaux", "OD": "Opérations diverses", "EX": "Extournes",
            "TV": "OD TVA", "ST": "Stocks", "IM": "Immobilisations", "EM": "Emprunts"}


def plain(text: str) -> str:
    """Majuscules sans accents (comparaisons)."""
    text = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode()
    return text.upper()


def crop_of(*texts: str) -> str | None:
    """Production reconnue dans un des libellés (ou None)."""
    for text in texts:
        value = plain(text)
        for pattern, label in _CROPS:
            if pattern.search(value):
                return label
    return None


def tokens(text: str) -> set[str]:
    """Mots de 4 lettres et plus, et nombres de 6 chiffres et plus (contrôle de fuite)."""
    value = plain(text)
    return set(re.findall(r"[A-Z]{4,}", value)) | set(re.findall(r"\d{6,}", value))
