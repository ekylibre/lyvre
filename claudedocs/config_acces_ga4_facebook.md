# Configuration des accès — Google Analytics (GA4) & Facebook

> Guide pas-à-pas pour obtenir les identifiants à saisir dans
> **Configuration › Intégrations** de l'application (table
> `external_connections`, par instance). Les clés ci-dessous correspondent au
> design (`design_dashboard_visibilite_impact.md` §6).
>
> ⚠️ Les interfaces de Google Cloud et de Meta changent régulièrement : les
> **noms d'écrans** peuvent varier légèrement, la **logique** reste la même.
> Liens officiels en annexe.

---

# Partie A — Google Analytics 4 (GA4)

## A.0 Ce qu'on obtient
Un accès **lecture seule, automatisé** aux statistiques du site (utilisateurs,
sessions, taux d'engagement, durée, pages, acquisition) via la **GA4 Data API**,
sans intervention humaine après configuration.

**Deux valeurs à produire :**

| Clé app (`service = ga4`) | Contenu |
|---|---|
| `ga4.property_id` | `472641442` (déjà connu, voir A.2) |
| `ga4.credentials_json` | Le **contenu** du fichier JSON de clé du compte de service |

## A.1 Pré-requis
- Être **administrateur** de la propriété GA4 (pour accorder un accès).
- Un compte Google pouvant créer un projet sur **Google Cloud** (gratuit pour cet usage).

## A.2 Récupérer le Property ID
- Dans GA4 : **Admin** (roue crantée) → **Paramètres de la propriété** → l'**ID de
  propriété** s'affiche en haut (un nombre).
- Il apparaît aussi dans l'URL fournie : `…/p472641442/…` → **`472641442`**.
- ⚠️ Ne pas confondre avec l'ID de **flux** (« G-XXXX », l'ID de mesure) : on veut
  l'**ID de propriété numérique**.

## A.3 Créer un projet Google Cloud + activer l'API
1. Aller sur **console.cloud.google.com**.
2. En haut, **Sélectionner un projet → Nouveau projet** (ex. nom : *seconde-nature-analytics*).
3. Une fois le projet sélectionné : menu **APIs et services → Bibliothèque**.
4. Rechercher **« Google Analytics Data API »** → **Activer**.

