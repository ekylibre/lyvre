"""Clés d'API : création, vérification, droits effectifs (lot AK1, claudedocs/design_api_mcp_aiffel.md § 2 D6, § 5).

- Clé `lyv_<public_id 10>_<secret 43>` ; seule l'empreinte SHA-256 du secret est gardée, comparée en temps constant.
- Une clé ne donne jamais plus que le rôle de son utilisateur : écriture impossible pour un expert-comptable,
  et plus rien si l'utilisateur perd son accès à l'instance (contrôle à chaque appel).
"""
from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import string
from dataclasses import dataclass
from datetime import datetime, timedelta

from app.extensions import db
from app.models import ApiKey, InstanceMembership, User
from app.models.api_key import STATE_ACTIVE
from app.models.instance_membership import ROLE_ACCOUNTANT
from app.services import api_domains

PREFIX = "lyv_"
PUBLIC_ALPHABET = string.ascii_lowercase + string.digits
DEFAULT_DAYS, MAX_DAYS = 365, 730
DEFAULT_RATE, DEFAULT_DAILY = 60, 200
MAX_RATE, MAX_DAILY = 600, 5000
NAME_MAX = 80
_DUMMY_HASH = hashlib.sha256(b"lyvre-dummy").hexdigest()


class ApiKeyError(Exception):
    def __init__(self, message, field=None, status=422):
        super().__init__(message)
        self.message, self.field, self.status = message, field, status


@dataclass(frozen=True)
class KeyContext:
    """Clé vérifiée, posée sur `g.api_key` pour la requête (détachée de la session SQLAlchemy)."""
    id: int
    name: str
    instance_id: int
    user_id: int
    reads: frozenset
    writes: frozenset
    rate_per_minute: int
    creations_per_day: int


def _hash(secret: str) -> str:
    return hashlib.sha256(secret.encode()).hexdigest()


def _split(token: str) -> tuple[str, str] | None:
    if not token.startswith(PREFIX):
        return None
    rest = token[len(PREFIX):]
    public_id, sep, secret = rest.partition("_")
    if not sep or len(public_id) != 10 or len(secret) < 32:
        return None
    return public_id, secret


def verify(token: str) -> ApiKey | None:
    """Clé active correspondant au jeton, ou None (durée constante que la clé existe ou non)."""
    from app.access import role_for
    parts = _split(token or "")
    key = db.session.query(ApiKey).filter_by(public_id=parts[0]).first() if parts else None
    expected = key.secret_hash if key is not None else _DUMMY_HASH
    ok = hmac.compare_digest(expected, _hash(parts[1] if parts else ""))
    if key is None or not ok or key.state() != STATE_ACTIVE:
        return None
    user, instance = key.user, key.instance
    if user is None or not user.is_active or instance is None or not instance.is_active:
        return None
    if role_for(user, instance) is None:
        return None
    return key


def effective(key: ApiKey) -> tuple[frozenset, frozenset]:
    """(domaines lus, domaines écrits) au moment de l'appel : domaines de la structure, rôle de l'utilisateur."""
    from app.access import role_for
    available = set(api_domains.available(key.instance.chart))
    reads = frozenset(d for d in key.reads if d in available)
    role = role_for(key.user, key.instance)
    writes = frozenset() if role in (None, ROLE_ACCOUNTANT) else frozenset(
        d for d in key.writes if d in reads and api_domains.writable(d))
    return reads, writes


def context(key: ApiKey) -> KeyContext:
    reads, writes = effective(key)
    return KeyContext(id=key.id, name=key.name, instance_id=key.instance_id, user_id=key.user_id, reads=reads,
                      writes=writes, rate_per_minute=key.rate_per_minute, creations_per_day=key.creations_per_day)


# ------------------------------------------------------------------ administration


