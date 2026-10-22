# 7. Annexe — analyse détaillée de paperasse (romainsimon/paperasse)

> Les conclusions de cette analyse sont **intégrées** aux docs 1 à 6 (voir §7.7). Cette annexe garde le détail et les références aux fichiers, pour justifier les choix.

Dépôt examiné au commit `f2e15c4` (10/08/2026), cloné le 2026-10-23 : 6 skills, environ 200 fichiers, environ 730 Ko de Markdown.

- **Lus en entier** : `README.md`, `comptable/SKILL.md`, `comptable/references/{setup,integrations,formats,arborescence,closing,cloture-workflow}.md`, `data/pcg_2026.json`, `data/sources.json`.
- **Survolés par leurs titres** : `tva.md`, `taxes.md`, `calendar.md`, `regional.md`, `pcg.md`.
- **Analysés par deux agents** : `syndic/`, `notaire/`, `fiscaliste/`, `controleur-fiscal/`, `commissaire-aux-comptes/`, `evals/`, `scripts/`.

J'ai vérifié moi-même un échantillon de leurs constats (marqués ✔) dans les fichiers du dépôt.

## 7.1 Ce que paperasse est, et n'est pas

- C'est une **collection de prompts en Markdown** pour agents de code (Claude Code, Codex…). Ils s'appuient sur des fichiers locaux (`company.json`, `data/journal-entries.json`) et sur des scripts Node ou Python. Il n'y a **ni logiciel, ni base de données, ni intangibilité**. Le « journal » est un fichier JSON modifiable.
- Le skill `comptable` vise les **sociétés commerciales à l'IS** (SAS, SASU, SARL, EURL), avec un profil SaaS : Stripe, PCA d'abonnements, CIR.
- ✔ **Rien sur les associations** : aucune mention de la loi 1901, du règlement 2018-06, des fonds dédiés ni des contributions volontaires en nature (CVN). Une seule ligne sur le reçu fiscal (66 % / 75 %), côté `fiscaliste`.
- ✔ **Presque rien sur la comptabilité des SCI** : `legal-forms.md` couvre EI, EURL, SASU, SARL, SAS et le compte 455, sans SCI. La 2072 apparaît **une seule fois** dans tout le dépôt (`fiscaliste/references/revenus-fonciers-lmnp.md`, l. 131). Le `fiscaliste` renvoie la « SCI à l'IS » vers `comptable`, qui n'en parle pas.

**Conséquence** : paperasse apporte des **méthodes**, pas de contenu pour nos deux référentiels. Notre matière première reste `Base_compta.md` et les recueils ANC.

## 7.2 Ce que l'on reprend (et où)

