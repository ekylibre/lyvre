# Besoins — Front React + Mantine

> Statut : **réalisé** (2026-10-22) — validé au brainstorm du 2026-10-22 (réponses au §9), US1–US7 cochées au §7.
> Étape suivante : `/sc:design` (architecture de la SPA, API, routage, coexistence), puis `/sc:workflow`.

## 1. Contexte

| Constat (commit `2b4a216`) | Valeur |
|----------------------------|--------|
| Gabarits Jinja | 84, 22 domaines (blueprints) |
| Routes Flask d'écrans | ≈ 150 |
| Front actuel | Bootstrap 5.3 + HTMX 2.0 (refonte « front réactif » terminée en oct. 2026) |
| Îlots React 18 existants | `EntryForm` (saisie d'écriture), `ReconcileWorkspace` (rapprochement) |
| API JSON `/api/v1` | 14 routes (session, comptes, tiers, écritures, rapprochement) |
| Graphiques | ECharts (tableau de bord, rapports, impact) |
| Mantine | v9 (9.7.x) : `core`, `hooks`, `form`, `dates`, `notifications`, `charts` (Recharts), `dropzone`, `modals`, `spotlight` ; PostCSS requis |

Le front mélange trois technologies (Jinja/Bootstrap, HTMX, React) et des composants maison
(combobox de comptes, éditeur de lignes, aperçu de pièce). La refonte remplace l'ensemble par une
seule application React + Mantine, **dans le même dépôt** que le back Flask.

## 2. Objectifs

- **O1 — Interface homogène et moderne** : un seul système de composants partout (formulaires,
  tableaux, modales, notifications, thème clair/sombre). Bootstrap, HTMX et les gabarits d'écran
  disparaissent à la fin.
- **O2 — Ergonomie riche** : tableaux avancés, sélecteurs de dates, listes avec recherche,
  glisser-déposer de fichiers, création / édition en modale, palette de commandes.
- **O3 — Maintenance soutenable seul** : migration écran par écran, livrable à tout moment,
  TypeScript côté front, API JSON documentée et testée côté back.

Hors objectifs : application mobile, mode hors ligne, autre langue que le français, refonte des
règles métier (comptabilité, synchronisations, imports) — le back ne change que pour exposer l'API.

## 3. Décisions du brainstorm

| # | Sujet | Décision |
|---|-------|----------|
| FM1 | Forme | **SPA complète** : une application React avec routeur côté client ; Flask sert l'API JSON et la page d'entrée, **même origine**, cookie de session existant |
| FM2 | Migration | **Progressive, écran par écran** : ancien et nouveau coexistent ; chaque domaine bascule quand il est prêt ; Jinja/HTMX/Bootstrap supprimés à la fin |
| FM3 | URL | **Mêmes URL** : un écran migré garde son URL (`/purchases/` reste `/purchases/`) ; favoris et liens inchangés |
| FM4 | Apparence | Thème Mantine, **couleur principale et logo de l'association**, clair / sombre |
| FM5 | Reste côté serveur | **Exports et PDF** : CSV / ODS / XLSX, PDF du rapport d'activité, pièces jointes, sauvegardes `.zip` (gabarits d'impression Jinja conservés). **Connexion et choix d'instance passent en React** |
| FM6 | Graphiques | **Au cas par cas** : Mantine Charts par défaut, ECharts si un graphique l'exige |
| FM7 | Ordre | Socle (mise en page, navigation, instance, thème, connexion), puis **écrans simples** (CRUD) pour éprouver le socle, puis les écrans riches |
| FM8 | Tests | Tests de vues HTML → **tests d'API pytest** ; composants en **Vitest** ; **parcours de bout en bout (Playwright)** sur les flux critiques |
| FM9 | Ergonomie transverse | **Tableaux avancés**, **modales / panneaux** pour créer et modifier sans quitter la liste, **palette de commandes** (Ctrl+K) |
| FM10 | Mobile | **Lisible, pas optimisé** : responsive Mantine sans effort spécifique |
| FM11 | Charte | Couleur principale et logo **conçus par l'utilisateur (en cours)** : le thème doit les accepter sans retouche des écrans (jetons de thème centralisés, valeurs provisoires en attendant) |
| FM12 | Raccourcis | Seulement ceux de la saisie et du rapprochement (NF2) ; pas de raccourcis transverses sur les listes |
| FM13 | Palette | Navigation, recherche (tiers, factures, écritures) et les quelques actions de F8 : suffisant |
| FM14 | Préférences | Thème clair / sombre, colonnes masquées, choix de tableaux mémorisés **dans le compte utilisateur** (côté serveur, suivent l'utilisateur d'un poste à l'autre) |
| FM15 | Délai | **Le plus vite possible** : découpage favorisant les gains rapides, pas d'embellissement hors besoins |
| FM16 | Ordre des chantiers | Refonte **avant** la mise en production Qonto de la SCI ; tout le travail reste sur la **branche locale en cours** (`main`, non poussée) |

## 4. Utilisateurs

| Profil | Usage | Attentes |
|--------|-------|----------|
| Trésorier (Seconde Nature, SCI) | Usage intensif sur ordinateur : banque, rapprochement, saisie, factures d'achat, clôture | Rapidité, clavier, pas de perte de contexte |
| Administrateur | Instances, utilisateurs, intégrations, sauvegardes | Écrans clairs, actions sûres (confirmations) |
| Bénévole / membre du bureau | Consultation : tableau de bord, rapports, rapport d'activité, temps de travaux | Lisibilité |

Multi-instance : l'instance courante et son plan comptable (`asso` / `sci`) pilotent les menus
(`menu_config`) ; le changement d'instance reste possible depuis l'en-tête.

## 5. Exigences fonctionnelles

### 5.1 Socle

- **F1 — Mise en page** : en-tête (instance courante, sélecteur d'instance, utilisateur, thème
  clair/sombre), navigation latérale ou supérieure issue de `menu_config` (plan comptable + droits
  admin), zone de contenu, notifications (remplacent les toasts actuels).
- **F2 — Connexion / déconnexion / choix d'instance** en React, avec le même mécanisme de session
  et la même protection CSRF ; redirection vers l'écran demandé après connexion.
- **F3 — Routage** : navigation sans rechargement entre écrans migrés ; un lien vers un écran non
  encore migré charge l'ancienne page (rechargement complet) ; retour / avant du navigateur, URL
  partageables (filtres, tri, mois, onglet dans l'URL).
- **F4 — Erreurs** : messages d'erreur métier affichés au champ ou en notification ; session
  expirée → retour à la connexion sans perte silencieuse ; 403 / 404 / 409 (pas d'instance) gérés.
- **F5 — Thème** : couleur principale et logo de l'association, mode clair / sombre mémorisé par
  utilisateur (FM14), formats français (montants `1 234,56 €`, dates `jj/mm/aaaa`).

### 5.2 Composants transverses

- **F6 — Tableaux avancés** : tri (multi-colonnes), filtres par colonne et filtres globaux
  (exercice, mois, recherche), sélection multiple et actions groupées, colonnes masquables
  (choix mémorisé dans le compte utilisateur, FM14), pagination ou défilement pour les grandes listes, état vide explicite.
- **F7 — Modales et panneaux** : création / modification rapide sans quitter la liste quand le
  formulaire est court ; page dédiée gardée pour les fiches riches (facture d'achat, écriture).
  Confirmation avant toute action destructive (remplace `hx-confirm`).
- **F8 — Palette de commandes (Ctrl+K)** : aller à un écran, chercher un tiers, une facture, une
  écriture (par n°, nom, montant), lancer quelques actions (nouvelle écriture, nouvelle facture,
  importer un OFX).
- **F9 — Formulaires** : validation côté serveur source de vérité, erreurs au champ, saisie des
  montants à la française, sélecteurs de date, combobox avec recherche (comptes, tiers, produits).
- **F10 — Fichiers** : dépôt par glisser-déposer (OFX, factures, archives, photos), progression,
  aperçu PDF / image ; téléchargements (exports, pièces, sauvegardes) servis par Flask.
- **F11 — Tâches longues** : synchronisations et imports en arrière-plan avec suivi de progression
  (mécanisme `sync_jobs` existant).

### 5.3 Écrans à porter (tous)

| Groupe | Domaines |
|--------|----------|
| Compta | Tableau de bord, écritures (saisie = îlot `EntryForm` à porter en Mantine), balance, grand livre, bilan, compte de résultat, plan comptable, journaux, exercices, catalogue |
| Banque | Comptes bancaires (OFX / Qonto, contreparties), rapprochement (îlot `ReconcileWorkspace` à porter), versements Stancer, factures d'achat (liste, saisie avec lecture de pièce, fiche, règlements, fournisseurs, remplacements) |
| Tiers | Entités, adhérents, temps de travaux, règles de catégorisation |
| Asso | Odoo (commandes POS, factures clients), indicateurs, Visibilité & Impact, rapport d'activité (édition, photos, logo, archives) |
| Imports / Exports | Fichier OFX, import de tonnages, temps, exports |
| Configuration | Instances (création, sauvegarde / restauration `.zip`), utilisateurs, intégrations, paramètres de synchro |

Chaque écran porté conserve **toutes** les fonctions de l'écran actuel (filtres, actions, messages)
sauf décision contraire notée dans le workflow.

### 5.4 Côté serveur

- **F12 — API JSON** couvrant tous les écrans migrés (lecture, création, modification,
  suppression, actions métier), sous `/api/v1`, mêmes règles d'accès que les vues actuelles
  (connexion, admin, instance courante).
- **F13 — Les services métier ne changent pas** : l'API appelle les mêmes services que les vues
  Jinja (`purchase_entry`, `purchase_posting`, `ledger`, `reconciler`…).
- **F14 — Retrait** : à la bascule d'un domaine, ses gabarits et routes HTML sont supprimés
  (pas de double maintenance durable) ; à la fin, plus de Bootstrap ni de HTMX.

## 6. Exigences non fonctionnelles

| # | Exigence |
|---|----------|
| NF1 | **Aucune régression fonctionnelle** : chaque écran migré passe ses tests d'API et un contrôle manuel dans Chrome avant suppression de l'ancien |
| NF2 | **Raccourcis existants conservés** : ceux de la saisie d'écriture et du rapprochement (voir `doc/saisie_rapprochement.md`) |
| NF3 | **Performance** : navigation entre écrans < 300 ms perçus ; listes de 500 lignes fluides ; bundle initial raisonnable (chargement des écrans à la demande) |
| NF4 | **Accessibilité** : navigation au clavier, libellés ARIA, focus visible, contraste correct en clair et sombre (niveau des composants Mantine, pas d'audit formel) |
| NF5 | **Sécurité** : même origine, cookie de session, CSRF sur toutes les écritures, aucune donnée sensible dans les URL ; identifiants d'intégration jamais renvoyés au front |
| NF6 | **Déploiement inchangé** : une seule image Docker (build Node multi-étapes existant, sans Node à l'exécution), Dokploy |
| NF7 | **Maintenance** : TypeScript strict, `make check` = pytest + Vitest + typecheck (+ E2E) ; versions de dépendances épinglées |
| NF8 | **Navigateurs** : Chrome / Firefox / Edge récents ; pas d'Internet Explorer ni de vieux Safari |
| NF9 | **Mobile** : lisible (responsive Mantine), sans optimisation dédiée |

## 7. Récits utilisateur et critères d'acceptation

**US1 — Socle.** L'utilisateur se connecte, choisit son instance, navigue.
- [x] Connexion, déconnexion, choix et changement d'instance en React ; retour à l'écran demandé.
- [x] Menus identiques à `menu_config` selon le plan comptable et les droits.
- [x] Thème aux couleurs de l'association, bascule clair / sombre mémorisée.
- [x] Un lien vers un écran non migré ouvre l'ancienne page ; le retour vers un écran migré fonctionne.
      *(vrai pendant la migration ; depuis la phase H, tous les écrans sont dans la SPA.)*

**US2 — Écran simple (ex. journaux, exercices, plan comptable).**
- [x] Liste en tableau avancé (tri, filtre, colonnes), création / modification en modale,
      suppression confirmée, erreurs au champ.
- [x] Ancienne page et gabarit supprimés ; tests d'API couvrant les mêmes cas que les anciens tests de vues.

**US3 — Saisie et rapprochement.**
- [x] Mêmes raccourcis et mêmes comportements que les îlots actuels, en composants Mantine.
- [x] Parcours E2E : saisir une écriture équilibrée ; rapprocher puis annuler (Ctrl+Z).

**US4 — Factures d'achat.**
- [x] Liste (filtres, badges, suppression), dépôt glisser-déposer, formulaire prérempli avec champs
      « à vérifier » et aperçu, fiche, règlements, envoi à Qonto (avec la même garde).
- [x] Parcours E2E : déposer une facture PDF, l'enregistrer, la retrouver comptabilisée.

**US5 — Palette de commandes.**
- [x] Ctrl+K ouvre la palette ; recherche d'un tiers, d'une facture, d'une écriture ; ouverture de l'écran.

**US6 — Tableau de bord et rapports.**
- [x] Graphiques équivalents (Mantine Charts ou ECharts) lisibles en clair et sombre ; exports
      (CSV / ODS / XLSX / PDF) inchangés. *(PDF du rapport d'activité vérifié identique. L'étiquette
      ADEME impactco2.fr, qui n'existait que dans l'ancien aperçu à l'écran, n'est plus affichée : à rétablir
      si besoin.)*

**US7 — Fin de migration.**
- [x] Plus aucun gabarit d'écran Jinja (seuls restent ceux d'impression / PDF), plus de Bootstrap ni HTMX.
- [x] Documentation (`architecture`, `routes`, `installation`, `docker`, guides) à jour.

## 8. Risques

| Risque | Effet | Parade envisagée |
|--------|-------|------------------|
| Volume (≈ 150 routes, 84 gabarits) | Chantier long, maintenance seul | Migration par domaine, livrable à chaque étape (FM2) |
| Refonte « front réactif » récente | Travail HTMX jeté, îlots à réécrire | Réutiliser la logique des îlots (états, raccourcis, API) en changeant seulement les composants |
| Deux fronts en parallèle | Incohérences visuelles, double maintenance | Bascule d'un domaine complet à la fois, suppression immédiate de l'ancien (F14) |
| API à créer pour tout | Duplication avec les vues | Vues et API appellent les mêmes services (F13) ; vues supprimées à la bascule |
| Mantine 9 / React 19 | Montée de version des îlots (React 18 aujourd'hui) | À trancher au design |
| Tests de vues existants (≈ 640 tests dont beaucoup de vues) | Perte de couverture pendant la migration | Réécrire en tests d'API avant de supprimer les vues (NF1) |

## 9. Questions tranchées (2026-10-22)

1. **Couleur et logo** : en cours de conception par l'utilisateur → FM11 (thème paramétrable, valeurs provisoires).
2. **Raccourcis sur les listes** : non → FM12.
3. **Palette de commandes** : navigation + recherche + actions de F8 → FM13.
4. **Préférences** : dans le compte utilisateur → FM14.
5. **Délai** : le plus vite possible → FM15.
6. **Qonto SCI** : mise en production après la refonte ; travail conservé sur la branche locale en cours → FM16.
