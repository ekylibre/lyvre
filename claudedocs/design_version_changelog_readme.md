# Conception — numéro de version, changelog, README

Source : `claudedocs/besoins_version_changelog_readme.md` (V1–V8, V-R1–V-R3, C-R1–C-R6,
R-R1–R-R6). 26/10/2026.

## 0. Découpage

| Lot | Contenu |
|---|---|
| **R1** | Source unique (`data/changelog.yml`), version lue par le serveur et l'interface, script de publication, `CHANGELOG.md` généré |
| **R2** | Page « Nouveautés », pastille dans le menu, étiquettes de structure |
| **R3** | Historique rétroactif (18 versions, §5) rédigé dans `data/changelog.yml` |
| **R4** | Données de démonstration et nouvelles captures |
| **R5** | README réécrit |

## 1. Source unique : `data/changelog.yml`

```yaml
next:                      # entrées en attente de la prochaine publication
  - kind: new
    text: "Numéro de version et page « Nouveautés »."
versions:                  # la plus récente en tête
  - version: "2026.10.18"
    date: 2026-10-26
    title: "Brevo"
    entries:
      - kind: new          # new | improved | fixed | action
        structure: asso    # asso | sci | (absent : toutes)
        text: "La liste des adhérents se synchronise vers Brevo, sans doublon."
        tech: "Lot B1–B3, migration a1c3e5f7b9d2, table brevo_links."   # facultatif, CHANGELOG.md seulement
      - kind: action
        text: "Autoriser l'adresse IP du serveur dans Brevo, puis saisir la clé dans Intégrations."
```

- **Le numéro de version est celui de la première entrée de `versions`** (V-R1) : il n'est écrit
  nulle part ailleurs à la main.
- `text` : une phrase pour un trésorier, qui dit ce qui change à l'écran (C-R2). `tech` : la précision
  pour le développeur ou l'hébergeur (lot, migration, variable).
- `kind: action` : action requise à la mise à jour (C-R3), affichée en tête de la version, en
  évidence.
- `structure` : étiquette « Associations » ou « SCI » (V7), jamais de masquage.

## 2. R1 — Version et publication

### 2.1 Serveur (`app/version.py`)

- `version()` lit `data/changelog.yml` (mis en cache au démarrage) et renvoie le numéro de la
  première version publiée ; `commit()` lit `APP_COMMIT` (variable d'environnement, vide si
  inconnue).
- Image Docker : `ARG SOURCE_COMMIT=""` puis `ENV APP_COMMIT=$SOURCE_COMMIT`, transmis par le compose
  (`args: SOURCE_COMMIT: ${SOURCE_COMMIT:-}`). Si Dokploy ne le fournit pas, le commit n'est
  simplement pas affiché.
- La session (connectée ou non) renvoie `app: {version, commit}` : la page publique `/about` l'affiche
  aussi.

### 2.2 Script `scripts/release.py`

| Commande | Effet |
|---|---|
| `check` | vérifie le fichier (types, dates décroissantes, numéros croissants, format `AAAA.MM.N`), que `CHANGELOG.md` et `frontend/package.json` sont à jour |
| `build` | régénère `CHANGELOG.md`, la version de `frontend/package.json` et le badge de version du README (entre deux balises de commentaire) |
| `publish [--title "…"]` | transforme `next` en nouvelle version : numéro `AAAA.MM.N` (N suivant dans le mois courant, 1 au changement de mois), date du jour, puis `build`. **Ne commite et ne pousse rien** ; il affiche les commandes `git commit` et `git tag v<version>` à lancer (V8 : le premier tag est posé à la prochaine publication) |

Un test pytest appelle `check` : un `CHANGELOG.md` ou un `package.json` désynchronisé fait échouer la
suite.

### 2.3 `CHANGELOG.md`

Généré, avec un avertissement en tête (« ne pas modifier : `scripts/release.py build` »). Une
section par version (`## 2026.10.18 — Brevo (26/10/2026)`), les entrées groupées par catégorie
(**Action requise** en premier, puis Nouveautés, Améliorations, Corrections), l'étiquette
de structure entre crochets, et la précision `tech` en italique à la suite.

## 3. R2 — Page « Nouveautés »

- **API** : `GET /api/v1/changelog` (utilisateur connecté) renvoie les versions publiées, sans la
  partie `next`, avec `text`, `kind` et `structure`, sans `tech`.
