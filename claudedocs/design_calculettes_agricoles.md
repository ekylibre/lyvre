# Conception : lot AG12, mini-calculettes agricoles

> **Statut** : **validée** (07/11/2026, AGD29). Réponses aux questions du § 8 :
> - **Q-C5 Menu** : un menu **« Outils »**, avec un **filtre par type** de structure (agricole, association, société, SCI). Les calculettes agricoles sont le premier contenu ; d'autres types pourront s'y ajouter (§ 5).
> - **Q-C6 Export** : **copie en texte** seulement (pas de PDF).
> - **Q-C7 Sourçage du groupe C** : validé. Je cherche les sources officielles et te présente chaque paramètre avant d'écrire la calculette.
> - **Q-C8 Zonages** : **Lexicon et IGN** (Géoplateforme).
> - **Q-C9 Ordre** : validé (pilotes 23, 25, 08, puis a → b → c → d → e).
> - **Q-C10 Calculatrice agricole** : **liste exhaustive** proposée au § 9, à cocher par toi avant AG12.c.
>
> **Cadrage** :
> - `compta_agri.md` § 7 bis : exigences C1 à C7 ;
> - décisions :
>   - **AGD12** : 16 calculettes d'Agriia retenues sur 20 ;
>   - **AGD13** : 5 calculettes propres à Lyvre ;
>   - **AGD14** : utilisateurs connectés seulement ;
>   - **AGD15** : pas de données en direct ;
>   - **AGD16** : fiches de tiers hors git ;
> - concept repris d'Agriia, mais **ni son contenu ni sa présentation**.

---

## 1. Ce qui existe déjà

Neuf calculettes sur 21 reposent sur un service de Lyvre déjà écrit et testé, avec ses paramètres réglementaires datés.

| # | Calculette | Service existant | Paramètres (`data/regulatory/`) | Préremplissage |
|---|---|---|---|---|
| 08 | Micro-BA ou réel | `micro_ba.summary`, `ba_regimes` | `ba.micro.*` | recettes des 3 dernières années |
| 13 | Plafond DEP | `dep.ceiling` | `ba.dep.*` | bénéfice, nombre d'exploitants (GAEC) |
| 15 | Révision du fermage | `rent_revision` (indices `FERMAGES`) | indices saisis ou INSEE | bail choisi, loyer, indice de référence |
| 17 | Cotisations MSA | `msa_estimate.estimate` | `msa.*` | assiette (AG7) |
| 21 | Marge brute d'un atelier | `analytic_margins` | — | produits, aides et charges opérationnelles de l'activité, surface |
| 22 | Coût de revient d'un matériel | `assets.schedule` | — | amortissement et frais du bien |
| 23 | Amortissement | `assets.days360`, `default_coefficient` | — | bien choisi, ou saisie libre |
| 24 | Remboursement forfaitaire | `rfa.compute` | `vat.rfa.*` | ventes de l'année par taux |
| 25 | Acompte de TVA du RSA | `vat_installments` | `vat.rsa.*` | TVA due l'année précédente |

**Données externes déjà branchées** :
- **Lexicon** (clé OSFarm, AGD4, `lexicon.py`, `geodata.py`) : parcelles, RPG (`graphic_parcels`), zonages (`protected_natural_zones`, `protected_water_zones`), communes ;
- **IGN** : géocodage, cadastre.

## 2. Choix structurants (proposés)

1. **Un registre, un gabarit, un écran.**
   - Chaque calculette est un module `app/services/calculators/<code>.py` qui déclare :
     - `SPEC` : titre, catégorie, entrées typées (montant, nombre, date, choix, unité), exemple chargeable ;
     - `prefill(ctx)` : valeurs lues dans l'instance, **avec leur origine** ;
     - `compute(inputs)` : résultat, détail du calcul, avertissements ;
     - `METHOD` : texte « méthode et limites » ;
     - `PARAMS` : clés des paramètres réglementaires utilisés.
   - L'écran est **générique** : le formulaire est construit depuis `SPEC`, et le résultat suit toujours le même gabarit (C1).
