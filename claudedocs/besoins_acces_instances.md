# Besoins — Utilisateurs et rôles dès la création d'une instance

Brainstorm du 23/10/2026. Spécification de besoins uniquement : la conception viendra avec `/sc:design`
ou `/sc:workflow`.

## 1. Contexte : ce qui existe

- **Accès sélectif par rôle** (lot A, `instance_memberships`) :
  - trois rôles : Administrateur, Trésorier, Expert-comptable (lecture seule, contrôlée côté serveur) ;
  - un administrateur global (`users.is_admin`) est administrateur de toutes les instances, sans ligne d'accès ;
  - les autres utilisateurs ne voient que leurs instances.
- **Gestion actuelle des accès** :
  - page **Utilisateurs** (administrateur global) : un rôle par instance pour chaque utilisateur ;
  - page **Accès** (administrateur de l'instance, depuis l'instance) : ajout par email d'un compte
    existant, ou d'un nouveau compte avec mot de passe initial ; modification du rôle, retrait ;
    garde « au moins un administrateur ».
- **Manque** :
  - le formulaire « Nouvelle instance » et l'import d'une instance depuis un fichier ne donnent aucun
    accès : seuls les administrateurs globaux y entrent ensuite ;
  - l'administrateur global ne peut pas gérer les membres depuis la fiche de l'instance
    (`/instances/<id>`) sans s'y connecter.

## 2. Décisions du brainstorm

| Sujet | Décision |
|---|---|
| Rôles | Inchangés : Administrateur, Trésorier, Expert-comptable |
| Nombre d'utilisateurs à la création | Plusieurs, liste facultative |
| Nouveau compte | Mot de passe initial saisi par l'administrateur, transmis hors application (pas d'invitation par email) |
| Où | Formulaire « Nouvelle instance », import d'instance depuis un fichier, fiche instance de l'administrateur global |
| Administrateur parmi les lignes | Avertissement sans blocage s'il n'y en a aucun |
| Comptes désactivés | Accès possible ; il prend effet à la réactivation du compte |
| Mot de passe initial | Changement obligatoire à la première connexion (F5) |
| Qui crée les instances | L'administrateur global seulement |

## 3. Objectifs

1. Créer une instance **prête à l'emploi** : l'association a ses utilisateurs et leurs rôles dès sa
   création, sans aller-retour par la page Utilisateurs ni connexion à l'instance.
2. Permettre à l'administrateur global de **gérer les accès d'une instance depuis sa fiche**, avec
   les mêmes règles que la page Accès.

## 4. Exigences fonctionnelles

### F1 — Section « Utilisateurs et rôles » à la création

- **F1.1** Le formulaire « Nouvelle instance » a une section facultative « Utilisateurs et rôles » :
  une liste de lignes ; chaque ligne porte un utilisateur et un rôle.
- **F1.2** Chaque ligne choisit entre :
  - **un utilisateur existant**, par une liste à recherche (nom, email). Les administrateurs globaux
    sont exclus ; les comptes désactivés sont proposés avec une mention « désactivé » ;
  - **un nouvel utilisateur** : email, nom (facultatif), mot de passe initial (8 caractères au moins).
- **F1.3** Le rôle se choisit parmi les trois rôles existants. Valeur proposée : Administrateur pour
  la première ligne, Trésorier pour les suivantes.
- **F1.4** Un même utilisateur ne figure qu'une fois. Un email saisi en « nouvel utilisateur » qui
  correspond à un compte existant est signalé : la ligne propose de prendre ce compte.
- **F1.5** Contrôle d'ensemble avant toute création. Si une ligne est invalide (email, mot de passe,
  rôle, doublon), rien n'est créé : ni la base, ni l'instance, ni les comptes. L'erreur est rattachée
  à la ligne fautive.
- **F1.6** En cas de succès, la notification résume ce qui a été fait, par exemple : « Instance
  créée ; 1 compte créé, 2 accès donnés ».
- **F1.7** Une instance sans aucune ligne reste possible ; elle n'est alors accessible qu'aux
  administrateurs globaux. Une aide le rappelle.
- **F1.8** Avec au moins une ligne mais aucun Administrateur, un avertissement non bloquant indique
  que seuls les administrateurs globaux pourront gérer les accès de l'instance.
- **F1.9** Un accès donné à un compte désactivé est accepté. Il prend effet à la réactivation du
  compte, et la ligne le signale.

### F2 — Import d'une instance depuis un fichier

- **F2.1** La même section est proposée quand l'import **crée** une instance (slug inconnu).
- **F2.2** Elle n'est pas proposée quand l'import **restaure** une instance existante : les accès,
  stockés dans la méta-base, restent inchangés.
- **F2.3** Même règle de tout ou rien que F1.5 : si les accès sont invalides, le fichier n'est pas
  installé.

### F3 — Accès depuis la fiche instance (administrateur global)

- **F3.1** La fiche `/instances/<id>` a une section « Accès » :
  - liste des membres (nom, email, rôle, compte actif ou non) ;
  - administrateurs globaux affichés à part, non modifiables.
- **F3.2** Actions identiques à la page Accès : ajouter un utilisateur existant ou nouveau, changer
  un rôle, retirer un accès.