- **Route** `/changelog` (SPA). Les versions sont en cartes, la plus récente en tête. Les actions
  requises sont en encadré, avec l'étiquette `Associations` ou `SCI` sur les entrées concernées.
- **Menu utilisateur** : une entrée « Nouveautés » avec le numéro de version en sous-titre, et une
  **pastille** si `preferences.changelog_seen` est différent de la version courante (C-R4).
  Ouvrir la page enregistre `changelog_seen = version` par la route existante
  `PATCH /api/v1/me/preferences`. Un nouvel utilisateur ne voit pas de pastille : sa préférence est
  initialisée à la version courante à sa première session.
- **Version affichée** en bas du menu utilisateur (« Lyvre 2026.10.19 · a1b2c3d ») et dans le pied
  de `/about`.

## 4. R4 — Données de démonstration et captures

- **Base** : on continue avec la base jetable des tests de bout en bout (`scripts/e2e_server.py`,
  instances de `frontend/e2e/fixtures.json`), complétée par une instance association de
  démonstration si elle manque, avec des noms fabriqués. Aucune donnée réelle (R-R4).
- **Services extérieurs simulés** : nouvelle option `--demo` de `e2e_server.py`.
  - **Sirene** : réponses tirées de `tests/fixtures/sirene/`, données publiques de l'INSEE.
  - **Brevo** : faux compte en mémoire, avec des contacts fabriqués.
  - **Documenso** : état de signature posé en base, aucun envoi.

  La carte des parcelles appelle le service public de l'IGN : la capture est sautée, avec un
  message, si le réseau manque.
- **Script** `scripts/readme_screenshots.mjs`, étendu. Captures en 1440 × 900, en thème clair, plus
  le tableau de bord en sombre :

| Fichier | Écran |
|---|---|
| `tableau-de-bord.png`, `-sombre.png` | existants, rafraîchis |
| `rapprochement.png` | rapprochement bancaire au clavier |
| `cloture.png` | assistant de clôture |
| `ventes.png`, `facture.png` | existants, rafraîchis |
| `bail.png` | fiche d'un bail (lots, loyer, signature) |
| `bail-carte.png` | carte des parcelles et bâtiments d'un bail |
| `sirene.png` | Structure › « Compléter depuis Sirene » (modal de proposition) |
| `brevo.png` | rapport d'aperçu Brevo |
| `adherents.png` | liste des adhérents et échéances |
| `nouveautes.png` | page « Nouveautés » |
| `integrations.png`, `abonnements.png` | existants, rafraîchis |

## 5. R3 — Historique rétroactif (à valider)

Regroupement des 172 commits par lot. Date de la version = date du dernier commit du lot. Pas de
tag (V8).

