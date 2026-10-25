# Besoins — fonctions réservées aux associations, pré-remplissage par l'API Sirene

Brainstorm du 25/10/2026. Deux sujets indépendants :

- **A.** n'afficher les éléments propres aux associations que pour une association ;
- **B.** pré-remplir la structure et les tiers depuis l'API Sirene v4 de l'INSEE.

---

## A. Éléments propres aux associations

### Constat

Le critère existe déjà : c'est le plan comptable de l'instance (`instances.chart` : `asso`, `sci`). Le menu filtre
correctement par ce critère. Il masque déjà pour une SCI :

- Dons et Reçus fiscaux ;
- États ;
- Recettes et dépenses ;
- Indicateurs ;
- Adhérents et Temps de travaux ;
- Configuration › Reçus fiscaux et Catégories ;
- Import de tonnages.

Il reste des éléments d'association **dans des pages communes**.

### Exigences

Règle générale : « association » veut dire `chart == "asso"`. Toute autre structure (SCI aujourd'hui, entreprise demain)
ne voit pas ces éléments.

| # | Écran | Élément | Association | Autre structure |
|---|---|---|---|---|
| A1 | Tableau de bord | Tuile « Adhésions » | visible | masquée |
| A2 | Configuration › Structure | Numéro RNA | visible | masqué |
| A3 | Configuration › Structure | Bloc « Signataire des reçus fiscaux » | visible | masqué |
| A4 | Configuration › Structure | Bloc « Associés (sociétés) » | **masqué** | visible |
| A5 | Tiers › formulaire | Cases « Adhérent de l'association », « Bénévole » | visible | masquées |
| A6 | Tiers › formulaire | Nature et mention « exigées pour un reçu fiscal », aide HelloAsso de l'e-mail | visible | masquées. L'adresse reste visible, utile aux factures et aux baux. |
| A7 | Tiers › fiche | Badges Adhérent / Bénévole, tuiles d'adhésion (HelloAsso, caisse), temps de bénévolat, section HelloAsso | visible | masqués |
| A8 | Exercices › clôture | Étape et écritures de fonds dédiés | visible | masquée |

- **A9** — Le serveur applique la même règle. Les données concernées ne sont ni calculées ni renvoyées pour une autre structure, par exemple `new_members` du tableau de bord. Les routes propres aux associations (reçus fiscaux, fonds dédiés) refusent une autre structure : le menu ne suffit pas, une URL saisie à la main doit aussi être refusée.
- **A10** — Les données déjà en base ne sont ni modifiées ni supprimées : elles sont seulement masquées. Exemple : un tiers marqué adhérent avant le passage en SCI.
- **A11** — Les libellés communs restent neutres. Exemple : la description de la page Structure ne cite plus les reçus fiscaux pour une SCI.

### Critères d'acceptation

- Sur une instance SCI, aucun des éléments A1–A3 et A5–A8 n'apparaît, et le bloc Associés (A4) apparaît.
- Sur une instance association, l'affichage est l'inverse.
- Une route d'association appelée directement sur une SCI répond 404, ou 403 si c'est l'usage du projet.
- Les tests couvrent les deux structures pour chaque écran modifié.

---

## B. Pré-remplissage par l'API Sirene v4

### Constat technique (vérifié le 25/10/2026 avec la clé du `.env`)

**Accès**
- Base : `https://api.insee.fr/api-sirene/4`, version 4.0.8.0.
- En-tête d'authentification : `X-INSEE-Api-Key-Integration`.
- La v4 est en bêta ouverte depuis le 13/10/2026. Elle deviendra la version officielle mi-2027 ; la 3.11 est maintenue jusqu'à mi-2028, mais n'accepte pas cette clé.

**Routes**
- `GET /etat-courant/unites-legales/{siren}` renvoie :
  - `denominationUniteLegale`, `sigleUniteLegale` ;
  - `categorieJuridiqueUniteLegale` (code, par exemple 6540 = SCI) ;
  - `activitePrincipaleUniteLegale` (NAF) ;
  - `etatUniteLegale` (4 = cessée) ;
  - `nicSiegeUniteLegale` ;
  - `identifiantAssociationUniteLegale` (RNA).
- `GET /etat-courant/etablissements/{siret}?champs=…` : l'adresse (`adresseEtablissement`) n'est renvoyée que si on la demande dans `champs`. L'adresse du siège demande un second appel (SIREN + NIC du siège).
- `POST /etat-courant/unites-legales/multicritere` : recherche avec un corps JSON (`denominationUniteLegale`, `etatUniteLegale`, `nombre`, `curseur`).
  - Les résultats sont nombreux, triés par pertinence, actifs et cessés mêlés : il faut filtrer sur l'état et limiter le nombre.
- `POST /etat-courant/etablissements/multicritere` : filtres `siren`, `codePostalEtablissement`, `etatEtablissement`, etc. Pas de filtre sur la raison sociale.

**Contenu**
- Pas de TVA intracommunautaire dans la v4. Elle peut se calculer à partir du SIREN (clé FR), mais rien ne garantit que l'entreprise soit assujettie.
- Quota : **30 requêtes par minute**, 2 000 par heure. Au-delà, l'API répond 429, avec les en-têtes `x-rate-limit-*`.

### Décisions de l'utilisateur

- **D1** — La clé est **une clé du serveur** : variables `SIRENE_API_URL` et `SIRENE_API_KEY`, comme `MAIL_*`. Il n'y a ni intégration ni réglage par instance. Sans clé configurée, les boutons Sirene sont absents.
- **D2** — Les tiers se cherchent **par nom ou par numéro** (SIREN ou SIRET), avec un code postal facultatif, puis on choisit dans une liste.
- **D3** — Quand un champ est déjà rempli, on **montre les différences** :
  - un champ vide est rempli directement ;
  - un champ rempli mais différent est listé (valeur actuelle → valeur Sirene), et on coche ce qu'on remplace ;
  - rien n'est enregistré avant « Enregistrer ».

### Exigences — structure (Configuration › Structure)

- **B1** — Un bouton « Compléter depuis Sirene » à côté du SIREN. Il s'active quand le SIREN fait 9 chiffres valides (contrôle de Luhn).
- **B2** — Champs proposés :
  - raison sociale ;
  - adresse du siège : ligne 1 (numéro + indice + type de voie + libellé), complément, code postal, ville, pays « France » ;
  - forme juridique (libellé tiré du code de catégorie juridique) ;
  - RNA pour une association ;
  - code NAF (D6) ;
  - TVA intracommunautaire calculée (D7).
- **B3** — Si l'unité légale est cessée ou introuvable, un message clair s'affiche et aucun champ n'est modifié.

### Exigences — tiers (création et modification)

- **B4** — Une zone de recherche dans le formulaire du tiers :
  - la saisie de 9 ou 14 chiffres déclenche une recherche directe par numéro ;
  - sinon, une recherche par nom, avec un code postal facultatif ;
  - la recherche est déclenchée par un bouton ou par Entrée, pas à chaque frappe, à cause du quota.
- **B5** — Liste de résultats, 10 au plus, unités actives d'abord : raison sociale, SIREN, ville du siège, forme juridique. Le choix d'une ligne propose les champs selon D3.
- **B6** — Champs proposés au tiers :
  - nom ;
  - SIRET du siège, ou de l'établissement choisi si on a saisi un SIRET ;
  - adresse ligne 1, complément, code postal, ville, pays ;
  - personne morale ou physique (`person_kind`) ;
  - TVA intracommunautaire calculée, signalée « calculée, à vérifier » (D7) ;
  - code NAF (D6) ;
  - TVA intracommunautaire calculée (D7).
- **B7** — Entrepreneur individuel : le nom est composé du prénom et du nom. Si la diffusion est restreinte (`statutDiffusion` = P), seuls les champs diffusés sont proposés, avec une mention.
- **B8** — Le nom d'un tiers est unique en base. Si le nom Sirene existe déjà pour un autre tiers, on le signale avant l'enregistrement.

### Exigences non fonctionnelles

- **B9** — Les appels partent **du serveur**, jamais du navigateur : la clé ne quitte pas le serveur. Un point d'API Lyvre authentifié sert de relais.
- **B10** — Respect du quota :
  - cache serveur des réponses par SIREN ou SIRET (24 h) ;
  - un 429 donne le message « réessayez dans une minute » ;
  - délai d'attente court (10 s).
- **B11** — L'API Sirene en panne n'empêche pas la saisie manuelle : la recherche affiche simplement une erreur.
- **B12** — Les tests n'appellent jamais l'API réelle : les réponses sont simulées, à partir d'exemples réels anonymisés ou de données publiques.
- **B13** — Le rôle Expert-comptable (lecture seule) ne voit pas les boutons qui modifient une fiche.
- **B14** — Documentation : la variable `SIRENE_*` est décrite dans `doc/docker.md` et dans l'exemple d'environnement. Sur Lyvre, elle s'ajoute dans l'onglet Environment.

### Critères d'acceptation

- SIREN 840 968 499 saisi dans Structure, puis « Compléter » : les champs vides se remplissent et les différences s'affichent à cocher.
- Dans un nouveau tiers, la recherche « floricotte » propose l'entreprise, et la choisir remplit le nom, le SIRET et l'adresse.
- Sans `SIRENE_API_KEY`, aucun bouton Sirene n'apparaît.
- Au 31e appel dans la minute, l'utilisateur voit un message d'attente, pas une erreur technique.

---

## Décisions complémentaires (25/10/2026)

- **D4 (Q1) — Unifier les mentions légales.** Forme juridique, greffe ou RCS et TVA intracommunautaire de la structure : une seule saisie, dans Configuration › Structure, reprise par les baux et par les factures.
  - Ventes › Facturation n'affiche plus ces champs. Il montre la valeur de Structure, avec un lien pour la modifier.
  - Les valeurs déjà saisies dans Facturation sont reprises dans Structure à la migration, si Structure est vide. Si les deux sont remplies et diffèrent, c'est la valeur de Structure qui reste ; la différence est journalisée pour vérification.
  - La mention « RCS Saintes 840 968 499 » des factures est composée à partir du greffe et du SIREN.
- **D5 (Q2) — Casse.** La valeur Sirene est proposée telle quelle (souvent en majuscules). L'utilisateur la modifie dans le champ s'il le souhaite, avant d'enregistrer. Pas de mise en forme automatique.
- **D6 (Q3) — Code NAF enregistré** dans la structure et dans les tiers : nouveau champ « Activité (NAF) », code et libellé.
- **D7 (Q4) — TVA intracommunautaire calculée** (FR + clé + SIREN), proposée pour la structure comme pour les tiers, avec la mention « calculée à partir du SIREN, à vérifier ».
- **D8 (Q5) — Enrichissement groupé des tiers.**
  - Depuis la liste des tiers, l'action « Mettre à jour depuis Sirene » porte sur les tiers qui ont un SIREN ou un SIRET (tous, ou la sélection).
  - Les appels se font en tâche de fond, au rythme du quota.
  - L'écran de revue liste, tiers par tiers, les champs vides à remplir et les champs différents (valeur actuelle → valeur Sirene). Tout est à cocher, rien n'est appliqué sans validation.
  - Les tiers cessés ou introuvables sont signalés, jamais modifiés.
- **D9 (Q6) — Factures d'achat.** La même recherche Sirene est disponible pour le fournisseur, à la saisie d'une facture d'achat.
  - Un fournisseur trouvé et déjà connu (même SIRET ou SIREN) est rattaché.
  - Sinon, le nouveau tiers est créé pré-rempli, après confirmation.

### Exigences ajoutées

- **B15** — Champ NAF (code + libellé) sur la structure et sur les tiers. Le libellé vient de la nomenclature NAF rév. 2, fournie avec l'application, sans appel réseau. Si Sirene renvoie un code en NAF 2025 (`nomenclatureActivitePrincipale…`), le code est gardé tel quel et la nomenclature est indiquée.
- **B16** — Libellé de la forme juridique tiré de la nomenclature INSEE des catégories juridiques (niveau III), fournie avec l'application.
- **B17** — Enrichissement groupé : la tâche de fond suit sa progression et peut être arrêtée. Elle reprend les tiers non traités si le quota l'interrompt. Ses résultats restent consultables jusqu'à validation ou abandon.
- **B18** — Le SIREN d'un tiers est déduit de son SIRET (9 premiers chiffres). Les SIREN et SIRET invalides (contrôle de Luhn) sont signalés et ne sont pas envoyés à Sirene.
- **B19** — À la saisie d'une facture d'achat, la recherche ne crée jamais de tiers sans confirmation, et ne modifie pas un tiers existant : sa mise à jour passe par la fiche tiers.

### Critères d'acceptation ajoutés

- Une facture de vente émise après l'unification porte la même forme juridique et le même RCS que Structure, et un bail généré aussi.
- L'enrichissement groupé de 50 tiers se termine sans erreur 429 visible. Il dure environ deux minutes, au rythme du quota, et propose une revue où rien n'est modifié avant validation.
- À la saisie d'une facture d'achat, rechercher un fournisseur par nom propose de rattacher le tiers existant de même SIREN plutôt que d'en créer un second.

Étape suivante : `/sc:design claudedocs/besoins_sci_sirene.md`.
