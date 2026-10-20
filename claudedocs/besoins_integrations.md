# Besoins — Écran des intégrations

> Statut : **RÉALISÉ** (2026-10-20). Questions ouvertes tranchées dans `design_integrations.md` §1 ;
> écarts de mise en œuvre dans `design_integrations.md` §13.

## 1. Contexte

| Constat (état au commit `f3b10b4`) | Valeur |
|------------------------------------|--------|
| Écran | `/configuration/external-connections/` — `external_connections/index.html` |
| Intégrations | 6 : Stancer, Odoo, HelloAsso, SMTP, Google Analytics (GA4), Facebook (Page) |
| Présentation | Une carte par intégration, **tous les champs de toutes les intégrations sur une seule page** |
| Statut affiché | « Configuré » / « À configurer » = champs obligatoires remplis (base ou repli `.env`) |
| Notion d'activation | Aucune : une intégration configurée est utilisée d'office |
| Test de fonctionnement | Uniquement SMTP (bouton « Tester la connexion », `check_smtp_connection`) |
| Suivi des synchronisations | `SyncJob` pour Stancer (`payouts`, `payout_payments`) et métriques (GA4 + Facebook) ; rien pour Odoo ni HelloAsso |

Problèmes : page longue et peu lisible, impossible de savoir si des identifiants saisis **fonctionnent
réellement** (une clé expirée reste « Configuré »), impossible de couper une intégration sans effacer
ses identifiants.

## 2. Objectifs

- **O1 — Vue d'ensemble lisible** : voir d'un coup d'œil quelles intégrations sont actives et opérationnelles.
- **O2 — Configuration ciblée** : on configure une intégration à la fois, sur sa propre page.
- **O3 — Confiance** : savoir si les identifiants fonctionnent, dès l'enregistrement et à la demande.
- **O4 — Maîtrise** : pouvoir désactiver une intégration sans perdre sa configuration.

## 3. Utilisateurs

| Profil | Usage | Attentes |
|--------|-------|----------|
| Administrateur de l'instance | Ponctuel : mise en place, renouvellement d'une clé, diagnostic d'une synchro en échec | Statut clair, message d'erreur compréhensible, pas de fuite de secrets |

Accès inchangé : réservé aux administrateurs (`admin_required`), par instance (base tenant).

## 4. Besoins fonctionnels

### F1 — Page index
- F1.1 Liste des 6 intégrations (carte ou ligne), chacune avec : nom, courte description de son usage
  dans l'application, **statut**, date et résultat du dernier test.
- F1.2 Statuts possibles (un seul affiché, par ordre de priorité) :

  | Statut | Condition |
  |--------|-----------|
  | **Désactivée** | Interrupteur sur « off » (quelle que soit la configuration) |
  | **À configurer** | Activée, mais champs obligatoires incomplets (base + repli `.env`) |
  | **Non testée** | Activée, configurée, aucun test depuis la dernière modification de la configuration |
  | **Opérationnelle** | Dernier test réussi, configuration inchangée depuis |
  | **En erreur** | Dernier test en échec |

- F1.3 Un clic sur une intégration ouvre sa page de détail.
- F1.4 La page index **ne lance aucun appel externe** : elle affiche le dernier résultat connu.

### F2 — Page de détail (une par intégration)
- F2.1 Interrupteur **Activée / Désactivée**, modifiable indépendamment du formulaire.
- F2.2 Formulaire des champs de l'intégration, avec les comportements actuels conservés :
  champs obligatoires marqués, origine de la valeur (en base / repli `.env`), secrets jamais réaffichés
  (champ vide + « laisser vide pour garder »), `credentials_json` en zone de texte.
- F2.3 Bloc **état** : statut (F1.2), date du dernier test, message du dernier test (succès : ce qui a
  été vérifié, ex. « Connecté à Odoo en tant que … » ; échec : cause lisible).
- F2.4 Bouton **Tester maintenant** (généralise le bouton SMTP actuel à toutes les intégrations),
  désactivé si l'intégration est désactivée ou incomplète.
- F2.5 Bloc **dernière synchronisation** quand elle existe : date, statut et message du dernier
  `SyncJob` du service, avec lien vers l'écran concerné (Versements Stancer, Visibilité & Impact…).
  Absent pour les intégrations sans synchronisation suivie (voir Q3).
- F2.6 Lien de retour vers l'index.

### F3 — Test de fonctionnement
- F3.1 Déclenché **automatiquement après chaque enregistrement** de la configuration d'une intégration
  activée et complète, et **manuellement** par le bouton F2.4. Pas de test au chargement de l'index
  ni de test périodique.
- F3.2 Le test vérifie une **authentification réelle** par un appel léger et en lecture seule :

  | Intégration | Vérification attendue |
  |-------------|----------------------|
  | Stancer | Lecture d'un versement (liste limitée à 1) avec la clé et le mode configurés |
  | Odoo | Authentification XML-RPC (URL, base, login, clé API) |
  | HelloAsso | Obtention d'un jeton OAuth2 + lecture de l'organisation `org_slug` |
  | SMTP | Connexion, TLS le cas échéant, authentification, `NOOP` (comportement actuel) |
  | GA4 | Rapport minimal sur la propriété avec la clé du compte de service |
  | Facebook | Lecture de la Page `page_id` avec le token |

