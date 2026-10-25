# Conception — intégration Brevo : adhérents synchronisés vers une liste de contacts

Source : `claudedocs/besoins_brevo.md` (R1–R11, D1–D4). 25/10/2026.

## 0. Constat mesuré (compte Brevo et Seconde Nature, agrégats seulement)

Comparaison faite sur des empreintes SHA-256 des e-mails : aucun e-mail en clair n'a circulé.

| Mesure | Valeur |
|---|---|
| Contacts Brevo | 562 (1 sans e-mail), offre gratuite |
| Adhérents Lyvre | 331, tous avec e-mail, aucun en double |
| Adhérents **déjà présents** dans Brevo (même e-mail) | **319** |
| … dont désinscrits (`emailBlacklisted`) | 14 |
| … dans les listes « Adhérents 20 Juin 2026 » (n° 10 et 11) | 307 |
| Contacts des listes 10 et 11 inconnus des adhérents Lyvre | 39 |
| Contacts avec un `EXT_ID` | 0 |
| E-mails en double dans Brevo | 0 |
| Attributs existants utiles | `PRENOM` (336 renseignés), `NOM`, `DATE_ADH` (123, date), `EXT_ID` |
| Quota annoncé (en-têtes `x-sib-ratelimit-*`) | 20 requêtes par seconde |

Conséquence : la première synchronisation est surtout un **rattachement** (319 contacts) ; une
création aveugle aurait produit 319 erreurs ou, avec fusion, des suppressions.

Points de l'API qui fixent la conception :
- **L'e-mail est l'identifiant unique.** `ext_id` est un identifiant secondaire, posé par l'appelant.
- **Modifier l'e-mail d'un contact désinscrit le réinscrit.** Lyvre ne change donc jamais l'e-mail
  d'un contact désinscrit : il signale un conflit.
- **`forceMerge` supprime un des deux contacts.** Lyvre ne l'envoie jamais.
- `POST /v3/contacts/batch` met à jour par `id` (204, sans détail par contact en cas d'échec) ;
  `GET /v3/contacts` liste 500 contacts par page, avec `listIds`, `emailBlacklisted` et les attributs.

## 1. Découpage en lots

| Lot | Contenu | Migration |
|---|---|---|
| **B1** | Intégration (réglages, test, IP), client Brevo, attributs | aucune |
| **B2** | Liens adhérent ↔ contact, moteur de synchronisation, aperçu à blanc, rapport | `brevo_links` |
| **B3** | Écran Adhérents (boutons, rapport), enchaînement après HelloAsso | aucune |

## 2. B1 — Intégration et client

### 2.1 Déclaration (`external_config`)

- `SERVICE_KEYS["brevo"] = ["api_key", "list_id"]`, `api_key` dans `SECRET_KEYS`, les deux requis.
- `SERVICE_CHARTS["brevo"] = {"asso"}` (R1) ; libellé « Brevo », description « Liste de contacts
  des adhérents ». Repli `.env` de développement : `BREVO_API_KEY` seulement.
- La garde des associations (`app/association_only.py`) reçoit le module d'API `brevo`.

### 2.2 Client (`services/brevo_client.py`)

- `requests`, en-tête `api-key`, délai de 15 s. Débit : au plus 10 requêtes par seconde (moitié du
  quota annoncé), et sur 429, attente jusqu'à `x-sib-ratelimit-reset` puis nouvelle tentative (3 au
  plus).
- Méthodes : `account()`, `lists()`, `attributes()`, `create_attribute(name, type)`,
  `contacts()` (toutes les pages), `create_contact(email, ext_id, attributes, list_ids)`,
  `update_batch(rows)` (paquets de 50 par `id`), `unlink(list_id, ids)`.
- **IP non autorisée** : un 401 dont le message contient « unrecognised IP » devient
  `BrevoError("ip_not_allowed")`, avec le message « L'adresse IP du serveur (x.x.x.x) n'est pas
  autorisée dans Brevo : ajoutez-la dans Sécurité › IP autorisées. » (l'adresse est tirée de la
  réponse). Clé refusée : `invalid_key`. Ni la clé ni le corps brut ne sont journalisés.

### 2.3 Test et liste

- **Tester** (`PROBES["brevo"]`) : compte (nom, offre), puis présence de la liste choisie.
- La fiche de l'intégration propose la **liste** dans une liste déroulante lue chez Brevo
  (`GET /api/v1/brevo/lists`), avec le nombre de contacts. On peut y choisir une liste existante
  (les listes 10 et 11) ou en créer une dans Brevo puis la choisir.

### 2.4 Attributs (question ouverte 1)

Deux familles, pour ne pas écraser ce que l'association entretient dans Brevo :

