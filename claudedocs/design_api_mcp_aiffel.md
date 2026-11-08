# Accès API par clé et serveur MCP pour Aiffel : conception

> Statut : **conception** (08/11/2026, /sc:design). Besoins : `claudedocs/besoins_api_mcp_aiffel.md` (A1 à A7, Q1 à Q6).
> Lots proposés : AK1 à AK4 (§ 10). Prochaine étape : validation des décisions D1 à D9, puis /sc:implement AK1.

## 1. Vue d'ensemble

```
                 Authorization: Bearer lyv_<id>_<secret>
 Aiffel ───────────────────────────────────────────────┐
 (client MCP)   POST {APP_BASE_URL}/mcp   (JSON-RPC)   │
 script, Fourmy GET  /api/v1/...          (REST)       │
                POST /api/v1/agent/tools/<outil>       │
                                                       ▼
 ┌──────────────────────────── Flask (gunicorn gthread) ────────────────────────────┐
 │ 1. api_auth.authenticate (before_request, avant CSRF et tenant)                  │
 │    clé → méta `api_keys` → utilisateur + instance + domaines → g.api_key          │
 │ 2. CSRF : ignoré si g.api_key (pas de cookie, pas de session)                    │
 │ 3. tenant._select_tenant : instance = celle de la clé ; rôle revérifié           │
 │ 4. api_auth.authorize : route → domaine (lecture/écriture) ; limites ; journal  │
 │                                                                                  │
 │  /mcp ─► mcp_server (JSON-RPC 2.0) ─┐                                             │
 │  /api/v1/agent/tools/<n> ───────────┼─► agent_tools (registre par domaine)        │
 │                                     │     lecture : outils de l'assistant (réutilisés)│
 │                                     │     écriture : brouillons (achats, tiers, OD) │
 │  /api/v1/... (GET) ─► vues existantes, filtrées par domaine                      │
 │                                     ▼                                             │
 │                 services existants (purchase_entry, attachments, ledger…)         │
 └──────────────────────────────────────────────────────────────────────────────────┘
   méta-base : api_keys            base de l'instance : api_calls, colonnes d'origine
```

Principes :
- **Un seul chemin d'écriture** : les outils d'agent (MCP et REST) appellent les mêmes services que l'interface.
- **Refus par défaut** : une route ou un outil sans domaine déclaré est refusé à une clé.
- **Aucune session** : une requête par clé ne lit ni n'écrit le cookie de session.

## 2. Décisions

