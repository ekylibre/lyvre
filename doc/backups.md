# Sauvegardes et restauration d'instances

Chaque instance possède sa propre base SQLite. L'interface `/instances/<id>` permet à un admin de :

- créer une sauvegarde atomique (copie SQLite « hot »),
- télécharger un fichier de sauvegarde,
- restaurer l'instance à partir d'un fichier `.db`,
- supprimer une vieille sauvegarde.

> Les instances Postgres ne sont pas couvertes par ce mécanisme — un message d'erreur explicite s'affiche, et il faut utiliser `pg_dump` / `pg_restore` côté serveur.

---

## Format des fichiers

Tous les fichiers de sauvegarde vivent dans `instance/backups/`. Convention de nommage :

```
<slug>-YYYYMMDD-HHMMSS.db                # sauvegarde manuelle
pre-restore-<slug>-YYYYMMDD-HHMMSS.db    # snapshot automatique pris avant une restauration
```

Le préfixe `pre-restore-` distingue les snapshots de sécurité créés automatiquement avant chaque restauration.

---

## Créer une sauvegarde

1. Menu utilisateur → **Instances**.
2. Cliquer sur **Détail** à côté de l'instance souhaitée.
3. Cliquer sur **Créer une sauvegarde** dans le cadre « Sauvegardes ».

Sous le capot, le service utilise l'API en ligne de SQLite (`sqlite3.Connection.backup`), donc :

- la sauvegarde est **atomique**,
- les lecteurs concurrents (autres requêtes HTTP) ne sont pas bloqués,
- aucune action n'est nécessaire de la part de l'utilisateur final.

La sauvegarde apparaît immédiatement dans la liste, avec sa taille et son horodatage.

---

## Télécharger une sauvegarde

Cliquer **Télécharger** envoie le fichier `.db` au navigateur en `application/octet-stream`. Le contenu est identique à un fichier SQLite ordinaire — vous pouvez l'ouvrir avec n'importe quel outil (DB Browser for SQLite, sqlite3 CLI, etc.).

> **Attention sécurité** — Un fichier de sauvegarde contient **tous les credentials** stockés dans la table `external_connections`. Traitez ces fichiers comme des secrets : ne les laissez pas traîner sur des disques partagés ou dans des emails non chiffrés.

---

## Restaurer une instance

1. **Instances → Détail → Restaurer un fichier…**
2. Sélectionner un fichier `.db` (SQLite valide).
3. Confirmer la boîte de dialogue.

Le service effectue dans l'ordre :

1. Vérification du magic header (`SQLite format 3\0`).
2. Vérification de l'intégrité via `PRAGMA integrity_check`.
3. **Création d'un snapshot de sécurité** (`pre-restore-…`) de la base actuelle.
4. Remplacement atomique du fichier de l'instance (`os.replace`).
5. Purge du cache d'engines pour cette instance.

Si l'une de ces étapes échoue, la base actuelle reste intacte et un message d'erreur explicite est affiché.

### Rollback

Le `pre-restore-…` créé à l'étape 3 reste visible dans la liste des sauvegardes. Pour revenir à l'état d'avant restauration, il suffit de :

1. Cliquer **Télécharger** sur le `pre-restore-…`.
2. Cliquer **Restaurer un fichier…** et uploader ce fichier.

---

## Supprimer une sauvegarde

Cliquer **Supprimer** sur une ligne de la liste demande confirmation puis supprime le fichier du disque. Aucune trace n'est conservée.

---

## Tailles et rétention

- Limite d'upload : **500 Mo** par fichier (`MAX_CONTENT_LENGTH` dans `app/__init__.py`).
- Aucune purge automatique des vieux fichiers — l'admin gère manuellement.
- Les sauvegardes consomment l'espace disque du serveur ; pour une rétention longue, télécharger et stocker hors-ligne.

---

## Limitations connues (v1)

- **Postgres non supporté** pour backup/restore via UI.
- **Pas de planification** — il n'y a pas de cron intégré. Pour des sauvegardes automatisées, un cron côté OS peut appeler la base de données directement (à scripter à part).
- **Pas de chiffrement** — le fichier `.db` est en clair. Si le serveur héberge des données sensibles, chiffrer le système de fichiers en amont (LUKS, eCryptfs, etc.).
- **Concurrence pendant restauration** — SQLite ne bloque pas les requêtes lectures en cours, mais une lecture commencée juste avant le `os.replace` peut voir un état incohérent. À éviter en heures de pointe ; un mode maintenance sera ajouté plus tard si nécessaire.
- **Pas d'audit log** — l'horodatage des fichiers est la seule trace.

---

## Dépannage

| Message | Cause | Action |
|---------|-------|--------|
| « Sauvegardes disponibles uniquement pour les instances SQLite » | L'instance pointe sur Postgres ou autre. | Utiliser les outils natifs (`pg_dump`). |
| « Le fichier n'est pas une base SQLite valide » | Magic header absent — fichier corrompu ou mauvais format. | Vérifier que le fichier provient bien d'une sauvegarde précédente. |
| « PRAGMA integrity_check a échoué » | Fichier SQLite corrompu. | Régénérer une sauvegarde depuis une source saine. |
| « Le fichier dépasse la taille maximale » | > 500 Mo. | Augmenter `MAX_CONTENT_LENGTH` dans `app/__init__.py` et redémarrer. |
| « Nom de fichier de sauvegarde invalide » | URL trafiquée (ne matche pas la regex). | Ne pas modifier les URLs à la main — utiliser les liens de l'UI. |
