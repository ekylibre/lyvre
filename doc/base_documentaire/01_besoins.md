# 1. Besoins : base documentaire et assistant contextuel

> Statut : cadrage (sortie de `/sc:brainstorm`). Les choix faits par défaut sont marqués **[défaut]**. Ils peuvent être remis en cause : voir §7, questions ouvertes.

## 1.1 Objectifs

| # | Objectif | Indicateur de réussite |
|---|---|---|
| O1 | Donner à l'utilisateur non comptable (trésorier bénévole, gérant de SCI) une réponse **juste, sourcée et adaptée à sa structure** | ≥ 90 % de réponses correctes sur le jeu d'évaluation (doc 5) ; 100 % des réponses citent au moins une fiche ou un article |
| O2 | **Une seule source de vérité** pour les règles : états, contrôles, schémas d'écriture et aide utilisent les mêmes identifiants | Aucune règle comptable codée en dur hors des fichiers `data/kb/` (à terme) |
| O3 | Un assistant **qui agit sur le logiciel** sans jamais court-circuiter la validation humaine | 0 écriture validée, 0 clôture, 0 suppression déclenchée par l'assistant |
| O4 | **Respecter la logique par type de structure** (asso, SCI, extensible) | Une même question (« où passer une cotisation ? ») donne 756x pour une asso, et « non applicable » ou un autre traitement pour une SCI |
| O5 | Rester **simple à exploiter** : pas de nouvelle base, pas de service externe hors API Claude | Le déploiement Docker existant suffit ; l'assistant se désactive par simple absence de clé |

## 1.2 Utilisateurs et rôles (existants, cf. lot A.1)

| Rôle | Base documentaire (UI) | Assistant : questions | Assistant : actions |
|---|---|---|---|
| `admin` (instance) | lecture | oui | propositions (brouillons, règles) |
| `treasurer` (saisie) | lecture | oui | propositions (brouillons) |
| `accountant` (expert-comptable) | lecture | oui | **aucune** : lecture seule, comme dans le reste de l'app |
| administrateur global | lecture et **édition du corpus** (lot 4) | oui | idem `admin` |

## 1.3 Exigences fonctionnelles

### Base documentaire (BD)

- **BD1.** Le corpus est formé de **fiches** en Markdown avec un en-tête YAML : identifiant, référentiel(s), comptes, articles, sources, date de vérification, niveau de risque. Voir doc 2.
- **BD2.** Chaque fiche relève d'un **référentiel** (`pcg2026`, `asso_2018_06`, `sci`…). Une instance ne voit que les fiches de sa pile de référentiels.
- **BD3.** Les **règles exécutables** sont séparées des fiches, en YAML par référentiel : composition des états, contrôles, schémas d'écriture, correspondances fiscales. Elles **citent** des fiches. Voir doc 3.
- **BD4.** Les **textes primaires** (PDF ANC) sont découpés en extraits indexés plein texte, avec leur page. L'assistant peut ainsi citer « PCG 2026, art. 1031-3, p. 112 ».
- **BD5.** **Fraîcheur, à deux niveaux.** La règle vient de paperasse : bandeau d'obsolescence à 6 mois, et registre des sources avec `next_check`.
  - Chaque fiche porte une **date de dernière vérification**. Au-delà de 12 mois **[défaut]**, l'UI et l'assistant signalent « à revérifier ».
  - Chaque source du registre porte une **date de prochaine vérification**, par exemple le 15 janvier pour un recueil ANC annuel. Passé cette date, `kb_check` échoue.
  - Les **seuils et taux** (franchise TVA, seuil CAC, taux de valorisation) ne figurent jamais dans le texte d'une fiche. Ils sont dans des données datées et sourcées : paperasse cite des seuils périmés faute de les dater.
- **BD6.** Le marqueur ⚠️ (`risque: expert`) signale les sujets réservés à l'expert-comptable : fiscalité, jugement, legs, « projet défini ». L'assistant y répond par le principe général et un renvoi explicite à l'expert.
- **BD7.** Dans l'UI **sans IA** :
  - un onglet « Règle » sur la fiche d'un compte (fiches qui citent ce compte) ;
  - un lien « Pourquoi ? » sur chaque anomalie de l'assistant de clôture ;
  - une recherche dans la palette Ctrl+K (catégorie « Aide comptable »).