- F3.3 Le résultat (succès/échec, date, message) est **conservé** pour être affiché sur l'index et
  le détail ; seul le **dernier** résultat est gardé (pas d'historique).
- F3.4 Toute modification de la configuration (enregistrement) remet le statut à « Non testée »
  jusqu'au test suivant (automatique en F3.1, donc transitoire en pratique).
- F3.5 Un test en échec n'empêche pas l'enregistrement : la configuration est enregistrée, le statut
  passe à « En erreur » avec le message.

### F4 — Effet de l'activation sur le reste de l'application
- F4.1 Une intégration **désactivée** est traitée partout comme non disponible : boutons de
  synchronisation / relance / mise à jour masqués ou désactivés (Versements Stancer, Commandes et
  factures Odoo, Adhérents HelloAsso / relances SMTP / mise à jour Odoo, synchro des métriques).
- F4.2 Le message affiché à ces endroits distingue « désactivée » de « non configurée » et renvoie
  vers la page de détail de l'intégration.
- F4.3 Par défaut (migration), une intégration est **activée** : aucun changement de comportement
  pour les instances existantes.

## 5. Besoins non fonctionnels

- NF1 **Sécurité** : aucun secret dans les messages de test, les journaux ni le HTML (y compris les
  erreurs renvoyées par les API externes, à filtrer). Actions de modification protégées par CSRF.
- NF2 **Délai** : chaque test borné par un timeout (≤ 10 s) ; l'enregistrement reste utilisable si
  le service externe ne répond pas (le test échoue proprement avec « délai dépassé »).
- NF3 **Messages en français**, compréhensibles par un non-technicien (« Clé API refusée par Odoo »
  plutôt qu'une trace XML-RPC brute ; le détail technique peut suivre).
- NF4 **Multi-instance** : activation et résultats de test propres à chaque instance (base tenant).
- NF5 **Cohérence UI** : conventions actuelles (Bootstrap 5, HTMX / `hx-select`, toasts) ; pas
  d'îlot React nécessaire.
- NF6 **Testabilité** : chaque test d'intégration remplaçable par un double en test (aucun appel
  réseau dans pytest).

## 6. Récits utilisateur et critères d'acceptation

**US1 — Vue d'ensemble.** En tant qu'admin, j'ouvre Paramètres › Connexions externes et je vois
les 6 intégrations avec leur statut.
- [x] L'index n'affiche aucun champ de configuration.
- [x] Une intégration désactivée apparaît « Désactivée » même si elle est configurée.
- [x] L'ouverture de l'index ne déclenche aucun appel réseau.

**US2 — Configurer une intégration.** Je clique sur Odoo, je saisis les identifiants et j'enregistre.
- [x] La page de détail ne montre que les champs d'Odoo.
- [x] Après enregistrement, un test est lancé et son résultat est affiché (succès ou cause de l'échec).
- [x] Le statut de l'index reflète ce résultat.

**US3 — Diagnostiquer.** Une synchro Stancer échoue ; j'ouvre Stancer et je clique « Tester maintenant ».
- [x] Le résultat indique la cause (clé refusée, délai dépassé, mode incohérent…).
- [x] Je vois aussi la date et le statut de la dernière synchronisation des versements.

**US4 — Couper une intégration.** Je désactive Facebook sans effacer le token.
- [x] Le token reste enregistré ; réactiver suffit à reprendre.
- [x] Les actions qui dépendent de Facebook ne sont plus proposées, avec un message renvoyant vers l'intégration.

**US5 — Rien ne casse.** Après migration, une instance existante fonctionne comme avant.
- [x] Toutes les intégrations sont activées ; leur statut est « Non testée » (ou « À configurer »).
- [x] Le repli `.env` fonctionne toujours.

## 7. Hors périmètre

- Test au chargement de l'index et test périodique / planifié (pas d'ordonnanceur aujourd'hui).
- Historique des tests et alertes (email, notification) en cas d'échec.
- Vérification des **permissions** fines (droits d'écriture Odoo, expiration du token Facebook…).
- Ajout de nouvelles intégrations ; guide de récupération des identifiants dans l'écran.

## 8. Questions ouvertes (à trancher en `/sc:design`)

1. **Q1 — Stockage** : activation et dernier test dans `external_connections` (clés réservées
   `_enabled`, `_last_check_*`) ou nouvelle table dédiée (une ligne par service) ?
2. **Q2 — Activation et repli `.env`** : une intégration configurée uniquement par `.env` peut-elle
   être désactivée depuis l'UI ? (Proposition : oui, l'interrupteur prime sur `.env`.)
3. **Q3 — Dernière synchronisation pour Odoo, HelloAsso, SMTP** : pas de `SyncJob` aujourd'hui.
   Afficher « non suivi », ou tracer leurs opérations (import commandes/factures, synchro adhérents,
   envoi de relances) ? GA4 et Facebook partagent le `SyncJob` `metrics` : afficher le même pour les deux ?
4. **Q4 — Test synchrone ou en arrière-plan** : le test après enregistrement peut prendre jusqu'à
   10 s (NF2). Réponse bloquante avec indicateur, ou test HTMX déclenché au chargement de la page de
   détail après redirection ?
5. **Q5 — URL** : garder `/configuration/external-connections/` (+ `/<service>`) ou renommer en
   « Intégrations » (`/configuration/integrations/`) avec redirection ? Le libellé de menu change-t-il ?
