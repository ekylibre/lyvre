# Design : utilisateurs et rôles dès la création d'une instance

Ce document répond à `claudedocs/besoins_acces_instances.md` (F1 à F5, US1 à US6). Il s'appuie sur
ce qui existe déjà : `instance_memberships` et ses trois rôles, `app/access.py`, la page Accès
(`app/api/access.py`) et la page Utilisateurs (`app/api/users.py`).

## 1. Vue d'ensemble

```
             Nouvelle instance ─┐   Import (création) ─┐   Fiche instance ─┐   Page Accès ─┐   Utilisateurs ─┐
                                ▼                       ▼                   ▼                ▼                 ▼
API     POST /instances   POST /instances/import   /instances/<id>/members   /access/members   /users
                                └──────────┬────────────┘                   └───────┬────────┘                 │
Service                        grants.validate / grants.apply          memberships.add / set_role / remove    │
                                           │                                         │                         │
                                           └────────── app/services/instance_access.py ──────────┐            │
                                                                                                  ▼            ▼
Méta-base                         users (+ must_change_password)   instance_memberships   ← flag posé à la création
                                                                                            ou quand un admin fixe
Garde                tenant._select_tenant : must_change_password → 403 `password_change_required`
                     ou redirection /password, sauf liste blanche (session, mot de passe, déconnexion)
```

Principe : **un service unique** (`app/services/instance_access.py`) porte toutes les règles d'accès.
Les cinq points d'entrée l'appellent et aucun ne réécrit les règles.

## 2. Données (méta-base)

| Table | Changement |
|---|---|
| `users` | `must_change_password BOOLEAN NOT NULL DEFAULT 0` |
| `instance_memberships` | Inchangée |

- La colonne est ajoutée par `seed_meta.py` (`_ensure_column`, même procédé que `preferences`). Il
  n'y a pas d'Alembic pour la méta-base.
- Valeur `false` pour les comptes existants : aucun utilisateur actuel n'est bloqué.
- Modèle : `User.must_change_password = db.Column(db.Boolean, nullable=False, default=False, server_default=db.false())`.

**Quand le drapeau est posé à `true`** (F5.1, F5.2) :