def _new_token() -> tuple[str, str, str]:
    while True:
        public_id = "".join(secrets.choice(PUBLIC_ALPHABET) for _ in range(10))
        if db.session.query(ApiKey.id).filter_by(public_id=public_id).first() is None:
            break
    secret = secrets.token_urlsafe(32)
    return public_id, secret, f"{PREFIX}{public_id}_{secret}"


def _member_role(instance, user_id) -> tuple[User, str]:
    from app.access import role_for
    user = db.session.get(User, user_id) if user_id else None
    role = role_for(user, instance) if user is not None and user.is_active else None
    if role is None:
        raise ApiKeyError("Choisissez un membre actif de la structure.", "user_id")
    return user, role


def _int(value, default, low, high, label, field) -> int:
    if value in (None, ""):
        return default
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise ApiKeyError(f"{label} : nombre entier attendu.", field) from None
    if not low <= number <= high:
        raise ApiKeyError(f"{label} : entre {low} et {high}.", field)
    return number


def _domains(instance, role: str, data: dict) -> tuple[list[str], list[str]]:
    available = api_domains.available(instance.chart)
    reads_in, writes_in = data.get("read_domains") or [], data.get("write_domains") or []
    if not isinstance(reads_in, list) or not isinstance(writes_in, list):
        raise ApiKeyError("Domaines : listes attendues.", "read_domains")
    unknown = [d for d in [*reads_in, *writes_in] if d not in available]
    if unknown:
        raise ApiKeyError(f"Domaine inconnu pour cette structure : {', '.join(map(str, unknown))}.", "read_domains")
    writes = [d for d in available if d in writes_in]
    not_writable = [api_domains.label(d) for d in writes if not api_domains.writable(d)]
    if not_writable:
        raise ApiKeyError(f"Écriture non proposée pour : {', '.join(not_writable)}.", "write_domains")
    if writes and role == ROLE_ACCOUNTANT:
        raise ApiKeyError("Un expert-comptable consulte sans modifier : une clé rattachée à lui ne peut pas écrire.",
                        "write_domains")
    reads = [d for d in available if d in reads_in or d in writes]   # l'écriture suppose la lecture
    if not reads:
        raise ApiKeyError("Cochez au moins un domaine.", "read_domains")
    return reads, writes


def _expiry(value, now: datetime) -> datetime:
    if value in (None, ""):
        return now + timedelta(days=DEFAULT_DAYS)
    try:
        day = datetime.fromisoformat(str(value)[:10])
    except ValueError:
        raise ApiKeyError("Date d'expiration attendue au format AAAA-MM-JJ.", "expires_on") from None
    end = day.replace(hour=23, minute=59, second=59)
    if end <= now:
        raise ApiKeyError("La date d'expiration doit être future.", "expires_on")
    if end > now + timedelta(days=MAX_DAYS + 1):
        raise ApiKeyError("Expiration à deux ans au plus.", "expires_on")
    return end


def _name(value) -> str:
    name = str(value or "").strip()
    if not name:
        raise ApiKeyError("Donnez un nom à la clé (son usage, par exemple « Aiffel — saisie terrain »).", "name")
    return name[:NAME_MAX]


def create(instance, data: dict, by_user) -> tuple[ApiKey, str]:
    """Nouvelle clé (commit) et le jeton complet, montré une seule fois."""
    now = datetime.utcnow()
    name = _name(data.get("name"))
    user, role = _member_role(instance, data.get("user_id") or by_user.id)
    reads, writes = _domains(instance, role, data)
    public_id, secret, token = _new_token()
    key = ApiKey(public_id=public_id, secret_hash=_hash(secret), instance_id=instance.id, user_id=user.id, name=name,
                 read_domains=json.dumps(reads), write_domains=json.dumps(writes),
                 rate_per_minute=_int(data.get("rate_per_minute"), DEFAULT_RATE, 1, MAX_RATE, "Requêtes par minute",
                                      "rate_per_minute"),
                 creations_per_day=_int(data.get("creations_per_day"), DEFAULT_DAILY, 0, MAX_DAILY,
                                        "Créations par jour", "creations_per_day"),
                 expires_at=_expiry(data.get("expires_on"), now), created_at=now, created_by_id=by_user.id)
    db.session.add(key)
    db.session.commit()
    return key, token


