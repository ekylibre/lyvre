# Besoins — Relevés de compte Qonto (PDF)

Demande du 01/11/2026 : « dans les comptes liés à Qonto, un bouton pour récupérer les relevés de compte au
format PDF, les stocker et pouvoir ensuite les consulter depuis l'interface ».

Statut : **besoins complets** (réponses du 01/11/2026, § 6) — reste l'essai réel de l'API, puis la conception.

## 1. Objectif

Avoir dans Lyvre, à côté des transactions d'un compte Qonto, les **relevés mensuels officiels** (PDF de la
banque) : pièces justificatives de la trésorerie, utiles au rapprochement, à la clôture et au contrôle
(expert-comptable, commissaire aux comptes, administration), sans aller les chercher dans Qonto.

## 2. Ce que permet l'API Qonto (vérifié le 01/11/2026 sur docs.qonto.com)

| Point | Documentation |
|---|---|
| Liste | `GET /v2/statements` — filtres `bank_account_ids[]` (ou `ibans[]`, exclusifs), `period_from` / `period_to` (exemples `01-2023`, format ambigu : MM-AAAA dans les exemples, « ISO 8601 » dans le texte), `sort_by`, pagination `page` / `per_page` (max 100) |
| Détail | `GET /v2/statements/{id}` |
| Champs | `id`, `bank_account_id`, `period` (« MM-YYYY »), `file` : `file_name`, `file_content_type` (`application/pdf`), `file_size`, `file_url` |
| Lien du PDF | **expire au bout de 30 minutes** : il faut télécharger et conserver le fichier, pas le lien |
| Authentification | « API key, OAuth 2.0 » ; portée `organization.read` (la même que les transactions déjà synchronisées) |
| Limites | 1 000 requêtes / 10 s par IP ; pas de limite propre aux relevés |

Incertitude : le tableau des portées ne confirme pas explicitement l'accès par **clé d'API** (mode utilisé
par Lyvre). À vérifier par un appel réel sur l'essai Ekylibre (5003), en lecture seule, avant de concevoir.

## 3. Exigences fonctionnelles

- **F1 — Récupérer** : sur la fiche d'un compte bancaire rattaché à Qonto (Banque › Transactions, carte
  Qonto), un bouton « Récupérer les relevés » télécharge les relevés PDF disponibles et absents de Lyvre.
- **F2 — Stocker** : chaque relevé est conservé dans les fichiers de l'instance (comme les pièces
  jointes), avec le compte, le mois, la taille, la date de récupération et l'identifiant Qonto ; un même
  mois n'est pas stocké deux fois.
- **F3 — Consulter** : une liste des relevés du compte (mois, date de récupération, taille) ; un clic
  ouvre le PDF dans le navigateur ; téléchargement possible.
- **F4 — Retour** : à la fin, un message dit combien de relevés ont été récupérés, déjà présents, en
  erreur (motif lisible, jamais le message brut de Qonto).
- **F5 — Sans Qonto** : si l'intégration Qonto est désactivée ou les identifiants absents, le bouton est
  désactivé avec la raison (comme « Synchroniser Qonto ») ; les relevés déjà stockés restent consultables.

## 4. Exigences non fonctionnelles

- **Lecture seule** côté Qonto : aucun envoi, aucune écriture (règle des copies d'essai, voir
  `project_test_copies_no_qonto`).
- **Droits** : récupérer = droit d'écriture sur l'instance ; consulter = lecture (comptable compris), à
  confirmer.
- **Isolement** : fichiers par instance (multi-instance), servis seulement à un utilisateur connecté de
  l'instance, jamais par une URL publique ; le lien Qonto n'est pas conservé.
- **Durée** : la récupération de plusieurs années peut être longue → tâche de fond suivie à l'écran
  (comme la synchronisation Qonto), relançable sans doublon.