- **F3.3** Les règles et messages sont ceux de la page Accès actuelle : garde « au moins un
  administrateur » (hors administrateurs globaux), refus pour un administrateur global, refus d'un
  doublon. Les deux écrans partagent la même logique côté serveur, sans divergence.
- **F3.4** Ces actions fonctionnent aussi sur une instance désactivée, pour préparer les accès
  avant de la réactiver.

### F4 — Cohérence

- **F4.1** Les accès donnés à la création apparaissent aussitôt sur la page Utilisateurs (colonne
  « Accès ») et sur la page Accès de l'instance.
- **F4.2** Chaque accès créé enregistre son auteur (`created_by_user_id`), comme aujourd'hui.

### F5 — Changement du mot de passe initial

- **F5.1** Un compte créé avec un mot de passe initial est marqué « mot de passe à changer ». Cela
  vaut pour tous les points de création : création d'instance, import, fiche instance, page Accès,
  page Utilisateurs.
- **F5.2** Le marquage s'applique aussi quand un administrateur fixe le mot de passe d'un autre
  utilisateur. Il ne s'applique pas quand l'utilisateur change son propre mot de passe.
- **F5.3** À la connexion, un compte marqué est dirigé vers un écran « Choisissez votre mot de
  passe » : mot de passe actuel, nouveau mot de passe (8 caractères au moins, différent de
  l'actuel), confirmation. Le reste de l'application reste inaccessible jusqu'au changement.
- **F5.4** Le blocage vaut aussi côté serveur : tant que le mot de passe n'est pas changé, l'API
  refuse tout, sauf la session, le changement de mot de passe et la déconnexion.
- **F5.5** Une fois le mot de passe changé, le marquage est levé et l'utilisateur arrive sur son
  instance comme d'habitude.

## 5. Exigences non fonctionnelles

- **Sécurité**
  - Création d'instance, import et section Accès de la fiche : réservés à l'administrateur global,
    contrôlé côté serveur.
  - Les mots de passe initiaux ne sont jamais renvoyés ni journalisés.
  - Les mots de passe sont hachés comme pour les autres comptes.
- **Atomicité** : validation complète avant le provisioning de la base. Si l'écriture des comptes
  ou des accès échoue après le provisioning, la base créée est supprimée.
- **Cohérence** : aucune nouvelle notion de rôle ; mêmes libellés et mêmes messages que la page Accès.
- **Accessibilité et ergonomie**
  - Lignes ajoutées et retirées au clavier.
  - Erreurs annoncées par ligne.
  - Formulaire utilisable sur téléphone.
- **Tests**
  - API : création avec comptes nouveaux et existants, doublons, tout ou rien, import en création
    ou en restauration, gardes de la fiche, blocage tant que le mot de passe n'est pas changé.
  - Vitest : formulaire.
  - E2E : un parcours de création avec deux utilisateurs.

## 6. Histoires utilisateur et critères d'acceptation

**US1. Créer une instance avec son trésorier.**
En tant qu'administrateur global, je crée « Asso X », j'ajoute marie@… (compte existant) en
Trésorier et un nouveau compte paul@… en Administrateur.
- Après création, Marie et Paul voient Asso X dans leur sélecteur d'instances, chacun avec son rôle.
- Paul se connecte avec le mot de passe initial et doit le changer avant d'accéder à l'instance.
- Aucun autre utilisateur non administrateur ne voit Asso X.

**US2. Erreur sans effet de bord.**
Je crée une instance dont une ligne a un mot de passe trop court.
- La création est refusée et l'erreur s'affiche sur cette ligne.
- Aucune base, aucune instance et aucun compte ne sont créés.

**US3. Import avec utilisateurs.**
J'importe une sauvegarde sous un slug nouveau et j'ajoute un expert-comptable.
- L'instance est créée depuis le fichier.
- L'expert-comptable y accède en lecture seule.

**US4. Restauration sans toucher aux accès.**
J'importe une sauvegarde sur un slug existant.
- La section utilisateurs n'est pas proposée.
- Les accès existants sont inchangés.

**US6. Premier changement de mot de passe.**
Paul se connecte pour la première fois avec son mot de passe initial.
- Il arrive sur « Choisissez votre mot de passe ».
- Les autres pages et l'API lui restent fermées tant que le mot de passe n'est pas changé.
- Après le changement, il arrive sur Asso X ; à la connexion suivante, il n'est plus redirigé.

**US5. Gérer les accès depuis la fiche.**
Depuis `/instances/<id>`, je change le rôle de Paul et je retire Marie.
- Les changements sont visibles sur la page Utilisateurs.
- Retirer le dernier administrateur de l'instance est refusé avec le message habituel.

## 7. Hors périmètre

- Nouveaux rôles ou droits par domaine.
- Invitation par email, réinitialisation de mot de passe en libre-service (« mot de passe oublié »).
- Envoi automatique des identifiants.
- Changement de l'administrateur global en membre d'instance.

## 8. Questions tranchées (23/10/2026)

1. **Administrateur parmi les lignes** : avertissement sans blocage (F1.8).
2. **Comptes désactivés** : accès possible, effectif à la réactivation (F1.9).
3. **Mot de passe initial** : changement obligatoire à la première connexion (F5).
4. **Création d'instance** : réservée à l'administrateur global.
