# Conception — fonctions réservées aux associations, mentions légales unifiées, API Sirene

Source : `claudedocs/besoins_sci_sirene.md` (exigences A1–A11, B1–B19, décisions D1–D9). 25/10/2026.

## 0. Découpage en lots

| Lot | Contenu | Dépend de | Migration |
|---|---|---|---|
| **G1** | Éléments d'association réservés aux associations (A1–A11) | — | aucune |
| **G2** | Mentions légales unifiées dans Structure, champs NAF et SIREN (D4, D6) | — | `organization`, `billing_settings`, `entities` |
| **G3** | Service Sirene, nomenclatures, pré-remplissage de la Structure (B1–B3, B9–B16) | G2 | aucune |
| **G4** | Recherche Sirene dans le tiers et la facture d'achat (B4–B8, B18, B19, D9) | G3 | aucune |
| **G5** | Mise à jour groupée des tiers (D8, B17) | G4 | aucune (réutilise `sync_jobs`) |

Chaque lot se livre seul, avec ses tests, et la suite complète passe à chaque lot.

---

## 1. G1 — Éléments d'association

### 1.1 Règle

`app/tenant.py` gagne `is_association() -> bool` : `current_chart() == "asso"`. Toute autre valeur
(`sci` aujourd'hui) veut dire « autre structure ». Côté client, `useIsAssociation()` dans
`api/session.ts` lit `instance.chart`, déjà présent dans la session.

### 1.2 Garde côté serveur (A9)

Le menu masque déjà les rubriques d'association, mais une URL saisie à la main ne doit pas aboutir.
On ajoute un troisième `before_request` dans `app/api/__init__.py`, sur le modèle de
`_read_only_accountant` :

```python
ASSOCIATION_ONLY_MODULES = {"receipts", "members", "work_times", "task_types", "simple_operations",
                            "simple_categories", "simple_reports", "activity_report", "impact"}
ASSOCIATION_ONLY_ENDPOINTS = {"api.fiscal_years_dedicated_fund_add", ...}   # routes « fonds dédiés »

@bp.before_request
def _association_only():
    view = current_app.view_functions.get(request.endpoint)
    module = view.__module__.rsplit(".", 1)[-1] if view else ""
    if (module in ASSOCIATION_ONLY_MODULES or request.endpoint in ASSOCIATION_ONLY_ENDPOINTS) \
            and not is_association():
        return error_response("association_only", "Réservé aux associations.", 403)
```

- **Test exhaustif** : il parcourt `app.url_map`. Toute route de ces modules, appelée sur une instance SCI, répond 403. C'est le même principe que `test_every_api_write_route_is_refused_to_accountant`.
- **Les vues HTML** (`app/views/*`) des mêmes rubriques suivent la même règle, par un `before_request` du blueprint des vues. La SPA affiche alors sa page « introuvable ».

### 1.3 Écran par écran

| Exigence | Serveur | Client |
|---|---|---|
| A1 Tuile Adhésions | `queries/dashboard.py` : `stats.new_members` vaut `None` hors association, et n'est pas calculé | `DashboardPage` : la tuile s'affiche si `new_members !== null` |
| A2–A3 RNA, signataire | `api/organization.py` : hors association, les clés `rna`, `signatory_*` sont **ignorées** à l'écriture (A10 : rien n'est effacé) | `OrganizationPage` : champ et bloc masqués |
| A4 Associés | Pour une association, `has_associates` est ignoré à l'écriture | bloc masqué si association |
| A5–A6 Formulaire du tiers | `api/entities.py` : hors association, `is_member`, `is_benevole` et la nature du tiers pour les reçus sont ignorés à l'écriture | `EntityForm` : cases, mention « reçu fiscal » et aide HelloAsso masquées. L'adresse reste. |
| A7 Fiche du tiers | Hors association, le détail ne contient ni `work_times`, ni `helloasso`, ni les dates d'adhésion | `EntityDetailPage` : badges, tuiles et sections masqués |
| A8 Clôture | `services/closing.py` : `steps(fy)` et `DECIDED_BEFORE_CLOSE` excluent `dedicated_funds` hors association. Une ligne `closing_steps` existante pour cette étape est ignorée. | `ClosingPage` : l'étape disparaît d'elle-même, puisque la liste vient du serveur |
| A11 Libellés | Libellés neutres | Description de la page Structure selon la structure |