2. **Le calcul vit dans les services existants.** Une calculette qui a déjà son service l'appelle, sans recopier la règle. La calculette « micro-BA » et l'écran du micro-BA donnent donc toujours le même chiffre.
3. **Paramètres** : uniquement ceux de `data/regulatory/` (AG0.6), affichés avec leur pastille de fiabilité, leur source et leur date de vérification.
   - Un paramètre absent **bloque** la calculette, avec un message. Jamais de valeur dans le code.
4. **Deux usages** (C2) :
   - **libre** : rien n'est lu ;
   - **prérempli** : chaque valeur lue est modifiable, et son origine est affichée (« recettes 2025, comptabilité »).
5. **Aucune écriture** (C3). Le résultat peut proposer un **lien d'action** vers l'écran existant, qui fait la validation :
   - réviser le bail ;
   - préparer la DEP ;
   - enregistrer l'option du micro-BA ;
   - ajouter un rappel à l'échéancier.
6. **Copie** du résultat et de sa méthode en texte (C4). **Pas de PDF** (Q-C6).
7. **Pas de données en direct** (C7) :
   - prix, cours, tarifs d'achat et barèmes départementaux se **saisissent**, avec leur date et leur source ;
   - seuls Lexicon (RPG, zonages) et l'IGN (géocodage) sont appelés, comme aujourd'hui.
8. **Assistant** (C6) : un seul outil `calculator(code, inputs)`, qui renvoie le même résultat que l'écran, méthode comprise.
9. **API** :
   - `GET /api/v1/calculators` : liste par catégorie ;
   - `GET /api/v1/calculators/<code>` : spécification, préremplissage, paramètres ;
   - `POST /api/v1/calculators/<code>` : calcul, sans rien enregistrer.
   
   Utilisateurs connectés, instance agricole (AGD14).

## 3. Les 21 calculettes, par groupe

### Groupe A : calcul déjà dans Lyvre (9)

08, 13, 15, 17, 21, 22, 23, 24, 25 (§ 1). Travail : le module de calculette, le préremplissage et la méthode. Aucune nouvelle règle.

### Groupe B : calcul simple, entrées saisies, sans paramètre réglementaire (6)

| # | Calculette | Entrées | Calcul |
|---|---|---|---|
| 06 | Calculatrice agricole | selon l'outil | conversions (ha, a, m² ; t, q, kg ; l, hl), règle de trois, débit de chantier (largeur × vitesse × rendement), dose de semis (grains/m² × PMG ÷ germination), prix de l'unité d'azote (prix ÷ teneur), pluviométrie (mm ↔ m³/ha) |
| 11 | Réfaction humidité | poids brut, humidité mesurée, **humidité de base** et frais de séchage saisis | poids aux normes = brut × (100 − mesurée) ÷ (100 − base) ; réfaction ; coût de séchage |
| 12 | Prix d'équilibre | charges de l'atelier par ha (préremplies par AG8), rendement, aides, cours saisi | seuil en €/t, marge au cours saisi |
| 14 | Coût d'un chantier d'entraide | tarif de l'outil et du tracteur, débit, coût du chauffeur (**barème départemental saisi**) | (outil + tracteur) ÷ débit + chauffeur ÷ débit, par ha |
| 09 | Solaire sur hangar | puissance (kWc), productible (kWh/kWc/an), **tarif d'achat saisi**, autoconsommation | production, recette annuelle, rappel des revenus accessoires (AG6.7) |
| 05 | Gazole et GNR | consommation, **prix saisis**, taux de remboursement (paramètre à sourcer) | écart de coût, remboursement estimé |

La calculette 05 a besoin d'un paramètre (taux de remboursement de TICPE) : elle passe en groupe C pour cette partie.

### Groupe C : paramètres ou données à sourcer (6)

| # | Calculette | À sourcer avant d'écrire | Source envisagée |
|---|---|---|---|
| 02 | Validité du Certiphyto | durée de validité, fenêtre de renouvellement | Code rural, arrêtés Certiphyto |
| 20 | Mise à jour du DUER | fréquence de mise à jour selon l'effectif | Code du travail (R. 4121-2) |
| 10 | Exonération TO-DE | taux, plafonds, seuils de rémunération de l'année | msa.fr, Code rural, loi de financement de la Sécurité sociale |
| 16 | Aides PAC | montants unitaires de l'année : DPB, paiement redistributif, écorégime, aide JA | instruction technique, arrêtés ; alimente aussi AG3 |
| 04 | Carte RPG | jeu `graphic_parcels` (Lexicon), campagnes disponibles | Lexicon (clé OSFarm) |
| 07 | Zonages de ma parcelle | zones vulnérables, Natura 2000, autres zonages | Lexicon (`protected_*_zones`) ; BCAE à confirmer |

