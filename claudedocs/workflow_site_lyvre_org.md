# Plan d'implémentation — site lyvre.org, README, mise à jour automatique

Source : `claudedocs/besoins_site_lyvre_org.md` (SP-1…9, DM-1…3, RM-1…5, MJ-1…5). 17/11/2026.
Modèle technique : `fourmy/apps/site` (Astro 7, nginx, CSP stricte) et `fourmy/docker/site.*`.
Étape suivante : `/sc:implement`, lot par lot, dans l'ordre du §2.

## État (18/11/2026, `main`, site et démo en ligne)

| Lot | État |
|---|---|
| L1 Source et génération | ✅ `data/features.yml`, `scripts/public_content.py`, sections du README, liste noire par empreintes, `tests/test_public_content.py` |
| L2 README | ✅ réécrit (agricole, société, liens site et démo), sections générées |
| L3 Site Astro | ✅ `site/` : 10 pages (dont Comparatif), une page par version, RSS, `version.json`, thème sombre ; 38 tests Playwright + axe (ordinateur, mobile) |
| L4 Contact | ✅ `site/contact/contact.py` + 15 tests (Brevo simulé) ; envoi réel vérifié le 18/11 |
| L5 Image et Dokploy | ✅ Service Compose `site` du projet Dokploy « Lyvre », branche `main` ; DNS en place (`lyvre.org`, `www` → 301, `demo`) ; webhook GitHub intermittent (doc/site.md › Déploiement) |
| L6 Captures | ✅ `make captures` : 20 captures, noms vraisemblables en mode `--demo`, jeu d'essai agricole complété par l'API (inventaire, TVA, MSA, marges, aides, clés d'API) |
| L7 Démo | ✅ code prêt (18/11) : `app/demo.py` (garde), `scripts/demo_seed.py` (4 structures par l'API), remise à zéro dans `docker/entrypoint.sh`, `docker-compose.demo.yml`, bandeau et identifiants dans la SPA, `tests/test_demo.py` ; en ligne le 18/11 : service Compose Dokploy `demo` (composeId `2Hhm4Ole2KDxrmVmEXiRK`, branche `main`), `demo.lyvre.org` ; connexion, 4 structures et refus 403 vérifiés ; propositions « Activer … » masquées |
| L8 Recette | ✅ 18/11 : tout validé, Lighthouse 100 (accueil, fonctionnalités, comparatif, démo, contact) ; pas de liste Brevo pour les contacts (choix du 18/11) |

**Déploiement (17/11/2026).** Projet Dokploy « Lyvre », service Compose `site` (appName `lyvre-site-1aur6o`,
dépôt `ekylibre/lyvre`, branche `site-lyvre-org`, `docker-compose.site.yml`, redéploiement à chaque push),
domaines `lyvre.org` et `www.lyvre.org` (Let's Encrypt). Variables : `BREVO_API_KEY` (celle de `.env`),
`CONTACT_TO=contact@lyvre.org`, `CONTACT_FROM=site@lyvre.org`. Vérifié en interrogeant le serveur
(`curl --resolve lyvre.org:443:76.13.49.203`) : pages en 200, `version.json` (2026.11.5), `www` → apex en 301,
formulaire relayé au service de contact (champ piège → « merci » sans envoi).

**Évolutions après la recette (18/11/2026)**

| Évolution | Détail |
|---|---|
| Fonctionnalités par module | `/fonctionnalites/` refaite : un module par domaine avec ses écrans, filtre par structure (`?pour=`), index des modules, sous-parties du module agricole avec leurs captures ; `features.yml` › `domains` prend `intro` et `captures`, les fonctionnalités `group` |
| Fonctionnalités agricoles | 18 fonctionnalités de la 2026.11.6 (inventaire, biens vivants, DEP et JA, liasse, aides, TVA agricole…) ; README régénéré |
| Comparatif | `/comparatif/` reprend la page À propos de l'application ; critères, points forts et limites sortis dans `frontend/src/features/about/comparison.ts` (une seule source) ; limite TVA corrigée (CA12A agricole) |
| Nouveautés | versions repliées, ligne « version — titre — date », nombre de changements et actions requises |
| Captures | noms sans « E2E » ni marque réelle ; 9 nouveaux écrans (écritures, bilan, TVA, marges, MSA, inventaire, aides, clés d'API) |
| Performance | décalages au chargement supprimés (polices préchargées, menu et filtre sur une ligne sur mobile) : Lighthouse 100 |

**Reste à faire**

| # | Action | Qui |
|---|---|---|
| R1 | ✅ DNS Gandi (18/11) | utilisateur |
| R2 | ✅ Brevo : IP `76.13.49.203` autorisée (18/11, selon l'utilisateur) | utilisateur |
| R3 | ✅ Brevo : expéditeur `site@lyvre.org` ; boîte `contact@lyvre.org` (18/11, selon l'utilisateur) | utilisateur |
| R4 | ✅ Envoi réel depuis la page Contact (18/11), reçu dans `contact@lyvre.org` ; reste la recette L8 | — |
| R5 | ✅ Fusion dans `main` en avance rapide et tag `v2026.11.6` (18/11) ; services Dokploy `site` et `demo` passés sur `main` | — |
| R7 | 🟡 Démo en ligne (18/11) ; remise à zéro de la nuit (02:00 UTC) à constater le 19/11 | — |
| R6 | 🟡 Version 2026.11.6 publiée (18/11, tag `v2026.11.6`) ; éditeur Ekylibre SAS, mentions alignées sur fourmy.org ; reste : termes de la liste noire | utilisateur |
| R8 | Webhook GitHub → Dokploy à vérifier (push du 18/11 sans déploiement, deux fois) | utilisateur |
| R9 | TVA calculée sur le jeu d'essai agricole : les lignes de TVA importées du FEC n'ont pas de code ; à coder dans le jeu d'essai pour une capture du formulaire CA12A | facultatif |

**L7, ce qui a changé depuis le plan.** Le jeu de démonstration de `e2e_server.py` crée les bases par
`create_all`, sans migrations Alembic : l'image de production les migre au démarrage (`flask db upgrade`,
`scripts/migrate_instances.py`) et échouerait. Les données des captures (ventes, bail, encaissements) sont
créées par appels d'API dans `readme_screenshots.mjs`, pas par le seed. La démo demande donc un seed passant
par l'API ou les services (instances créées comme dans l'application), et un garde `LYVRE_DEMO` sur les écritures
sensibles (mot de passe, utilisateurs, instances, `PUT /integrations/<service>` : une démo publique ne doit pas
permettre de configurer un SMTP). Estimation maintenue : ~1 j.

## 0. Choix techniques retenus pour ce plan

| Sujet | Choix | Raison |
|---|---|---|
| Générateur | Astro (statique), `site/` à la racine, **npm** (comme `frontend/`, pas de pnpm ni de turbo) | Même outillage que fourmy, sans le monorepo |
| Données du site | Lues **à la construction** par `site/src/lib/data.ts` : `data/changelog.yml` (versions publiées, `text` seul) et `data/features.yml` | MJ-5 : rien à recommiter pour le site |
| Données du README | Sections balisées régénérées par `scripts/release.py` (Python), comme le badge actuel | MJ-2, RM-5 ; un seul point d'entrée pour le développeur |
| Images | Les captures restent en PNG dans `doc/images/` ; un `prebuild` du site les copie dans `site/src/assets/captures/`, et `astro:assets` produit le WebP/AVIF | Une seule source d'images pour le README et le site |
| Charte | Jetons de couleur et polices repris de `frontend/src/app/lyvre.css`, logos de `frontend/src/assets/lyvre-*.svg` (copiés au `prebuild`) | Aucune divergence avec l'application |
| Contact | Petit service Python `site/contact/` (Flask, ~120 lignes) dans le compose du site, que nginx relaie sur `/api/contact` → Brevo (création du contact + e-mail transactionnel) | Site statique (CSP `script-src 'self'`), clé Brevo hors de l'image |
| Image Docker | `docker/site.Dockerfile` (Node → nginx) + `docker/site.Dockerfile.dockerignore` propre à elle : la `.dockerignore` racine exclut `doc/` et `README.md`, dont le site a besoin | Comme fourmy |
| Déploiement | `docker-compose.site.yml` (services `site` + `contact`), nouveau service Compose Dokploy branché sur `main`, domaines `lyvre.org` + `www.lyvre.org` | Dokploy construit sur push ; clone superficiel suffisant |
| Liste noire | `data/public_denylist.sha256` : empreintes SHA-256 de termes normalisés (minuscules, sans accents) ; `release.py check` découpe les textes publics en n-grammes (1 à 4 mots) et compare. Un fichier local facultatif `.public-denylist` (ignoré par Git) sert à générer les empreintes | Question ouverte 6 : rien de lisible dans le dépôt public |
| Démo | Même image que l'application, compose `docker-compose.demo.yml`, variable `LYVRE_DEMO=1` : bandeau, intégrations coupées, jeu de données fabriqué, remise à zéro chaque nuit | DM-1…3 sans fork de l'application |

## 1. Prérequis et décisions (lot P, à régler au fil de l'eau)

| # | Sujet | Bloque | Défaut si non tranché |
|---|---|---|---|
| P1 | Publier les 74 entrées de `next` (`release.py publish --title "Comptabilité agricole et sociétés"`) | L2 (contenu du README), L8 (recette) | Publier avant la mise en ligne |
| P2 | DNS Gandi : `lyvre.org` A, `www` A ou CNAME, `demo` A vers le serveur Dokploy ; supprimer la redirection web Gandi de `www` | L5, L7 | — (action manuelle requise) |
| P3 | Éditeur du site (mentions légales, destinataire du contact, liste Brevo) | L3 (pages légales), L4 | Placeholder visible, bloquant pour la mise en ligne |
| P4 | Termes de la liste noire (fichier local `.public-denylist`) | L1 (contenu du fichier d'empreintes) | Mécanisme livré avec une liste vide |
| P5 | Démo : remise à zéro chaque nuit, identifiants publics `demo@lyvre.org` / mot de passe affiché | L7 | Ces valeurs |
| P6 | Nombre de versions dans le README | L1 | 5 |

## 2. Lots, ordre et dépendances

```
L1 Source et génération ──► L2 README ──────────────────────────┐
   │                                                            │
   └──► L3 Site Astro ──► L4 Contact ──► L5 Image + Dokploy ──► L8 Recette
                │                              ▲                ▲
L6 Captures ────┘ (images du site et README)   │                │
L7 Démo (indépendant jusqu'au déploiement) ────┴────────────────┘
```

L1 d'abord. Ensuite L2, L3 et L6 peuvent avancer **en parallèle**. L7 est indépendant jusqu'à
son déploiement. L5 a besoin de L3 et L4, et de P2 pour les domaines.

---

### L1 — Source unique et génération (MJ-1, MJ-2, MJ-3) · ~½ j

1. **`data/features.yml`** : schéma
   `{id, domain, title, text, structures: [asso|sci|agri|societe], capture?, since?, status: available|soon}`
   et ordre des domaines (Comptabilité, Banque, Ventes, Achats, Adhérents, Baux et associés,
   Agricole, TVA et société, Clôture et expert-comptable, Intégrations). Contenu initial tiré des
   sections « Pour qui », « Aperçu » et « Fonctionnalités » du README, complété des entrées
   `agri` et `societe` du changelog.
2. **`app/version.py`** : `load_features()` et `validate_features()` (domaines connus, `since`
   = version publiée existante, `capture` = fichier présent dans `doc/images/`, ids uniques).
   Corriger au passage le message d'erreur des structures (« asso » ou « sci » alors que
   `agri` et `societe` sont acceptés).
3. **`scripts/release.py`** : nouvelles sections balisées dans `expected()`.
   - `<!-- features -->…<!-- /features -->` : les `<details>` par domaine (format actuel).
   - `<!-- news -->…<!-- /news -->` : les N dernières versions (titre, date, 2 ou 3 entrées
     `new`/`action`, plus un lien vers `CHANGELOG.md` et `lyvre.org/nouveautes/`).
   - `<!-- overview -->` (facultatif) : la grille « Aperçu » tirée des fonctionnalités ayant
     une capture marquée `overview: true`.
   - Le texte du message de `build` et la liste `git add` de `publish` incluent `data/features.yml`.
4. **Liste noire** : `data/public_denylist.sha256`, `release.py denylist add <terme>` (écrit
   l'empreinte), contrôle dans `check()` sur tout `text` publié, sur `features.yml` et sur
   le README généré.
5. **Tests** (`tests/test_version.py`) : sections régénérées, fonctionnalité avec une version
   ou une capture inconnue → erreur, terme de la liste noire → erreur (empreinte de test),
   `next` jamais présent dans les sections générées.

**Point de contrôle** : `python scripts/release.py check` et `make test` au vert ; un README
modifié à la main dans une section balisée fait échouer `check`.

### L2 — README à jour (RM-1…5) · ~½ j · après L1 (et P1 pour le contenu)

1. Réécrire les parties manuelles : accroche (exploitation agricole, société), « Pour qui »
   avec un bloc **exploitation agricole** (micro-BA ou réel, MSA, calculettes, plans agricoles)
   et un bloc **société** (CA3, liasse 2050, JEI), « Intégrations », « Démarrage rapide ».
2. Remplacer le paragraphe figé « Nouveautés » et la liste « Fonctionnalités » par les balises
   de L1, puis `release.py build`.
3. Liens : lyvre.org et la démo dans l'en-tête et les badges (badge « site » et « démo »).
4. « Contribuer » : documenter `data/features.yml`, `make captures` et `make site`.

**Point de contrôle** : rendu GitHub vérifié (aperçu local), `release.py check` au vert.

### L3 — Site Astro (SP-1…5, SP-8, SP-9) · ~1,5 j · après L1

1. **Squelette** `site/` : `package.json` (astro, @astrojs/sitemap, @astrojs/rss, sharp, yaml,
   @fontsource des polices de l'application, versions figées), `astro.config.mjs` (repris de
   fourmy : `trailingSlash: "always"`, `assetsInlineLimit: 0`, i18n `fr` sans préfixe),
   `scripts/prebuild.mjs` (copie des captures et des logos), `.gitignore` des copies.
2. **Données** `src/lib/data.ts` : versions publiées (sans `next` ni `tech`), version courante,
   fonctionnalités groupées, structures (libellés repris de `app/version.py`).
   `src/lib/site.ts` : `PUBLIC_SITE_URL`, `PUBLIC_DEMO_URL`, `PUBLIC_REPO_URL`.
3. **Mise en page** `layouts/Base.astro` + `styles/site.css` : en-tête (SP-1, avec les boutons
   Démo et Installer), pied de page (version, licence, liens légaux), thème clair et sombre
   (`prefers-color-scheme`), aucun script en ligne.
4. **Pages** : `index` (SP-2), `fonctionnalites/` (SP-3), `nouveautes/` et
   `nouveautes/[version]/` (SP-4), `nouveautes/rss.xml`, `installer/` (SP-5, contenu de
   `doc/docker.md` et `doc/installation.md`), `demo/` (SP-6), `contact/` et `contact/merci/`
   (formulaire HTML sans JS, `action="/api/contact"`), `mentions-legales/`,
   `donnees-personnelles/` (SP-8), `version.json` (SP-9), `404`, `robots.txt`, image Open Graph.
5. **Tests** `site/tests/` (Playwright + axe, comme fourmy) : chaque page s'affiche sans
   violation axe, la version du pied de page est celle de `changelog.yml`, aucune chaîne
   `tech` ni chemin de code (`app/`, `migration`) sur les pages Nouveautés.
6. **Makefile** : `site-install`, `site` (build), `site-dev`, `site-check` (astro check, build,
   e2e) ; `check` inclut `site-check`.

**Point de contrôle** : `make site-check` au vert ; Lighthouse ≥ 95 en local (`astro preview`).

### L4 — Formulaire de contact Brevo (SP-7) · ~½ j · après L3

1. `site/contact/app.py` (Flask + requests, `requirements.txt` figé) : `POST /api/contact`.
   - Validation : nom, e-mail, profil dans une liste fermée, message ≤ 5 000 caractères,
     consentement obligatoire.
   - Anti-robots : champ piège (envoi ignoré mais réponse « merci »), délai minimal de 3 s
     (horodatage signé HMAC dans un champ caché).
   - Limite de débit en mémoire par IP (`X-Forwarded-For` de nginx), 5 envois sur 10 minutes.
   - Brevo : `POST /v3/contacts` (`updateEnabled`, liste `BREVO_CONTACT_LIST_ID`, attribut
     profil), puis `POST /v3/smtp/email` vers `CONTACT_TO` avec `replyTo` = l'expéditeur.
   - Réponse : redirection 303 vers `/contact/merci/`, ou retour au formulaire avec un code
     d'erreur dans l'adresse. Rien n'est écrit sur disque ; les journaux ne contiennent pas le
     message.
2. Variables (Dokploy uniquement) : `BREVO_API_KEY`, `BREVO_CONTACT_LIST_ID`, `CONTACT_TO`,
   `CONTACT_FROM`, `CONTACT_SECRET`.
3. Tests pytest du service (Brevo simulé) : envoi valide, champ piège, délai trop court,
   11e envoi limité, profil inconnu refusé.

**Point de contrôle** : envoi réel depuis l'environnement local vers une liste de test Brevo
(avec la clé du `.env`, après accord) ; e-mail reçu, « Répondre » vers l'expéditeur.

### L5 — Image, compose et Dokploy (MJ-5, SEO, sécurité) · ~½ j · après L3, L4, P2

1. `docker/site.Dockerfile` : étape `node:22` (`npm ci` dans `site/`, `prebuild`, `astro build`)
   puis `nginx:alpine` ; `ARG PUBLIC_SITE_URL / PUBLIC_DEMO_URL`.
   `docker/site.Dockerfile.dockerignore` : garde `data/`, `doc/images/`, `frontend/src/assets/`,
   `frontend/src/app/lyvre.css`, `site/`, et exclut le reste (`.env*`, `instance/`, `claudedocs/`).
2. `docker/site.nginx.conf` (repris de fourmy) : `www` → apex en 301, CSP stricte et en-têtes,
   cache long sur `/_astro/`, relais de `/api/contact` seulement (`POST`, 32 ko max) vers
   `contact:5000`, tout autre `/api/` → 404.
3. `docker-compose.site.yml` : services `site` (exposé 80) et `contact` (non exposé), images
   sans nom fixe (même règle que `docker-compose.yml`).
4. **Dokploy** (API avec `DOKPLOY_URL` / `DOKPLOY_API_KEY`, **après confirmation**) : projet
   « Lyvre » (ou « Seconde Nature », à confirmer), service Compose `site` sur
   `ekylibre/lyvre` `main`, fichier `docker-compose.site.yml`, déploiement automatique sur push,
   domaines `lyvre.org` et `www.lyvre.org` → `site:80` avec Let's Encrypt, variables du contact.
5. Documentation : `doc/site.md` (construction, déploiement, variables, contact) et une ligne
   dans `doc/README.md`.

**Point de contrôle** : `docker compose -f docker-compose.site.yml up --build` en local ; après
P2 : HTTPS sur `lyvre.org`, 301 depuis `www`, en-têtes vérifiés (`curl -I`).

### L6 — Captures d'écran à la demande (MJ-4) · ~½ j · parallèle à L2/L3

1. `scripts/readme_screenshots.mjs` : liste de captures pilotée par `data/features.yml`
   (`capture`) plus les vues fixes (tableau de bord clair et sombre) ; ajout des vues
   **agricoles** (dossier agricole fabriqué par `e2e_server.py`, `_seed_agri`) et **société**
   (déclaration CA3).
2. `make captures` : démarre `e2e_server.py --demo` sur une base neuve, attend qu'il réponde,
   lance le script, arrête le serveur. Les images vont dans `doc/images/`, le site les reprend
   au `prebuild`.
3. `release.py check` signale toute capture citée et absente (L1) ; il ne lance jamais les
   captures.

**Point de contrôle** : `make captures` régénère toutes les images sans intervention ; aucune
donnée réelle à l'écran (relecture visuelle).

### L7 — Démo en ligne (DM-1…3) · ~1 j · indépendant, déploiement après P2

1. Mode démo dans l'application : `LYVRE_DEMO=1`.
   - Bandeau « Démonstration — données fictives, remises à zéro chaque nuit » (composant de
     `AppShell`, valeur fournie par la session).
   - Intégrations coupées : envoi d'e-mails, Brevo, Qonto, HelloAsso, Documenso, Sirene (simulé),
     assistant. Les écrans de clés sont en lecture seule.
   - Création d'instance et changement de mot de passe refusés.
2. `scripts/demo_seed.py` : réutilise les jeux de données de `e2e_server.py` et `e2e_demo.py`
   (association, SCI, exploitation agricole, société) dans un `INSTANCE_DIR` vide, avec le
   compte de démonstration. Il faut d'abord extraire ces fonctions de `e2e_server.py` dans un
   module commun, sans changer leur comportement pour les tests de bout en bout.
3. Remise à zéro : au démarrage du conteneur (`DEMO_RESET_ON_START`) et chaque nuit (tâche
   planifiée Dokploy qui redémarre le service, ou boucle `cron` dans le conteneur, au choix en
   implémentation).
4. `docker-compose.demo.yml` (même image, volume jetable), service Dokploy `demo`, domaine
   `demo.lyvre.org`.
5. Tests : en mode démo, l'envoi d'e-mail et la création d'instance sont refusés ; le seed est
   idempotent.

**Point de contrôle** : connexion à `demo.lyvre.org` avec les identifiants affichés sur le site ;
la base revient à l'état initial après un redémarrage.

### L8 — Recette (critères du §5 des besoins) · ~¼ j · fin

- [x] `https://lyvre.org` en HTTPS, `www` → apex en 301.
- [x] (2026.11.6, 18/11) Ajout d'une entrée `next`, puis `publish` et push : la version apparaît sur le site (pied
      de page, Nouveautés, RSS, `version.json`) et dans le README.
- [x] Une entrée `next` non publiée n'apparaît nulle part.
- [x] (`release.py check`) `pytest` échoue si le README n'est pas régénéré, ou sur un terme de la liste noire.
- [x] Contact : e-mail reçu ✅ ; champ piège ignoré ✅ (17/11) ; limite de débit couverte par les tests
      unitaires ; pas de liste Brevo pour l'instant (décision du 18/11 ; `BREVO_CONTACT_LIST_ID` à renseigner plus tard).
- [x] « Essayer la démo » ouvre une session sur `demo.lyvre.org`.
- [x] Aucun `tech` ni chemin de code ✅ ; axe sans violation ✅ (30 tests Playwright contre la production,
      ordinateur et mobile) ; Lighthouse 100 partout (18/11 : accueil, fonctionnalités, démo, contact ;
      performance, accessibilité, bonnes pratiques, SEO ; profil mobile).
- Remarques traitées (18/11) : captures refaites avec des noms vraisemblables (`e2e_demo.rename_for_captures`,
      mode `--demo` seulement) ; propositions « Activer » masquées dans la démo (tableau de bord, intégrations).

## 3. Récapitulatif

| Lot | Charge | Dépend de | Parallèle avec |
|---|---|---|---|
| L1 Source et génération | ½ j | — | L6, L7 |
| L2 README | ½ j | L1, P1 | L3, L6 |
| L3 Site Astro | 1½ j | L1 | L2, L6, L7 |
| L4 Contact | ½ j | L3, P3 | L7 |
| L5 Image et Dokploy | ½ j | L3, L4, P2 | L7 |
| L6 Captures | ½ j | — (L1 pour la liste) | L2, L3 |
| L7 Démo | 1 j | P2 (déploiement) | L2 à L6 |
| L8 Recette | ¼ j | tout | — |
| **Total** | **~5 j** | | |

## 4. Risques

| Risque | Parade |
|---|---|
| Une donnée réelle dans le site public (captures, textes, README) | Captures uniquement sur base fabriquée, liste noire contrôlée par `check`, relecture visuelle à L6 |
| La `.dockerignore` racine prive l'image du site de `doc/` | `.dockerignore` propre à l'image (L5.1) |
| Abus du formulaire ou fuite de la clé Brevo | Service dédié, limite de débit, clé dans Dokploy seulement, aucun stockage local |
| Démo détournée (envoi d'e-mails, stockage de fichiers) | Intégrations coupées, taille des pièces limitée, remise à zéro chaque nuit |
| README et site qui divergent | Même source (`features.yml`, `changelog.yml`) ; `check` dans pytest |
| Ressources du serveur Dokploy (une instance de plus pour la démo) | Vérifier la charge avant L7 ; démo mise en veille si besoin |