### 1.4 Tests

- Pytest : chaque payload ci-dessus est testé sur une instance association et sur une instance SCI ; un champ d'association envoyé à une SCI est sans effet ; la route 403 ; les étapes de clôture d'une SCI.
- Vitest : `OrganizationPage`, `EntityForm`, `EntityDetailPage` et `DashboardPage` sont rendus avec `chart: "sci"` puis `chart: "asso"`.

---

## 2. G2 — Mentions légales unifiées, NAF, SIREN des tiers

### 2.1 Modèle

**`organization`** (Configuration › Structure), qui devient la seule source des mentions légales :

| Colonne | Type | Statut |
|---|---|---|
| `legal_form` | String(100) | existante |
| `rcs_city` | String(100) | existante (greffe) |
| `share_capital_cents` | Integer, nullable | **nouvelle**, reprise de Facturation |
| `vat_number` | String(20) | **nouvelle**, reprise de Facturation |
| `naf_code` | String(8) | **nouvelle** (« 6820B », tel que Sirene v4 le renvoie, sans point) |
| `naf_nomenclature` | String(12) | **nouvelle** (`NAFRev2` ou `NAF2025`, valeur renvoyée par Sirene) |

**`billing_settings`** : suppression de `legal_form`, `share_capital_cents`, `rcs` et `vat_number`.
Facturation garde le paiement, les textes, le logo et les e-mails.

**`entities`** :

| Colonne | Type | Rôle |
|---|---|---|
| `siren` | String(9), indexée | **nouvelle**. Toujours égale aux 9 premiers chiffres du `siret` s'il y en a un ; peut exister seule. Sert au rapprochement des fournisseurs (D9) et à la mise à jour groupée. |
| `naf_code`, `naf_nomenclature` | comme ci-dessus | **nouvelles** |

### 2.2 Migration `g2…` (après `e2a4c6e8f0b3`)

1. Ajout des colonnes.
2. Reprise de Facturation vers Structure, champ par champ :
   - Structure vide → valeur de Facturation copiée.
   - Les deux remplies et différentes → **Structure garde sa valeur**. La migration écrit un avertissement dans la sortie (`[G2] forme juridique : Structure « X » conservée, Facturation « Y » ignorée`), visible dans les journaux de déploiement.
   - `rcs` (texte libre, « RCS Saintes 840 968 499 ») → `rcs_city` par l'expression `RCS\s+(.+?)(?:\s+[AB])?(?:\s+\d[\d\s]*)?$`. Si le texte ne se lit pas : avertissement, et `rcs_city` reste vide.
3. `entities.siren` = `substr(siret, 1, 9)` pour tout SIRET de 14 chiffres.
4. Suppression des 4 colonnes de `billing_settings` (`batch_alter_table`, SQLite).
5. `downgrade` : recrée les colonnes et y recopie les valeurs de Structure.

### 2.3 Usages à rebrancher

| Endroit | Avant | Après |
|---|---|---|
| `templates/sales/document.html` | `settings.legal_form`, `settings.share_capital_cents`, `settings.rcs`, `settings.vat_number` | `org.*`. La mention RCS est composée par `organization.rcs_mention(org)` : « RCS Saintes 840 968 499 ». |
| `services/sale_documents.py` (facture électronique) | `settings.vat_number` | `org.vat_number` |
| `services/billing.py` | `TEXT_FIELDS`, `readiness` (« TVA (Facturation) »), `save` | Ces champs disparaissent de `TEXT_FIELDS`. `readiness` renvoie « N° de TVA intracommunautaire (Configuration › Structure) ». La validation de la TVA et du capital passe dans `services/organization.py`. |
| `services/lease_documents.py` | `org.rcs_city` + SIREN, recomposé sur place | utilise `organization.rcs_mention(org)` |
| `BillingSettings.tsx` | 4 champs saisis | bloc « Mentions légales » en lecture : les valeurs de Structure et un lien « Modifier dans Structure » |
| `OrganizationPage.tsx` | — | nouveau bloc « Mentions légales » : forme juridique, capital, greffe, TVA intracommunautaire, activité (NAF, code et libellé en lecture) |