| Point d'entrée | Situation | Drapeau |
|---|---|---|
| `instance_access.create_user` (création d'instance, import, fiche, page Accès) | Compte créé | oui |
| `POST /users` | Compte créé par un administrateur | oui |
| `PATCH /users/<id>` avec `password` | `id` ≠ utilisateur courant | oui |
| `PATCH /users/<id>` avec `password` | Son propre compte | non |
| `POST /me/password` | Changement par l'utilisateur | levé (`false`) |

## 3. Service `app/services/instance_access.py`

```python
class AccessError(Exception):            # message, field (chemin Mantine : "members.1.password"), status
    ...

@dataclass
class Grant:                             # une ligne validée, rien n'est encore écrit
    role: str
    user: User | None                    # compte existant
    email: str | None = None             # nouveau compte
    full_name: str | None = None
    password: str | None = None

def parse_grants(items, *, field="members") -> list[Grant]
    """Valide toute la liste sans écrire : forme, rôle connu, utilisateur existant (non admin global),
    nouvel email (format, pas de compte existant → « Un compte existe : choisissez-le dans la liste »),
    mot de passe (8 caractères au moins), doublons (même user_id ou même email). Lève AccessError sur la
    première ligne fautive, avec `field=f"{field}.{i}.<champ>"`."""

def grants_warnings(grants) -> list[str]
    """F1.8 : lignes sans Administrateur ; F1.9 : comptes désactivés (accès effectif à la réactivation)."""

def apply_grants(instance, grants, by_user) -> dict
    """Crée les comptes (must_change_password=True) et les accès ; flush, sans commit.
    Renvoie {"created": n, "granted": m} pour la notification (F1.6)."""

def create_user(email, full_name, password) -> User          # utilisé par apply_grants et add_member
def members(instance) -> list[dict]                          # extrait de app/api/access.py (_members)
def add_member(instance, data, by_user) -> tuple[User, bool] # extrait de access_add_member
def set_role(instance, user_id, role) -> InstanceMembership  # garde « dernier administrateur »
def remove_member(instance, user_id) -> str                  # idem
```

- **Refactorisation** : `app/api/access.py` garde ses routes et ses messages, mais délègue à ce
  service (`members`, `add_member`, `set_role`, `remove_member`, `_ensure_an_admin_remains`).
  Les tests existants de la page Accès servent de filet.
- **Instance désactivée** (F3.4) : le service travaille sur un objet `Instance` explicite, pas sur
  `g.current_instance`, donc l'état actif n'entre pas en jeu. La fiche instance passe l'instance par
  son id.

## 4. API

### 4.1 Création d'instance : `POST /api/v1/instances` (admin global)

Corps actuel, avec un champ en plus :

```json
{"slug": "asso-x", "label": "Asso X", "provisioning_mode": "auto", "chart": "asso", "bookkeeping": "double",
 "members": [
   {"user_id": 12, "role": "treasurer"},
   {"email": "paul@exemple.fr", "full_name": "Paul", "password": "••••••••", "role": "admin"}
 ]}
```

Ordre des opérations, pour le tout ou rien (F1.5, ENF Atomicité) :

1. Valider slug, libellé, plan et mode de tenue (inchangé).
2. `grants = parse_grants(data.get("members") or [])`. En cas d'erreur, réponse 422 avec
   `fields: {"members.1.password": "…"}`. Rien n'est créé.
3. Provisionner la base (mode auto). Il ne reste après cela que des écritures en méta-base.
4. Dans un `try` : ajouter `Instance`, `flush`, `apply_grants`, `commit`.
   - Si une exception survient, `rollback`. En mode auto, supprimer aussi le fichier `.db` créé
     (nouveau helper `instance_provisioning.discard_sqlite_database(url)`), puis relancer
     l'exception.
5. Réponse 201 :
   - `notices` : « Instance « Asso X » créée ; 1 compte créé, 2 accès donnés. » ;
   - un `notice(level="warning")` par avertissement.

### 4.2 Import : `POST /api/v1/instances/import` (multipart)

- Nouveau champ de formulaire `members`, du JSON sérialisé, même format qu'en 4.1.
- **Slug inconnu (création)** : `parse_grants` est appelé avant `stage_upload_to_path`. Ensuite,
  même séquence d'opérations ; en cas d'échec après installation, le fichier installé est supprimé.
- **Slug existant (restauration)** : si `members` est non vide, réponse 422 « Une restauration ne
  modifie pas les accès : gérez-les depuis la fiche de l'instance. » (F2.2). Le serveur reste
  ferme même si le front ne montre pas la section.

### 4.3 Accès depuis la fiche : `/api/v1/instances/<id>/members` (admin global)

| Méthode | Route | Corps | Effet |
|---|---|---|---|
| GET | `/instances/<id>/members` | — | `items` comme `/access/members`, `meta.roles` |
| POST | `/instances/<id>/members` | `{user_id, role}` ou `{email, full_name?, password, role}` | `add_member` |
| PATCH | `/instances/<id>/members/<user_id>` | `{role}` | `set_role` |
| DELETE | `/instances/<id>/members/<user_id>` | — | `remove_member` |

- Mêmes réponses et messages que `/access/members`.
- `POST /access/members` accepte aussi `user_id`, en plus de l'email, pour que les deux écrans
  aient le même contrat.
- `members[].is_active` est déjà renvoyé : la ligne affiche « désactivé ».

### 4.4 Mot de passe : `POST /api/v1/me/password`

- Corps : `{current_password, new_password}`.
- Contrôles : `current_password` exact (sinon 422 sur ce champ) ; `new_password` d'au moins
  8 caractères et différent de l'actuel.
- Effet : `set_password`, `must_change_password = False`, commit. Réponse : `session_payload()`.
- L'endpoint est ajouté à `READ_ONLY_ALLOWED` : un expert-comptable doit pouvoir changer son mot
  de passe.

### 4.5 Session

`session_payload().user` reçoit `must_change_password` (booléen).

### 4.6 Garde côté serveur (F5.4)

La garde se place dans `app/tenant.py::_select_tenant`, juste après la vérification de
`is_active`. Elle couvre ainsi l'API et les routes Flask (exports, PDF, FEC, rapport d'activité) :

