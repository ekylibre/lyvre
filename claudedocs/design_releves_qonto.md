# Conception — Relevés de compte (Qonto et dépôt manuel)

Besoins : `claudedocs/besoins_releves_qonto.md` (F1–F7, décisions R1–R7, essai de l'API du 01/11/2026).
Statut : **proposition** (01/11/2026), à valider avant `/sc:implement`.

## 1. Vue d'ensemble

```
Banque › Transactions (compte)                       Compta › Exercices (FEC)
 ├─ carte Qonto : « Synchroniser Qonto » ──┐          └─ « Archive pour l'expert-comptable »
 └─ carte Relevés                          │                     │
     ├─ « Récupérer les relevés » (Qonto)  │                     ▼
     ├─ « Déposer un relevé » (hors Qonto) │          GET /fiscal-years/<id>/accountant-archive.zip
     └─ liste des mois → PDF               │             FEC + releves/<compte>/<AAAA-MM>.pdf
              │                            ▼
              ▼                    qonto_sync.sync_bank_account
   app/services/bank_statements.py  ◄── fetch_qonto() en fin de synchro (erreur non bloquante)
     ├─ fetch_qonto(ba)  ── QontoClient.list_statements / statement / download
     ├─ store_upload(ba, mois, fichier)
     └─ path_for(statement)
              │
              ▼
   table bank_statements  +  instance/uploads/<slug>/releves/<compte>/<AAAA-MM>.pdf
```

Réutilise : stockage et contrôle des pièces (`attachments` : dossier de l'instance, `sniff`, `_within`,
10 Mo), sauvegarde des `uploads/` (déjà incluse dans `instance_backup`), garde d'écriture du rôle
comptable (`app/api/__init__.py`, méthodes d'écriture refusées), `require_integration("qonto", …)`,
`integrations.describe_error` / `mask_secrets` pour les messages d'erreur.

## 2. Données

Nouvelle table **`bank_statements`** (base de l'instance, migration Alembic après `d4f6b8c0e2a3`) :

| Colonne | Type | Rôle |
|---|---|---|
| `id` | entier, PK | |
| `bank_account_id` | FK `bank_accounts.id`, **RESTRICT**, non nul | compte du relevé |
| `period` | date, non nul | 1er jour du mois du relevé |
| `source` | `qonto` \| `upload` | origine |
| `qonto_id` | texte(36), nul | identifiant du relevé chez Qonto |
| `file_path` | texte, non nul | relatif au dossier de l'instance (`releves/<compte>/<AAAA-MM>.pdf`) |
| `file_name` | texte | nom d'origine (Qonto ou dépôt), pour le téléchargement |
| `file_size` | entier | octets |
| `sha256` | texte(64) | empreinte du PDF stocké |
| `fetched_at` | datetime | récupération ou dépôt |
| `replaced_at` | datetime, nul | dernier remplacement (R4) |
| `user_id` | entier, nul | auteur (clic, dépôt) ; nul pour la synchro automatique |

Contrainte **unique (`bank_account_id`, `period`)** : un relevé par compte et par mois.
Pas de suppression (R6) : ni route, ni bouton. Un compte qui a des relevés ne se supprime pas (RESTRICT,
message « le compte a des relevés ») ; le détacher de Qonto conserve ses relevés.

## 3. Règles

- **R1 — Mois visés** : exercice qui contient la date du jour (sinon le dernier ouvert) ; du mois de début
  au **dernier mois terminé** (Qonto ne publie que des mois clos).
- **R2 — Automatique** : en fin de `sync_bank_account`, `fetch_qonto(ba)` ; une erreur (clé sans accès,
  réseau) est **ajoutée aux erreurs du résultat sans faire échouer la synchronisation**.
- **R4 — Remplacement** : relevé Qonto déjà stocké avec le même `qonto_id` **et** la même taille → ignoré
  sans téléchargement ; sinon téléchargé, et si l'empreinte diffère le fichier est remplacé (`replaced_at`).
  Un dépôt manuel sur un mois déjà déposé remplace aussi.
- **Lien du PDF (30 min)** : téléchargé aussitôt après la liste ; s'il a expiré (403/404 sur l'URL),
  `GET /v2/statements/{id}` redonne un lien, une seule nouvelle tentative.
- **Contrôle du fichier** : signature `%PDF-` exigée (Qonto comme dépôt), 10 Mo au plus ; écriture dans un
  fichier temporaire puis renommage (pas de PDF tronqué si l'enregistrement échoue).
- **R3 — Dépôt** : sur les comptes **non rattachés à Qonto** seulement (sur un compte Qonto, la synchro
  remplacerait le dépôt) ; mois de l'exercice en cours ou d'un exercice ouvert.
- **Droits (R6)** : récupérer et déposer = écriture (refusé au comptable par la garde existante) ;
  liste et PDF = tous les rôles de l'instance.

## 4. Interfaces

### Client Qonto (`app/services/qonto_client.py`)
- `list_statements(bank_account_id, period_from, period_to)` → liste (pages suivies), périodes `MM-AAAA`.
- `statement(statement_id)` → relevé (lien renouvelé).
- `download(url)` existe déjà.

### Service `app/services/bank_statements.py`
- `months(fy, today)` → mois visés (R1).
- `fetch_qonto(bank_account, client=None) -> dict` → `{"new", "replaced", "unchanged", "errors"}` ; commit.
- `store_upload(bank_account, period, file_storage, user_id) -> BankStatement` ; `StatementError` (fichier,
  compte Qonto, mois hors exercice).
- `path_for(statement) -> Path` (vérifié dans le dossier de l'instance).
- `for_fiscal_year(fy) -> list[BankStatement]` (archive).

### API (`app/api/bank_statements.py`)
| Méthode | Route | Rôle |
|---|---|---|
| GET | `/api/v1/bank-accounts/<id>/statements` | mois de l'exercice : relevé (période, source, nom, taille, date, remplacé le, URL) ou « manquant » ; `can_fetch`, `can_upload`, raison si Qonto indisponible |
| POST | `/api/v1/bank-accounts/<id>/statements/fetch` | récupération immédiate (synchrone : ≤ 12 PDF de ~40 Ko) ; notices « n nouveau(x), n remplacé(s), n inchangé(s) » |
| POST | `/api/v1/bank-accounts/<id>/statements` | dépôt (multipart : `period` AAAA-MM, `file`) |

### Vues fichiers (`app/views/bank_statements.py`, `login_required`, instance courante)
- `GET /bank-statements/<id>.pdf` → PDF en ligne (`inline`), nom d'origine.
- `GET /fiscal-years/<id>/accountant-archive.zip` → **F7** : `FEC` (figé ou généré, comme
  `views/fec.py` ; absent si l'exercice ne le permet pas encore, avec un `LISEZMOI.txt` qui le dit) +
  `releves/<libellé du compte>/<AAAA-MM>.pdf` des mois de l'exercice + `LISEZMOI.txt` (liste des mois
  manquants par compte).

### Écrans
- **Banque › Transactions** : carte **Relevés** sous la carte Qonto — tableau des mois de l'exercice
  (mois, « Récupéré le … » / « Déposé le … » / « Manquant », remplacé le, lien PDF) ; bouton
  « Récupérer les relevés » (compte Qonto, désactivé avec la raison si l'intégration est coupée) ou
  « Déposer un relevé » (autres comptes : mois + fichier). Boutons masqués pour le comptable.
- **Résultat de synchronisation Qonto** : « n relevé(s) récupéré(s) » ajouté au compte rendu.
- **Compta › Exercices** (panneau FEC) : bouton « Archive pour l'expert-comptable (ZIP) ».

## 5. Sécurité

- Chemins construits par le serveur seulement (`releves/<id du compte>/<AAAA-MM>.pdf`), vérifiés dans le
  dossier de l'instance ; jamais servis hors d'une session de l'instance.
- Le lien Qonto n'est **ni stocké ni journalisé** ; messages d'erreur passés par `mask_secrets`.
- Copies d'essai : lecture seule chez Qonto (liste + téléchargement), compatible avec la règle des copies.

## 6. Tests prévus

- Service : mois visés (exercice à cheval, mois en cours exclu) ; récupération avec un faux client
  (nouveau, inchangé sans téléchargement, remplacé si empreinte différente, lien expiré puis renouvelé,
  fichier non PDF refusé) ; dépôt (compte Qonto refusé, mois hors exercice, remplacement).
- Synchro Qonto : relevés récupérés en fin de synchro ; erreur des relevés n'empêche pas la synchro.
- API / droits : comptable lit la liste et le PDF, ne récupère ni ne dépose ; pas de route de suppression ;
  compte avec relevés non supprimable.
- Archive : contenu du ZIP (FEC présent ou non, relevés, LISEZMOI).
- Écran (Vitest) : carte Relevés (bouton selon le compte et le rôle, mois manquants, dépôt).

## 7. Découpage

| Lot | Contenu |
|---|---|
| **RQ1** | Table + migration, client (`list_statements`, `statement`), service `fetch_qonto` / `path_for`, API liste + récupération, vue PDF, carte Relevés (liste + bouton) |
| **RQ2** | Récupération automatique en fin de synchro Qonto + compte rendu |
| **RQ3** | Dépôt manuel pour les comptes hors Qonto |
| **RQ4** | Archive ZIP pour l'expert-comptable (FEC + relevés) depuis le panneau FEC |

Essai sur le 5003 après RQ1 (4 relevés attendus : juillet à octobre 2026).

## 8. Points à valider

1. **Récupération au clic synchrone** (pas de tâche de fond) : un exercice = 12 PDF de ~40 Ko au plus.
2. **Dépôt réservé aux comptes hors Qonto.**
3. **Archive expert-comptable** = nouveau ZIP de l'exercice (FEC + relevés) à côté du téléchargement du FEC.
4. Compte bancaire avec relevés **non supprimable** (conséquence de « personne ne supprime »).
