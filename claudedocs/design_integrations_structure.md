# Conception — intégrations selon le type de structure

> Statut : conception validée le 23/10/2026 (§ 10) ; lot I1 réalisé le 23/10/2026.
> Besoins : `claudedocs/besoins_integrations_structure.md` (F0–F6, décisions D1–D11).

## 1. Choix structurants

| # | Choix | Raison |
|---|---|---|
| C1 | L'**interrupteur** d'une intégration passe dans la **base méta** : `Instance.integrations` (JSON) | `/api/v1/session` est sans instance (meta seule) et doit construire les menus (Stancer, Odoo), les masquages et l'encart du tableau de bord. Même choix que `has_associates` |
| C2 | La base de l'instance garde les **réglages** (`external_connections`) et le **dernier test** (`integration_states`) | Les secrets restent dans la base de l'instance ; `integration_states.enabled` n'est plus lu qu'à l'initialisation (C4) |
| C3 | L'**applicabilité** et les **recommandations** par structure sont des constantes de `external_config` | Aucun réglage à saisir : elles découlent de `Instance.chart` |
| C4 | Initialisation **paresseuse** : une instance dont `integrations` est vide (NULL) est initialisée à la première requête, à partir de sa base | Pas de script obligatoire au déploiement : la SCI garde Qonto activée sans intervention |
| C5 | Repli `.env` derrière un drapeau `INTEGRATIONS_ENV_FALLBACK` (vrai en développement seulement) | D5 ; explicite et testable |
| C6 | Côté écran, un seul accès : `useIntegration(slug)` (session) pour **activée ?**, la méta de chaque page pour **disponible ?** | Activée = masquer ou non ; disponible = bandeau « non configurée » ou bouton grisé |

## 2. Données

### 2.1 Base méta — `instances.integrations`