| # | Principe paperasse | Fichiers | Reprise chez nous |
|---|---|---|---|
| P1 | **Table de routage** dans chaque `SKILL.md` : domaine → fichier de référence | `syndic/SKILL.md` l. 41-59, `notaire/SKILL.md` l. 77-87 | Index `mots_cles` / `ecrans` des fiches (doc 2) ; rien à router en plus, car les fiches de la pile sont toutes en contexte |
| P2 | **Contexte obligatoire avant tout conseil** (`company.json`, sinon parcours de configuration) | `comptable/SKILL.md`, `references/setup.md` | Notre contexte est **déjà en base** (`organization`, exercice, plan, TVA) ; l'outil `get_context` remplace `company.json`. Repris : « inférer un maximum, demander un minimum ». L'assistant peut proposer de compléter l'identité (SIREN, RNA) via l'écran Structure |
| P3 | **Format de réponse** Faits / Hypothèses / Analyse / Calculs / Risques / Actions / Limites, sections vides omises | `comptable/SKILL.md`, `notaire/SKILL.md` l. 165-186 | Doc 4 §4.6, avec « Calculs » ajouté (sorties de l'outil `compute`) |
| P4 | **Niveaux de risque** 🔴 CRITIQUE / 🟠 ATTENTION / 🟡 INFO | `references/formats.md` | Correspondance : `Check.level` (`anomalie` / `info`) et `risque:` des fiches ; ajouter un niveau `critique` pour les contrôles bloquants à la clôture |
| P5 | **Calculs déterministes**, jamais de calcul mental : `calc.js` en centimes BigInt, arrondi au demi supérieur | `scripts/calc.js`, `scripts/test-deterministic-calculations.js` | Outil `compute` (doc 4 §4.5). Nos montants sont déjà en centimes entiers. Fonctions utiles : prorata au jour (CCA, PCA), amortissement linéaire au jour, seuil proratisé sur un exercice court |
| P6 | **Contrôles après chaque calcul** (quotes-parts = total, débit = crédit, écart budgétaire > 20 % à justifier) | `syndic/SKILL.md` l. 184-193 | Contrôles `egalite` du doc 3 ; contrôle « variation > X % vs N-1 » à ajouter (P9) |
| P7 | **Fraîcheur** : `metadata.last_updated`, bandeau « ⚠️ SKILL POTENTIELLEMENT OBSOLÈTE » au-delà de 6 mois ; liste des valeurs à revérifier avant de les citer (taux, seuils) | tous les `SKILL.md` | `verifie_le` des fiches (doc 2 §2.8). Seuils et taux dans des **données datées**, jamais dans le texte des fiches |
| P8 | **Registre de sources avec échéance** : `next_check`, `update_frequency`, `check_instructions` ; `update_data.py` signale les données périmées (> 400 j si annuelle, > 730 j si rare) et sort en erreur | `fiscaliste/data/sources.json`, `fiscaliste/scripts/update_data.py` | **Repris tel quel** dans `sources.yml` : ajout de `prochaine_verif` et `instructions` ; `kb_check` échoue si une source est périmée |
| P9 | **Contrôles de cohérence de clôture** : 512 = relevé, 401/411 = balance âgée, 445 = dernière déclaration, variations > 10 % vs N-1 à expliquer | `comptable/references/closing.md` (« Contrôles de cohérence ») | Nouveaux contrôles `info` : variation N/N-1 par ligne du CDR (seuil paramétrable), comptes de tiers créditeurs ou débiteurs anormaux (411 créditeur) |
| P10 | **Contrôles du FEC** (axe 1 du contrôleur fiscal, 8 points) | `controleur-fiscal/SKILL.md` | Notre `app/services/fec.py` (`check`, `verify`) en couvre déjà 6. **Manquent** : CompteNum appartenant aux racines du PCG, et refus des montants négatifs (le motif accepte `-?\d+,\d{2}`). À ajouter au lot 2 |
| P11 | **Contrôles croisés du commissaire aux comptes** : résultat du bilan = résultat du CDR, actif = passif, balance ↔ états ligne à ligne | `commissaire-aux-comptes/references/procedures-detaillees.md` | En partie dans nos tests de `reports.py`. À ajouter comme contrôle de clôture (`etats_coherents`), qui alimente « Expliquer » |
| P12 | **Évaluations** : mêmes questions **avec** et **sans** skill, assertions en langage naturel notées par un juge LLM | `evals/run_evals.py`, `evals/config.yaml`, `*/evals/evals.json` | Doc 5, jeu d'évaluation, **amélioré** (§7.4) |
| P13 | **Mémoire de gestion** : `journal/YYYY.md`, une ligne datée par action | `syndic/references/journal-gestion.md` | Existe déjà chez nous sous une meilleure forme : `ClosingEvent` et le journal d'audit. L'outil `get_context` peut en résumer les derniers événements |

## 7.3 Source de données à reprendre : arrhes/PCG (CC0)

`data/pcg_2026.json` de paperasse vient de **github.com/arrhes/PCG**, sous licence CC0, mis à jour en avril 2026. Ce dépôt est plus utile que paperasse lui-même pour notre socle :

| Contenu | Intérêt pour nous |
|---|---|
| `versions/<année>/pcg_<année>.json` (2023 à 2026), avec `flat`, `nested` et `diff` (`from`, `to`, `added`, `removed`, `modified`) | Plan du **socle `pcg2026`** avec ✔ `system: minimal \| facultatif` : 433 comptes obligatoires et 405 facultatifs, soit la distinction caractères normaux / italiques de l'art. 1121-1 (fiche A-08). Le `diff` donne les changements d'une année à l'autre, ce qui alimente la revue annuelle (doc 2 §2.8) |
| `sources/<année>/pcg_<année>0101.md` et `recueil_<année>0101.md` | ✔ **PCG et recueil EIC convertis en Markdown**, avec les titres (Livre, Titre, Chapitre, Section) et les articles en `**Art. n**` ou `***Art. n***`. Les textes primaires `PCG26` et `REC-EIC26` sont plus faciles à découper que nos PDF (doc 2 §2.7). Le recueil **non lucratif** n'y est pas : il reste à extraire avec PyMuPDF |

✔ **Vérification des citations du Livre IV** faite dans ce texte : les articles 1011-1, 1021-1, 1031-1 (partie double), 1031-2, 1031-3 (validation qui « interdit toute modification ou suppression »), 1031-4 (clôture), 1032-1, 1032-2, 1121-1, 513-5 et 811-7 sont **présents** dans le PCG au 1er janvier 2026. Les fiches A-02 à A-06 peuvent passer de `a_confirmer` à `publie`, avec la ligne du texte en preuve (doc 6 §6.4, point 1).

✔ Dans ce même PCG 2026, la classe 58 n'a **que** le compte `58 Virements internes`, sans 580. Le « 580 » de `Base_compta.md` (D-05) est un usage courant, pas un compte du plan. Notre 581 asso n'est donc pas une anomalie (doc 6 §6.5 corrigé).

## 7.4 Évaluations : ce qu'on garde, ce qu'on corrige

Fonctionnement de paperasse :
- 47 cas au total ✔ : comptable 10, fiscaliste 20, syndic 8, notaire 4, contrôleur fiscal 3, commissaire aux comptes 2.
- Chaque cas est exécuté par `claude --bare -p` avec `claude-sonnet-4-6` ✔, une fois avec le `SKILL.md` en prompt système et une fois avec un rôle d'une ligne sans outils.
- Un juge `claude-haiku-4-5` ✔ note chaque assertion.
- Le chiffre « 88 % / 75 % » est le taux moyen d'assertions réussies, avec et sans skill.
- Le cache est indexé par le contenu, seuls les skills modifiés sont relancés, et la CI ne bloque jamais.

| Garder | Corriger chez nous |
|---|---|
| Format de cas simple (`prompt`, `files`, `assertions`) | **Assertions déterministes d'abord** : citations, comptes présents ou absents, action proposée, montants. Le juge ne sert qu'à la qualité rédactionnelle |
| Comparaison avec et sans base documentaire | Une comparaison qui isole le **corpus** : mêmes outils, mêmes consignes, corpus retiré. Celle de paperasse retire aussi les outils, ce qui fausse la mesure |
| Cache par empreinte de contenu, relance des seuls cas touchés | Plusieurs exécutions par cas (3), avec la variance affichée |
| Données d'essai réalistes (FEC avec anomalies volontaires) | **Bases d'instance de test** (comme les fixtures e2e) plutôt que des fichiers, puisque l'assistant lit le logiciel par ses outils |
| — | **Seuil bloquant** avant un changement de modèle ou de consignes (≥ 90 %, doc 5) |

Défauts relevés dans le dispositif paperasse, à ne pas reproduire :
- `aggregate_benchmark.py` et `generate_review.py` attendent une organisation des dossiers que `run_evals.py` ne produit pas.
- Un `grading.json` est incohérent avec son `evals.json`.
- Les données d'essai du FEC (point décimal, ordre non chronologique) contredisent la spécification, mais le juge les a jugées « conformes ».

## 7.5 Ce que l'on ne reprend pas (erreurs ou inadéquations relevées)

| Constat | Où | Pourquoi l'écarter |
|---|---|---|
| ✔ Les cessions d'immobilisations vont en **775** (« Cession d'actif ») | `comptable/references/pcg.md`, `cloture-workflow.md` (tableau de catégorisation) | Antérieur au règlement 2022-06 : depuis 2025, prix de cession en 757 et VNC en 657 (A-09). Paperasse se contredit : son propre `pcg_2026.json` n'a plus de 775 ✔ |
| ✔ Amortissement apparié par `'28' + compte.substring(1)` (2183 → 28183) | `scripts/generate-statements.js` l. 279 | Donne des comptes hors PCG ; correspondance des états codée en dur en JS, comptes non affectés **ignorés sans message** (42, 46, 47, 512 créditeur…). Notre YAML par préfixes avec contrôle de couverture (doc 3) est plus sûr |
| FEC : montants écrits par `Math.abs`, fichier produit malgré une écriture déséquilibrée, pas de contrôle de trous | `scripts/generate-fec.js` | Notre `fec.py` est plus strict : génération bloquée, vérification à blanc, numérotation continue |
| ✔ Intérêts de comptes courants déductibles au « taux BCE + 2 points » | `comptable/references/legal-forms.md` l. 240 | Erroné selon l'agent : le plafond de l'art. 39-1-3° CGI est le taux effectif moyen des prêts aux entreprises. **À vérifier** avant toute fiche S-07 |
| ✔ Abattement de 23 000 € proratisé sur les cessions de **parts de SCI** | `notaire/references/societes.md` l. 118 | Selon l'agent, l'abattement ne s'applique pas aux sociétés à prépondérance immobilière. **À vérifier** |
| Plan de copropriété « autonome », calqué sur le PCG (411, 501) | `syndic/data/plan-comptable-copro.json` | Selon l'agent, le décret 2005-240 utilise la classe 45 pour les copropriétaires ; incohérences entre le `.md` et le `.json`. Sans objet pour nous tant qu'aucune couche `copro` n'est prévue |
| Aucun mécanisme de couches : chaque plan est un fichier autonome, sans `parent` ni sens normal | `syndic/data/plan-comptable-copro.json` | Notre `referentiels.yml` (`etend`, `comptes_redefinis`, `regles_remplacees`) couvre ce manque |
| Seuils datés, à revérifier : franchise TVA 36 800 / 39 100 €, seuils de nomination d'un CAC | `cloture-workflow.md`, `controleur-fiscal`, `commissaire-aux-comptes` | Ne coder aucun seuil sans source primaire datée (doc 2 §2.3) |

