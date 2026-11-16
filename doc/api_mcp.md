# Accès API par clé et serveur MCP

Une **clé d'API** ouvre une structure à un agent (Aiffel, l'assistant de Fourmy) ou à un script, sans session de
navigateur. La même clé sert au **serveur MCP** de Lyvre et à l'**API REST**. Besoins et conception :
`claudedocs/besoins_api_mcp_aiffel.md`, `claudedocs/design_api_mcp_aiffel.md` (lots AK1 à AK4).

## Principes

- **Une clé, une structure, un utilisateur.** La clé ne donne jamais plus que le rôle de la personne à qui elle est
  rattachée. Un expert-comptable (lecture seule) ne peut pas avoir de clé qui écrit. Si la personne perd son accès,
  la clé cesse de fonctionner.
- **Par domaine, en lecture et en écriture.** Les domaines disponibles sont : Comptabilité, Banque, Achats, Ventes,
  Tiers, TVA et fiscal, Immobilisations et stocks, Agronomie (exploitations seulement), Échéancier et Documents.
  Cocher l'écriture coche la lecture.
- **Rien n'est définitif sans vous.** Les outils d'écriture ne créent que des brouillons :
  - factures d'achat « à vérifier », jamais comptabilisées avant d'être marquées vérifiées ;
  - tiers « à vérifier » ;
  - écritures non validées (brouillard).
  Aucun outil ne comptabilise, ne valide, ne numérote ni n'envoie.
- **Une clé par usage**, par exemple « Aiffel — saisie terrain » ou « Aiffel — questions bureau ». Le nom de la clé
  sert de badge sur ce qu'elle saisit.
- **Jamais d'administration.** Utilisateurs, accès, intégrations, clés, sauvegardes, imports, clôture et validation
  restent fermés aux clés.

## Créer une clé

Configuration › **Accès API** (administrateur de la structure) › **Créer une clé**. Le formulaire demande :

- le nom de l'usage ;
- l'utilisateur rattaché ;
- les domaines, dans la grille Lecture / Écriture ;
- la date d'expiration (un an par défaut, deux ans au plus) ;
- les limites (requêtes par minute, créations par jour).

La clé `lyv_…` s'affiche **une seule fois**, avec l'adresse du serveur MCP et la configuration à copier. Lyvre n'en
garde que l'empreinte. Une clé perdue se révoque et se remplace.

Chacun retrouve les clés rattachées à lui dans le menu de l'utilisateur › **Mes clés d'API**, avec leur journal, et
peut les révoquer.

## Se connecter

L'adresse publique vient de `APP_BASE_URL` : par exemple `https://app.lyvre.org` en production et `https://lyvre.org`
en essai.

| Accès | Adresse | Contenu |
|---|---|---|
| Serveur MCP | `APP_BASE_URL/mcp` | Transport HTTP streamable, sans session (réponses JSON). Outils filtrés par les domaines de la clé. |
| API REST | `APP_BASE_URL/api/v1/…` | Lecture (GET) des écrans, dans les domaines de la clé. |
| Outils par REST | `GET /api/v1/agent/tools`, `POST /api/v1/agent/tools/<outil>` | Mêmes outils que le serveur MCP. |
| Pièces | `POST /api/v1/agent/files` (multipart `file`) | PDF, JPEG ou PNG de 10 Mo au plus. Rend un `file_token` pour les outils d'écriture. |

Chaque appel porte l'en-tête `Authorization: Bearer lyv_…`. Configuration d'un client MCP :

```json
{ "mcpServers": { "lyvre": { "type": "http", "url": "https://app.lyvre.org/mcp",
    "headers": { "Authorization": "Bearer lyv_…" } } } }
```

La page **Aide API et MCP** (Configuration › Accès API) donne l'adresse de l'installation et la liste réelle des
outils par domaine.

## Outils

- **Toujours disponibles**
  - `get_context` : identité et situation du dossier ;
  - `list_calculators` et `run_calculator` : calculettes. Le préremplissage depuis la structure demande le domaine
    Comptabilité en lecture.
- **Lecture**
  - repris de l'assistant Claude : soldes, écritures, contrôles de clôture, TVA, résultat fiscal, MSA, paramètres
    réglementaires, marges, aides, échéancier ;
  - factures d'achat, comptes et transactions bancaires, pièces de vente, recherche d'un tiers, immobilisations.
- **Écriture**
  - `create_purchase_draft` : facture d'achat en brouillon. Avec une pièce, Lyvre la lit (Factur-X, OCR) ; une
    dépense sans facture passe aussi par cet outil, le ticket servant de pièce ;
  - `attach_document` : pièce jointe à un brouillon de la même clé ;
  - `create_supplier` : fournisseur à vérifier, complété par Sirene ;
  - `create_entry_draft` : écriture non validée.
- **Idempotence**
  - Une création qui porte une `external_ref` déjà connue (par exemple `fourmy:intervention/123`) renvoie l'objet
    existant au lieu d'en créer un second.
  - Une `idempotency_key` déjà reçue de la même clé fait de même.

## Vérifier ce qu'un agent a saisi

- Les objets créés par une clé portent un **badge** à son nom : liste et fiche des achats, fiche tiers, fiche écriture.
- Achats : compteur et filtre **Saisies par clé à vérifier**. Sur la fiche, le bouton **Marquer vérifiée**
  comptabilise la facture si elle est complète.
- Tableau de bord, carte « À traiter » : nombre de saisies par clé à vérifier.

## Journal et limites

- **Journal** (bouton Journal sur la clé) : chaque appel REST ou outil MCP, refus compris.
  - On y voit la date, l'appel, le domaine, le résultat et l'objet créé.
  - Le journal est gardé 180 jours. Il ne contient jamais la clé ni le contenu des requêtes.
- **Débit** : 60 requêtes par minute par défaut. Au-delà, la réponse est 429 avec `Retry-After` (erreur JSON-RPC
  `-32000` sur `/mcp`). Un lot MCP compte au plus 10 messages, chacun compté.
- **Créations** : 200 par jour par défaut, dépôts de pièces compris (jour de Paris). Au-delà, les créations sont
  refusées et la lecture continue.
- **Taille** : 15 Mo au plus par requête sur `/mcp` et `/api/v1/agent/*`.

## Mise en place

- `seed_meta.py` crée la table `api_keys` dans la méta-base. L'entrypoint Docker le lance au démarrage.
- La migration `a2c4e6f8b1d3` ajoute à chaque structure le journal et l'origine des objets : `flask db upgrade`.
- `APP_BASE_URL` doit être l'adresse publique HTTPS. Le proxy doit transmettre l'en-tête `Authorization` vers `/mcp`
  et `/api/v1`.