Colonne `TEXT NULL` ajoutée par `seed_meta._ensure_column` (pas d'Alembic en méta).

```json
{"enabled": ["qonto", "smtp"], "dismissed": ["qonto"]}
```

- `enabled` : intégrations activées (sous-ensemble des intégrations applicables).
- `dismissed` : propositions écartées par « Ne plus proposer » (tableau de bord seulement).
- `NULL` : jamais initialisée (C4).

Accesseurs du modèle `Instance` : `enabled_integrations() -> set[str]`,
`set_integration(slug, enabled)`, `dismiss_integration(slug)` (sérialisation JSON, liste triée).

### 2.2 Base de l'instance

Inchangée (aucune migration Alembic). `integration_states.enabled` devient historique : lu par
l'initialisation (§ 4.3), plus jamais écrit.

## 3. Constantes (`app/services/external_config.py`)

```python
# Structures pour lesquelles l'intégration existe ; absente = toutes (D1).
SERVICE_CHARTS = {"helloasso": {"asso"}, "ga4": {"asso"}, "facebook": {"asso"}}
# Proposées à l'activation (D6, F4.1).
RECOMMENDED = {"sci": ["qonto"], "asso": ["helloasso"]}
```

Les logos sont côté front (§ 6.4).

`SERVICE_LABELS["smtp"]` devient « SMTP (emails) » (relances et reçus fiscaux).

## 4. Backend

### 4.1 `external_config`

| Fonction | Rôle |
|---|---|
| `applies(service, chart=None)` | Intégration applicable à la structure de l'instance courante |
| `applicable()` | Liste ordonnée des intégrations applicables |
| `is_enabled(service)` | `applies(service)` **et** `service in instance.enabled_integrations()` ; lit `g.current_instance` (requêtes et fils d'arrière-plan l'ont déjà) |
| `set_enabled(service, enabled)` | Écrit la base méta (commit méta) ; refuse un service non applicable |
| `get(service, key)` | Repli `.env` seulement si `INTEGRATIONS_ENV_FALLBACK` |
| `source(service, key)` | `"env"` seulement si le repli est actif |
| `is_configured`, `is_available`, `unavailable_reason`, `unavailable_message` | Inchangés dans leur contrat |
| `required_message(service)` | « Cette action nécessite l'intégration SMTP (emails), désactivée. » (F5) |
| `proposals(instance)` | `RECOMMENDED[chart]` − activées − écartées |

Config : `Config.INTEGRATIONS_ENV_FALLBACK = False`, `DevelopmentConfig.INTEGRATIONS_ENV_FALLBACK = True`
(surchargé par la variable d'environnement du même nom). Tests : faux par défaut ; les tests du
repli l'activent explicitement.

### 4.2 Erreur « intégration nécessaire »

Nouvelle aide dans `app/api/__init__.py` :

```python
def integration_required(service):   # → ApiError 409
    ApiError("integration_required", external_config.required_message(service), status=409,
             extra={"service": service})
```

- Intégration **désactivée** → `integration_required` (le front affiche le message F5).
- Activée mais **non configurée** → `conflict` actuel avec `unavailable_message` (F5.3).

Appliquée à : `POST /members/reminders/send` (et l'envoi unitaire), `POST /receipts/send`,
la synchronisation Odoo des tiers, les synchronisations Qonto / Stancer / HelloAsso / métriques
(défense, l'écran ne les montrant plus). Le message actuel des reçus « SMTP non configuré »
passe par `unavailable_message("smtp")`.

### 4.3 Initialisation paresseuse (C4)

`app/tenant.py`, après la sélection de l'instance (base ouverte) :

```
si instance.integrations is NULL :
    enabled = [s for s in applicable()
               if réglages requis présents EN BASE (external_connections, sans .env)
               and integration_states.enabled n'est pas False]
    instance.integrations = {"enabled": enabled, "dismissed": []} ; commit méta
```

Idempotent ; une seule fois par instance. Les tests de l'initialisation partent d'une instance à
`NULL`.

Script de constat `scripts/integrations_report.py` (lecture seule, pas d'écriture) : pour chaque
instance, intégrations qui seraient activées et **valeurs fournies aujourd'hui par le `.env` et
absentes de la base** (noms des clés, jamais les valeurs) — à saisir dans la fiche avant la mise en
production (F6.2).

### 4.4 API Intégrations (`app/api/integrations.py`)

| Route | Changement |
|---|---|
| `GET /integrations` | Seulement `applicable()` ; chaque élément ajoute `recommended: bool` |
| `GET/PUT /integrations/<s>`, `POST …/check` | 404 si non applicable |
| `POST /integrations/<s>/enabled` | Écrit la méta (C1) ; invalide la session côté front |
| `POST /integrations/<s>/dismiss` (nouveau) | Admin de l'instance ; ajoute à `dismissed` |
| Fiche | `fields[].source` ne vaut plus `env` hors développement |

### 4.5 Session (`app/api/session.py`)

`instance` gagne :

```json
"integrations": {"enabled": ["qonto", "smtp"], "proposed": ["qonto"]}
```

`proposed` n'est renvoyé que pour un administrateur de l'instance (vide sinon). Si `integrations`
est encore `NULL` (instance jamais ouverte), `enabled: []` jusqu'à la première requête d'instance.

`build_nav(..., features=…)` reçoit en plus les intégrations activées : `{"associates", "stancer",
"odoo", …}`.

### 4.6 Menus (`app/menu_config.py`)

| Menu | Avant | Après |
|---|---|---|
| Trésorerie › Versements Stancer | `charts: _ASSO` | `charts: _ALL, feature: "stancer"` |
| Odoo (Commandes POS, Factures clients) | `charts: _ASSO` | `charts: _ALL, feature: "odoo"` |

Les autres menus ne changent pas (Adhérents, Reçus fiscaux et Indicateurs restent liés à la
structure, pas à une intégration).

### 4.7 Création d'instance (`app/api/instances.py`)

- Méta du formulaire : `integrations_by_chart: {chart: [{value, label, recommended}]}`.
- `POST /instances` accepte `integrations: [slug]` ; filtré par `applies(·, chart)` ; enregistré
  dans `Instance.integrations` (non NULL : pas d'initialisation paresseuse).
- Défaut (champ absent) : les recommandées de la structure.

### 4.8 Notifications

`notify_job` ne crée pas de notification pour une tâche dont l'intégration est désactivée (cas
d'une tâche lancée juste avant la désactivation). L'historique n'est pas filtré (D7).

## 5. Inventaire des écrans

Règle : **activée ?** (session) masque ou montre ; **disponible ?** (méta de la page) grise et
affiche le bandeau. Données déjà importées : toujours visibles (F3.4).

| Intégration | Écran | Masqué si désactivée |
|---|---|---|
| Qonto | Factures d'achat | Bouton « Synchroniser les factures Qonto », ligne « Qonto : factures à partir du… », compteurs « modifiées dans Qonto », colonne et filtre « Statut Qonto », badge « envoi Qonto en échec », bandeau |
| Qonto | Saisie d'une facture | Case « Envoyer à Qonto » (déjà conditionnée par `qonto.upload`) |
| Qonto | Fiche d'une facture | Ligne « Qonto » et bouton « Envoyer à Qonto » ; la ligne « Qonto : statut » reste pour une facture venue de Qonto |
| Qonto | Comptes et caisses | Bouton « Comptes Qonto » |
| Qonto | Transactions d'un compte | Carte Qonto (synchronisation, paramètres, détacher) et bandeau ; badge « Qonto » du compte conservé |
| Qonto | Import OFX | Avertissement « compte synchronisé avec Qonto » conservé (fait sur le compte) |
| Stancer | Menu Versements, tuile du tableau de bord | Menu (§ 4.6), tuile « Versements Stancer » |
| Odoo | Menu Odoo, fiche d'un tiers, tableau de bord | Menu, bouton « Mettre à jour la fiche Odoo », tuile « Ventes de l'exercice » si elle ne vient que d'Odoo et série « Factures Odoo » du graphique |
| HelloAsso | Tiers, Adhérents | Bandeau, bouton de synchronisation ; section « HelloAsso » d'une fiche si vide |
| GA4, Facebook | Visibilité & Impact | Boutons de synchronisation et infobulles « indisponible » ; saisie manuelle conservée |
| SMTP | Adhérents, Relances, Reçus fiscaux | **Rien de masqué** : fonction courante (§ 6.3) |

## 6. Frontend

### 6.1 Session et accès

- `types` de session : `instance.integrations: { enabled: string[]; proposed: string[] }`.
- `useIntegration(slug): boolean` dans `api/session.ts`.
- Bascule (fiche Intégration) et « Ne plus proposer » : invalident `SESSION_KEY` (menus et
  masquages à jour sans recharger).

### 6.2 `IntegrationNotice`

Ne s'affiche que si l'intégration est **activée** et non disponible (désormais : non configurée).
Signature inchangée ; il lit `useIntegration(name)`. Les étiquettes viennent d'un dictionnaire
partagé `features/integrations/catalog.ts` (libellé, logo).

### 6.3 « Intégration nécessaire » (F5)

Composant `RequiresIntegration` qui enveloppe un bouton d'action courante :

```tsx
<RequiresIntegration name="smtp" action="L'envoi par email">
  <Button onClick={send}>Envoyer les relances</Button>
</RequiresIntegration>
```

- Activée : rend l'enfant tel quel (le grisage « non configurée » reste géré par la page).
- Désactivée : le bouton reste visible ; le clic ouvre une fenêtre « L'envoi par email nécessite
  l'intégration SMTP (emails), désactivée. » avec **Activer l'intégration** (lien vers la fiche,
  administrateur) ou « Contactez un administrateur ». Le `onClick` d'origine n'est pas appelé.
- Une réponse API `integration_required` (contournement, état périmé) affiche la même fenêtre.

Points d'usage : envoi des relances (Adhérents, Relances), envoi des reçus (groupé et unitaire).

### 6.4 Logos (D11)

- Fichiers SVG officiels dans `frontend/src/assets/integrations/<slug>.svg` (importés par Vite,
  servis par l'application). SMTP : icône `Mail` de lucide.
- `IntegrationLogo({ slug, size })` : logo sur une **pastille blanche** arrondie (lisible en thème
  sombre sans variante), `alt` = libellé.
- Carte de la page Intégrations : logo 40 px à gauche du nom ; en-tête de la fiche : logo 32 px
  à gauche du titre (`PageHeader` reçoit un `icon` facultatif).

### 6.5 Page Intégrations

- Badge « Recommandée » pour une intégration recommandée non activée, bouton **Activer** (vers la
  fiche, où l'activation précède la configuration et le test).
- Ordre : activées, puis recommandées, puis les autres.

### 6.6 Tableau de bord

- Encart administrateur, un par intégration de `proposed` : logo, « Activez Qonto pour
  synchroniser vos comptes bancaires et vos factures d'achat. », **Configurer** (fiche) et
  **Ne plus proposer** (`POST …/dismiss`). Texte par intégration dans `catalog.ts`.
- Tuiles et série Odoo/Stancer masquées selon `useIntegration` (§ 5).

### 6.7 Création d'instance

Cases « Intégrations » sous le choix du plan comptable : intégrations applicables, recommandées
pré-cochées ; la liste suit le plan choisi.

## 7. Séquences

**Désactiver Qonto** : fiche → `POST /integrations/qonto/enabled {false}` → méta mise à jour →
front invalide la session → Factures d'achat : bouton, colonne, filtre, bandeau masqués ; les
factures Qonto déjà importées restent.

**Envoyer des relances, SMTP désactivée** : clic → `RequiresIntegration` → fenêtre avec lien
« Activer l'intégration » ; aucun appel. Contournement : `POST /members/reminders/send` → 409
`integration_required` → même fenêtre.

**Première requête après déploiement (SCI)** : `integrations` NULL → Qonto paramétrée en base →
`enabled: ["qonto"]` ; SMTP fournie par le `.env` seulement → désactivée (signalée par le script
de constat).

## 8. Tests

| Niveau | Cas |
|---|---|
| pytest | Applicabilité (liste SCI sans HelloAsso/GA4/Facebook, 404) ; bascule méta ; repli `.env` actif/inactif ; initialisation paresseuse (paramétrée en base, `.env` seul, désactivée explicitement, non applicable) ; `integration_required` 409 vs `conflict` ; session `enabled`/`proposed` (admin vs trésorier) ; menus Stancer/Odoo par intégration ; création d'instance avec intégrations ; `dismiss` ; pas de notification d'une intégration désactivée |
| Vitest | `IntegrationNotice` muet si désactivée ; Factures d'achat sans éléments Qonto ; `RequiresIntegration` (fenêtre, lien admin, pas d'appel) ; badge « Recommandée » ; encart du tableau de bord et « Ne plus proposer » ; cases de création d'instance selon le plan |
| E2E | SCI : liste des intégrations (logos, Qonto recommandée), désactivation de Qonto puis Factures d'achat silencieuse ; association : relance avec SMTP désactivée → message |

Les tests existants qui comptent sur « ligne absente = activée » ou sur le repli `.env` sont
adaptés (fixture qui active les intégrations nécessaires).

## 9. Lots

| Lot | Contenu |
|---|---|
| I1 | Méta `instances.integrations`, constantes, `external_config` (applicabilité, bascule méta, repli `.env` en développement), initialisation paresseuse, API Intégrations (filtre, 404, `dismiss`, `recommended`), session, menus Stancer/Odoo, création d'instance (API), notifications ; tests pytest |
| I2 | Front « silence » : `useIntegration`, `IntegrationNotice`, masquages de l'inventaire § 5, tableau de bord (tuiles) ; Vitest |
| I3 | Proposition : page Intégrations (badge, Activer, ordre), encart du tableau de bord, cases de création d'instance ; Vitest |
| I4 | « Intégration nécessaire » : `integration_required` côté API, `RequiresIntegration` (relances, reçus) ; tests |
| I5 | Logos (fichiers officiels, `IntegrationLogo`, `PageHeader icon`), script de constat, documentation (`doc/`), E2E |

## 10. Risques et points d'attention

- **Bases réelles** : la colonne méta et l'initialisation s'appliquent aux vraies bases au
  premier démarrage ; à ne lancer qu'avec ton accord, après le script de constat et la saisie en
  base des valeurs aujourd'hui fournies par le `.env` (SMTP, HelloAsso, Odoo, Stancer de
  l'association).
- **Copies de test (5001)** : sans identifiants Qonto, Qonto y sera désactivée à l'initialisation
  — comportement voulu.
- **Restauration d'une sauvegarde** : l'interrupteur est en méta, il n'est pas restauré (comme
  `has_associates`) ; les réglages le sont.
- **Logos** : les fichiers officiels sont à récupérer sur les kits presse des marques
  (téléchargement à faire avec ton accord, ou fichiers déposés par toi dans
  `frontend/src/assets/integrations/`).

Validé le 23/10/2026 : mise en place sur les vraies bases (constat, saisie des réglages venant du
`.env`, initialisation) au moment de la migration des bases de production
(compta.seconde-nature.net) ; activation non restaurée avec une sauvegarde : accepté ; logos à
prendre dans les kits presse des marques.