**Règle** : chaque paramètre est ajouté à `data/regulatory/` avec sa source officielle, sa date de vérification et sa fiabilité (« À vérifier » tant que tu ne l'as pas validé, AGD5). Les fiches Agriia ne servent qu'à **trouver** la source officielle (AGD16).

## 4. Gabarit du résultat (C1)

- **Résultat principal** : un ou deux chiffres, avec l'unité.
- **Détail** : chaque étape du calcul et ses valeurs.
- **Entrées** : la valeur de chacune et son origine (saisie, comptabilité, paramètre).
- **Méthode et limites** : un texte court. Par exemple : « estimation, hors cas particuliers… ».
- **Paramètres** : clé, valeur, période de validité, source cliquable, pastille de fiabilité.
- **Actions** : liens vers l'écran qui agit (§ 2.5).
- **Copier** : le résultat, le détail, la méthode et les sources, en texte brut.

## 5. Écrans

- Menu **Outils** (Q-C5), pour toutes les structures :
  - chaque outil déclare les types de structure auxquels il s'adresse (`charts` : agri, asso, societe, sci) ;
  - un **filtre par type** (agricole, association, société, SCI), réglé par défaut sur le type de l'instance ;
  - une grille par catégorie (fiscal, social, TVA, gestion, cultures, élevage, réglementaire) ;
  - un badge « préremplie » quand l'instance peut fournir des valeurs. Le préremplissage ne lit que l'instance courante : un outil d'un autre type s'utilise en saisie libre.
- Page d'une calculette `/calculators/<code>` :
  - formulaire à gauche, avec le bouton « Charger l'exemple » ;
  - résultat à droite, selon le gabarit du § 4.
- Liens contextuels depuis les écrans existants. Par exemple :
  - « Simuler » sur la page Micro-BA ;
  - « Calculer le nouveau loyer » sur un bail ;
  - « Prix d'équilibre » sur les marges.

## 6. Tests

- **Registre** : chaque calculette a une spécification valide, un exemple qui se calcule sans erreur, une méthode non vide et des paramètres présents.
- **Groupe A** : le résultat de la calculette égale celui du service existant sur le même jeu de données (pas de double règle).
- **Groupes B et C** : cas chiffrés écrits à la main, sources en commentaire.
- **Outil de l'assistant** : même résultat que l'API, sans appel à l'API Claude.

## 7. Sous-lots

| Sous-lot | Contenu | Dépend de |
|---|---|---|
| **AG12.a** ✅ | Cadre : registre, API, écran générique, gabarit, copie, menu ; 3 calculettes pilotes : 23 amortissement, 25 acompte de TVA, 08 micro-BA | — |
| **AG12.b** ✅ | Reste du groupe A : 13 DEP, 15 fermage, 17 MSA, 21 marge brute, 22 coût d'un matériel, 24 RFA ; liens depuis les écrans existants | AG12.a |
| **AG12.c** | Groupe B : 06 (outils cochés au § 9), 11, 12, 14, 09 (et 05 sans le remboursement) | AG12.a, § 9 |
| **AG12.d** | Groupe C, après sourçage et ta validation des paramètres : 02, 20, 10, 16, 05 (remboursement), 04, 07 | AG12.a, Q-C7 |
| **AG12.e** | Outil `calculator` de l'assistant | AG12.a, AG9b |

## 7 bis. Réalisé (AG12.a)

- **Cadre** `app/services/calculators/` :
  - registre des modules (`SPEC`, `prefill`, `prefill_options`, `on_date`, `compute`) ;
  - entrées typées (montant en centimes, nombre, entier, pourcentage, date, choix, texte) et validées ;
  - paramètres lus à la date de calcul, un paramètre absent bloquant (409) ;
  - gabarit `Result` ; texte copiable avec les entrées et leur origine, la méthode, les paramètres (source, fiabilité) et les sources.
- **API** :
  - `GET /api/v1/calculators?chart=` : liste filtrée par type, par défaut celui de l'instance ;
  - `GET /api/v1/calculators/<code>?choice=` : spécification, préremplissage, choix de préremplissage, paramètres ;
  - `POST /api/v1/calculators/<code>` : calcul. Il est permis à l'expert-comptable en lecture seule, puisqu'il n'écrit rien.
- **Menu « Outils » › Calculettes** (toutes structures) : `/outils/`, avec un filtre par type et un badge « préremplie » ; page générique `/outils/<code>` (formulaire, origine des valeurs préremplies, exemple, résultat, copie, liens d'action).
- **Pilotes** :
  - **23 Amortissement** : bien simulé passé à `assets.schedule`, préremplissage depuis un bien du registre ;
  - **25 Acomptes de TVA** : `vat_installments.proposed_amount`, `blocks`, `due_date`, dispense ; préremplissage par la référence de l'année (CA12A ou saisie) ;
  - **08 Micro-BA ou réel** : bénéfice par `ba_regimes.micro_profit`, extrait de `simulation` pour une règle unique ; préremplissage par `ba_regimes.simulation`.
- Tests : chaque exemple se calcule ; même résultat que le registre des immobilisations, que `vat_installments` et que `micro_profit` ; paramètre absent bloquant ; filtre par type ; calcul permis à l'expert-comptable.

## 7 ter. Réalisé (AG12.b)

- **Règles partagées extraites**, pour qu'écran et calculette ne divergent pas :
  - `dep.ceiling_for` (plafond de la DEP, appelé par `dep.ceiling`) ;
  - `rfa.flat_amount` (forfait, appelé par `rfa.compute`) ;
  - `rent_revision.apply_ratio` (révision au centime, appelée par `revise`).
- **Calculettes** :
  - **13 DEP** : préremplie par l'exercice (résultat fiscal avant DEP, associés exploitants, durée, déductions non rapportées) ;
  - **15 Révision d'un fermage ou d'un loyer** : indices lus dans Lyvre (`rent_indices`) ou saisis ; préremplie depuis un bail ;
  - **17 Cotisations MSA** : `msa_estimate.estimate`, avec le même repli sur le dernier barème connu ; préremplie depuis un exploitant (assiette retenue de l'historique, statut, ATEXA) ;
  - **21 Marge brute** : même définition que l'état des marges ; préremplie depuis une activité et une campagne ;
  - **22 Coût de revient d'un matériel** : charges fixes et variables à l'heure et à l'hectare ; amortissement prérempli depuis le registre ;
  - **24 Remboursement forfaitaire** : forfait et contrôle du seuil ; préremplie par les ventes de l'année précédente.
- **Liens « Calculette »** (instance agricole) depuis les écrans suivants : Remboursement forfaitaire, Cotisations MSA, Marges par activité, Résultat fiscal (DEP, micro-BA), Baux, Immobilisations (amortissement, coût d'un matériel).
- Tests : même résultat que la règle du service pour chaque calculette ; indice manquant bloquant ; seuil du RFA.

## 8. Questions

- **Q-C5 Place dans le menu** : une entrée « Calculettes » dans le menu agricole ? Ou dans un menu « Outils » ?
- **Q-C6 Export PDF** : nécessaire dès AG12.a, ou la copie en texte suffit-elle pour commencer ?
- **Q-C7 Sourçage du groupe C** : je cherche les sources officielles (Légifrance, BOFiP, msa.fr, instructions techniques PAC) et je te présente chaque paramètre à valider avant d'écrire la calculette. Cela te convient-il ?
- **Q-C8 Zonages (07)** : Lexicon couvre-t-il assez les zonages utiles (zones vulnérables nitrates, Natura 2000, zones ICHN) ? Ou faut-il ajouter une source IGN (Géoplateforme, sans clé) ? Les BCAE sont-elles nécessaires ?
- **Q-C9 Ordre** : pilotes 23, 25 et 08 d'abord, puis a → b → c → d → e. D'accord ?
- **Q-C10 Calculatrice agricole (06)** : les six outils du § 3 (conversions, règle de trois, chantier, semis, azote, pluviométrie) te conviennent-ils ? Faut-il en retirer ou en ajouter (enrouleur d'irrigation, par exemple) ?

## 9. Calculatrice agricole (06) : liste des outils à cocher (Q-C10)

Calculs simples, sans paramètre réglementaire. Toute valeur de référence (densité, PMG, teneur, durée de gestation,
coefficient) est **saisie** par l'utilisateur, jamais fixée dans le code. Coche les outils à retenir.

**Surfaces et mesures**

| # | Outil | Calcul |
|---|---|---|
| 06.01 | Conversion de surfaces | ha, a, m², km² |
| 06.02 | Surface d'une parcelle | rectangle, triangle, trapèze, à partir des côtés |
| 06.03 | Conversion de masses et de volumes | t, q, kg ; m³, hl, l |
| 06.04 | Règle de trois | proportion à trois termes |
| 06.05 | Pourcentage et variation | part, hausse ou baisse en % |

**Chantiers et matériel**

| # | Outil | Calcul |
|---|---|---|
| 06.06 | Débit de chantier | ha/h = largeur (m) × vitesse (km/h) × rendement ÷ 10 |
| 06.07 | Temps de chantier | surface ÷ débit |
| 06.08 | Carburant par hectare | consommation (l/h) ÷ débit (ha/h) |
| 06.09 | Vitesse d'avancement | distance mesurée ÷ temps chronométré |

**Semis et plantation**

| # | Outil | Calcul |
|---|---|---|
| 06.10 | Dose de semis | kg/ha = grains/m² × PMG (g) ÷ (taux de levée × 100) |
| 06.11 | Densité de plantation | plants/ha = 10 000 ÷ (inter-rang × espacement) |
| 06.12 | Semences à commander | dose × surface ÷ conditionnement (doses, sacs) |

**Fertilisation**

| # | Outil | Calcul |
|---|---|---|
| 06.13 | Prix de l'unité fertilisante | €/unité = prix (€/t) ÷ (teneur % × 10) |
| 06.14 | Dose de produit pour un apport visé | kg/ha = unités visées × 100 ÷ teneur |
| 06.15 | Unités apportées par une dose | unités = dose × teneur ÷ 100 |
| 06.16 | Apport d'un effluent | unités N, P, K = quantité × teneurs saisies |

**Pulvérisation**

| # | Outil | Calcul |
|---|---|---|
| 06.17 | Préparation de la cuve | produit par cuve = dose/ha × volume de cuve ÷ volume/ha |
| 06.18 | Nombre de cuves | volume/ha × surface ÷ volume de cuve |
| 06.19 | Débit de buse | l/min = volume/ha × vitesse × écartement ÷ 600 |

**Irrigation et eau**

| # | Outil | Calcul |
|---|---|---|
| 06.20 | Pluviométrie | 1 mm = 10 m³/ha |
| 06.21 | Dose d'un enrouleur | mm = débit (m³/h) × 1 000 ÷ (largeur arrosée (m) × vitesse (m/h)) |
| 06.22 | Durée d'irrigation | dose visée × surface ÷ débit |

**Récolte et stockage**

| # | Outil | Calcul |
|---|---|---|
| 06.23 | Rendement | q/ha = poids récolté ÷ surface |
| 06.24 | Capacité d'un silo ou d'un tas | volume (cylindre, parallélépipède) × densité saisie |
| 06.25 | Besoin en balles | besoin total ÷ poids d'une balle saisi |

**Élevage**

| # | Outil | Calcul |
|---|---|---|
| 06.26 | Besoin en fourrage | têtes × kg MS/jour × jours, comparé au stock |
| 06.27 | Gain moyen quotidien | (poids final − poids initial) ÷ jours |
| 06.28 | Conversion du lait | litres ↔ kg avec une densité saisie |
| 06.29 | Date prévisionnelle de mise bas | date de saillie + durée de gestation saisie |
| 06.30 | Chargement | UGB ÷ surface, avec des coefficients UGB saisis (les coefficients PAC viendront avec la calculette 16) |

**Économie simple**

| # | Outil | Calcul |
|---|---|---|
| 06.31 | Prix de revient unitaire | charges ÷ quantité produite |
| 06.32 | HT, TVA et TTC | à partir de l'un des trois et du taux |
| 06.33 | Marge et taux de marque | prix de vente − coût ; marge ÷ coût, marge ÷ prix |
| 06.34 | Mensualité d'un emprunt | annuité constante : capital × t ÷ (1 − (1 + t)^−n), tableau d'amortissement |