- **Sauvegardes** : les relevés font partie des fichiers sauvegardés de l'instance.
- **Erreurs** : lien expiré (> 30 min) → nouvelle demande du relevé, pas d'échec définitif.

## 5. Récits et critères d'acceptation

1. *En tant que trésorier, je récupère d'un clic les relevés Qonto de l'exercice.*
   - Le bouton apparaît seulement sur un compte rattaché à Qonto.
   - Après récupération, juillet à octobre 2026 apparaissent dans la liste du compte Ekylibre.
   - Un second clic ne crée aucun doublon et annonce « 0 nouveau ».
2. *En tant que comptable, je consulte le relevé d'un mois pendant le rapprochement.*
   - Le PDF s'ouvre depuis la liste des relevés, sans passer par Qonto.
3. *En tant qu'administrateur, je sais pourquoi la récupération est impossible.*
   - Intégration désactivée ou clé refusée : message clair, aucun fichier partiel.

## 6. Décisions (réponses du 01/11/2026)

| # | Question | Décision |
|---|---|---|
| R1 | Mois récupérés | **Tous les relevés de l'exercice en cours** (du début de l'exercice au dernier mois disponible) |
| R2 | Déclenchement | Au clic **et automatiquement** à chaque synchronisation Qonto, quand un nouveau relevé est disponible |
| R3 | Comptes hors Qonto | **Oui** : dépôt manuel d'un relevé PDF (compte et mois), dans la même liste |
| R4 | Relevé modifié | **Remplacé** par la nouvelle version |
| R5 | Consultation | Page du compte **et export pour l'expert-comptable** (relevés de l'exercice joints) |
| R6 | Droits | Le comptable (lecture) **consulte** ; **personne ne supprime** un relevé depuis l'interface |
| R7 | Contrôle de solde | **Hors périmètre** pour l'instant |

Conséquences sur les exigences :
- F1 : la récupération porte sur les mois de l'exercice en cours ; F1 bis : la synchronisation Qonto
  récupère aussi les relevés manquants ou changés (en tâche de fond, sans bloquer la synchronisation).
- F2 : un mois déjà stocké est **remplacé** si Qonto renvoie un fichier différent (même compte, même mois).
- F6 — **Déposer** : sur tout compte bancaire, dépôt d'un PDF de relevé pour un mois donné (remplace
  celui du mois, même règle que R4).
- F7 — **Export expert-comptable** : les relevés des mois de l'exercice sont inclus dans l'export
  destiné à l'expert-comptable.
- Pas de suppression dans l'interface (R6) ; droits : récupérer / déposer = écriture, consulter = lecture.
- Question technique restante : remplacement « fichier différent » = taille ou empreinte du PDF.
- Constat : Lyvre n'a pas encore d'« export expert-comptable » (seul le FEC se télécharge,
  `app/views/fec.py`) : F7 suppose de le créer (archive de l'exercice : FEC + relevés), ou de proposer les
  relevés en archive à côté du FEC — à trancher en conception.

## 7. Essai réel de l'API (01/11/2026, essai Ekylibre 5003, lecture seule)

- **La clé d'API fonctionne** (en-tête `identifiant:clé`, production) : l'incertitude du § 2 est levée.
- `period_from=07-2026&period_to=10-2026` (format **MM-AAAA**) : 5 relevés ; sans filtre : 76 relevés
  (historique depuis l'ouverture), une seule page.
- `bank_account_ids[]=<qonto_account_id du compte Lyvre>` : 4 relevés (07 à 10/2026) du compte principal,
  PDF de 37 à 42 Ko, nom du type `2026-07-ekylibre-8704-compte-principal-1-statement.pdf`.
- L'organisation a un **second compte Qonto** (« osfarm », relevé de juillet 2026) non rattaché dans
  Lyvre : il n'est pas récupéré tant qu'il n'est pas rattaché à un compte bancaire Lyvre.
- Aucun PDF téléchargé pendant l'essai.

Suite : `/sc:design`.
