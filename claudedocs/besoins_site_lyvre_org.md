# Site public lyvre.org, README et mise à jour automatique — besoins

> Statut : **exigences à valider** (`/sc:brainstorm`, 17/11/2026). Modèle : site fourmy.org
> (`fourmy/docs/site-public-exigences.md`, `fourmy/apps/site`). Étape suivante : `/sc:design` ou
> `/sc:workflow`, puis `/sc:implement`.

## 1. Objectifs

1. Présenter Lyvre sur **lyvre.org** (et `www.lyvre.org`) : ce que c'est, pour qui (association,
   SCI, exploitation agricole, société), fonctionnalités illustrées, nouveautés, installation.
2. Deux appels à l'action : **Installer** (Docker, dépôt `ekylibre/lyvre`) et **Essayer la démo**
   (`demo.lyvre.org`, données fictives).
3. Recevoir les demandes : **formulaire de contact via Brevo**.
4. Mettre le **README à jour** (présentation agricole et société, nouveautés tirées du changelog).
5. Garder README et site **à jour sans ressaisie** : une source unique dans le dépôt, un script
   qui régénère le README et les données du site, et le site reconstruit à chaque push sur `main`.

## 2. Décisions (17/11/2026)

| Sujet | Décision |
|---|---|
| Emplacement | Dossier `site/` du dépôt lyvre, **Astro** (comme fourmy), charte et logos Lyvre (`frontend/src/assets/lyvre-*.svg`) |
| Déploiement | **Nouveau service Dokploy** (projet « Seconde Nature » ou projet dédié « Lyvre »), construit par Dokploy depuis le dépôt à chaque push sur `main`. Aucune CI n'est ajoutée |
| Historique Git | **Pas nécessaire** : contrairement à fourmy (commits conventionnels), la version et les nouveautés viennent de `data/changelog.yml`, qui suffit avec un clone superficiel |
| Script de mise à jour | **Génération déterministe** (sans IA) + **captures d'écran à la demande**. Pas de brouillon assisté par Claude, pas de redéploiement par l'API (Dokploy redéploie sur push) |
| Appels à l'action | Installer (Docker) · Démo en ligne |
| Contact | Brevo : contact ajouté à une liste + e-mail transactionnel à l'équipe |
| Langue | Français seul ; structure prête pour `/en/` |

## 3. Exigences fonctionnelles

### Site lyvre.org

- **SP-1 En-tête** : logo, navigation (Lyvre, Fonctionnalités, Nouveautés, Installer, Contact),
  boutons **« Essayer la démo »** et **« Installer »**. Version courante en pied de page.
- **SP-2 Accueil** : promesse (comptabilité libre, sobre et souveraine), les quatre atouts
  (« En bref » du README), bloc « Pour qui » par structure avec capture, bloc Intégrations
  (Qonto, HelloAsso, Brevo, Sirene, Documenso, IGN…), auto-hébergement et licence AGPL.
- **SP-3 Fonctionnalités** : une carte par fonctionnalité (domaine, titre, phrase, capture,
  structures concernées, version d'arrivée), regroupées comme dans le README (Comptabilité,
  Banque, Ventes, Achats, Adhérents, Baux, Clôture…).
- **SP-4 Nouveautés** : versions publiées de `data/changelog.yml`, la plus récente en tête ;
  champ `text` uniquement (jamais `tech`), actions requises en évidence, étiquettes de structure.
  Une page par version (lien permanent) et un flux **RSS/Atom**.
- **SP-5 Installer** : démarrage rapide Docker repris de `doc/docker.md` et `doc/installation.md`,
  prérequis, lien GitHub, sauvegardes, mise à jour (avec les actions requises).
- **SP-6 Démo** : lien vers `demo.lyvre.org` avec identifiants de démonstration affichés,
  rappel que les données sont fictives et remises à zéro.
- **SP-7 Contact** : nom, e-mail, profil (association, SCI, exploitation, société, expert-comptable,
  développeur, autre), message, consentement. Accusé de réception à l'écran.
- **SP-8 Pages légales** : mentions légales (éditeur à préciser, §6), données personnelles
  du formulaire (finalité, durée de conservation, droits, sous-traitant Brevo).
- **SP-9 `version.json`** : version et date publiées, lisibles par d'autres outils.

### Démo en ligne

- **DM-1** Une instance Lyvre à part sur `demo.lyvre.org` (service Dokploy distinct de la
  production), alimentée par les données fictives de `scripts/e2e_demo.py` (association, SCI,
  et une exploitation agricole à ajouter).