## 7.6 Apport pour la couche SCI (fiches S-xx)

Paperasse ne fournit **pas** de comptabilité de SCI, mais du **droit et de la fiscalité** utilisables comme points de départ. Les fiches restent en `brouillon` (doc 6 §6.3), et chaque point est à recouper sur Légifrance ou le BOFiP :

| Fiche | Matière trouvée dans paperasse | Fichier |
|---|---|---|
| S-01 | Art. 1832 à 1873 C. civ. ; au moins 2 associés, capital libre, 99 ans au plus ; acte notarié si apport d'immeuble | `notaire/references/societes.md` l. 7-18, `templates/statuts-sci.md` |
| S-01 / S-08 | IR par défaut (art. 8 et 239 bis AA CGI), associés imposés à proportion de leurs parts, pas d'amortissement déductible ; option IS (art. 206-2, 239, irrévocable) avec amortissement de l'immeuble et plus-value professionnelle | `societes.md` l. 48-68, `notaire/references/cas-speciaux.md` l. 47 |
| S-03 | Charges déductibles au régime réel (2044) : intérêts d'emprunt, travaux de réparation, d'entretien et d'amélioration, taxe foncière hors TEOM, assurances, frais de gestion, charges de copropriété non récupérables ; art. 14 à 33 quater, 28, 31 CGI | `fiscaliste/references/revenus-fonciers-lmnp.md` l. 31-39, `data/regimes-fonciers-lmnp.json` |
| S-03 | Déficit foncier imputable sur le revenu global jusqu'à 10 700 € par an (21 400 € temporaire), intérêts jamais imputables sur le revenu global, report sur 10 ans (art. 156-I-3°) | idem l. 41-53 |
| S-03 | Micro-foncier exclu pour les SCI (nuance à vérifier pour un associé qui détient aussi des biens en direct) | idem l. 21-23 |
| S-06 / S-10 | Statuts types : AG dans les six mois de la clôture (approbation, affectation, quitus) ; majorités ; affectation au prorata des parts | `notaire/templates/statuts-sci.md` art. 17-22 |
| S-10 | **Art. 1856 C. civ.** (reddition annuelle des comptes) : **absent** de paperasse | — |

