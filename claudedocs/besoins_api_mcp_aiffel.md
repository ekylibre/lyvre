# Accès API par clé et connecteur MCP pour Aiffel — besoins

> Statut : **besoins** (08/11/2026, /sc:brainstorm). Prochaine étape : /sc:design.
> Demande : « ajoute un accès API avec clef et un connecteur MCP paramétrable par module lecture / écriture pour permettre à Aiffel de lire et écrire des informations ».
> Aiffel : assistant vocal ou écrit d'Ekylibre, qui saisit après validation (`claudedocs/compta_agricole/audit_logiciels.md` § 1.4).

## 1. Constat

- **Authentification** : l'API `/api/v1` ne connaît que la session de l'interface (cookie, jeton CSRF, choix de l'instance en session). Elle n'a ni clé ni jeton, ni accès machine.
- **Rôles** : `admin`, `treasurer`, `accountant` (lecture seule contrôlée côté serveur), par instance (`instance_memberships`).
- **Outils existants à réutiliser** : l'assistant Claude (`app/services/assistant/tools.py`) a déjà des outils de lecture (contexte, soldes, écritures, TVA, résultat fiscal, MSA, marges, aides, échéancier, contrôles de clôture, calculettes) et des outils de proposition (écriture, appel MSA, échéance) qui produisent des **brouillons à valider**.
- **MCP** : Lyvre est seulement client MCP (Lexicon, pour l'assistant) ; il n'expose aucun serveur MCP.

## 2. Réponses (08/11/2026)

| # | Question | Réponse |
|---|---|---|
| A1 | Que peut écrire Aiffel ? | **Brouillons à valider** : écritures en brouillard, factures d'achat, tiers, pièces de vente en brouillon. Rien de définitif sans un humain (ni validation, ni numéro, ni envoi, ni encaissement). |
| A2 | Découpage des droits | **Par domaine métier**, une case lecture et une case écriture chacun, limités aux domaines de la structure. |
| A3 | Rattachement de la clé | **Instance + utilisateur** : jamais plus que le rôle de l'utilisateur ; nom, expiration, révocation ; affichée une seule fois ; appels journalisés. |
| A4 | Forme d'accès | **MCP distant (HTTP streamable) + API REST** existante, avec la même clé (`Authorization: Bearer`). |
| A5 | Usages prioritaires | **Questions sur le dossier** et **saisie d'achats et de dépenses**. Les ventes et l'agronomie viendront ensuite. |
| A6 | Traçabilité | **Badge d'origine + file à valider** : « Aiffel, clé X » sur chaque objet, compteur dans « À traiter », journal par clé. |
| A7 | Limites | **Débit + plafond d'écriture** par clé (exemple : 60 requêtes par minute, 200 créations par jour), réglables ; au-delà, HTTP 429 avec message. |

## 3. Objectifs

1. Aiffel lit le dossier d'une structure pour répondre (vocal ou écrit), sans session navigateur.
2. Aiffel prépare des saisies que l'utilisateur retrouve dans Lyvre, prêtes à valider.
3. L'administrateur de la structure garde la main : il choisit ce qu'une clé lit ou écrit, la coupe à tout moment et voit ce qu'elle a fait.

## 4. Exigences fonctionnelles

### R1 Clés d'API (écran Configuration › Accès API, administrateur de l'instance)
- Créer une clé : nom (par exemple « Aiffel — tracteur »), utilisateur rattaché (soi-même ou un membre de la structure), domaines en lecture et en écriture, expiration (par défaut 1 an, au plus 2 ans), limites (R7).
- La clé est **affichée une seule fois** à la création, puis seulement un préfixe reconnaissable (`lyv_…abcd`). Elle n'est jamais stockée en clair.
- Liste : nom, utilisateur, domaines, création, dernier usage, expiration, état (active, expirée, révoquée).
- **Révoquer** : effet immédiat. **Modifier** les domaines et les limites sans changer la clé.
- Une clé ne donne **jamais plus que le rôle de son utilisateur** : l'écriture est impossible pour un expert-comptable. Si l'utilisateur perd son accès à l'instance, la clé cesse de fonctionner.
- Un utilisateur voit les clés rattachées à lui, même s'il n'est pas administrateur, et peut les révoquer.

### R2 Domaines (lecture / écriture)
Liste à arrêter en conception, alignée sur le menu et filtrée par structure (asso, SCI, agri, société) :
- Comptabilité (écritures, comptes, balance, grand livre, éditions) ;
- Banque (comptes, transactions, rapprochement) ;
- Achats (factures d'achat, règlements, pièces) ;
- Ventes (devis, factures, avoirs, encaissements) ;
- Tiers (fournisseurs, clients, adhérents) ;
- TVA et fiscal (déclarations, résultat fiscal, MSA) ;
- Immobilisations ;
- Agronomie (activités, campagnes, surfaces, stocks et inventaire) — exploitation ;
- Échéancier (échéances, fiches) ;
- Documents (consultation des pièces).

L'écriture d'un domaine suppose sa lecture. Un domaine sans opération d'écriture en v1 n'a pas de case écriture.

### R3 API REST par clé
- `/api/v1` accepte `Authorization: Bearer <clé>`. L'instance est **celle de la clé** : pas de choix d'instance, pas de session ni de CSRF pour ces appels.
- Chaque route relève d'un domaine. Hors des domaines de la clé : **403** avec le domaine manquant.
- Les écritures passent par les **mêmes contrôles** que l'interface (validations, verrous de période, exercice clos).
- Hors périmètre de la clé, même si son utilisateur a les droits : administration (utilisateurs, intégrations, clés, sauvegardes, restauration), clôture, validation des écritures, émission, envoi.

### R4 Serveur MCP distant
- Point d'accès MCP de Lyvre (transport HTTP streamable), authentifié par la même clé.
- Les **outils exposés dépendent des domaines** de la clé (`tools/list` filtré) ; un outil appelé hors domaine est refusé.
- Outils de lecture : ceux de l'assistant Claude, regroupés par domaine et décrits pour un agent (paramètres, unités, montants en euros).
- Outils d'écriture : création de brouillons uniquement (R5), avec un résultat qui donne le lien vers l'objet dans Lyvre.
- Nom, description et instructions du serveur donnent le contexte : structure, exercice en cours, règle « rien n'est définitif sans validation ».

### R5 Écriture = brouillons (v1 : achats et dépenses)
- **Facture d'achat en brouillon** : fournisseur (retrouvé ou proposé), date, montants HT / TVA / TTC ou TTC seul, lignes (produit ou compte), **pièce jointe** (photo, PDF, Factur-X) avec la lecture existante (OCR, Factur-X).
- **Dépense sans facture** (ticket, frais) : facture d'achat en brouillon, avec le ticket en pièce jointe (Q3).
- **Tiers** : création d'un fournisseur s'il est introuvable (Sirene si SIREN connu), marqué « à vérifier ».
- **Écriture en brouillard** : générique, pour le domaine Comptabilité en écriture.
- Rien n'est validé, comptabilisé définitivement, numéroté ni envoyé par une clé.
- Idempotence : une création répétée avec la même clé d'idempotence ne crée pas de doublon (agent qui réessaie).

### R6 Traçabilité
- Chaque objet créé par clé porte son **origine** (clé, utilisateur, date), visible sous forme de badge (« Aiffel ») sur les listes et les fiches.
- La carte **« À traiter »** du tableau de bord compte les brouillons créés par clé et pas encore validés, avec un lien vers la liste filtrée.
- **Journal des appels** par clé (date, outil ou route, domaine, résultat, objet créé), consultable par l'administrateur, conservé au moins 90 jours. Pas de contenu sensible au journal (montants et libellés seulement si utiles, jamais la clé).

### R7 Limites
- Débit par clé (requêtes par minute) et plafond de créations par jour, réglables ; valeurs par défaut prudentes.
- Au-delà : 429, message lisible et en-tête de délai ; tentatives refusées inscrites au journal.

## 5. Exigences non fonctionnelles

- **Sécurité** : clé longue et aléatoire, stockée sous forme d'empreinte, comparaison à temps constant ; HTTPS seulement ; refus de toute clé expirée, révoquée, ou dont l'utilisateur ou l'instance est désactivé ; aucune clé dans les URL ni dans les journaux.
- **Isolement** : une clé ne voit que sa structure (base de l'instance) ; aucun accès à la méta-base hors de sa propre vérification.
- **Cohérence** : mêmes services et contrôles que l'interface ; pas de second chemin d'écriture.
- **Compatibilité MCP** : spécification MCP en vigueur (HTTP streamable), testée avec un client de référence ; l'authentification par en-tête Bearer convient à Aiffel (Q2).
- **Performance** : lecture comparable à l'interface ; pièces jointes jusqu'à 20 Mo.
- **Langue** : messages, descriptions d'outils et erreurs en français.
- **Documentation** : page de documentation de l'API et des outils MCP, générée à partir des domaines et des outils réels.

## 6. Récits utilisateur et critères d'acceptation

1. *En tant qu'administrateur de la ferme*, je crée une clé « Aiffel » rattachée à moi, en lecture sur tout et en écriture sur Achats, et je copie la clé une fois.
   - La clé n'est plus affichable ensuite ; la liste montre son préfixe, ses domaines et son expiration.
2. *En tant qu'Aiffel*, je demande « quelle est ma trésorerie et qu'est-ce que je dois payer ce mois-ci ? ».
   - Les outils de lecture Banque, Achats et Échéancier répondent.
   - Un outil d'un domaine non accordé n'apparaît pas dans la liste et il est refusé s'il est appelé.
3. *En tant qu'Aiffel*, je saisis « 2 t d'engrais chez la coop, 1 200 € TTC » avec la photo du bon.
   - Une facture d'achat en brouillon existe, avec la pièce, le fournisseur rattaché ou proposé et le badge « Aiffel ».
   - Le résultat de l'outil donne le lien vers la facture.
   - Aucune écriture n'est validée.
4. *En tant qu'exploitant*, je vois « 3 brouillons d'Aiffel à valider » dans « À traiter », je les ouvre, je les corrige et je les valide comme les autres.
5. *En tant qu'administrateur*, je révoque la clé : l'appel suivant d'Aiffel reçoit 401, et le journal montre le dernier appel accepté.
6. *En tant qu'expert-comptable* (lecture seule), je ne peux pas créer de clé avec écriture, même si l'administrateur coche l'écriture pour moi.
7. Une boucle d'agent qui dépasse 60 requêtes par minute reçoit 429 ; au-delà de 200 créations dans la journée, les créations sont refusées et la lecture continue.

## 7. Hors périmètre (v1)

- Validation, émission, envoi, encaissement, rapprochement, clôture par clé.
- Écriture dans les domaines Ventes et Agronomie (lecture seulement en v1, A5).
- OAuth (délégation par écran de consentement) : la clé suffit en v1.
- Webhooks vers Aiffel (événements Lyvre).
- Synchronisation automatique Ekylibre ↔ Lyvre par Aiffel (le connecteur Ekylibre existant reste la voie de lecture d'Ekylibre).

## 8. Réponses aux questions ouvertes (08/11/2026)

| # | Question | Réponse |
|---|---|---|
| Q1 | Liste des domaines, environnement d'essai | La liste exacte des domaines et le rattachement de chaque route restent à arrêter en conception (inventaire de `app/api`). **Essai (staging) sur `lyvre.org`.** Le dépôt sera déplacé vers `https://github.com/ekylibre/lyvre` à la fin de ce développement. |
| Q2 | Authentification du client MCP d'Aiffel | **En-tête avec la clé** (`Authorization: Bearer lyv_…`). Pas d'OAuth en v1. |
| Q3 | Dépense sans facture | **Facture d'achat en brouillon** (la pièce est le ticket ou la photo). Pas d'écriture en brouillard pour ce cas. |
| Q4 | Granularité des clés | **Une clé par usage** (par exemple « Aiffel — saisie terrain », « Aiffel — questions bureau »), chacune avec ses domaines et ses limites. |
| Q5 | Lien avec l'outil de gestion agricole | Avec **Fourmy**, qui remplace Ekylibre (`https://github.com/ekylibre/fourmy`, `https://fourmy.org/`, version alpha en cours). Les objets créés peuvent porter une **référence externe** (système d'origine et identifiant), pour éviter les doubles saisies. Le format reste à fixer avec Fourmy. |
| Q6 | Adresse du point MCP | **`app.lyvre.org` en production**, mais l'adresse publique doit être **paramétrable** selon l'installation : réglage d'URL publique, jamais codé en dur. |

### Conséquences sur les exigences

- **R1** : la création d'une clé propose un nom d'usage. Une même personne peut avoir plusieurs clés actives sur une structure.
- **R4** : l'URL du point MCP affichée à l'administrateur (et dans la documentation) vient du réglage d'URL publique de l'installation (`app.lyvre.org`, `lyvre.org` en essai, ou l'adresse locale).
- **R5** : une dépense sans facture devient une **facture d'achat en brouillon**, avec le ticket en pièce jointe. L'écriture en brouillard reste un outil générique du domaine Comptabilité.
- **R5 et R6** : facultatif à la création, un champ **référence externe** (`fourmy:<identifiant>`) sert de clé d'idempotence métier. Une seconde création avec la même référence renvoie l'objet existant.
- **Hors périmètre v1** : la synchronisation avec Fourmy, qui est en version alpha. Seule la référence est gardée.

## 9. Questions restantes pour la conception

- La liste définitive des domaines et le rattachement de chaque route (Q1).
- Le format des identifiants Fourmy à retenir comme référence externe (Q5), à voir avec l'équipe Fourmy.
- Le nom du réglage d'URL publique, s'il existe déjà (URL des liens dans les e-mails, Documenso, etc.), à réutiliser plutôt qu'à dupliquer.