```python
PASSWORD_CHANGE_ALLOWED = {"api.session_info", "api.change_password", "api.logout",
                           "auth.logout", "spa.page", "static"}   # spa.page : le shell HTML de /password
if current_user.must_change_password and request.endpoint not in PASSWORD_CHANGE_ALLOWED:
    if is_api_request():
        return error_response("password_change_required", "Choisissez un nouveau mot de passe pour continuer.", 403)
    return redirect("/password")
```

- Le nom exact de l'endpoint du shell SPA est à reprendre de l'existant.
- Le login n'est pas concerné : on n'est pas encore authentifié à ce moment-là.

## 5. Front

### 5.1 `features/access/MembersEditor.tsx` (nouveau)

Éditeur de lignes contrôlé, branché sur `useForm` sous `members` :

```ts
type MemberRow =
  | { kind: "existing"; user_id: string | null; role: Role }
  | { kind: "new"; email: string; full_name: string; password: string; role: Role };
<MembersEditor form={form} users={UserOption[]} roles={RoleOption[]} />
```

- **Ligne** :
  - `SegmentedControl` « Compte existant / Nouveau compte » ;
  - pour un compte existant : `Select` avec recherche, libellé « Nom — email », mention
    « désactivé » ; les administrateurs globaux et les utilisateurs déjà choisis sont exclus ;
  - pour un nouveau compte : email, nom, `PasswordInput` ;
  - `Select` du rôle ;
  - bouton « Retirer ».
- « Ajouter un utilisateur » ajoute une ligne. Rôle proposé : `admin` pour la première ligne,
  `treasurer` ensuite.
- Si l'email d'une ligne « Nouveau compte » correspond à un compte de la liste, la ligne propose
  « Utiliser ce compte » (F1.4).
- Une `Alert` non bloquante s'affiche s'il y a des lignes mais aucun administrateur (F1.8).
- Les erreurs serveur `members.1.password` arrivent par `applyApiError` → `form.setErrors`. Les
  chemins Mantine correspondent sans adaptation.
- La liste des comptes vient de `GET /api/v1/users`, déjà réservé à l'administrateur global comme
  toute la création.
- Avant envoi, `toMembersPayload(rows)` produit le JSON : `user_id` en nombre, champs vides retirés.
  C'est une fonction pure, testée avec Vitest.

### 5.2 Intégrations

| Écran | Changement |
|---|---|
| `InstancesPage` › `CreateForm` | Section « Utilisateurs et rôles » avec `MembersEditor` ; la modale passe en taille `lg` |
| `ImportInstancePage` | `MembersEditor` affiché quand le slug saisi ou déduit ne correspond à aucune instance connue ; `members` est envoyé en JSON dans le `FormData` |
| `InstanceDetailPage` | Section « Accès » : `MembersManager` sur `/api/v1/instances/<id>/members` |
| `AccessPage` | Extraite en `MembersManager({ endpoint })`, réutilisée telle quelle |

`MembersManager` contient la table actuelle de la page Accès (rôle modifiable, retrait) et la modale
d'ajout. La modale prend un compte existant ou un nouveau compte, comme une ligne de
`MembersEditor`.

### 5.3 Mot de passe à changer

