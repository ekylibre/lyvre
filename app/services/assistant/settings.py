"""Réglages de l'intégration « Assistant Claude » (lot AG9b, AGD26).

- Clé : `ANTHROPIC_API_KEY` du `.env` du serveur si elle existe (prioritaire, intégration active, réglage en
  lecture seule), sinon la clé saisie dans l'intégration de l'instance.
- Modèle : `claude-haiku-5-5` par défaut, ou `claude-sonnet-5-5` / `claude-opus-5-5` (Q-C2).
- Quota mensuel de tokens (entrée + sortie) par instance ; 0 = sans limite.
"""
from __future__ import annotations

from app.services import external_config

SERVICE = "assistant"
DEFAULT_MODEL = "claude-haiku-5-5"
MODELS = {"claude-haiku-5-5": "Claude Haiku 5.5", "claude-sonnet-5-5": "Claude Sonnet 5.5",
          "claude-opus-5-5": "Claude Opus 5.5"}
FALLBACK_MODELS = {"claude-sonnet-5-5", "claude-opus-5-5"}      # repli serveur en cas de refus (pas Haiku 5.5)
DEFAULT_MONTHLY_TOKENS = 2_000_000
# Prix publics par million de tokens (entrée, sortie), API Claude, 06/11/2026 ; lecture du cache ≈ 10 % de l'entrée,
# écriture ≈ 125 % : estimation affichée comme telle (la facture d'Anthropic fait foi).
PRICES = {"claude-haiku-5-5": (0.10, 0.50), "claude-sonnet-5-5": (2.00, 10.00), "claude-opus-5-5": (4.00, 20.00)}
LEXICON_MCP_URL = "https://lexicon.osfarm.org/mcp"
MCP_BETA = "mcp-client-2025-11-20"
MAX_ACTIVE_PER_INSTANCE = 2


def model() -> str:
    value = (external_config.get(SERVICE, "model") or "").strip()
    return value if value in MODELS else DEFAULT_MODEL


def monthly_tokens() -> int:
    raw = (external_config.get(SERVICE, "monthly_tokens") or "").replace(" ", "")
    try:
        return max(int(raw), 0) if raw else DEFAULT_MONTHLY_TOKENS
    except ValueError:
        return DEFAULT_MONTHLY_TOKENS


def lexicon() -> bool:
    return (external_config.get(SERVICE, "lexicon") or "").strip().lower() in ("oui", "true", "1", "yes", "on")


def cost_usd(model: str, input_tokens: int, output_tokens: int, cache_read: int = 0, cache_write: int = 0) -> float:
    price_in, price_out = PRICES.get(model, PRICES[DEFAULT_MODEL])
    return round((input_tokens * price_in + output_tokens * price_out + cache_read * price_in * 0.1
                  + cache_write * price_in * 1.25) / 1_000_000, 4)


def available() -> bool:
    return external_config.is_available(SERVICE)


def client(timeout: float | None = None):
    import anthropic
    key = external_config.get(SERVICE, "api_key")
    if not key:
        raise RuntimeError("Clé de l'API Claude absente (Configuration › Intégrations).")
    kwargs = {"api_key": key}
    if timeout is not None:
        kwargs["timeout"] = timeout
    return anthropic.Anthropic(**kwargs)


def describe_error(exc: BaseException) -> str:
    """Message en français pour une erreur de l'API Claude."""
    import anthropic
    if isinstance(exc, anthropic.AuthenticationError):
        return "Clé de l'API Claude refusée."
    if isinstance(exc, anthropic.PermissionDeniedError):
        return "La clé de l'API Claude n'a pas accès à ce modèle."
    if isinstance(exc, anthropic.NotFoundError):
        return "Modèle inconnu de l'API Claude : vérifiez le réglage « Modèle »."
    if isinstance(exc, anthropic.RateLimitError):
        return "API Claude saturée (limite de débit) : réessayez dans un moment."
    if isinstance(exc, anthropic.APITimeoutError):
        return "L'API Claude ne répond pas (délai dépassé)."
    if isinstance(exc, anthropic.APIConnectionError):
        return "API Claude injoignable (réseau)."
    if isinstance(exc, anthropic.APIStatusError):
        return f"Erreur de l'API Claude ({exc.status_code})."
    if isinstance(exc, RuntimeError):
        return str(exc)
    return f"Erreur inattendue : {type(exc).__name__}."
