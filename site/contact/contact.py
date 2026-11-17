"""Formulaire de contact de lyvre.org (lot L4) : POST /api/contact, relayé par le nginx du site.
Servi par `gunicorn contact:app` (docker/contact.Dockerfile).

Envoi classique d'un formulaire HTML (le site est statique, sans script en ligne) : la réponse est
toujours une redirection, vers /contact/merci/ ou vers /contact/?erreur=<code>.

- Validation stricte (nom, e-mail, profil d'une liste fermée, message, consentement).
- Robots : champ piège rempli ou formulaire envoyé moins de 3 s après son ouverture → « merci », sans envoi.
- Débit : 5 envois par IP sur 10 minutes, 60 en tout par heure (mémoire du processus : un seul worker).
- Brevo : e-mail transactionnel à CONTACT_TO avec « Répondre » vers l'expéditeur, puis contact ajouté à la
  liste BREVO_CONTACT_LIST_ID (facultative). Rien n'est écrit sur disque ; les journaux ne contiennent ni
  le message ni l'adresse.

Variables : BREVO_API_KEY, CONTACT_TO, CONTACT_FROM, BREVO_CONTACT_LIST_ID (facultative),
CONTACT_PROXY_HOPS (proxys devant le service, 2 par défaut : Traefik puis nginx).
"""
from __future__ import annotations

import logging
import os
import re
import threading
import time
from collections import defaultdict, deque

import requests
from flask import Flask, redirect, request

API_BASE = "https://api.brevo.com/v3"
PROFILES = {
    "asso": "Association",
    "sci": "SCI",
    "agri": "Exploitation agricole",
    "societe": "Société",
    "expert": "Cabinet d'expertise comptable",
    "dev": "Développement ou hébergement",
    "autre": "Autre",
}
EMAIL = re.compile(r"^[^@\s<>\"']{1,64}@[^@\s<>\"']+\.[^@\s<>\"']{2,}$")
MIN_DELAY_MS = 3000
PER_IP = (5, 600)
GLOBAL = (60, 3600)
THANKS = "/contact/merci/"

log = logging.getLogger("lyvre.contact")


class RateLimiter:
    def __init__(self, per_ip=PER_IP, overall=GLOBAL, clock=time.monotonic):
        self.per_ip, self.overall, self.clock = per_ip, overall, clock
        self.hits: dict[str, deque] = defaultdict(deque)
        self.all: deque = deque()
        self.lock = threading.Lock()

    def allow(self, ip: str) -> bool:
        now = self.clock()
        with self.lock:
            mine = self.hits[ip]
            for queue, (_, window) in ((mine, self.per_ip), (self.all, self.overall)):
                while queue and now - queue[0] > window:
                    queue.popleft()
            if len(mine) >= self.per_ip[0] or len(self.all) >= self.overall[0]:
                return False
            mine.append(now)
            self.all.append(now)
            if len(self.hits) > 10_000:  # mémoire bornée
                for key in [k for k, q in self.hits.items() if not q]:
                    del self.hits[key]
            return True


class Brevo:
    def __init__(self, api_key: str, timeout: float = 15):
        self.headers = {"api-key": api_key, "accept": "application/json", "content-type": "application/json"}
        self.timeout = timeout

    def post(self, path: str, payload: dict) -> requests.Response:
        return requests.post(f"{API_BASE}{path}", json=payload, headers=self.headers, timeout=self.timeout)


def create_app(config: dict | None = None, brevo: Brevo | None = None, limiter: RateLimiter | None = None) -> Flask:
    app = Flask(__name__)
    app.config.update(
        BREVO_API_KEY=os.environ.get("BREVO_API_KEY", ""),
        CONTACT_TO=os.environ.get("CONTACT_TO", "contact@lyvre.org"),
        CONTACT_FROM=os.environ.get("CONTACT_FROM", "site@lyvre.org"),
        BREVO_CONTACT_LIST_ID=os.environ.get("BREVO_CONTACT_LIST_ID", ""),
        CONTACT_PROXY_HOPS=int(os.environ.get("CONTACT_PROXY_HOPS", "2")),
        MAX_CONTENT_LENGTH=32 * 1024,
    )
    app.config.update(config or {})
    limiter = limiter or RateLimiter()

    def client() -> Brevo | None:
        if brevo is not None:
            return brevo
        key = app.config["BREVO_API_KEY"]
        return Brevo(key) if key else None

    def fail(code: str):
        return redirect(f"/contact/?erreur={code}#formulaire", code=303)

    @app.get("/api/contact/sante")
    def health():
        return {"ok": True, "brevo": bool(app.config["BREVO_API_KEY"] or brevo)}

    @app.post("/api/contact")
    def contact():
        form = request.form
        if form.get("website"):
            log.info("contact ignoré : champ piège rempli")
            return redirect(THANKS, code=303)
        started = form.get("started_at", "")
        if started.isdigit() and time.time() * 1000 - int(started) < MIN_DELAY_MS:
            log.info("contact ignoré : envoyé trop vite")
            return redirect(THANKS, code=303)

        name = " ".join(form.get("name", "").split())
        email = form.get("email", "").strip()
        profile = form.get("profile", "autre")
        message = form.get("message", "").strip()
        if not (1 <= len(name) <= 120 and len(email) <= 200 and EMAIL.match(email) and profile in PROFILES
                and 10 <= len(message) <= 5000 and form.get("consent") == "on"):
            return fail("champs")

        if not limiter.allow(client_ip(app.config["CONTACT_PROXY_HOPS"])):
            log.warning("contact refusé : limite de débit")
            return fail("trop")

        api = client()
        if api is None:
            log.error("contact impossible : BREVO_API_KEY absente")
            return fail("service")
        try:
            sent = api.post("/smtp/email", {
                "sender": {"email": app.config["CONTACT_FROM"], "name": "Site lyvre.org"},
                "to": [{"email": app.config["CONTACT_TO"]}],
                "replyTo": {"email": email, "name": name},
                "subject": f"[lyvre.org] {PROFILES[profile]} — {name}",
                "textContent": f"{name} <{email}>\nProfil : {PROFILES[profile]}\n\n{message}\n",
            })
        except requests.RequestException as exc:
            log.error("contact : Brevo injoignable (%s)", type(exc).__name__)
            return fail("service")
        if sent.status_code >= 300:
            log.error("contact : envoi refusé par Brevo (HTTP %s)", sent.status_code)
            return fail("service")

        list_id = app.config["BREVO_CONTACT_LIST_ID"]
        if str(list_id).isdigit():
            try:
                added = api.post("/contacts", {"email": email, "listIds": [int(list_id)], "updateEnabled": True})
                if added.status_code >= 300:
                    log.warning("contact : ajout à la liste refusé par Brevo (HTTP %s)", added.status_code)
            except requests.RequestException as exc:
                log.warning("contact : ajout à la liste impossible (%s)", type(exc).__name__)
        log.info("contact envoyé (%s)", profile)
        return redirect(THANKS, code=303)

    @app.errorhandler(413)
    def too_large(_):
        return fail("champs")

    return app


def client_ip(hops: int) -> str:
    """IP du visiteur : l'entrée de X-Forwarded-For posée par le premier proxy de confiance (Traefik)."""
    chain = [p.strip() for p in request.headers.get("X-Forwarded-For", "").split(",") if p.strip()]
    if len(chain) >= hops:
        return chain[-hops]
    return chain[0] if chain else (request.remote_addr or "?")


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
app = create_app()