| Attribut | Type | Source Lyvre | Règle |
|---|---|---|---|
| `PRENOM`, `NOM` | texte | voir 2.5 | **partagé** : écrit seulement s'il est vide dans Brevo |
| `DATE_ADH` | date | dernière adhésion (HelloAsso ou caisse) | **géré par Lyvre** : toujours écrit |
| `LYVRE_STATUT` | texte | statut d'adhésion (« À jour (HelloAsso) », « Caisse seulement », « Inconnu ») | géré par Lyvre |
| `LYVRE_ECHEANCE` | date | date anniversaire | géré par Lyvre |
| `LYVRE_BENEVOLE` | booléen | bénévole | géré par Lyvre |
| `EXT_ID` | texte (`ext_id`) | `lyvre-<slug de l'instance>-<id du tiers>` | géré par Lyvre |

- Le test liste les attributs manquants. Un bouton « Créer les attributs manquants » les crée
  (`POST /v3/contacts/attributes/normal/{nom}`) : c'est une action explicite, jamais automatique.
- Un attribut manquant n'est pas envoyé : Brevo l'ignorerait sans rien dire. Le rapport le signale.

### 2.5 Prénom et nom (question ouverte 2)

- Par ordre de priorité : prénom et nom du dernier article d'adhésion HelloAsso du tiers (champs
  `user_first_name`, `user_last_name`, fiables), sinon ceux du payeur de sa dernière commande,
  sinon rien. **Le nom Lyvre n'est pas découpé** : un découpage deviné serait faux pour les noms
  composés.
- Partagés (2.4) : ils ne complètent que des contacts sans prénom ni nom.

## 3. B2 — Liens et moteur de synchronisation

### 3.1 Table `brevo_links` (base de l'instance)