| # | Décision | Motif |
|---|---|---|
| D1 | **Serveur MCP écrit dans Flask** (JSON-RPC 2.0 sur `POST /mcp`, transport HTTP streamable en mode **sans état, réponses JSON**, sans SSE), sans le SDK `mcp`. | Le SDK officiel est ASGI (Starlette) : il faudrait un second serveur à côté de gunicorn (WSGI). Le sous-ensemble utile (`initialize`, `ping`, `tools/list`, `tools/call`) tient en environ 200 lignes. La spécification permet de répondre en `application/json` sans flux SSE. Le SDK sert de client de référence dans les tests. |
| D2 | **REST par clé : lecture seulement (GET)** sur les domaines lus. Les écritures passent toutes par les **outils d'agent** : `tools/call` en MCP, ou `POST /api/v1/agent/tools/<outil>` en REST. | Les routes d'écriture de l'interface comptabilisent, valident ou envoient (exemple : `POST /purchases` comptabilise aussitôt). Les ouvrir une à une serait fragile. Les outils garantissent « brouillon seulement » à un seul endroit. |
| D3 | Une facture d'achat créée par clé **n'est pas comptabilisée** tant qu'un humain ne l'a pas marquée **vérifiée**. `purchase_state` renvoie « à compléter » avec le motif « Saisie par « Aiffel — terrain » : à vérifier ». | `post_ready` et « Comptabiliser les factures prêtes » balayeraient sinon ces factures. Le contrôle humain est exigé par A1. |
| D4 | Une écriture en brouillard créée par clé (outil `create_entry_draft`) est une **écriture non validée**, comme une saisie manuelle. Elle porte l'origine et compte dans « À traiter » jusqu'à sa validation. | La validation existante (numéro, lot) est le contrôle humain. |
| D5 | **Clés dans la méta-base** (`api_keys`) ; **journal et origine dans la base de l'instance** (`api_calls`, colonnes `origin_*`). | La clé doit être vérifiée avant le choix de l'instance. Le journal et les objets restent dans la structure (sauvegarde, restauration, isolement). |
| D6 | Format de clé `lyv_<id public 10>_<secret 32 octets base64url>` ; seule l'**empreinte SHA-256** du secret est stockée ; comparaison `hmac.compare_digest`. | Le secret, aléatoire et long, n'a pas besoin d'un hachage lent. L'id public permet de retrouver la clé sans balayer la table et s'affiche comme « préfixe ». |
| D7 | Débit par minute **en mémoire** (fenêtre glissante, par processus) ; plafond quotidien de créations **compté dans `api_calls`**. | La production tourne avec un seul processus gunicorn (`-w 1`, 8 fils). Le plafond quotidien doit survivre à un redémarrage. |
| D8 | URL MCP = `APP_BASE_URL` + `/mcp` (réglage existant : `app.lyvre.org` en production, `lyvre.org` en essai). | Q6 : paramétrable, et c'est déjà le réglage des liens des e-mails (mot de passe oublié, résumé de l'échéancier). |
| D9 | Pièce jointe : **10 Mo** (limite actuelle de `attachments`), en base64 dans l'appel d'outil ou déposée avant par `POST /api/v1/agent/files` (multipart) qui rend un jeton. Jamais par URL. | Une URL de téléchargement ouvrirait une faille SSRF. Les besoins disaient 20 Mo : on garde la limite commune. |

## 3. Modèle de données

### 3.1 Méta-base : `api_keys` (créée par `seed_meta.py`, `create_all(bind_key="meta")`)

| Colonne | Type | Rôle |
|---|---|---|
| `id` | int PK | |
| `public_id` | str(10), unique, index | Partie visible (`lyv_<public_id>_…`) |
| `secret_hash` | str(64) | SHA-256 hexadécimal du secret |
| `instance_id` | FK `instances.id`, cascade | Structure de la clé |
| `user_id` | FK `users.id`, cascade | Utilisateur rattaché : la clé ne dépasse jamais son rôle |
| `name` | str(80) | Usage (Q4) : « Aiffel — saisie terrain » ; c'est aussi le badge d'origine |
| `read_domains` | text (JSON, liste) | Domaines lus |
| `write_domains` | text (JSON, liste) | Domaines écrits, sous-ensemble de `read_domains` |
| `rate_per_minute` | int, 60 | Débit |
| `creations_per_day` | int, 200 | Plafond de créations |
| `expires_at` | datetime | Par défaut création + 1 an, au plus 2 ans |
| `revoked_at`, `revoked_by_id` | datetime, FK users | Révocation |
| `created_at`, `created_by_id` | | |
| `last_used_at` | datetime | Mis à jour au plus une fois par minute |

État calculé : `active`, `expired` ou `revoked`.

### 3.2 Base de l'instance (migration Alembic `ak1_…`)

**`api_calls`** (journal, R6 et R7) :

| Colonne | Type | Rôle |
|---|---|---|
| `id` | int PK | |
| `key_id` | int, index | Id de la clé dans la méta-base (pas de clé étrangère : autre base) |
| `at` | datetime, index | Moment de l'appel |
| `channel` | str(4) | `mcp` ou `rest` |
| `target` | str(80) | Nom de l'outil, ou endpoint Flask |
| `domain` | str(20) | Domaine de l'appel |
| `access` | str(5) | `read` ou `write` |
| `status` | int | Code HTTP, ou 200 / 4xx équivalent pour un outil MCP |
| `error` | str(300) | Message de refus, sans données sensibles |
| `object_type`, `object_id` | str(20), int | Objet créé (`purchase`, `entity`, `journal_entry`) |
| `idempotency_key` | str(80), index | Clé d'idempotence reçue ; unique avec `key_id` quand elle est renseignée |
| `duration_ms` | int | Durée de l'appel |