## A.4 Créer un compte de service + sa clé JSON
1. Menu **IAM et administration → Comptes de service → Créer un compte de service**.
2. Nom : ex. *ga4-reader*. **Créer et continuer**. (Aucun rôle Google Cloud
   nécessaire à cette étape — l'accès se donne **côté GA4**, étape A.5.) **OK**.
3. Ouvrir le compte de service créé → onglet **Clés → Ajouter une clé → Créer une
   clé → JSON** → un fichier `.json` se télécharge.
4. **Conserver ce fichier en lieu sûr** (c'est un secret, cf. A.7).
5. Noter l'**adresse e-mail** du compte de service : elle ressemble à
   `ga4-reader@seconde-nature-analytics.iam.gserviceaccount.com`.

## A.5 Donner l'accès lecture à GA4
1. Dans GA4 : **Admin → Gestion de l'accès à la propriété** (Property Access Management).
2. **+ → Ajouter des utilisateurs**.
3. Coller l'**e-mail du compte de service** (A.4.5).
4. Rôle : **Lecteur** (Viewer). Décocher l'envoi d'e-mail de notification. **Ajouter**.

> C'est cette étape qui autorise l'API à lire vos données — sans elle, l'appel
> renverra une erreur de permission.

## A.6 Renseigner l'application
Dans **Configuration › Intégrations › Google Analytics (GA4)** :
- `property_id` : `472641442`
- `credentials_json` : **copier-coller le contenu complet** du fichier `.json`
  (de `{` à `}`).

## A.7 Sécurité
- Le JSON est un **secret** : ne jamais le committer dans Git, ne pas le partager.
- S'il fuite : **IAM → Comptes de service → Clés → Supprimer la clé**, puis en
  recréer une (A.4) et mettre à jour `credentials_json`.
- Accès **lecture seule** sur GA4 (rôle Lecteur) : risque limité.

## A.8 Vérifier que ça marche
- Côté app : bouton **Synchroniser** du dashboard Impact → le bloc « Site web »
  se remplit, le bandeau de fraîcheur affiche la date.
- Test rapide indépendant : dans Google Cloud, **APIs et services → Identifiants**
  permet de vérifier l'API activée ; l'absence d'erreur de quota/permission au
  premier sync confirme l'accès.

---

# Partie B — Facebook (Page Seconde Nature)

## B.0 Périmètre (important)
| Donnée | Statut | Moyen |
|---|---|---|
| **Page** — nombre d'abonnés (`followers_count` / `fan_count`) | ✅ **v1 automatique** | Graph API, permission de base |
| **Page** — portée & engagement (insights) | 🟡 **v2** | Nécessite permission `read_insights` + **revue d'app Meta** (délai) |
| **Groupe Facebook** (`assosecondenature`) | ❌ Non automatisable | API Groupes dépréciée → **saisie manuelle** |
| **Vinted** | ❌ Aucune API | **saisie manuelle** |

**Quatre valeurs à produire (v1) :**

| Clé app (`service = facebook`) | Contenu |
|---|---|
| `facebook.page_id` | ID numérique de la Page |
| `facebook.page_token` | *Page Access Token* longue durée |
| `facebook.app_id` | ID de l'app Meta |
| `facebook.app_secret` | Secret de l'app Meta |

## B.1 Pré-requis
- Être **administrateur** de la Page Facebook « Seconde Nature ».
- Un compte sur **developers.facebook.com** (gratuit).

## B.2 Créer une app Meta
1. Aller sur **developers.facebook.com → Mes applications → Créer une application**.
2. Type : **Business** (Entreprise). Renseigner un nom (ex. *Seconde Nature Stats*).
3. Une fois créée : **Paramètres → Général** → relever **Identifiant de l'app**
   (`app_id`) et **Clé secrète** (`app_secret`, cliquer « Afficher »).

## B.3 Trouver le Page ID
Plusieurs options :
- **Graph API Explorer** (B.4) : appeler `GET /me/accounts` une fois connecté →
  liste vos Pages avec leur `id` et `name`.
- Ou : sur la Page, **Paramètres → À propos / Transparence de la Page** affiche
  souvent l'ID.
- L'identifiant `61586651294117` visible dans l'URL du profil est un bon candidat,
  **à confirmer** via `GET /me/accounts` (méthode fiable).

## B.4 Générer un Page Access Token
1. Ouvrir l'**Explorateur d'API Graph** (Graph API Explorer) : developers.facebook.com/tools/explorer
2. Sélectionner votre application (en haut à droite).
3. **Get Token → Get User Access Token** ; cocher les permissions :
   - `pages_show_list`
   - `pages_read_engagement`
   - *(v2 uniquement, pour la portée :)* `read_insights`
4. Valider la fenêtre de connexion Facebook (en tant qu'**admin de la Page**).
5. Appeler `GET /me/accounts` → repérer la Page → copier son **`access_token`**
   (c'est le **Page Access Token**) et son **`id`** (= `page_id`).

## B.5 Rendre le token longue durée (ne pas expirer)
Le token obtenu en B.4 expire vite (~1–2 h). Pour un token **longue durée** :
1. Échanger le **User token** court en **User token longue durée (60 j)** :
   ```
   GET https://graph.facebook.com/v19.0/oauth/access_token
       ?grant_type=fb_exchange_token
       &client_id={app_id}
       &client_secret={app_secret}
       &fb_exchange_token={user_token_court}
   ```
2. Avec ce User token longue durée, rappeler `GET /me/accounts` :
   le **Page Access Token** qui en découle **n'expire pas** tant que vous restez
   admin de la Page et que l'app n'est pas supprimée.
3. C'est **ce Page token** que l'on stocke dans `facebook.page_token`.

> 💡 Pour vérifier la durée de vie d'un token : **Outils → Débogueur de jetons
> d'accès** (Access Token Debugger) → champ *Expire* doit indiquer *Jamais*.

## B.6 Renseigner l'application
Dans **Configuration › Intégrations › Facebook (Page)** :
- `page_id`, `page_token`, `app_id`, `app_secret`.

## B.7 Vérifier que ça marche
- Test direct (navigateur ou Explorer) :
  ```
  GET https://graph.facebook.com/v19.0/{page_id}?fields=followers_count,fan_count&access_token={page_token}
  ```
  → doit renvoyer les nombres d'abonnés/fans.
- Côté app : **Synchroniser** → le bloc « Facebook » du dashboard se remplit.

## B.8 Insights (portée/engagement) — jalon v2
- Métriques visées : `page_impressions`, `page_post_engagements` (et autres).
- Nécessite la permission **`read_insights`** en **accès avancé**, donc une
  **revue d'app Meta** (App Review) avec description d'usage + parfois vidéo de
  démonstration. Délai non négligeable → traité séparément, après la v1.
- En attendant : la **portée** peut être **saisie manuellement** comme Vinted/groupe.

## B.9 Maintenance
- Si le token cesse de fonctionner (changement d'admin, app passée en mode Live,
  mot de passe réinitialisé) : refaire B.4–B.5 et mettre à jour `facebook.page_token`.
- Garder l'app Meta **active** ; pour la v1 (données publiques de Page), le **mode
  Développement** suffit avec votre propre compte admin.

---

# Annexe — Rappel ADEME Base Empreinte (facteurs environnementaux)

Source actée pour `impact_factors`. Pointeurs pour relever les valeurs (à valider
par le bureau avant communication) :
- **base-empreinte.ademe.fr** → rechercher les facteurs **textile / vêtements**
  et les données **réemploi / fin de vie évitée**.
- Renseigner ensuite dans **Impact → Facteurs** :
  - `textile.avg_weight_kg` — poids moyen d'un article (kg)
  - `textile.co2e_per_kg` — kg CO₂e évités par kg réemployé
  - `textile.water_l_per_kg` — litres d'eau évités par kg
  - `equiv.car_km_per_co2e_kg` — équivalent km voiture par kg CO₂e (communication)
- Chaque facteur stocke son **libellé de source** et son **URL** ADEME (traçabilité financeurs).

---

# Annexe — Liens officiels
- GA4 Data API : https://developers.google.com/analytics/devguides/reporting/data/v1
- Comptes de service Google : https://cloud.google.com/iam/docs/service-accounts-create
- Accès propriété GA4 : https://support.google.com/analytics/answer/9305587
- Graph API (Pages) : https://developers.facebook.com/docs/pages-api
- Tokens longue durée : https://developers.facebook.com/docs/facebook-login/guides/access-tokens/get-long-lived
- Débogueur de jetons : https://developers.facebook.com/tools/debug/accesstoken
- ADEME Base Empreinte : https://base-empreinte.ademe.fr
