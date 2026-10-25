# Sirene (INSEE)

Pré-remplissage de la Structure (lot G3), puis des tiers (lots G4, G5), depuis l'API Sirene v4.

## Configuration

Variable du serveur `SIRENE_API_KEY` (voir [docker.md](docker.md)) ; pas d'intégration par instance.
La session indique `services.sirene` : sans clé, aucun bouton Sirene n'apparaît. L'expert-comptable
ne voit pas les boutons (lecture seule).

## Service (`app/services/sirene.py`)

- Appels côté serveur, en-tête `X-INSEE-Api-Key-Integration`, délai de 10 s. Routes v4 :
  `/etat-courant/unites-legales/{siren}`, `/etat-courant/etablissements/{siret}` (avec `champs`, sinon
  l'adresse n'est pas renvoyée), et leurs `…/multicritere` (POST, 100 numéros par appel).
- **Quota** : 30 requêtes par minute et 2 000 par heure, par une clé. `RateLimiter` en mémoire du
  processus : un appel interactif hors quota est refusé tout de suite (« réessayez dans N s ») sans
  appeler l'INSEE ; une tâche de fond attend son tour. Valable avec un seul processus gunicorn.
- **Cache** des fiches 24 h (pas des recherches par nom).
- **Erreurs** : numéro inconnu → 404 ; quota → 429 `sirene_busy` + `retry_after` ; clé absente ou
  INSEE en panne → 503 `sirene_unavailable`. Le message de l'INSEE n'est jamais affiché tel quel.

## Proposition

`GET /api/v1/sirene/proposal?siren=` (siège) ou `?siret=` (`for=entity` pour un tiers) : champs Lyvre,
`computed` (n° de TVA calculé : `FR` + clé + SIREN, Sirene ne le fournit pas), `state` (`ceased` :
unité cessée ou établissement fermé), `warnings` (diffusion partielle, siège proposé à la place d'un
établissement fermé), `labels` (forme juridique, NAF). Dénomination dans la casse de Sirene.

`GET /api/v1/sirene/search?q=&postal_code=` : nom (2 appels : unités légales actives, puis leurs
sièges ou leurs établissements du code postal), SIREN ou SIRET.

Le modal de proposition remplit le formulaire sans enregistrer : champs vides cochés, champs
différents « Actuel → Sirene » à cocher, champs identiques masqués. Le greffe du RCS et le capital
ne sont pas dans Sirene.

## Tiers et factures d'achat (lot G4)

- **Formulaire du tiers** : « Rechercher dans Sirene » en tête (ouvert à la création), et « Compléter
  depuis Sirene » dès que le SIRET ou le SIREN est valide. Champs proposés : nom, nature, adresse,
  n° de TVA (calculé), SIRET, SIREN, activité (NAF de l'établissement). Un SIREN déjà porté par un
  autre tiers est signalé, avec un lien vers ce tiers.
- **Facture d'achat**, bloc Fournisseur : « Chercher dans Sirene ». Un tiers de même SIREN est
  choisi tel quel et n'est jamais modifié. Sinon la facture passe en « Créer un fournisseur » (nom,
  SIRET, TVA) et transmet la fiche Sirene (`new_entity` : adresse, activité, nature, SIREN),
  appliquée seulement à la création du tiers, à l'enregistrement de la facture.
- **Reconnaissance des fournisseurs** (`purchase_sync.find_supplier`) : identifiant Qonto, TVA,
  SIRET, puis **SIREN** (tiré du SIRET ou d'un n° de TVA français), IBAN, nom.

## Mise à jour groupée des tiers (lot G5)

- **Tiers › Entités** : « Mettre à jour depuis Sirene » sur la sélection, ou sur tous les tiers qui
  ont un SIREN ou un SIRET (le nombre est affiché).
- **Tâche de fond** `sirene_refresh` (`services/sirene_refresh.py`) : paquets de 100 tiers, 3 appels
  par paquet (unités légales, établissements des tiers à SIRET, sièges des tiers à SIREN seul) ;
  50 tiers ≈ 3 appels. Elle attend le quota au besoin, s'arrête entre deux paquets sur demande, et
  **n'écrit rien** : chaque tiers est classé à revoir, à jour, cessé ou fermé, introuvable, ou au
  numéro invalide. Une seule comparaison à la fois par instance.
- **Revue** `/entities/sirene-review/<job>` (lien de la notification de fin) : champs vides cochés,
  champs différents à cocher. « Appliquer la sélection » écrit en une transaction ; un champ modifié
  depuis la comparaison (verrou optimiste) ou un nom déjà pris est laissé tel quel, avec son motif.
  La revue appliquée reste consultable, en lecture.
- API : `POST /api/v1/entities/sirene-refresh` `{entity_ids?}`, `GET …/<job>`, `POST …/<job>/apply`
  `{changes: {entity_id: [champs]}}`, `POST …/<job>/cancel`. Écritures refusées à l'expert-comptable.

## Nomenclatures

`data/insee/categories_juridiques.json`, `naf_rev2.json`, `naf_2025.json` (code → libellé),
construits par `scripts/build_insee_nomenclatures.py <cj|naf_rev2|naf_2025> <fichier INSEE>` depuis
les fichiers publiés par l'INSEE (source et date en tête de chaque JSON) : 260 catégories juridiques
(niveau III), 732 sous-classes NAF rév. 2, 747 sous-classes NAF 2025. Sans
fichier, le code s'affiche à la place du libellé. Codes NAF stockés sans point (« 6820B »), affichés
« 68.20B ».

## Tests

Sans réseau : `tests/api/test_sirene.py` simule l'INSEE à partir de `tests/fixtures/sirene` (données
publiques de l'INSEE elle-même). `tests/conftest.py` vide `SIRENE_API_KEY`.