- **Page** : `features/auth/ChangePasswordPage.tsx`.
  - Route publique-authentifiée `/password`, ajoutée à `spa_routes.json` et à `BARE_PAGES`.
  - Formulaire : mot de passe actuel, nouveau, confirmation (vérifiée côté client).
  - Si `must_change_password` est vrai, un texte explique que c'est la première connexion.
  - Après succès, redirection vers `/`.
- **Garde front** :
  - dans le layout racine, si `session.user?.must_change_password` et que le chemin n'est pas
    `/password`, alors `navigate("/password", { replace: true })` ;
  - le client API traite l'erreur `password_change_required` de la même façon (filet).
- **Accès volontaire** : l'entrée « Changer mon mot de passe » dans le menu utilisateur de l'en-tête
  pointe sur la même page. Le changement volontaire est un bénéfice annexe, cohérent avec F5.2.

## 6. Diagramme de séquence : création avec utilisateurs

```
Admin ─▶ SPA CreateForm ─ POST /instances {…, members} ─▶ instances_create
                                                           ├ valider champs instance
                                                           ├ parse_grants ─✗─▶ 422 fields members.i.*
                                                           ├ provision_sqlite_database
                                                           ├ try: Instance + apply_grants + commit
                                                           │   ✗ rollback + discard_sqlite_database ─▶ 500/422
                                                           └ 201 notices (+ warnings)
Paul ─▶ /login ─▶ session.must_change_password ─▶ /password ─ POST /me/password ─▶ / (Asso X)
```

## 7. Tests

| Niveau | Cas |
|---|---|
| Service | `parse_grants` : forme, rôle inconnu, admin global refusé, doublons (id et email), email d'un compte existant, mot de passe court, chemins de champ ; `apply_grants` : drapeau posé, `created_by_user_id` ; avertissements |
| API instances | Création avec un compte existant et un nouveau ; tout ou rien (aucun `.db`, aucune instance, aucun compte) ; échec après provisioning → fichier supprimé ; import en création avec `members` ; restauration avec `members` → 422 |
| API fiche | CRUD sur une instance active et sur une désactivée ; garde du dernier administrateur ; 403 pour un non-admin global |
| API Accès | Non-régression après refactorisation ; ajout par `user_id` |
| Mot de passe | Drapeau posé par `POST /users`, par `PATCH /users/<id>` (autrui), pas pour soi ; garde : API 403 `password_change_required`, export Flask redirigé, liste blanche passante ; `/me/password` : mauvais actuel, trop court, identique, succès qui lève le drapeau ; expert-comptable autorisé |
| Vitest | `toMembersPayload` ; rôle proposé par défaut |
| E2E | US1 + US6 : création avec deux lignes, connexion du nouveau compte, changement imposé, arrivée sur l'instance |

## 8. Migration et déploiement

- `seed_meta.py` ajoute la colonne : c'est sans risque, avec une valeur par défaut à `false`.
- À jouer sur les copies du serveur d'essai (5001). Sur les vraies bases, uniquement avec ton
  accord : la règle en vigueur reste valable.
- Aucune migration tenant.

## 9. Documentation à mettre à jour

- `doc/routes.md` : instances `members`, `/instances/<id>/members`, `/me/password`, `/password`,
  garde.
- `doc/models.md` : `users.must_change_password`.
- `doc/services.md` : `instance_access`.

## 10. Découpage proposé pour `/sc:implement`

1. **E1. Service et refactorisation.** `instance_access`, la colonne `must_change_password` et sa
   pose dans `/users`, refactorisation de `access.py`, tests service et non-régression.
2. **E2. API.** Création d'instance avec `members`, import, `/instances/<id>/members`, tests.
3. **E3. Mot de passe.** `/me/password`, garde tenant, session, page `/password`, garde front,
   lien menu, tests.
4. **E4. Front.** `MembersEditor` dans la création et l'import, `MembersManager` dans la fiche et
   dans la page Accès, Vitest, E2E, documentation.