Purge : lignes de plus de 180 jours supprimées à la première écriture de chaque jour, ce qui couvre l'exigence de 90 jours.

**Colonnes d'origine** sur `purchases`, `entities` et `journal_entries` :

| Colonne | Type | Rôle |
|---|---|---|
| `origin_key_id` | int, null | Clé qui a créé l'objet |
| `origin_label` | str(80) | Nom de la clé au moment de la création (le badge reste lisible après révocation) |
| `external_ref` | str(120), index, null | Référence externe (Q5) : `fourmy:<type>/<id>`, unique par table quand renseignée |
| `checked_at`, `checked_by_id` | datetime, int | `purchases` et `entities` seulement : vérification humaine (D3) |

## 4. Domaines (réponse à Q1)

Clés stables. La colonne « Écriture v1 » liste ce qui ouvre la case écriture.

| Clé | Libellé | Structures | Lecture : outils et routes | Écriture v1 |
|---|---|---|---|---|
| `accounting` | Comptabilité | toutes | `get_balances`, `search_entries`, `get_closing_checks` ; GET `entries`, `journals`, `chart`, `reports`, `fiscal_years`, `lettering`, `analytic`, `simple_reports`, `simple_operations`, `simple_categories` | `create_entry_draft` |
| `bank` | Banque | toutes | `get_bank_accounts`, `list_bank_transactions` ; GET `bank_accounts`, `bank_statements`, `reconciliation`, `cash`, `cash_forecast` | aucune |
| `purchases` | Achats | toutes | `list_purchases`, `get_purchase` ; GET `purchases`, `receipts`, `coop_statements`, `rfa` | `create_purchase_draft`, `attach_document` |
| `sales` | Ventes | toutes | `list_sales` ; GET `sales`, `subscriptions`, `payouts`, `ereporting` | aucune (A5) |
| `parties` | Tiers | toutes | `find_party` ; GET `entities`, `members`, `associates`, `share_movements`, `leases`, `sirene` | `create_supplier` |
| `tax` | TVA et fiscal | toutes | `get_vat`, `get_tax_result`, `get_msa`, `get_parameter` ; GET `vat_returns`, `vat_books`, `tax_result`, `tax_profiles`, `msa`, `regulatory` | aucune |
| `assets` | Immobilisations et stocks | toutes | `list_assets` ; GET `assets`, `stock` | aucune |
| `agronomy` | Agronomie | agri | `get_margins`, `get_aids` ; GET `aids`, `analytic` (marges), `work_times` | aucune (A5) |
| `agenda` | Échéancier | toutes | `get_agenda`, `get_deadline_fiche` ; GET `agenda`, `checklists` | aucune |
| `documents` | Documents | toutes | `get_document` (métadonnées et lien) ; GET `documents` | aucune |

