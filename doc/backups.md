# Sauvegardes et restauration d'instances

Chaque instance possède sa propre base SQLite. L'interface `/instances/<id>` permet à un admin de :

- créer une sauvegarde : archive `.zip` contenant la base (copie SQLite « hot », atomique) et les
  **pièces jointes** de l'instance (factures d'achat saisies),
- télécharger un fichier de sauvegarde,
- restaurer l'instance à partir d'une archive `.zip` (base + pièces) ou d'un fichier `.db` (base seule),
- supprimer une vieille sauvegarde.

> Les instances Postgres ne sont pas couvertes par ce mécanisme — un message d'erreur explicite s'affiche, et il faut utiliser `pg_dump` / `pg_restore` côté serveur.

---

## Format des fichiers

Tous les fichiers de sauvegarde vivent dans `instance/backups/`. Convention de nommage :

```
<slug>-YYYYMMDD-HHMMSS.zip                # sauvegarde manuelle
pre-restore-<slug>-YYYYMMDD-HHMMSS.zip    # snapshot automatique pris avant une restauration
<slug>-YYYYMMDD-HHMMSS.db                 # ancienne sauvegarde (base seule), toujours restaurable
```

Contenu d'une archive :

```
database.db                              # copie de la base de l'instance
uploads/achats/AAAA/MM/<id>-<nom>.pdf    # pièces de instance/uploads/<slug>/ (sauf tmp/, en attente)
```

Le préfixe `pre-restore-` distingue les snapshots de sécurité créés automatiquement avant chaque
restauration. Une ancienne sauvegarde `.db` porte le badge « base seule » dans la liste.

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

Cliquer **Télécharger** envoie l'archive (`application/zip`). Une fois décompressée, `database.db` est un fichier SQLite ordinaire — vous pouvez l'ouvrir avec n'importe quel outil (DB Browser for SQLite, sqlite3 CLI, etc.) ; `uploads/` contient les pièces jointes.

> **Attention sécurité** — Un fichier de sauvegarde contient **tous les credentials** stockés dans la table `external_connections`. Traitez ces fichiers comme des secrets : ne les laissez pas traîner sur des disques partagés ou dans des emails non chiffrés.

---

## Importer un fichier (créer ou restaurer depuis la liste)

Depuis **Instances → Importer un fichier**, vous pouvez déposer une archive `.zip` ou un fichier `.db` / `.backup` SQLite. Comportement automatique :

- **Si le slug** déduit du nom de fichier (`<slug>[-YYYYMMDD-HHMMSS]?.zip|db|sqlite|backup`) **correspond à une instance existante** → restauration de cette instance, après **confirmation forte** : l'écran demande de saisir le slug de l'instance (snapshot de sécurité `pre-restore-…` créé automatiquement).
- **Sinon** → création d'une nouvelle instance utilisant le fichier comme base (et, pour une archive, ses pièces dans `instance/uploads/<slug>/`). Le slug et le libellé sont modifiables avant l'envoi.

Cas d'usage typique :

- Migration entre serveurs (téléchargez un backup, copiez le fichier, uploadez côté cible).
- Restauration au sein du même serveur (équivalent à passer par l'écran de détail).
- Création rapide d'une nouvelle instance à partir d'un gabarit existant (clonez `seconde-nature.db` sous un autre nom).

---

## Restaurer une instance

1. **Instances → Détail → Restaurer un fichier…**
2. Déposer une archive `.zip` ou un fichier `.db` (SQLite valide) dans la fenêtre.
3. **Saisir le slug de l'instance** pour confirmer (le bouton reste inactif sinon ; le serveur
   refuse aussi une restauration sans cette confirmation), puis **Restaurer**.

Le service effectue dans l'ordre :

1. Reconnaissance du type par l'en-tête (`SQLite format 3\0` ou `PK\x03\x04`).
2. Archive : contrôle des noms (`database.db` obligatoire, sinon seulement `uploads/…` ; aucun chemin
   absolu, aucun `..`, aucun lien symbolique), du nombre de fichiers (50 000) et de la taille
   décompressée (4 Go).
3. Vérification de l'intégrité de la base via `PRAGMA integrity_check`.
4. Archive : extraction des pièces dans un dossier d'attente (chemins confinés).
5. **Création d'un snapshot de sécurité** (`pre-restore-…`, base et pièces actuelles).
6. Remplacement atomique du fichier de l'instance (`os.replace`), puis du dossier des pièces
   (archive seulement : un `.db` laisse les pièces telles quelles).
7. Purge du cache d'engines pour cette instance.

Si l'une des étapes 1 à 5 échoue, la base et les pièces actuelles restent intactes et un message
d'erreur explicite est affiché.

### Rollback

Le `pre-restore-…` créé à l'étape 5 reste visible dans la liste des sauvegardes. Pour revenir à l'état d'avant restauration, il suffit de :

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
- **Pas de chiffrement** — l'archive (base et pièces) est en clair. Si le serveur héberge des données sensibles, chiffrer le système de fichiers en amont (LUKS, eCryptfs, etc.).
- **Concurrence pendant restauration** — SQLite ne bloque pas les requêtes lectures en cours, mais une lecture commencée juste avant le `os.replace` peut voir un état incohérent. À éviter en heures de pointe ; un mode maintenance sera ajouté plus tard si nécessaire.
- **Pas d'audit log** — l'horodatage des fichiers est la seule trace.

---

## Dépannage

| Message | Cause | Action |
|---------|-------|--------|
| « Sauvegardes disponibles uniquement pour les instances SQLite » | L'instance pointe sur Postgres ou autre. | Utiliser les outils natifs (`pg_dump`). |
| « Le fichier n'est ni une base SQLite ni une archive de sauvegarde » | En-tête inconnu — fichier corrompu ou mauvais format. | Vérifier que le fichier provient bien d'une sauvegarde précédente. |
| « Archive refusée : … » | Archive modifiée ou étrangère (chemin interdit, contenu inattendu, `database.db` absent, trop volumineuse). | Utiliser une archive produite par l'application. |
| « PRAGMA integrity_check a échoué » | Fichier SQLite corrompu. | Régénérer une sauvegarde depuis une source saine. |
| « Le fichier dépasse la taille maximale » | > 500 Mo. | Augmenter `MAX_CONTENT_LENGTH` dans `app/__init__.py` et redémarrer. |
| « Nom de fichier de sauvegarde invalide » | URL trafiquée (ne matche pas la regex). | Ne pas modifier les URLs à la main — utiliser les liens de l'UI. |