- **BD8.** Le corpus est **versionné dans git**, comme `data/plan_comptable_*.json`, et compilé au démarrage dans un index : pas de saisie en base en lot 1.
- **BD9.** **Socle PCG en données ouvertes.** Le plan et le texte du socle `pcg2026` viennent d'**arrhes/PCG**, licence CC0, la source de paperasse :
  - `pcg_2026.json` : 838 comptes, avec le statut obligatoire ou facultatif (art. 1121-1) et le diff d'une année sur l'autre ;
  - `pcg_20260101.md` : texte du PCG avec les articles balisés.

  La mise à jour annuelle consiste à reprendre la nouvelle version, puis à relire le diff.

### Assistant (AS)

- **AS1.** Panneau latéral (drawer Mantine) ouvrable depuis toutes les pages, par l'en-tête ou le raccourci Ctrl+J **[défaut]**. Il conserve la conversation pendant la navigation.
- **AS2.** **Contexte implicite** envoyé à chaque question :
  - type de structure, exercice sélectionné et son statut (ouvert, provisoire, clos), assujettissement TVA ;
  - rôle de l'utilisateur ;
  - page courante et objets affichés : écriture n°, compte, transaction bancaire, étape de clôture ;
  - **ce qui manque** au contexte : SIREN ou RNA absent, assujettissement TVA non renseigné, exercice précédent non clos. Le principe vient de paperasse : « inférer un maximum, demander un minimum ». L'assistant ne pose pas de questions dont la réponse est déjà en base. Il signale ce qui manque et renvoie vers l'écran Structure ou Exercices.
- **AS3.** **Outils de lecture**. L'assistant interroge le logiciel : soldes, balance, ligne d'état, écriture, transactions non rapprochées, contrôles de clôture, fonds dédiés, plan de comptes. Il ne lit que ce que l'utilisateur pourrait voir lui-même.
- **AS4.** **Outils de proposition**. L'assistant prépare une action **que l'utilisateur valide dans l'écran habituel** :
  - formulaire d'écriture prérempli (brouillon) ;
  - règle de catégorisation préremplie ;
  - ligne d'inventaire de clôture préremplie ;
  - navigation vers un écran filtré.

  Rien n'est enregistré sans clic de l'utilisateur.