- `entities.siren` est tenu à jour au même endroit que `siret` : `api/entities.py`, `purchase_entry`, `purchase_sync`, `counterparties`, l'import Ekylibre. Un helper `entity_identifiers.set_siret(entity, value)` normalise, contrôle (Luhn) et dérive le SIREN.

### 2.4 Tests

- Migration : sur une base de test contenant les deux sources, on vérifie la copie, le cas de conflit, la lecture du RCS libre, le SIREN des tiers et le `downgrade`.
- Facture PDF et facture électronique générées après G2 : mêmes mentions qu'avant pour une base déjà cohérente.
- Bail généré : mention RCS inchangée.

---

## 3. G3 — Service Sirene, nomenclatures, Structure

### 3.1 Configuration (D1)

- `app/config.py` : `SIRENE_API_URL` (par défaut `https://api.insee.fr/api-sirene/4`) et `SIRENE_API_KEY` (vide par défaut).
- La session expose `services: {sirene: bool}`, vrai si la clé est configurée. Le client masque tout ce qui concerne Sirene sinon.
- Pas d'intégration par instance, pas de repli `.env` à gérer : c'est une variable du serveur, comme `MAIL_*`.

### 3.2 `app/services/sirene.py`

**Interface :**

```python
class SireneError(Exception):          # code: not_configured | not_found | busy | unavailable | invalid
    code: str; message: str; retry_after: int | None

def available() -> bool
def legal_unit(siren: str) -> dict                          # GET /etat-courant/unites-legales/{siren}
def establishment(siret: str) -> dict                       # GET /etat-courant/etablissements/{siret}?champs=…
def legal_units(sirens: list[str]) -> dict[str, dict]       # POST unites-legales/multicritere {"siren": [...]} (100 max par appel)
def head_offices(sirens: list[str]) -> dict[str, dict]      # POST etablissements/multicritere {"siren": [...], "etablissementSiege": true}
def establishments(sirets: list[str]) -> dict[str, dict]    # POST etablissements/multicritere {"siret": [...]}
def search(text: str, postal_code: str | None, limit=10) -> list[Candidate]
def proposal(siren: str | None = None, siret: str | None = None) -> Proposal
```

**Appels :**

- **Requêtes** : `requests`, avec l'en-tête `X-INSEE-Api-Key-Integration` et un délai d'attente de 10 s. Les adresses sont demandées explicitement : `champs` inclut `adresseEtablissement`, qui n'est pas renvoyée par défaut.
- **Recherche** (`search`) :
  - 9 ou 14 chiffres, une fois les espaces retirés → `proposal` direct, renvoyé comme candidat unique.
  - Sinon, 1 appel `unites-legales/multicritere` (`denominationUniteLegale`, `etatUniteLegale` actifs, `nombre` = 10), puis :
    - sans code postal : 1 appel `head_offices(sirens)` pour la ville du siège ;
    - avec code postal : 1 appel `etablissements/multicritere` (`siren` = liste, `codePostalEtablissement`, `etatEtablissement` actif), qui renvoie les établissements de ces sociétés dans ce code postal, siège ou non.
  - Au total, 2 appels par recherche.
- **Quota** : `RateLimiter` en mémoire du processus (fenêtres glissantes de 30 requêtes par minute et 2 000 par heure).
  - Un appel interactif qui dépasse le quota lève `SireneError("busy", retry_after=s)` sans appeler l'API.
  - La tâche de fond (G5) attend son tour avec `limiter.wait()`.
  - Un 429 reçu de l'INSEE quand même (autre client de la même clé) donne `busy`, avec un `retry_after` tiré de `x-rate-limit-reset`.
  - Gunicorn tourne avec 1 processus et 4 fils : le limiteur, protégé par un verrou, est partagé. Avec plusieurs processus, il faudrait un stockage commun. C'est noté, hors périmètre.