| Colonne | Type | Rôle |
|---|---|---|
| `id` | Integer PK | |
| `entity_id` | FK `entities.id`, `ON DELETE SET NULL`, unique | adhérent lié ; nul après suppression du tiers (pour le retirer de la liste) |
| `contact_id` | BigInteger, unique, non nul | identifiant du contact Brevo |
| `email` | String(200) | e-mail tel qu'envoyé la dernière fois |
| `payload_hash` | String(64) | empreinte des valeurs envoyées (contact inchangé : pas d'appel) |
| `in_list` | Boolean | le contact est dans la liste cible |
| `state` | String(12) | `linked`, `conflict`, `removed` |
| `note` | String(300) | motif du conflit, dernière erreur |
| `synced_at` | DateTime | |

Un lien est **la** référence : un adhérent lié n'est plus jamais recherché par e-mail ni créé.

### 3.2 Déroulé d'une synchronisation (`services/brevo_sync.py`)

Une tâche de fond `sync_jobs` (`kind = brevo_sync`), avec `dry_run` (aperçu) ou non :

1. **Lecture** : adhérents de Lyvre (`member_rows`), liens, et **tous les contacts Brevo**, en une
   lecture paginée de 500 (2 appels aujourd'hui). Index par `id`, par e-mail normalisé et par
   `EXT_ID`. Lire tout le compte coûte moins qu'une recherche par contact, et voit les
   désinscriptions et les changements faits dans Brevo.
2. **Classement de chaque adhérent** :

| Cas | Décision |
|---|---|
| Lien existant, contact présent, même e-mail | `update` si l'empreinte a changé ou s'il n'est plus dans la liste, sinon `unchanged` |
| Lien existant, e-mail changé dans Lyvre, nouvel e-mail libre dans Brevo, contact **non désinscrit** | `update` avec `EMAIL` |
| Lien existant, nouvel e-mail déjà porté par un autre contact | `conflict` (« e-mail déjà utilisé dans Brevo par un autre contact ») |
| Lien existant, contact désinscrit et e-mail changé | `conflict` (« modifier l'e-mail réinscrirait le contact ») |
| Lien existant, contact supprimé dans Brevo | `create` (nouveau lien) |
| Pas de lien, contact trouvé par `EXT_ID` | `link` puis `update` |
| Pas de lien, contact trouvé par e-mail, non lié à un autre adhérent | `link` puis `update` (**cas des 319**) |
| Pas de lien, e-mail lié à un autre adhérent | `conflict` |
| Pas de lien, rien trouvé | `create` |
| Adhérent sans e-mail | `skipped` |

3. **Sorties** : les liens dont le tiers a disparu, n'est plus adhérent ou n'a plus d'e-mail donnent
   `unlink` (retrait de la liste, `state = removed`). Le contact n'est jamais supprimé.
4. **Écritures** (sauf aperçu) : créations une à une (`POST /v3/contacts` avec `ext_id`,
   `listIds`, sans `updateEnabled`) ; une réponse « existe déjà » (création concurrente) relit le
   contact et le lie. Mises à jour par paquets de 50 (`/contacts/batch`, par `id`) ; un 400 sur un
   paquet le rejoue contact par contact, pour isoler le fautif. Retraits par
   `/contacts/lists/{id}/contacts/remove`. Liens et empreintes enregistrés au fil de l'eau.
5. **Jamais envoyés** : `emailBlacklisted`, `forceMerge`, `updateEnabled`. Les désinscrits sont mis
   à jour (attributs, liste) mais restent désinscrits ; ils sont comptés à part.
6. **Rapport** (`sync_jobs.result`) : compteurs par décision, et la liste nominative des conflits,
   erreurs et désinscrits (nom Lyvre, motif ; pas d'e-mail dans les compteurs). Contacts de la liste
   cible non liés à un adhérent : comptés seulement, **jamais retirés** (les 39 des anciennes listes,
   si l'une d'elles est choisie).

### 3.3 Première synchronisation (D3, R5)

- Tant qu'aucun lien n'existe, le bouton de l'écran Adhérents ne propose que **l'aperçu**. Le
  rapport d'aperçu montre « 319 à rattacher, 12 à créer, 14 désinscrits, n conflits ». Un bouton
  « Synchroniser » lance alors la vraie tâche.
- Ensuite, l'aperçu reste disponible et la synchronisation directe devient possible.

### 3.4 Ordre de grandeur

Aujourd'hui : 2 lectures, 12 créations, 7 paquets de mises à jour, soit environ 21 appels, en
quelques secondes. Ensuite, les contacts inchangés ne coûtent rien : seulement les 2 lectures.

## 4. B3 — Écrans et déclencheurs

### 4.1 API (module `app/api/brevo.py`, réservé aux associations)

| Route | Rôle |
|---|---|
| `GET /api/v1/brevo/lists` | listes du compte (réglage) |
| `GET /api/v1/brevo/attributes` | attributs attendus : présents ou manquants |
| `POST /api/v1/brevo/attributes` | crée les manquants (administrateur de l'instance) |
| `POST /api/v1/brevo/sync` `{dry_run, entity_ids?}` | lance la tâche ; 409 si une tâche tourne ; 422 si la première n'est pas un aperçu |
| `GET /api/v1/brevo/sync/<job_id>` | progression et rapport |
| `GET /api/v1/brevo/status` | dernier passage, nombre de liens, conflits en cours |

Écritures refusées à l'expert-comptable par la garde existante (R11) ; consultation permise.

### 4.2 Écran Adhérents

- Bouton « Brevo » (si l'intégration est activée) : « Aperçu » et « Synchroniser », avec la date et
  le résultat du dernier passage.
- Rapport : `/entities/members/brevo/<job_id>` (lien de la notification de fin). Il affiche les
  compteurs, puis les conflits avec leur motif et un lien vers le tiers, puis les erreurs. Un
  rapport d'aperçu propose « Synchroniser ».
- Colonne facultative « Brevo » dans la liste des adhérents : lié, conflit, non lié.

### 4.3 Après HelloAsso (D2)

`POST /api/v1/helloasso/sync` lance ensuite `brevo_sync` sur les adhérents touchés (identifiants
renvoyés par `sync_helloasso`), si l'intégration est activée et que la première synchronisation a
eu lieu. Le message de HelloAsso l'indique.

## 5. Exigences transverses

- **Tests sans réseau** : faux Brevo en mémoire (contacts, listes, attributs), qui reproduit
  l'unicité de l'e-mail, la réinscription au changement d'e-mail, le 401 d'IP et le 429. Scénarios :
  rattachement des existants sans création ; deuxième passage sans appel d'écriture ; changement
  d'e-mail ; désinscrit jamais réinscrit ; conflit d'e-mail ; adhérent supprimé retiré de la liste ;
  aperçu sans écriture.
- **Données (R9)** : seuls les adhérents (`ADHERENT`) et les champs de 2.4. Les journaux ne contiennent
  ni la clé ni les e-mails.
- **Documentation** : `doc/integrations.md` (Brevo, IP autorisées, attributs, première
  synchronisation).

## 6. Points laissés à l'implémentation

- Taille maximale d'un paquet `/contacts/batch` : non documentée ; 50 par prudence, à confirmer.
- Format exact de l'erreur « e-mail déjà existant » à la création : à relever sur la réponse réelle,
  dans un test contrôlé au moment de B2.
- Choix de la liste cible : le réglage le laisse à l'utilisateur. La recommandation est une liste
  neuve « Adhérents (Lyvre) », qui ne mélange pas les 39 anciens contacts des imports de juin.