- **AS5.** **Réponses structurées**, d'après le format paperasse.
  - Question de traitement : Faits / Hypothèses / Traitement (écriture D/C) / Calculs (résultats d'outils) / Points d'attention / Sources, en omettant les sections vides.
  - Les points d'attention sont classés 🔴 critique / 🟠 attention / 🟡 info.
  - Question simple : réponse courte avec sa source.
- **AS6.** **Citations obligatoires**. Chaque affirmation normative renvoie à une fiche (`C-03`) ou à un extrait de texte primaire. Une règle introuvable dans le corpus ne s'invente pas : l'assistant le dit.
- **AS7.** **Calculs déterministes**. Tout montant est calculé par un outil du logiciel, en centimes entiers, et non par le modèle : report en fonds dédiés, résultat, prorata au jour (charges et produits constatés d'avance), amortissement linéaire, seuil proratisé sur un exercice court, valorisation du bénévolat. C'est le principe « jamais de calcul mental » de paperasse (`scripts/calc.js`), appliqué aux services Python. Le registre est au doc 4 §4.5.
- **AS8.** **Entrées depuis le logiciel** : boutons « Expliquer » sur une anomalie de clôture, une écriture déséquilibrée, une transaction en 471. Le bouton ouvre l'assistant avec la question et le contexte préremplis.
- **AS9.** **Historique** des conversations par instance et par utilisateur, consultable et supprimable par son auteur.
- **AS10.** **Désactivable**. Sans clé API ou si l'instance le désactive (Configuration › Intégrations), l'assistant disparaît. La base documentaire (BD7) reste disponible.

### Contrôles comptables (CT)

Contrôles exécutés par le logiciel, **sans IA**. Ils sont affichés à l'étape 1 de la clôture, et lus par l'assistant via `list_checks`. Ils sont issus des fiches, de l'analyse des skills « contrôleur fiscal » et « commissaire aux comptes » de paperasse, et de l'article 1214-47 du PCG.

| # | Contrôle | Gravité | Existe déjà ? |
|---|---|---|---|
| CT1 | FEC : 18 champs, équilibre global et par écriture, numérotation continue, dates dans l'exercice, champs requis | critique | ✅ `fec.check` / `fec.verify` |
| CT2 | FEC : CompteNum présent dans le plan de l'instance ; montants négatifs signalés | anomalie | ❌ à ajouter |
| CT3 | Comptes d'attente **471 à 473** soldés à la clôture (PCG art. 1214-47) | anomalie | ⚠️ aujourd'hui tout le préfixe `47`, donc fausse alerte possible sur 476 / 477 |
| CT4 | Cohérence des états : résultat du bilan = résultat du CDR, actif = passif, chaque compte affecté à une seule ligne | critique | ⚠️ couvert par les tests, pas par un contrôle |
| CT5 | Invariants asso : 19x et 191 jamais débiteurs, Σ86 = Σ87, lignes de fonds dédiés avec projet, pas de classe 8 depuis la banque | anomalie | ❌ à ajouter |
| CT6 | Tiers dans un sens anormal : 411 créditeur, 401 débiteur | info | ❌ à ajouter |
| CT7 | Variation N/N-1 d'une ligne du CDR au-delà d'un seuil (paperasse : 10 % ; seuil et montant minimal paramétrables) | info | ❌ à ajouter |

## 1.4 Exigences non fonctionnelles

| # | Exigence |
|---|---|
| NF1 | **Isolation multi-tenant** : outils exécutés dans le contexte `g.current_instance` et avec le rôle courant, par les mêmes services que l'API `/api/v1`. Jamais d'accès SQL libre. |
| NF2 | **Intangibilité préservée** : aucun outil ne valide, ne supprime, ne clôt ni ne rouvre. La liste des outils d'écriture est fermée et revue. |
| NF3 | **Données personnelles** : noms des adhérents ou salariés et IBAN ne sont envoyés au modèle que si un outil les renvoie pour répondre à la question. Mention dans la politique de l'instance. Rétention API standard. |
| NF4 | **Injection de prompt** : les libellés bancaires, factures et notes sont des **données**. Ils sont présentés au modèle comme résultats d'outil, jamais comme instructions. |
| NF5 | **Coût maîtrisé** : prompt caching du corpus et des outils ; plafond mensuel de jetons par instance, configurable ; journal `usage` par message. |
| NF6 | **Latence** : premier jeton affiché en moins de 3 s (streaming SSE). |
| NF7 | **Traçabilité** : chaque proposition acceptée garde l'identifiant du message de l'assistant (`source = "ASSISTANT"` sur l'écriture brouillon, `source_ref` = id du message). |
| NF8 | **Langue** : français par défaut. |
| NF9 | **Testabilité** : outils testés en pytest comme les services ; jeu d'évaluation rejouable (doc 5). Contrairement à paperasse : assertions déterministes avant le juge LLM, 3 exécutions par cas, comparaison avec ou sans corpus **à outils égaux**, seuil bloquant de 90 % avant tout changement de modèle ou de consignes. |

## 1.5 User stories et critères d'acceptation

**US1 — Question de traitement (asso)**
> En tant que trésorier, je demande « une subvention de 30 000 € n'est dépensée qu'à 18 000 € au 31/12, que faire ? ».
- L'assistant cite `C-03` et le règlement 2018-06, art. 132-1 à 132-3.
- Il propose D 6894 / C 194 pour 12 000 €, puis la reprise en 7894 en N+1.
- Il signale ⚠️ « projet défini ».
- Le bouton « Préparer l'écriture » ouvre la fiche Fonds dédiés ou le formulaire d'inventaire prérempli, sans rien enregistrer.

**US2 — Même question, SCI**
> Un gérant de SCI demande « où enregistrer une cotisation ? ».
- L'assistant n'utilise pas la fiche asso 756x : elle est hors de sa pile de référentiels.
- Il répond avec le sens PCG (756 = gains de change commerciaux) ou indique que la notion ne s'applique pas.

**US3 — Explication d'une anomalie**
> À l'étape 1 de la clôture, je clique « Expliquer » sur « Compte d'attente 471 non soldé (120,00 €) ».
- L'assistant lit les lignes 471 de l'exercice (outil) et cite `D-04`.
- Il propose, pour chaque ligne, un reclassement probable avec le lien vers l'écriture.

**US4 — Expert-comptable**
> Un `accountant` demande la même chose que US3.
- Il obtient l'analyse et les liens, mais **aucun** bouton d'action.

**US5 — Aide sans IA**
> Sur la fiche du compte 194, l'onglet « Règle » affiche la fiche `C-03`, avec ses sources et sa date de vérification.
- Fonctionne sans clé API.

**US6 — Hors corpus**
> « Quel est le taux de CFE de ma commune ? »
- L'assistant répond qu'il ne dispose pas de cette information.
- Il oriente vers la source officielle ou l'expert, **sans inventer**.

**US7 — Calcul**
> « Combien dois-je reporter en fonds dédiés pour le projet X ? »
- Le montant vient d'un outil adossé au service existant `app/services/dedicated_funds.py` (`funds_for`, `payload`, `balance_before`).
- Le modèle ne calcule rien lui-même.

**US8 — Liasse SCI**
> « Quelle ligne de la 2072 alimente le compte 615216 ? »
- Réponse « ligne 12 » tirée de la correspondance `sci/correspondance_2072.yml`, avec le marqueur « à vérifier sur le formulaire de l'année ».

## 1.6 Hors périmètre (lot 1)

- Production de la liasse fiscale ou de la 2072 complète. L'assistant explique, il ne déclare pas. C'est cohérent avec la FAQ n° 20 de `Base_compta.md`.
- Conseil fiscal personnalisé (IS ou IR, choix de régime, TVA sectorielle) : renvoi à l'expert.
- Lecture de pièces par l'assistant (PDF de facture) : la lecture Factur-X / OCR existe déjà (`invoice_reader.py`), on ne la double pas.
- Saisie libre en langage naturel qui enregistre directement (« passe une écriture de… ») : toujours via brouillon.
- Recherche web par le modèle **[défaut : désactivée]**, pour garder des réponses tirées du corpus seul.

## 1.7 Questions ouvertes

1. **Fournisseur du modèle.** Hypothèse retenue : API Claude (Anthropic), clé au niveau du serveur, comme les autres intégrations. Faut-il prévoir une clé par instance (facturation séparée par association) ?
2. **Hébergement des données.** Les associations acceptent-elles l'envoi de données comptables à l'API ? Faut-il un consentement explicite à l'activation, par instance ?
3. **Couches supplémentaires.** Faut-il prévoir dès maintenant `fondation`, `sci_is`, `entreprise_eic` (recueil EIC présent dans `ref_compta`) ? Le modèle de couches le permet ; seule la priorisation est à décider.
4. **Édition du corpus dans l'UI.** Lot 4 ou jamais ? L'édition par git est plus sûre et a une revue naturelle.
5. **Fiches SCI.** `Base_compta.md` ne contient **aucune** fiche SCI. Qui valide les fiches SCI rédigées (doc 6) : l'expert-comptable de la SCI ?
6. **Numérotation des articles.** `Base_compta.md` signale des citations du Livre IV « à confirmer ». Faut-il bloquer la publication de ces fiches (`statut: a_confirmer`) tant qu'elles n'ont pas été recoupées avec le PDF ?
7. **Quota.** Quel plafond mensuel par défaut (en jetons ou en euros) ?
8. **Seuil de variation N/N-1 (CT7).** Paperasse retient 10 %. Pour une petite association, faut-il ajouter un montant minimal (par exemple 500 €) pour éviter le bruit ?
9. **Couche copropriété.** Le skill `syndic` de paperasse montre que c'est un autre « type de structure », avec son propre plan (décret 2005-240). Faut-il l'envisager ? Le modèle de couches le permet, mais le plan de paperasse est à reprendre depuis le décret.