| Version | Date | Titre | Contenu (lots, commits) |
|---|---|---|---|
| 2026.04.1 | 28/04 | Première version | import initial : comptabilité association, banque OFX, tiers, adhérents, Odoo, Stancer |
| 2026.05.1 | 15/05 | Odoo | factures Odoo, menus |
| 2026.05.2 | 21/05 | Plusieurs structures | multi-instance, Docker, restauration d'instance, tableau de bord, correctif Stancer |
| 2026.06.1 | 25/06 | Relances | relance des adhérents |
| 2026.06.2 | 28/06 | Visibilité et rapport d'activité | indicateurs d'impact, rapport d'activité, note d'adhésion dans Odoo |
| 2026.10.1 | 20/10 | Plan SCI et intégrations | plan comptable SCI et menus par plan, états par plan, saisie et rapprochement au clavier, écran des intégrations (phases A–E) |
| 2026.10.2 | 21/10 | Banque Qonto | synchronisation des comptes et transactions Qonto (phases A–G) |
| 2026.10.3 | 22/10 | Factures d'achat | factures Qonto, catalogue, engagement, saisie avec lecture Factur-X / PDF / OCR, sauvegardes .zip (lots 2a, 2b) |
| 2026.10.4 | 22/10 | Nouvelle interface | interface React + Mantine (phases A–I), notifications des tâches de fond |
| 2026.10.5 | 23/10 | Obligations comptables | rôles par structure, identité, validation et FEC, assistant de clôture, à-nouveaux, fonds dédiés (lot A) |
| 2026.10.6 | 23/10 | Projets et budget | projets, budget, suivi, compte de résultat de projet, prévisionnel de trésorerie (lot C) |
| 2026.10.7 | 23/10 | Reçus fiscaux | reçus Cerfa, PDF figés, envoi, annulation, état annuel (lot B) |
| 2026.10.8 | 23/10 | Comptabilité simplifiée | caisse et dépôts, recettes et dépenses, états simplifiés, passage en partie double (lot D), page À propos |
| 2026.10.9 | 23/10 | Utilisateurs et rôles | comptes à la création d'instance, mot de passe initial (lot E), lecture des factures améliorée |
| 2026.10.10 | 23/10 | Associés | registre des parts, comptes courants, intérêts, import (A1–A6) |
| 2026.10.11 | 23/10 | Intégrations par structure | propositions, silence quand désactivée, logos (I1–I5) |
| 2026.10.12 | 23/10 | Ventes | factures, avoirs, devis, encaissements, relances, récurrentes, baux et quittances, abonnements (S0–S7), README |
| 2026.10.13 | 24/10 | Fiabilité comptable | validation par lots, verrouillage, lettrage, CCA/PCA, immobilisations, reprise FEC (F1–F6) |
| 2026.10.14 | 24/10 | Reprise Ekylibre | import d'un export Ekylibre dans une SCI (K1–K4), comptes de tiers par défaut |
| 2026.10.15 | 24/10 | Baux | assistant, modèles, carte IGN, signature Documenso, révision des loyers (L1–L5), mot de passe oublié |
| 2026.10.16 | 25/10 | Mise en production | service Lyvre (bascule du 25/10), droits du dossier de données, affichage du bilan et des graphiques |
| 2026.10.17 | 25/10 | Structure et Sirene | fonctions réservées aux associations, mentions légales unifiées, Sirene (G1–G5), migration de toutes les instances |
| 2026.10.18 | 26/10 | Brevo | synchronisation des adhérents (B1–B3), page À propos à jour |
| **2026.10.19** | à la publication | Version et nouveautés | ce lot : version, page Nouveautés, README — **premier tag `v2026.10.19`** |

Actions requises reprises dans l'historique : `SIRENE_API_KEY` (2026.10.17), IP Brevo et clé
(2026.10.18), migration de toutes les instances par l'entrypoint (2026.10.17, rien à faire).

## 6. R5 — README

Ordre des sections, en restant dans ce que GitHub affiche, clair et sombre (R-R6) :

1. **En-tête centré** : symbole (clair ou sombre selon le thème), « Lyvre », accroche, une phrase de
   valeur, badges (version générée par `release.py build`, licence, auto-hébergé, Docker, Factur-X,
   stack), puis la capture du tableau de bord (`<picture>` clair ou sombre).
2. **En bref** : tableau de 4 colonnes (Comptabilité complète · Banque sans saisie · Prêt pour
   l'expert-comptable · Libre et chez vous), une ligne chacune.
3. **Pour qui** : quatre blocs (Association · SCI · Expert-comptable · Hébergeur), chacun avec 3 ou 4
   points et une capture associée en deux colonnes (adhérents et reçus ; bail et carte ; clôture et
   FEC ; intégrations).
4. **Aperçu** : galerie de 2 × 4 captures avec légende.
5. **Fonctionnalités** : un `<details>` par domaine, même périmètre que `/about` (R-R3).
6. **Intégrations** : tableau service · usage · structures (Qonto, HelloAsso, Stancer, Odoo, SMTP,
   Documenso, Sirene, Brevo, GA4, Facebook).
7. **Démarrage rapide** : `git clone`, `cp .env.example .env`, `docker compose up -d`, puis
   première connexion ; lien vers `doc/installation.md` et `doc/docker.md`.
8. **Nouveautés** : la version courante et ses titres, lien vers `CHANGELOG.md`.
9. **Documentation**, **Contribuer** (tests, `release.py`), **Licence**.

## 7. Tests

- pytest : `release.py check` sur le dépôt ; calcul du numéro suivant (même mois, changement de
  mois, première du mois) ; génération du Markdown (ordre, étiquettes, actions requises) ;
  `version()` et `GET /api/v1/changelog` (sans `tech`, sans `next`) ; session avec `app.version`.
- Vitest : pastille affichée puis retirée à l'ouverture ; étiquettes de structure ; actions requises
  en tête.

## 8. Points laissés à l'implémentation

- Rédaction des entrées de chaque version rétroactive (R3), à partir des messages de commit et de la
  documentation des lots ; relue avant la publication.
- `.env.example` : il n'existe pas aujourd'hui. Le démarrage rapide en a besoin : il est créé avec
  des valeurs vides ou d'exemple, sans aucun secret.