- **DM-2** Remise à zéro planifiée (fréquence à fixer, §6) ; intégrations externes désactivées
  ou simulées (aucun envoi d'e-mail, aucune clé réelle).
- **DM-3** Bandeau « Démonstration » dans l'application de démo.

### README

- **RM-1** Présentation à jour : exploitation agricole (micro-BA / réel, MSA, calculettes,
  plans agricoles) et société (TVA CA3, liasse 2050) ajoutées à « Pour qui » et « Fonctionnalités ».
- **RM-2** Section « Nouveautés » **générée** : les N dernières versions publiées (titre, date,
  2-3 points), lien vers `CHANGELOG.md` et lyvre.org/nouveautes.
- **RM-3** Section « Fonctionnalités » **générée** depuis la même source que le site (SP-3).
- **RM-4** Liens vers lyvre.org et la démo dans l'en-tête et les badges.
- **RM-5** Les parties écrites à la main restent libres. Les parties générées sont délimitées
  par des balises de commentaire, comme le badge de version actuel (`<!-- version -->`).

### Script de mise à jour

- **MJ-1 Source unique** : `data/changelog.yml` (existant) pour la version et les nouveautés ;
  un nouveau `data/features.yml` pour les fonctionnalités (domaine, titre, texte, structures,
  capture, version d'arrivée, état disponible / à venir).
- **MJ-2** `scripts/release.py build` (ou une sous-commande) régénère en plus les sections
  balisées du README et les données consommées par le site. `publish` les régénère aussi.
- **MJ-3** `scripts/release.py check` (déjà appelé par pytest) échoue si le README généré n'est
  pas à jour, si une fonctionnalité pointe vers une version ou une capture inexistante, ou si
  une entrée publique contient un terme de la **liste noire** (noms de clients, d'instances,
  structures réelles, données du `.gitignore` « documents de travail »).
- **MJ-4 Captures, à la demande** : une commande lance `scripts/readme_screenshots.mjs` sur la
  base jetable (`e2e_server.py --demo`) et produit les images du README (`doc/images/`) et du
  site (formats optimisés, thèmes clair et sombre). Elle n'est pas lancée à chaque commit.
- **MJ-5** Le site lit `data/changelog.yml` et `data/features.yml` **à la construction** ; un push
  sur `main` suffit à le mettre à jour (aucun fichier généré à recommiter pour le site).

## 4. Exigences non fonctionnelles

- **Performance** : site statique, Lighthouse ≥ 95 sur les quatre axes, images WebP/AVIF.
- **Accessibilité** : WCAG AA, test axe (Playwright) comme fourmy.
- **Vie privée** : aucun cookie ni traceur tiers ; mesure d'audience éventuelle sans cookie.
- **Sécurité du contact** : point d'entrée limité en débit et en taille, champ piège et délai
  minimal, validation stricte, rien stocké hors de Brevo ; clé Brevo **uniquement dans les
  variables Dokploy** (jamais dans l'image ni le dépôt) ; en-têtes de sécurité (CSP, HSTS).
- **SEO** : titres, descriptions, sitemap, Open Graph, `www` → apex en 301.
- **Confidentialité du dépôt** : aucune donnée réelle (structures, comptes, clients) dans le site,
  les captures ou le README ; les captures ne viennent que des données fictives.
- **Portabilité** : le site se construit et se sert sans le reste de l'application (image séparée).

## 5. Critères d'acceptation

- `https://lyvre.org` sert le site en HTTPS ; `https://www.lyvre.org` redirige (301).
- Après `release.py publish` puis un push sur `main`, la nouvelle version apparaît sur le site
  (pied de page, Nouveautés, RSS) et dans le README, sans autre action.
- Une entrée `next` non publiée n'apparaît ni sur le site ni dans le README.
- `pytest` échoue si le README n'a pas été régénéré après une modification de `changelog.yml` ou
  de `features.yml`, ou si un terme de la liste noire figure dans un texte public.
- Le formulaire crée le contact dans la liste Brevo et envoie l'e-mail à l'équipe ; un envoi
  avec champ piège est ignoré ; 10 envois rapides depuis une IP sont limités.
- « Essayer la démo » ouvre `demo.lyvre.org`, où l'on se connecte avec les identifiants affichés.
- Aucun champ `tech` ni chemin de code n'apparaît sur le site.

## 6. Questions ouvertes

1. **74 entrées en attente sous `next`** (dont toute la comptabilité agricole) : publier une
   version avant la mise en ligne du site, pour que l'agricole y figure ?
2. **DNS** : `lyvre.org` pointe sur le parking Gandi, `www` sur sa redirection. Qui bascule les
   enregistrements A (apex et `www`, `demo`) vers le serveur Dokploy ?
3. **Éditeur et mentions légales** : Ekylibre SAS, l'association Seconde Nature ou bziiit ?
   L'éditeur fixe aussi le destinataire du formulaire et la liste Brevo à utiliser.
4. **Point d'entrée du contact** : le site est statique. Faut-il un petit service à côté (dans le
   même compose) ou une route publique dans une instance Lyvre ? À trancher en `/sc:design`.
5. **Démo** : fréquence de remise à zéro (chaque nuit ?), identifiants publics, scénario agricole
   à ajouter à `e2e_demo.py`, et ressources du serveur disponibles pour une instance de plus.
6. **Liste noire** : quels termes y mettre (instances et clients réels) ? Elle reste dans le dépôt
   public, donc sous une forme qui ne les révèle pas (empreintes, ou fichier hors dépôt).
7. **Profondeur des Nouveautés dans le README** : combien de versions (3 ? 5 ?).
