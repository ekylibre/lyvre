# Site public lyvre.org

Le site de présentation de Lyvre vit dans `site/` (Astro, statique) et se construit à partir des mêmes
sources que le README : rien n'y est ressaisi.

| Source | Sert à |
|---|---|
| `data/changelog.yml` (versions publiées, champ `text`) | version du pied de page, page « Nouveautés », une page par version, flux RSS, `version.json` |
| `data/features.yml` | « En bref », « Pour qui », « Aperçu », « Fonctionnalités » (modules, sous-parties, captures), « Intégrations » (site et README) |
| `frontend/src/features/about/comparison.ts`, `competitors.ts`, `openSourceVendors.ts` | page « Comparatif » (mêmes données que la page À propos de l'application) |
| `doc/images/*.png` | captures (converties en WebP à la construction) |
| `frontend/src/app/lyvre.css`, `frontend/src/assets/lyvre-*.svg` | couleurs de la charte (thèmes clair et sombre), logos, favicon |

La partie `next` du changelog et les précisions `tech` ne sont jamais publiées.

## Pages

| Page | Contenu |
|---|---|
| `/` | accueil : en bref, pour qui (une capture par type de structure), aperçu, nouveautés récentes |
| `/fonctionnalites/` | un module par domaine de `features.yml` : phrase d'introduction (`intro`), grande capture puis captures secondaires (`captures`), fonctionnalités en liste, regroupées en sous-parties (`group`, avec la capture de leurs fonctionnalités) ; filtre « Je tiens les comptes de… » (`?pour=asso\|sci\|agri\|societe`), index des modules ; « Ce que Lyvre ne fait pas encore » |
| `/comparatif/` | points forts, limites, deux tableaux (logiciels des comparatifs, logiciels open source) dont chaque case renvoie à sa source |
| `/nouveautes/` | versions repliées, une ligne « version — titre — date » avec le nombre de changements et les actions requises ; une page dépliée par version (`/nouveautes/<version>/`), flux RSS |
| `/installer/`, `/demo/`, `/contact/`, `/mentions-legales/`, `/donnees-personnelles/` | pages de texte, formulaire de contact |

Une fonctionnalité dont tout le module concerne la même structure n'affiche pas son étiquette (elle est en tête du
module) ; une fonctionnalité de la version courante prend l'étiquette « Nouveau », sauf si tout le module est nouveau
(mention en tête du module). Une fonctionnalité ne peut pas porter l'identifiant d'un module (ancre en double).

## Faire évoluer le contenu