- **Cache** : dictionnaire à durée de vie de 24 h, indexé sur (route, paramètres), 2 000 entrées au plus, sur le modèle de `geodata.fetch_json`. Les recherches par nom ne sont pas mises en cache, seules les fiches le sont.
- **Erreurs** : 404 → `not_found` ; 400 « doublon » de l'INSEE → `not_found`, avec le numéro valide tiré du message ; autres 4xx ou 5xx et réseau → `unavailable`. Aucune erreur n'est remontée telle quelle à l'écran.

### 3.3 Proposition normalisée

La fonction `proposal(...)` produit un `Proposal` : les champs Lyvre et leurs valeurs, plus des informations annexes.

| Champ Lyvre | Source Sirene |
|---|---|
| `name` | `denominationUniteLegale`. Pour un entrepreneur individuel (catégorie 1000) : `prenomUsuelUniteLegale` + `nomUniteLegale`. Casse d'origine (D5). |
| `siren`, `siret` | SIREN ; SIRET de l'établissement demandé, ou du siège (SIREN + `nicSiegeUniteLegale`) |
| `address_line1` | `numeroVoie` + `indiceRepetition` (B → bis, T → ter, Q → quater) + `typeVoie` + `libelleVoie` |
| `address_line2` | `complementAdresse` |
| `postal_code`, `city`, `country` | `codePostal`, `libelleCommune`, « France » ; ou `libellePaysEtranger` |
| `legal_form` | libellé de `categorieJuridiqueUniteLegale`, tiré de la nomenclature (3.4) |
| `naf_code`, `naf_nomenclature` | `activitePrincipaleUniteLegale` et sa nomenclature (structure) ; celles de l'établissement pour un tiers |
| `vat_number` | `FR` + clé + SIREN, clé = `(12 + 3 × (SIREN mod 97)) mod 97`. Indicateur `computed: ["vat_number"]` (D7). |
| `rna` | `identifiantAssociationUniteLegale` (Structure d'une association seulement) |
| `person_kind` | `individual` si catégorie 1000, sinon `company` (tiers) |

Informations annexes :
- `state` : `active`, ou `ceased` si `etatUniteLegale` = 4 ou l'établissement est fermé (3) ;
- `warnings` : par exemple « diffusion partielle : adresse non communiquée » (`statutDiffusion` = P), ou « établissement fermé, siège proposé » ;
- `labels` : les libellés de forme juridique et de NAF pour l'affichage.

### 3.4 Nomenclatures (B15, B16)

- `app/data/insee/categories_juridiques.json` : niveau III, code → libellé, environ 250 entrées.
- `app/data/insee/naf_rev2.json` et `naf_2025.json` : sous-classes, code → libellé.
- Générées une fois depuis les fichiers publiés par l'INSEE, par `scripts/build_insee_nomenclatures.py`, puis versionnées. Le script est relançable, et la source et la date sont notées en tête de chaque JSON.
- Accès : `services/nomenclatures.py` (`legal_form_label(code)`, `naf_label(code, nomenclature)`). Les fichiers sont chargés à la première demande. Un code inconnu renvoie le code lui-même.

### 3.5 API

| Route | Réponse |
|---|---|
| `GET /api/v1/sirene/search?q=&postal_code=` | `{items: [{siren, siret, name, legal_form, city, postal_code, head_office, active}]}` |
| `GET /api/v1/sirene/proposal?siren=` ou `?siret=` | `{proposal: {...champs}, computed: [...], state, warnings, labels, existing_entity: {id, name} \| null}` |

- Erreurs : `sirene_unavailable` 503 (pas de clé ou API en panne), `sirene_busy` 429 avec `retry_after`, `not_found` 404, `validation_error` 422 (numéro invalide, Luhn).
- Les deux routes sont en lecture et accessibles aussi à l'expert-comptable, mais ses écrans ne montrent pas les boutons (B13).
- `existing_entity` : tiers de l'instance qui a le même SIREN, s'il y en a un (sert à D9 et B8).

### 3.6 Client : composants partagés

- **`components/sirene/SireneProposalModal.tsx`** prend `current` (valeurs du formulaire), `proposal`, `labels`, `computed` et `warnings`, et renvoie par `onApply(values)` les valeurs retenues.
  - Les champs vides sont pré-cochés et regroupés sous « À compléter ».
  - Les champs différents sont listés « Actuel → Sirene », **non cochés**.
  - Les champs identiques ne sont pas affichés.
  - Le modal remplit le formulaire, sans enregistrer (D3).
- **`components/sirene/SireneSearch.tsx`** : une zone texte, un code postal facultatif et un bouton « Rechercher » (ou Entrée). Le résultat est une liste de 10 lignes au plus, et un clic sur une ligne lance la proposition. `busy` affiche « Trop de recherches, réessayez dans N s ». Il n'y a pas de recherche à la frappe.
- **`useSirene()`** : disponibilité (session), plus les mutations `search` et `proposal` (TanStack Query, sans cache côté client au-delà de la session).

### 3.7 Structure (B1–B3)

- À côté du SIREN, le bouton « Compléter depuis Sirene » s'active quand le SIREN est valide (Luhn, calculé côté client).
- Il ouvre `SireneProposalModal`.
- Pour une unité cessée, un message s'affiche et aucun champ n'est proposé.
- Le greffe (`rcs_city`) n'est pas dans Sirene : le modal le rappelle (« le greffe et le capital restent à saisir »).

---

## 4. G4 — Tiers et factures d'achat

### 4.1 Formulaire du tiers (B4–B8)

- En tête du formulaire, un bloc repliable « Rechercher dans Sirene » (`SireneSearch`). Un candidat choisi ouvre `SireneProposalModal` avec les valeurs du formulaire.
- Si `existing_entity` existe et n'est pas le tiers en cours, une alerte s'affiche : « Ce SIREN est déjà le tiers X », avec un lien (B8). Le nom en double est aussi contrôlé à l'enregistrement, par la contrainte d'unicité existante (message clair).
- Nouveaux champs du formulaire : SIREN (lecture, dérivé du SIRET) et activité (NAF : code saisi, libellé affiché).

### 4.2 Facture d'achat (D9, B19)

Dans le bloc Fournisseur de `PurchaseFormPage`, à côté de la liste des tiers : « Chercher dans Sirene ». Une fois le candidat choisi :
- si `existing_entity` existe : `entity_id` = ce tiers, et une ligne d'information s'affiche (« Fournisseur connu : X ») ;
- sinon : `entity_id = "new"`, et `new_name`, `supplier_siret` et `supplier_vat` (calculée) sont remplis. Les autres champs, comme l'adresse et le NAF, sont transmis dans `new_entity` (objet facultatif du corps).
- `services/purchase_entry.py` applique `new_entity` **seulement** à la création du tiers, au moment de l'enregistrement de la facture. C'est la confirmation demandée par B19. Un tiers existant n'est jamais modifié depuis ici.
- Le rapprochement existant par SIRET ou TVA (`purchase_sync`, `counterparties`) gagne la comparaison par `entities.siren`.

---

## 5. G5 — Mise à jour groupée des tiers (D8, B17)

### 5.1 Parcours

1. **Liste des tiers** : `DataGrid` avec sélection (déjà utilisé par Ventes et Adhérents). L'action « Mettre à jour depuis Sirene » porte sur la sélection, ou sur tous les tiers qui ont un SIREN si rien n'est sélectionné, avec le nombre affiché.
2. **Tâche de fond** `sync_jobs.start(kind="sirene_refresh")` :
   - Elle lit les SIREN et SIRET par paquets de 100, avec 3 appels par paquet : `legal_units`, `establishments` pour les tiers qui ont un SIRET, `head_offices` pour ceux qui n'ont qu'un SIREN.
   - Elle calcule, pour chaque tiers, les différences avec la base.
   - Elle range le tout dans `sync_jobs.result` (JSON) et avance sa progression tiers par tiers.
   - Elle attend le limiteur de débit au besoin.
   - Elle peut être arrêtée : un indicateur d'annulation est vérifié entre deux paquets.
3. **Notification** de fin (mécanisme existant), puis l'**écran de revue** `/entities/sirene-review/:jobId`. Il présente, tiers par tiers :
   - les champs à compléter, pré-cochés ;
   - les champs différents, non cochés ;
   - et en dessous, les tiers cessés, introuvables ou au numéro invalide (statut seul, aucune modification possible).
4. **« Appliquer la sélection »** : `POST /api/v1/entities/sirene-refresh/<job_id>/apply` avec `{changes: {entity_id: [champs]}}`.
   - Un champ dont la valeur en base a changé depuis la revue est **sauté** et signalé (verrou optimiste : la valeur « actuelle » de la revue est comparée à la base).
   - Le nom en double est sauté, avec un motif.
   - Une seule transaction ; réponse `{applied, skipped: [{entity_id, field, reason}]}`.
5. **« Abandonner »** ferme la revue. Le job garde son résultat jusqu'à son expiration normale (purge existante des jobs), ce qui permet de revenir à la revue tant que la notification existe.

### 5.2 Ordre de grandeur

50 tiers = 1 paquet = 3 appels, soit quelques secondes. Le quota ne se fait sentir qu'à partir d'environ 1 000 tiers.

### 5.3 API

| Route | Rôle |
|---|---|
| `POST /api/v1/entities/sirene-refresh` `{entity_ids?: number[]}` | `{job_id}` ; 409 si une mise à jour est déjà en cours dans l'instance |
| `GET /api/v1/entities/sirene-refresh/<job_id>` | `{status, progress, items: [{entity_id, name, state, changes: [{field, label, current, proposed, computed}]}]}` |
| `POST /api/v1/entities/sirene-refresh/<job_id>/apply` | voir 5.1, étape 4 |
| `POST /api/v1/entities/sirene-refresh/<job_id>/cancel` | arrête la tâche |

Ces routes sont refusées à l'expert-comptable, sauf la consultation (GET).

---

## 6. Exigences transverses

- **Tests sans réseau (B12)** :
  - Une fixture `sirene_api` remplace `sirene._post` et `sirene._get` par des réponses enregistrées dans `tests/fixtures/sirene/`.
  - Ces réponses sont des données **publiques et non personnelles** (l'INSEE, unités légales d'organismes publics) ou fabriquées.
  - Le limiteur est testé avec une horloge simulée.
  - La garde `requests` existante des tests (aucun appel réseau) continue de s'appliquer.
- **Sécurité (B9)** :
  - La clé ne sort jamais du serveur et n'apparaît pas dans les journaux. Les messages d'erreur sont filtrés : en-tête retiré des exceptions `requests` journalisées.
  - Les routes Sirene exigent une session et une instance, comme le reste de l'API.
- **Documentation (B14)** : `doc/docker.md` (tableau des variables, à côté de `MAIL_*`) et `.env.example`. Sur Lyvre, `SIRENE_API_KEY` s'ajoute dans l'onglet Environment, au déploiement de G3.
- **Bêta de l'API v4** : la route de base est configurable, et tout le format est contenu dans `services/sirene.py` (normalisation). Un changement de l'INSEE ne touche que ce fichier et ses fixtures.

## 7. Points laissés à l'implémentation

- La liste exacte des endpoints « fonds dédiés » dans `ASSOCIATION_ONLY_ENDPOINTS`. Elle est relevée par le test exhaustif de G1.
- Code NAF : stocké sans point, comme Sirene v4 le renvoie (« 8411Z », vérifié). L'affichage ajoute le point (« 84.11Z »), et les nomenclatures sont indexées sans point.
- La purge des jobs : vérifier sa durée dans `sync_jobs` ; si elle est trop courte pour une revue, garder le résultat 7 jours.
