"""Client Facebook Graph API (Page).

v1 : nombre d'abonnés de la Page (`followers_count` / `fan_count`). Les insights
(portée, engagement) nécessitent une revue d'app Meta → jalon v2.
"""
import requests

from app.services import external_config

GRAPH_API_VERSION = "v19.0"
GRAPH_BASE = f"https://graph.facebook.com/{GRAPH_API_VERSION}"
TIMEOUT = 20


class FacebookConfigError(Exception):
    pass


def from_app_config():
    page_id = external_config.get("facebook", "page_id")
    page_token = external_config.get("facebook", "page_token")
    if not page_id or not page_token:
        raise FacebookConfigError(
            "Facebook non configuré (page_id / page_token manquants)."
        )
    return FacebookClient(page_id, page_token)


class FacebookClient:
    def __init__(self, page_id, page_token):
        self.page_id = str(page_id).strip()
        self.page_token = page_token.strip()

    def fetch_page_followers(self):
        """Retourne le nombre d'abonnés (followers_count, fallback fan_count)."""
        url = f"{GRAPH_BASE}/{self.page_id}"
        params = {
            "fields": "followers_count,fan_count",
            "access_token": self.page_token,
        }
        resp = requests.get(url, params=params, timeout=TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        if data.get("followers_count") is not None:
            return int(data["followers_count"])
        if data.get("fan_count") is not None:
            return int(data["fan_count"])
        raise FacebookConfigError(
            "Réponse Facebook sans followers_count/fan_count "
            "(permissions insuffisantes ?)."
        )