| Je veux… | Je fais… |
|---|---|
| annoncer une nouveauté | une entrée sous `next` dans `data/changelog.yml`, puis `python scripts/release.py publish` |
| ajouter ou modifier une fonctionnalité, un profil, une intégration | `data/features.yml`, puis `python scripts/release.py build` (README) |
| refaire les captures | `make captures` (base jetable aux données fabriquées), puis relire les images |
| changer les écrans d'un module | `captures` du module dans `features.yml` (la première en grand), `capture` d'une fonctionnalité pour sa sous-partie |
| changer le comparatif | `frontend/src/features/about/` (l'application et le site le lisent tous les deux) |
| interdire un nom dans les textes publics | `python scripts/release.py denylist "terme"` (seule l'empreinte est enregistrée) |

`python scripts/release.py check`, lancé par `pytest`, échoue si :

- le README n'a pas été régénéré (sections entre `<!-- nom -->` et `<!-- /nom -->`) ;
- une fonctionnalité cite un domaine inconnu, une version non publiée ou une capture absente, ou porte l'identifiant
  d'un module ;
- une capture de module est absente de `doc/images/` ou n'a pas de texte alternatif ;
- un texte public (README, `features.yml`, versions publiées) contient un terme de la liste noire.

**Liste noire.** `data/public_denylist.sha256` contient des empreintes SHA-256 de termes normalisés (minuscules,
sans accents) : le dépôt est public, les noms eux-mêmes n'y figurent pas. Un fichier local `.public-denylist`
(ignoré par Git, un terme par ligne) est contrôlé en plus.

Le site est ensuite reconstruit par Dokploy à chaque push sur `main` (voir « Déploiement » : le webhook a déjà
manqué des push).

## Captures

`make captures` lance `scripts/e2e_server.py --demo` (base jetable des tests de bout en bout) puis
`scripts/readme_screenshots.mjs`. En mode `--demo` seulement, `scripts/e2e_demo.py` donne aux structures et à
l'utilisateur des noms vraisemblables (« SCI des Tilleuls », « SCI du Moulin », « EARL des Pins »,
`demo@lyvre.org`, sans marque réelle) ; les parcours E2E gardent leurs noms.

Le script crée par l'API les données de chaque écran : factures, devis, bail et abonnements de la SCI ; pour
l'exploitation du jeu d'essai agricole (`tests/fixtures/agri/A_earl_porcs_rs`) : exercice rouvert (l'import FEC le
clôt à titre provisoire), régime de TVA agricole et CA12A annuelle, lignes d'inventaire, deux associés exploitants
et leurs assiettes MSA passées, activités « Porcs charcutiers » et « Maïs grain » (productions Lexicon) avec la
ventilation des comptes, dossiers d'aide repris des écritures, clés d'API. Les lignes de TVA importées du FEC n'ont
pas de code : la capture de la TVA montre la liste des déclarations, pas un formulaire calculé.

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

Service en place : projet Dokploy « Lyvre », service Compose `site` (composeId `yV9WXDlaSRcV-aA01ETyV`, branche
`main`), serveur `76.13.49.203`, DNS Gandi en place. La clé Brevo est restreinte par adresse IP : celle du serveur
est autorisée dans Brevo (Sécurité › IP autorisées). Pas de liste Brevo pour les contacts du site
(`BREVO_CONTACT_LIST_ID` non renseigné, choix du 18/11/2026).

Essai local (Docker) :

```bash
docker compose -f docker-compose.site.yml -f docker-compose.site.local.yml up --build   # http://localhost:8080
```

**Webhook.** Le 18/11/2026, deux push sur `main` n'ont déclenché aucun déploiement. Après un push, vérifier le
dernier déploiement du service (Dokploy, ou `compose.one` par l'API) et, s'il manque, lancer `compose.deploy`.

**Décalages au chargement.** Les polices du premier affichage sont préchargées (`site/src/layouts/Base.astro`) et,
sur mobile, le menu et le filtre de structures tiennent sur une ligne qui défile : leur hauteur ne dépend pas de la
police chargée. Sans cela, le score Lighthouse de performance tombait à 81 (CLS 0,4).

Après déploiement : `curl -I https://www.lyvre.org` (301 vers `https://lyvre.org/`),
`curl -s https://lyvre.org/version.json`, et un message envoyé depuis la page Contact.

Contrôles en production (sans serveur local) : un fichier de configuration Playwright temporaire qui reprend
`site/playwright.config.ts` avec `baseURL: "https://lyvre.org"` et sans `webServer`, puis
`npx playwright test -c <ce fichier>` ; Lighthouse : `npx lighthouse@12.1.0 https://lyvre.org/fonctionnalites/`.

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

Les propositions « Activer … » (tableau de bord, intégrations, fenêtre « intégration désactivée ») sont masquées
en démonstration.

Dans Dokploy : service **Compose** `demo` (projet « Lyvre », composeId `2Hhm4Ole2KDxrmVmEXiRK`), dépôt
`ekylibre/lyvre`, branche `main`, fichier `docker-compose.demo.yml` ; domaine `demo.lyvre.org` → service `demo`, port 5000, HTTPS ; variable
`SECRET_KEY` (obligatoire). Essai local :

```bash
docker compose -f docker-compose.demo.yml -f docker-compose.demo.local.yml up --build   # http://localhost:5001
```

Tests : `.venv/bin/python -m pytest tests/test_demo.py`.
