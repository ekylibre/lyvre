# Site public lyvre.org

Le site de présentation de Lyvre vit dans `site/` (Astro, statique) et se construit à partir des mêmes
sources que le README : rien n'y est ressaisi.

| Source | Sert à |
|---|---|
| `data/changelog.yml` (versions publiées, champ `text`) | version du pied de page, page « Nouveautés », une page par version, flux RSS, `version.json` |
| `data/features.yml` | « En bref », « Pour qui », « Aperçu », « Fonctionnalités », « Intégrations » (site et README) |
| `doc/images/*.png` | captures (converties en WebP à la construction) |
| `frontend/src/app/lyvre.css`, `frontend/src/assets/lyvre-*.svg` | couleurs de la charte (thèmes clair et sombre), logos, favicon |

La partie `next` du changelog et les précisions `tech` ne sont jamais publiées.

## Faire évoluer le contenu

| Je veux… | Je fais… |
|---|---|
| annoncer une nouveauté | une entrée sous `next` dans `data/changelog.yml`, puis `python scripts/release.py publish` |
| ajouter ou modifier une fonctionnalité, un profil, une intégration | `data/features.yml`, puis `python scripts/release.py build` (README) |
| refaire les captures | `make captures` (base jetable aux données fabriquées), puis relire les images |
| interdire un nom dans les textes publics | `python scripts/release.py denylist "terme"` (seule l'empreinte est enregistrée) |

`python scripts/release.py check`, lancé par `pytest`, échoue si :

- le README n'a pas été régénéré (sections entre `<!-- nom -->` et `<!-- /nom -->`) ;
- une fonctionnalité cite un domaine inconnu, une version non publiée ou une capture absente ;
- un texte public (README, `features.yml`, versions publiées) contient un terme de la liste noire.

**Liste noire.** `data/public_denylist.sha256` contient des empreintes SHA-256 de termes normalisés (minuscules,
sans accents) : le dépôt est public, les noms eux-mêmes n'y figurent pas. Un fichier local `.public-denylist`
(ignoré par Git, un terme par ligne) est contrôlé en plus.

Le site est ensuite reconstruit par Dokploy à chaque push sur `main`.

## Construire et tester

```bash
make site          # npm ci, préparation (site/scripts/prebuild.mjs) et construction dans site/dist
make site-dev      # serveur de développement (http://localhost:4321)
make site-check    # types, construction, parcours et accessibilité (Playwright + axe, ordinateur et mobile)
```

Première fois : `npx --prefix site playwright install chromium`.

`site/scripts/prebuild.mjs` copie les sources dans `site/src/` (copies ignorées par Git), dérive
`tokens.css` de la charte de l'application et dessine l'image de partage `og.png`.

## Formulaire de contact

`site/contact/contact.py` (Flask, `gunicorn contact:app`) reçoit le formulaire sur `POST /api/contact`, relayé par
le nginx du site, et répond toujours par une redirection (`/contact/merci/` ou `/contact/?erreur=…`).

- Champs contrôlés (nom, e-mail, profil d'une liste fermée, message de 10 à 5 000 caractères, consentement).
- Robots : champ piège ou envoi moins de 3 s après l'ouverture → « merci » sans envoi.
- Débit : 5 messages par IP sur 10 minutes, 60 en tout par heure.
- Brevo : e-mail transactionnel à `CONTACT_TO` avec « Répondre » vers l'expéditeur, puis contact ajouté à la liste
  `BREVO_CONTACT_LIST_ID` si elle est renseignée. Rien n'est écrit sur disque ; les journaux ne contiennent ni le
  message ni l'adresse.

Tests : `.venv/bin/python -m pytest site/contact`.

## Déploiement (Dokploy)

`docker-compose.site.yml` : deux services construits depuis le dépôt.

| Service | Image | Rôle |
|---|---|---|
| `site` | `docker/site.Dockerfile` (Node → nginx) | site statique, `www` → apex en 301, CSP stricte, relais de `/api/contact` seulement |
| `contact` | `docker/contact.Dockerfile` (Python) | formulaire de contact, non exposé |

Chaque image a ses propres exclusions (`docker/*.Dockerfile.dockerignore`, en liste blanche) : la
`.dockerignore` racine exclut `doc/`, dont le site a besoin.

Dans Dokploy :

1. Service **Compose**, dépôt `ekylibre/lyvre`, branche `main`, fichier `docker-compose.site.yml`,
   déploiement automatique à chaque push.
2. Domaines `lyvre.org` et `www.lyvre.org` → service `site`, port 80, HTTPS Let's Encrypt.
3. Variables : `BREVO_API_KEY` (clé avec l'adresse IP du serveur autorisée dans Brevo), `CONTACT_TO`,
   `CONTACT_FROM` (expéditeur validé dans Brevo), `BREVO_CONTACT_LIST_ID` (facultative). Facultatives :
   `PUBLIC_SITE_URL`, `PUBLIC_DEMO_URL`.
4. DNS (Gandi) : enregistrements A de `lyvre.org` et de `www` vers l'adresse du serveur Dokploy, sans
   redirection web Gandi sur `www`.

Service en place : projet Dokploy « Lyvre », service Compose `site`, serveur `76.13.49.203`. La clé Brevo
est restreinte par adresse IP : celle du serveur doit être autorisée dans Brevo (Sécurité › IP autorisées).
Avant la mise à jour du DNS, le site se contrôle par l'adresse du serveur :
`curl -sk --resolve lyvre.org:443:76.13.49.203 https://lyvre.org/version.json`.

Essai local (Docker) :

```bash
docker compose -f docker-compose.site.yml -f docker-compose.site.local.yml up --build   # http://localhost:8080
```

Après déploiement : `curl -I https://www.lyvre.org` (301 vers `https://lyvre.org/`),
`curl -s https://lyvre.org/version.json`, et un message envoyé depuis la page Contact.

## Démo en ligne (demo.lyvre.org)

`docker-compose.demo.yml` : un service `demo`, même image que l'application, en mode démonstration
(`LYVRE_DEMO=1`, `app/demo.py`).

- **Données** : `scripts/demo_seed.py`, lancé par `docker/entrypoint.sh` après les migrations. Quatre
  structures fictives, créées comme dans l'application (migrations, plan comptable, règles) puis remplies par
  l'API : « Les Jardins Partagés » (association, adhérents HelloAsso, écritures, relevé à rapprocher), « SCI des
  Tilleuls » (factures, devis, bail, quittance, abonnements), « Atelier Bois & Cie » (société, factures),
  « EARL des Pins (fictive) » (jeu d'essai agricole `tests/fixtures/agri`, copié dans l'image).
- **Compte** : `DEMO_EMAIL` / `DEMO_PASSWORD` (défaut `demo@lyvre.org` / `demo-lyvre`, les valeurs de la page
  `/demo/` du site), administrateur de chaque instance mais pas administrateur global. L'administrateur de
  `seed_meta.py` reçoit un mot de passe aléatoire et est désactivé.
- **Remise à zéro** : à chaque démarrage (`DEMO_RESET_ON_START=1`) et chaque nuit à `DEMO_RESET_AT` (heure UTC,
  défaut `02:00`) : le conteneur arrête son processus principal, `restart: unless-stopped` le relance. Pas de
  volume. Le dossier d'instance n'est vidé que s'il est vide ou porte le marqueur `.lyvre-demo` : posé par
  erreur sur une vraie instance, `LYVRE_DEMO=1` arrête le conteneur sans rien effacer.
- **Garde** : aucun appel sortant (`requests` limité à `DEMO_ALLOWED_HOSTS`, vide par défaut ; SMTP coupé) ;
  refus (403 `demo`) des écritures sur les instances, les utilisateurs, les mots de passe, les réglages
  d'intégration, les clés d'API, les paramètres réglementaires, la restauration Ekylibre, l'assistant, l'agent
  et le serveur MCP ; pièces limitées à `DEMO_MAX_UPLOAD_MB` (10 Mo). Bandeau en tête de chaque page,
  identifiants sur la page de connexion.

Dans Dokploy : service **Compose** `demo` (projet « Lyvre »), dépôt `ekylibre/lyvre`, fichier
`docker-compose.demo.yml` ; domaine `demo.lyvre.org` → service `demo`, port 5000, HTTPS ; variable
`SECRET_KEY` (obligatoire). Essai local :

```bash
docker compose -f docker-compose.demo.yml -f docker-compose.demo.local.yml up --build   # http://localhost:5001
```

Tests : `.venv/bin/python -m pytest tests/test_demo.py`.
