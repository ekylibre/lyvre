"""Création d'adhésions HelloAsso via l'API v5 (paiement manuel "Other").

Endpoint utilisé :
  POST /v5/organizations/{orgSlug}/forms/{formType}/{formSlug}/items/manual-payment

Le payload exact peut nécessiter des ajustements selon la version de l'API ;
la fonction renvoie tout retour d'erreur HTTP au caller.
"""
from datetime import datetime

from app.services.helloasso_client import from_app_config


def _split_name(full_name):
    parts = (full_name or "").strip().split(None, 1)
    first = parts[0] if parts else ""
    last = parts[1] if len(parts) > 1 else ""
    return first, last


def build_manual_payment_payload(*, entity_name, entity_email,
                                 amount_cents, payment_date,
                                 item_name="Adhésion (saisie manuelle)"):
    first, last = _split_name(entity_name)
    iso_date = (
        payment_date.isoformat() if isinstance(payment_date, datetime)
        else str(payment_date)
    )
    user_block = {
        "firstName": first,
        "lastName": last,
        "email": entity_email,
    }
    return {
        "totalAmount": int(amount_cents),
        "paymentMean": "Other",
        "paymentDate": iso_date,
        "user": user_block,
        "items": [
            {
                "name": item_name,
                "amount": int(amount_cents),
                "type": "Membership",
                "user": user_block,
            }
        ],
    }


def post_manual_payment(client, form_type, form_slug, payload):
    """Envoie le paiement manuel à HelloAsso. Renvoie le JSON de réponse.

    Lève l'exception requests.HTTPError si l'API rejette la requête.
    """
    import requests
    url = f"{client.api_base}{client.org_path(f'/forms/{form_type}/{form_slug}/items/manual-payment')}"
    resp = requests.post(
        url,
        json=payload,
        headers={
            "Authorization": f"Bearer {client.token}",
            "Content-Type": "application/json",
        },
        timeout=30,
    )
    resp.raise_for_status()
    try:
        return resp.json()
    except ValueError:
        return {"raw": resp.text}


def create_membership_for_entity(*, entity, amount_cents, payment_date,
                                 form_type="Membership", form_slug="adhesion",
                                 client=None):
    """Crée une adhésion HelloAsso pour `entity` à la date donnée.

    Renvoie (success: bool, response_or_error: any).
    """
    if not entity.email:
        return False, "Tiers sans email — impossible d'identifier le payeur."
    if client is None:
        client = from_app_config()
    payload = build_manual_payment_payload(
        entity_name=entity.name,
        entity_email=entity.email,
        amount_cents=amount_cents,
        payment_date=payment_date,
    )
    try:
        data = post_manual_payment(client, form_type, form_slug, payload)
        return True, data
    except Exception as e:
        return False, str(e)