## 7.7 Où chaque conclusion est intégrée

| Conclusion | Intégrée dans |
|---|---|
| Fraîcheur à deux niveaux, registre des sources avec date de prochaine vérification (P7, P8) | doc 1 BD5 ; doc 2 §2.6 ; doc 5 tâches 1.1 et 1.5 |
| Socle PCG en données ouvertes (arrhes/PCG) | doc 1 BD9 ; doc 2 §2.1, §2.2, §2.6, §2.7 ; doc 3 §3.6 (`obligatoire`) ; doc 5 tâches 1.1b et 1.4 ; doc 6 §6.1 |
| Contexte déjà en base, « inférer un maximum, demander un minimum » (P2) | doc 1 AS2 ; doc 4 §4.4 |
| Format de réponse et niveaux de risque (P3, P4) | doc 1 AS5 ; doc 3 §3.4 (gravité `critique`) ; doc 4 §4.6 |
| Calculs déterministes (P5) | doc 1 AS7 ; doc 4 §4.5 (registre `compute`) |
| Contrôles de clôture, du FEC et de cohérence des états (P6, P9, P10, P11) | doc 1 §1.3 (CT1 à CT7) ; doc 3 §3.1 (contre-exemple) et §3.4 (types `sens_anormal`, `variation`, `etats_coherents`) ; doc 5 tâches 2.3 et 2.8 ; `exemples/asso/controles.yml` |
| Comptes d'attente limités à 471-473 (PCG art. 1214-47) | doc 1 CT3 ; doc 3 §3.4 ; doc 6 §6.5 ; fiche D-04 ; `exemples/asso/controles.yml` |
| Évaluations corrigées (P12) | doc 1 NF9 ; doc 5 « Jeu d'évaluation » |
| Citations du Livre IV vérifiées ; 580 n'est pas une anomalie | doc 5 tâche 1.2 ; doc 6 §6.2, §6.4, §6.5 |
| Matière SCI repérée, et erreurs à ne pas reprendre | doc 6 §6.3 |
| MCP : données vivantes plutôt que fichiers modifiables | doc 4 §4.12 |
| Couche copropriété possible | doc 1 §1.7, question 9 |
