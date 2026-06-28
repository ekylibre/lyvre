"""Client Google Analytics 4 (Data API).

Lecture seule des métriques mensuelles du site via un compte de service.
Import paresseux de `google.analytics.data` pour que l'application démarre même
si la dépendance n'est pas installée ou si GA4 n'est pas configuré.
"""
import json

from app.services import external_config


class GA4ConfigError(Exception):
    pass


# Mapping métrique GA4 → clé du catalogue.
_GA4_METRICS = {
    "activeUsers": "ga4.active_users",
    "sessions": "ga4.sessions",
    "screenPageViews": "ga4.screen_page_views",
    "engagementRate": "ga4.engagement_rate",
    "averageSessionDuration": "ga4.avg_session_duration",
}


def from_app_config():
    property_id = external_config.get("ga4", "property_id")
    credentials_json = external_config.get("ga4", "credentials_json")
    if not property_id or not credentials_json:
        raise GA4ConfigError(
            "GA4 non configuré (property_id / credentials_json manquants)."
        )
    return GA4Client(property_id, credentials_json)


class GA4Client:
    def __init__(self, property_id, credentials_json):
        self.property_id = str(property_id).strip()
        try:
            self._creds_info = json.loads(credentials_json)
        except (TypeError, ValueError) as exc:
            raise GA4ConfigError(f"credentials_json invalide : {exc}")

    def _client(self):
        try:
            from google.analytics.data_v1beta import BetaAnalyticsDataClient
            from google.oauth2 import service_account
        except ImportError as exc:
            raise GA4ConfigError(
                "Dépendance manquante : `pip install google-analytics-data`."
            ) from exc
        creds = service_account.Credentials.from_service_account_info(
            self._creds_info,
            scopes=["https://www.googleapis.com/auth/analytics.readonly"],
        )
        return BetaAnalyticsDataClient(credentials=creds)

    def fetch_monthly(self, year, month):
        """Retourne {metric_key: value} pour le mois (year, month)."""
        from google.analytics.data_v1beta.types import (
            DateRange, Metric, RunReportRequest,
        )
        from datetime import date

        start = date(year, month, 1)
        end = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
        # Borne de fin inclusive pour GA4.
        from datetime import timedelta
        end_incl = end - timedelta(days=1)

        client = self._client()
        request = RunReportRequest(
            property=f"properties/{self.property_id}",
            date_ranges=[DateRange(
                start_date=start.isoformat(), end_date=end_incl.isoformat()
            )],
            metrics=[Metric(name=name) for name in _GA4_METRICS],
        )
        response = client.run_report(request)

        result = {}
        if not response.rows:
            return result
        row = response.rows[0]
        for i, ga4_name in enumerate(_GA4_METRICS):
            key = _GA4_METRICS[ga4_name]
            try:
                result[key] = float(row.metric_values[i].value)
            except (ValueError, IndexError):
                continue
        return result