Règles :
- `get_context`, `list_calculators` et `run_calculator` : toujours permis à une clé valide, car ils ne révèlent pas de données sensibles du dossier (le contexte est indispensable à l'agent).
- Routes **jamais** ouvertes à une clé, quels que soient ses domaines : `session`, `users`, `instances`, `access`, `integrations`, `data_import`, `imports`, `ekylibre`, `odoo`, `brevo`, `assistant`, `notifications`, `organization` en écriture, et tout endpoint `api_keys_*`.
- Le classement vit dans `app/services/api_domains.py` : `MODULE_DOMAINS` (module `app.api.*` → domaine ou `None` pour « jamais »). Un **test** échoue si un module de `app/api` n'y figure pas : aucune route nouvelle n'est ouverte par oubli.
- Un domaine absent du plan de la structure (`agronomy` hors agri) n'est pas proposé à la création de la clé ; il est ignoré à l'exécution.

## 5. Authentification et autorisation

### 5.1 Ordre des hooks (`app/__init__.py`)
1. `api_auth.authenticate` (nouveau, enregistré **avant** `csrf.init_app` et `register_tenant_hooks`) :
   - s'applique seulement à `/api/v1/*` et `/mcp` portant `Authorization: Bearer lyv_…` ;
   - découpe `public_id` et secret, charge la clé (méta), vérifie l'empreinte en temps constant, puis refuse si la clé est révoquée ou expirée, l'utilisateur inactif, l'instance inactive, ou si l'utilisateur n'a plus accès (`role_for(user, instance)` vaut None) ;
   - tout refus donne **401** `invalid_api_key`, avec un message générique et un en-tête `WWW-Authenticate: Bearer` ;
   - en cas de succès : `g.api_key` (objet détaché : id, nom, domaines, limites), `login_manager` `_update_request_context_with_user(user)` sans `login_user` (pas de cookie), et `g.skip_session_save = True`.
2. CSRF : `WTF_CSRF_CHECK_DEFAULT = False` et un `before_request` qui appelle `csrf.protect()` sauf si `g.api_key` ou si la vue est exemptée. La protection de l'interface ne change pas.
3. `_select_tenant` : branche `g.api_key` : instance = `g.api_key.instance_id`, rôle = `role_for(...)`. Pas de `flask_session`, et `must_change_password` n'est pas contrôlé pour une clé.
4. `api_auth.authorize` (sur le blueprint `api` et la vue `/mcp`) :
   - REST : méthode autre que GET → 403 `read_only_key`, sauf `agent_*` ; domaine de l'endpoint absent des domaines lus → 403 `domain_forbidden` avec `extra={"domain": "bank"}` ;
   - limites (§ 7), puis journal en `after_request`.
5. La session n'est pas enregistrée : `SessionInterface` dérivée dont `should_set_cookie` renvoie False si `g.skip_session_save`.

### 5.2 Droits effectifs
- `read = key.read_domains ∩ domaines de la structure`.
- `write = key.write_domains ∩ read`, vide si le rôle de l'utilisateur est `accountant`. Le contrôle est fait **à chaque appel**, pas seulement à la création : un utilisateur rétrogradé perd l'écriture aussitôt.
- La création d'une clé avec écriture pour un expert-comptable est refusée en 422 (récit 6).

## 6. Serveur MCP (`app/mcp/server.py`, vue `POST /mcp`)

- **Transport** : HTTP streamable sans état.
  - `POST` reçoit un message JSON-RPC (ou un lot) et répond en `application/json`.
  - Une notification seule (`notifications/initialized`) reçoit 202 sans corps.
  - `GET` et `DELETE` reçoivent 405 : pas de flux serveur, pas de session.
  - En-tête `MCP-Protocol-Version` accepté : 2025-03-26, 2025-06-18, 2025-11-25.
  - Contrôle de `Origin` s'il est présent : il doit être absent ou égal à `APP_BASE_URL`, contre le rebinding DNS.
- **`initialize`** :
  - renvoie `serverInfo {name: "lyvre", version}` et `capabilities {tools: {listChanged: false}}` ;
  - `instructions` en français : nom de la structure, type, exercice en cours, domaines de la clé, règle « Toute création est un brouillon que l'utilisateur vérifie dans Lyvre ; ne promets jamais qu'une saisie est comptabilisée », montants en euros avec virgule.
- **`tools/list`** : outils des domaines lus, plus les outils d'écriture des domaines écrits. Chaque outil a `name`, `title`, `description`, `inputSchema`, et des `annotations` : `readOnlyHint` pour la lecture, `destructiveHint: false` et `idempotentHint` pour les créations avec clé d'idempotence.
- **`tools/call`** : passe par `agent_tools.run(name, args, key)`.
  - Le résultat est `content: [{type: "text", text: <JSON>}]` plus `structuredContent`.
  - Une erreur métier rend `isError: true` avec un message français ; un outil hors domaine aussi (récit 2), avec le code `domain_forbidden`.
- **Erreurs JSON-RPC** : `-32600` (requête invalide), `-32601` (méthode inconnue), `-32602` (arguments).
- **Limites** : un dépassement rend une erreur JSON-RPC `-32000` avec `data {retry_after}`, et la réponse HTTP est 429 avec `Retry-After`.

Configuration côté Aiffel (affichée une fois avec la clé) :

```json
{ "mcpServers": { "lyvre": { "type": "http", "url": "https://app.lyvre.org/mcp",
    "headers": { "Authorization": "Bearer lyv_k3f9a2b7cd_…" } } } }
```

## 7. Outils d'agent (`app/services/agent_tools.py`)

### 7.1 Registre
- `AgentTool(name, domain, access, description, schema, handler, idempotent=False)`.
- Les outils de lecture **enveloppent** ceux de `assistant/tools.py` : même handler, même schéma, et un domaine en plus.
- Nouveaux outils de lecture :

| Outil | Domaine | Contenu |
|---|---|---|
| `list_purchases` | `purchases` | Factures d'achat filtrées (à payer, échues, à compléter, période, fournisseur), au plus 50 |
| `get_purchase` | `purchases` | Une facture : lignes, état, règlements, lien |
| `get_bank_accounts` | `bank` | Comptes, solde, date du dernier relevé |
| `list_bank_transactions` | `bank` | Transactions filtrées, au plus 50 |
| `list_sales` | `sales` | Pièces de vente filtrées, au plus 50 |
| `find_party` | `parties` | Recherche d'un tiers par nom, SIREN, numéro de TVA ou e-mail |
| `list_assets` | `assets` | Immobilisations |
| `get_document` | `documents` | Métadonnées et lien d'une pièce |

- Tout résultat porte `url` (lien absolu `APP_BASE_URL` vers l'écran Lyvre) quand l'objet a une page.

### 7.2 `create_purchase_draft` (domaine `purchases`, écriture)

Arguments :

| Argument | Contenu |
|---|---|
| `supplier` | Objet `{name?, siren?, siret?, vat_number?, party_id?}` |
| `issue_date`, `due_date?` | Dates AAAA-MM-JJ |
| `total` (TTC), `untaxed?`, `tax?` | Montants en euros, chaîne « 1 200,00 » ou nombre |
| `invoice_number?` | Numéro de la facture |
| `lines?` | `[{label, amount_untaxed?, amount?, vat_rate?, account?, product?}]` |
| `file?` | `{name, content_base64}`, ou `file_token` (§ 2 D9) |
| `note?` | Texte libre |
| `external_ref?` | Référence externe (`fourmy:…`) |
| `idempotency_key?` | Clé d'idempotence |

Déroulé :
1. **Idempotence** : une `external_ref` déjà présente sur une facture, ou un `idempotency_key` déjà dans `api_calls` pour cette clé, renvoie l'objet existant (`created: false`) sans rien écrire.
2. **Plafond quotidien** (§ 8).
3. **Pièce** : `attachments.stage_bytes`, puis `purchase_entry.read_staged` (Factur-X, OCR existant). Ce qui est lu **complète** les arguments ; les arguments l'emportent.
4. **Fournisseur** :
   - `party_id`, ou rapprochement existant (`purchase_sync.match_entity` par SIRET, TVA ou nom) ;
   - sinon, si le domaine `parties` est écrit, création comme `create_supplier` ;
   - sinon, facture sans fournisseur (« Fournisseur à rattacher »).
5. **Contrôle** : `purchase_entry.validate_header`, puis lignes par défaut si absentes (`proposed_lines`, comme la saisie manuelle).
6. **Création** : `purchase_entry.create(..., post=False)`. C'est un nouveau paramètre : sans `post_ready`. Il pose `origin_*` et `external_ref`.
   - Un doublon possible (`purchase_entry.duplicates`) **n'arrête pas** la création : la facture reçoit le motif « Doublon possible de … » et le résultat l'indique.
7. **Résultat** : `{created, purchase_id, url, state: "à vérifier", reasons: [...], supplier: {id, name, created}, warnings}`.

Une dépense sans facture (Q3) passe par le même outil : la pièce est le ticket, et `invoice_number` peut être vide.

### 7.3 `create_supplier` (domaine `parties`, écriture)
- Arguments : `name`, `siren?`, `siret?`, `vat_number?`, `email?`, `external_ref?`.
- Si un SIREN ou un SIRET est donné : lecture Sirene (`sirene.search`) pour compléter la raison sociale, l'adresse et le code NAF.
- Refus si un tiers de même SIREN ou de même nom existe : le résultat renvoie le tiers existant (`created: false`).
- Compte fournisseur : comme `clean_new_entity` (compte collectif ou auxiliaire selon le plan).
- Le tiers créé porte `origin_*`, avec `checked_at` vide (« à vérifier »).

### 7.4 `create_entry_draft` (domaine `accounting`, écriture)
- Mêmes contrôles que `propose_entry` : exercice ouvert, journal, comptes, équilibre.
- Création réelle d'une **écriture non validée** par le service des écritures, avec garde de période.
- Plus `origin_*` et `external_ref`.

### 7.5 `attach_document` (domaine `purchases`, écriture)
- Ajoute la pièce à une facture d'achat **créée par une clé et pas encore vérifiée**. Refus sinon.

### 7.6 Exécution commune
- `agent_tools.run` :
  1. contrôle du schéma (repris de `assistant.tools.run`) et du domaine ;
  2. une transaction par appel : commit en cas de succès, rollback en cas d'erreur ;
  3. `LedgerGuardError` et `LedgerError` deviennent des messages ;
  4. résultat tronqué à 20 000 caractères ;
  5. inscription au journal.

## 8. Limites (R7)
- **Débit** : `RateLimiter` en mémoire, un deque d'horodatages par `key_id` protégé par un verrou.
  - Au-delà de `rate_per_minute` : 429 `rate_limited`, `Retry-After` en secondes, message « Trop de requêtes pour la clé « … » : réessayez dans N s ».
  - Le refus est inscrit au journal (sans compter dans le débit).
- **Créations** : avant un outil d'écriture, compte des `api_calls` du jour (heure de Paris) avec `object_id` non nul pour cette clé.
  - Au-delà de `creations_per_day` : 429 `daily_cap`. La lecture continue (récit 7).

## 9. Interface

### 9.1 Configuration › Accès API (`/settings/api-keys`, administrateur de l'instance)
- **Liste** : nom, utilisateur, préfixe `lyv_k3f9a2b7cd_…`, domaines (pastilles L / É), dernier usage, expiration, état. Actions : Modifier, Révoquer, Journal.
- **Création** (fenêtre) :
  - nom de l'usage, utilisateur (membres de la structure) ;
  - grille des domaines (lignes = domaines du plan, colonnes Lecture / Écriture) : cocher Écriture coche Lecture, et Écriture est grisé pour un expert-comptable ou un domaine sans écriture en v1 ;
  - expiration (1 an par défaut, au plus 2 ans), limites (repliées, avec valeurs par défaut).
- **Clé créée** : affichée une seule fois, avec un bouton Copier, l'URL MCP (`APP_BASE_URL/mcp`) et le bloc de configuration (§ 6). Avertissement : « Cette clé ne sera plus affichée. »
- **Journal** (tiroir) :
  - les 200 derniers appels (date, canal, outil ou route, domaine, résultat, lien vers l'objet créé) ;
  - filtres : refus seulement, créations seulement.
- **Mes clés** : un utilisateur non administrateur voit dans son profil les clés rattachées à lui, et peut les révoquer.

### 9.2 Origine et vérification
- **Badge** : `IconTile` « bot » avec `origin_label`, sur la liste des achats, la fiche d'achat, la liste des écritures et la fiche tiers.
- Le filtre « Saisies par clé » est ajouté à la liste des achats.
- **Fiche d'achat** créée par clé et non vérifiée : bandeau « Saisie par « Aiffel — saisie terrain » le 08/11/2026 : vérifiez puis marquez vérifiée ». Le bouton **Marquer vérifiée** pose `checked_at`, puis comptabilise si la facture est prête (`post_ready`). Enregistrer l'en-tête modifié ne vaut pas vérification.
- **Fiche tiers** créé par clé : bouton « Marquer vérifié ».
- **« À traiter »** (`AttentionCard`) : ligne « N saisies par clé à vérifier ». Elle compte les achats et les tiers non vérifiés, et les écritures d'origine clé non validées ; elle mène à la liste filtrée.

### 9.3 Documentation
- `GET /api/v1/agent/tools` : liste des outils, filtrée par la clé appelante, avec les schémas (pour un script REST).
- Page **Aide › API et MCP** (`/help/api`) : générée à partir de `MODULE_DOMAINS` et du registre `agent_tools`. Elle donne l'adresse MCP de l'installation, l'authentification, les domaines et les outils.

## 10. Lots

| Lot | Contenu | Tests principaux |
|---|---|---|
| **AK1 Clés et REST** | `api_keys` (méta), `api_auth` (authentification, CSRF, tenant, session), `api_domains` (+ test d'exhaustivité), GET par domaine, routes `api_keys_*` (CRUD, révocation), écran Configuration › Accès API (liste, création, affichage unique, révocation) | Clé valide, révoquée, expirée ; utilisateur retiré ; instance de la clé ; 403 hors domaine ; 403 sur POST ; pas de cookie de session ; expert-comptable sans écriture ; exhaustivité de `MODULE_DOMAINS` |
| **AK2 Serveur MCP et lecture** | `/mcp` (JSON-RPC), `agent_tools` (lecture : outils de l'assistant + nouveaux), `GET /api/v1/agent/tools`, `POST /api/v1/agent/tools/<n>` | `initialize`, `tools/list` filtré, `tools/call` hors domaine ; client de référence `mcp` (SDK Python, dépendance de test) en HTTP streamable ; Origin |
| **AK3 Écriture en brouillon** | Migration (`api_calls`, `origin_*`, `external_ref`, `checked_*`), `create_purchase_draft`, `create_supplier`, `create_entry_draft`, `attach_document`, `POST /agent/files`, `purchase_state` (D3), « Marquer vérifiée », badges, ligne « À traiter » | Récit 3 (photo → facture à vérifier, non comptabilisée) ; idempotence par `external_ref` et `idempotency_key` ; « Comptabiliser les prêtes » ignore les non vérifiées ; récit 4 |
| **AK4 Journal, limites, aide** | Journal (`after_request`, purge), tiroir Journal, `RateLimiter`, plafond quotidien, `last_used_at`, Mes clés, page d'aide | Récits 5 et 7 ; Retry-After ; purge |

### Réalisé

**AK1 (08/11/2026)** :
- Modèle et services :
  - `app/models/api_key.py` (méta, créé par `seed_meta.py` via `create_all`) ;
  - `app/services/api_keys.py` (jeton, vérification, droits effectifs, création, modification, révocation) ;
  - `app/services/api_domains.py` (domaines, classement des modules).
- Authentification : `app/api_auth.py` (authentification, CSRF sauf clé, session sans cookie, `authorize`), branche clé de `app/tenant.py`.
- Routes : `app/api/api_keys.py` (`/api-keys`, `/api-keys/<id>`, `/api-keys/<id>/revoke`, `/me/api-keys`).
- Écran : Configuration › Accès API (`features/apiKeys`).
- Tests : `tests/api/test_api_keys.py` (10 tests), `apiKeys.test.ts`.
- Mise en production : lancer `seed_meta.py`, comme le fait déjà l'entrypoint Docker, pour créer `api_keys`.

**AK2 (08/11/2026)** :
- `app/mcp_server.py` : `POST /mcp`, JSON-RPC 2.0, sans état. Méthodes `initialize` (instructions de la structure), `ping`, `tools/list`, `tools/call` ; lots de messages ; notifications reçues en 202. `GET` et `DELETE` répondent 405. Contrôles : `Origin`, `MCP-Protocol-Version`.
- `app/services/agent_tools.py` : registre par domaine.
  - 14 outils de l'assistant repris.
  - 7 outils nouveaux : `list_purchases`, `get_purchase`, `get_bank_accounts`, `list_bank_transactions`, `list_sales`, `find_party`, `list_assets`.
  - Contrôle des arguments par le schéma. Une lecture est toujours annulée en fin d'appel (rollback).
- `app/api/agent.py` : `GET /api/v1/agent/tools`, `POST /api/v1/agent/tools/<outil>`, par clé seulement.
- Tests :
  - `tests/api/test_mcp.py` (8 tests) ;
  - `tests/api/test_mcp_reference_client.py` : client officiel `mcp` 2.3.0 en HTTP réel. Le SDK n'est pas dans `requirements.txt` ; le test est sauté sans lui.
- Essai sur les données d'essai locales : les 21 outils répondent.

**AK3 (08/11/2026)** :
- Migration `a2c4e6f8b1d3` :
  - table `api_calls` ;
  - `origin_key_id`, `origin_label`, `external_ref` sur `purchases`, `entities` et `journal_entries` ;
  - `checked_at` et `checked_by_id` sur `purchases` et `entities`.
- `app/services/agent_writes.py` : `create_purchase_draft` (lecture de la pièce, fournisseur retrouvé ou créé si `parties` est écrit, lignes proposées, note et doublon dans `review_reason`), `attach_document`, `create_supplier` (Sirene), `create_entry_draft` (écriture non validée).
  - Idempotence par `external_ref` ou `idempotency_key`.
- Exécution (`agent_tools.run`) :
  - une écriture refusée est annulée ;
  - toute écriture est inscrite dans `api_calls`, y compris un refus ;
  - le contrôle de schéma accepte les types multiples (texte ou nombre).
- `purchase_entry.create(post=False, origin=…)`. Dans `purchase_state`, le motif « à vérifier » empêche la comptabilisation, y compris par « Comptabiliser les factures prêtes ».
- `app/services/agent_review.py`, routes de vérification :
  - `POST /purchases/<id>/check` : marquée vérifiée, puis comptabilisée si elle est prête ;
  - `POST /tiers/<id>/check`.
- Données ajoutées : `origin` dans les données des achats, des tiers et des écritures ; filtre `from_key=1` sur les achats ; `agent` dans le tableau de bord.
- `POST /api/v1/agent/files` : dépôt d'une pièce, qui rend un jeton.
- Interface :
  - `OriginBadge` (liste et fiche d'achat, fiche tiers, fiche écriture) ;
  - bandeau et bouton « Marquer vérifiée » sur la fiche d'achat, « Marquer vérifié » sur la fiche tiers ;
  - filtre « Saisies par clé à vérifier » ;
  - ligne « À traiter » du tableau de bord.
- Tests :
  - `tests/api/test_agent_writes.py` (10 tests, dont le garde-fou « aucun outil d'écriture ne comptabilise, ne valide ni n'envoie ») ;
  - `OriginBadge.test.tsx`.

## 11. Sécurité (contrôle)
- Le secret ne transite que dans l'en-tête. La clé n'apparaît ni dans une URL, ni dans un journal applicatif ; `api_calls` ne garde que `key_id`.
- Comparaison en temps constant. Un `public_id` inconnu passe aussi par une comparaison factice (même durée).
- Refus 401 uniformes : on ne révèle pas si la clé existe.
- Aucun accès à la méta-base hors de la vérification. L'instance vient **de la clé**, jamais d'un paramètre.
- Les outils d'écriture ne peuvent ni valider, ni comptabiliser, ni numéroter, ni envoyer (D2, D3). Un test parcourt le registre et vérifie qu'aucun handler n'appelle `post_ready`, la validation ou un envoi.
- Revue `/security-review` prévue à la fin de AK3.

## 12. Points à confirmer
- **D2** : REST par clé en lecture seule, écritures uniquement par les outils d'agent.
- **D3** : facture d'Aiffel non comptabilisée avant « Marquer vérifiée ». L'autre voie, la comptabiliser en brouillard tout de suite, est plus rapide mais touche les soldes avant tout contrôle.
- **D9** : pièce limitée à 10 Mo, au lieu des 20 Mo des besoins.
- Format `external_ref` côté Fourmy : `fourmy:<type>/<id>` proposé, à valider avec l'équipe Fourmy.