def update(key: ApiKey, data: dict) -> ApiKey:
    """Nom, domaines et limites (la clé ne change pas). Une clé révoquée ne se modifie plus."""
    if key.revoked_at is not None:
        raise ApiKeyError("Clé révoquée : créez-en une nouvelle.", status=409)
    from app.access import role_for
    if "name" in data:
        key.name = _name(data.get("name"))
    if "read_domains" in data or "write_domains" in data:
        merged = {"read_domains": data.get("read_domains", key.reads), "write_domains": data.get("write_domains", key.writes)}
        reads, writes = _domains(key.instance, role_for(key.user, key.instance) or ROLE_ACCOUNTANT, merged)
        key.read_domains, key.write_domains = json.dumps(reads), json.dumps(writes)
    if "rate_per_minute" in data:
        key.rate_per_minute = _int(data["rate_per_minute"], DEFAULT_RATE, 1, MAX_RATE, "Requêtes par minute",
                                   "rate_per_minute")
    if "creations_per_day" in data:
        key.creations_per_day = _int(data["creations_per_day"], DEFAULT_DAILY, 0, MAX_DAILY, "Créations par jour",
                                     "creations_per_day")
    if "expires_on" in data:
        key.expires_at = _expiry(data["expires_on"], datetime.utcnow())
    db.session.commit()
    return key


def revoke(key: ApiKey, by_user) -> ApiKey:
    if key.revoked_at is None:
        key.revoked_at, key.revoked_by_id = datetime.utcnow(), by_user.id
        db.session.commit()
    return key


def for_instance(instance) -> list[ApiKey]:
    return db.session.query(ApiKey).filter_by(instance_id=instance.id).order_by(ApiKey.created_at.desc()).all()


def for_user(user, instance) -> list[ApiKey]:
    return (db.session.query(ApiKey).filter_by(instance_id=instance.id, user_id=user.id)
            .order_by(ApiKey.created_at.desc()).all())


def payload(key: ApiKey, me_id: int | None = None) -> dict:
    user = key.user
    return {
        "id": key.id, "name": key.name, "prefix": key.prefix, "state": key.state(),
        "user": {"id": user.id, "email": user.email, "full_name": user.full_name, "is_me": user.id == me_id},
        "read_domains": key.reads, "write_domains": key.writes,
        "rate_per_minute": key.rate_per_minute, "creations_per_day": key.creations_per_day,
        "created_at": key.created_at.isoformat(), "expires_at": key.expires_at.isoformat(),
        "revoked_at": key.revoked_at.isoformat() if key.revoked_at else None,
        "last_used_at": key.last_used_at.isoformat() if key.last_used_at else None,
    }


def member_options(instance) -> list[dict]:
    """Membres actifs de la structure, avec leur rôle (pour rattacher une clé)."""
    from app.access import role_for
    ids = {m.user_id for m in db.session.query(InstanceMembership).filter_by(instance_id=instance.id)}
    users = db.session.query(User).filter(db.or_(User.is_admin.is_(True), User.id.in_(list(ids) or [0]))) \
        .filter(User.is_active.is_(True)).order_by(User.email)
    return [{"id": u.id, "email": u.email, "full_name": u.full_name, "role": role_for(u, instance)} for u in users]


def mcp_url() -> str | None:
    from flask import current_app
    base = (current_app.config.get("APP_BASE_URL") or "").rstrip("/")
    return f"{base}/mcp" if base else None


def api_url() -> str | None:
    from flask import current_app
    base = (current_app.config.get("APP_BASE_URL") or "").rstrip("/")
    return f"{base}/api/v1" if base else None
