# Conception : lot AG12, mini-calculettes agricoles

> **Statut** : **validée** (07/11/2026, AGD29). Réponses aux questions du § 8 :
> - **Q-C5 Menu** : un menu **« Outils »**, avec un **filtre par type** de structure (agricole, association, société, SCI). Les calculettes agricoles sont le premier contenu ; d'autres types pourront s'y ajouter (§ 5).
> - **Q-C6 Export** : **copie en texte** seulement (pas de PDF).
> - **Q-C7 Sourçage du groupe C** : validé. Je cherche les sources officielles et te présente chaque paramètre avant d'écrire la calculette.
> - **Q-C8 Zonages** : **Lexicon et IGN** (Géoplateforme).
> - **Q-C9 Ordre** : validé (pilotes 23, 25, 08, puis a → b → c → d → e).
> - **Q-C10 Calculatrice agricole** : **liste exhaustive** proposée au § 9 ; **les 34 outils sont retenus** (réponse du 07/11/2026).
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
| **AG12.c** ✅ | Groupe B : 06 (outils cochés au § 9), 11, 12, 14, 09 (et 05 sans le remboursement) | AG12.a, § 9 |
| **AG12.d** ✅ | Groupe C, après sourçage et ta validation des paramètres : 02, 20, 10, 16, 05 (remboursement), 04, 07 | AG12.a, Q-C7 |
| **AG12.e** ✅ | Outil `calculator` de l'assistant | AG12.a, AG9b |

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

## 7 quater. Réalisé (AG12.c)

- **Cadre** :
  - un module peut déclarer une liste de calculettes (`TOOLS`, objets `Tool`) ;
  - nouvelles catégories : économie, mesures et conversions, chantiers et matériel, semis et plantation, fertilisation, pulvérisation, irrigation et eau, récolte et stockage, énergie ;
  - contrôle `positive` des valeurs.
- **06 Calculatrice agricole** : les **34 outils** du § 9 (`calculatrice.py`, codes `calc-…`, numéros 06.01 à 06.34), rangés par famille dans le menu Outils. Toute valeur de référence (densité, PMG, teneurs, gestation, coefficients UGB, prix) est saisie.
- **Groupe B** (`gestion.py`) : 11 réfaction humidité (norme et tarif de séchage saisis), 12 prix d'équilibre (cours saisi), 14 coût d'un chantier d'entraide (barème saisi), 09 solaire (productible et tarif saisis, rappel des revenus accessoires), 05 gazole et GNR (prix saisis ; remboursement de TICPE en AG12.d).
- Tests : chaque exemple se calcule ; 22 cas chiffrés à la main ; valeurs refusées ; liste complète des 48 calculettes.

## 8. Questions

- **Q-C5 Place dans le menu** : une entrée « Calculettes » dans le menu agricole ? Ou dans un menu « Outils » ?
- **Q-C6 Export PDF** : nécessaire dès AG12.a, ou la copie en texte suffit-elle pour commencer ?
- **Q-C7 Sourçage du groupe C** : je cherche les sources officielles (Légifrance, BOFiP, msa.fr, instructions techniques PAC) et je te présente chaque paramètre à valider avant d'écrire la calculette. Cela te convient-il ?
- **Q-C8 Zonages (07)** : Lexicon couvre-t-il assez les zonages utiles (zones vulnérables nitrates, Natura 2000, zones ICHN) ? Ou faut-il ajouter une source IGN (Géoplateforme, sans clé) ? Les BCAE sont-elles nécessaires ?
- **Q-C9 Ordre** : pilotes 23, 25 et 08 d'abord, puis a → b → c → d → e. D'accord ?
- **Q-C10 Calculatrice agricole (06)** : les six outils du § 3 (conversions, règle de trois, chantier, semis, azote, pluviométrie) te conviennent-ils ? Faut-il en retirer ou en ajouter (enrouleur d'irrigation, par exemple) ?

## 9. Calculatrice agricole (06) : liste des outils à cocher (Q-C10)

Calculs simples, sans paramètre réglementaire. Toute valeur de référence (densité, PMG, teneur, durée de gestation,
coefficient) est **saisie** par l'utilisateur, jamais fixée dans le code. **Tous retenus** (07/11/2026).

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

## 10. Sourçage du groupe C (AG12.d, 07/11/2026) : paramètres proposés, à valider

Recherche faite le 07/11/2026. **Légifrance refuse les accès automatisés (HTTP 403)** : les articles de code et les
arrêtés n'ont pas pu être lus directement. Ils sont cités d'après des pages officielles qui y renvoient (service-public,
code.travail.gouv.fr, impots.gouv.fr, douane.gouv.fr, msa.fr) ou d'après la presse agricole, ce qui est indiqué à chaque
ligne. Rien n'entre dans `data/regulatory/` avant ta validation (AGD5) ; la fiabilité proposée suit l'échelle des
paramètres (V vérifié sur le texte, R recoupé sur une source officielle, A à vérifier).

### 02 Validité du Certiphyto

| Paramètre | Valeur | Source | Fiabilité proposée |
|---|---|---|---|
| `phyto.certiphyto.validity_years` | 5 ans | CRPM art. R254-8 (cité par la DRAAF Bretagne, note d'avril 2025) ; fiche service-public F31192 (vérifiée le 26/03/2026) | R |
| `phyto.certiphyto.renewal_window_months` | 12 mois avant la fin (« de préférence ») | service-public F31192 | R |
| Prorogations DEA / DENSA | expirant du 10/04/2024 au 30/04/2024 : + 3 ans ; du 01/05/2024 au 01/05/2025 : + 2 ans ; du 02/05/2025 au 01/05/2026 : + 1 an | service-public F31192 ; décrets n° 2024-326 du 9 avril 2024 et n° 2025-222 du 7 mars 2025 | R |

Calcul : date de fin = délivrance + 5 ans, prorogée selon la catégorie et la date d'échéance ; date conseillée de
renouvellement = 12 mois avant. Un projet de décret (renouvellement de 12 mois sans attestation jusqu'en 2027) n'est
**pas** retenu tant qu'il n'est pas publié.

### 20 Mise à jour du DUER

| Paramètre | Valeur | Source | Fiabilité proposée |
|---|---|---|---|
| `labour.duer.annual_threshold` | mise à jour au moins chaque année à partir de **11 salariés** | Code du travail art. R4121-2, 1° (texte lu sur code.travail.gouv.fr) | V |
| Autres cas | à tout aménagement important modifiant les conditions de santé, sécurité ou travail ; à toute information supplémentaire sur un risque | R4121-2, 2° et 3° | V |

Calcul : effectif et date de la dernière mise à jour → prochaine échéance (un an) ou « à chaque changement » sous 11
salariés ; rappel possible dans l'échéancier.

### 10 Exonération TO-DE

| Paramètre | Valeur | Source | Fiabilité proposée |
|---|---|---|---|
| `msa.tode.full_ceiling_smic` | exonération totale jusqu'à **1,25 SMIC** mensuel (depuis le 01/05/2024) | msa.fr (mise à jour du 01/04/2026) | R |
| `msa.tode.zero_ceiling_smic` | exonération nulle à partir de **1,6 SMIC** | presse sociale (Previssima, bulletinspaie) citant la LFSS 2025 art. 8 ; CRPM D741-60 non lu | A |
| `msa.tode.formula` | entre les deux : 1,25 × C ÷ 0,35 × (1,6 × SMIC mensuel ÷ rémunération − 1), C = taux des cotisations patronales exonérées | décret n° 2025-537 du 12 juin 2025 modifiant D741-60, d'après bulletinspaie ; texte non lu | A |
| Pérennité | dispositif permanent (LFSS 2025), étendu à certaines CUMA et coopératives de fruits et légumes | msa.fr | R |

Le taux C dépend des cotisations de l'employeur : il serait **saisi** (avis de la caisse). La durée maximale par salarié
et par an n'a pas été vérifiée : non retenue sans source.

### 16 Aides PAC 2026

| Paramètre | Valeur 2026 | Source | Fiabilité proposée |
|---|---|---|---|
| `pac.dpb.unit_value_cents` (Hexagone) | 127,70 € | arrêtés du 16/09/2026 (JORF n° 0229 du 01/10/2026) cités par la presse (Aliantis, Leandri Conseils) ; texte non lu | A |
| `pac.redistributive.amount_cents` | 48,50 €/ha (une source indique 48,58 €/ha : **écart**) | presse (Terre-net, Cerfrance, chambre des Landes) | A |
| `pac.redistributive.max_ha` | 52 premiers hectares | presse (La France Agricole) ; à confirmer pour 2026 | A |
| `pac.ecoregime.base_cents` / `higher_cents` / `organic_cents` / `hedges_bonus_cents` | 45,46 / 62,05 / 110 / 20 €/ha | arrêté du 16/09/2026 « écorégime » (JORFTEXT000054930379) cité par la presse ; texte non lu | A |
| `pac.young_farmer.amount_cents` | 3 700 € par exploitation | presse (Terre-net, Cerfrance) | A |
| Avance 2026 | 75 % à partir du 16/10/2026 | chambres d'agriculture (Vienne, Landes) | A |

Le coefficient stabilisateur (montant versé par DPB inférieur à sa valeur) et la transparence GAEC sont à préciser ;
les aides couplées (bovins, ovins, protéines) ne sont pas sourcées ici. **Tous ces montants demandent ta lecture de
l'arrêté sur Légifrance ou TéléPAC** avant d'être enregistrés.

### 05 Gazole non routier (partie « remboursement »)

| Paramètre | Valeur | Source | Fiabilité proposée |
|---|---|---|---|
| `energy.gnr.agri_rate_cents_per_hl` | tarif réduit **3,86 €/hl**, appliqué dès la facture sur attestation depuis le 01/07/2024 (sinon remboursement par la DGFiP) | douane.gouv.fr, page « Gazole non routier (GNR) » ; CIBS art. L312-35 | R |
| `energy.gnr.crisis_aid_cents_per_l` (2026) | avril 2026 : 3,86 c€/l (plafond 50 000 €) ; mai à décembre 2026 : 15 c€/l livré par mois | impots.gouv.fr, page de l'aide « travaux agricoles et forestiers » (décrets n° 2026-477 du 10 juin 2026 et n° 2026-982 du 23 octobre 2026 cités) | R |

Conséquence : depuis juillet 2024, il n'y a plus de « remboursement TICPE » à calculer pour un exploitant qui achète
avec attestation. La calculette 05 compterait l'**aide exceptionnelle 2026** (paramètre daté) et signalerait le tarif
réduit. Le tarif de droit commun du GNR n'a pas été sourcé : la comparaison « sans attestation » resterait à saisir.

### 04 Carte RPG et 07 zonages (données, pas de paramètres)

| Besoin | Source vérifiée (en ligne, sans clé) | Remarque |
|---|---|---|
| Parcelles et cultures (04) | IGN Géoplateforme WFS `RPG.LATEST:parcelles_graphiques`, `RPG.LATEST:codes_cultures` (et `RPG.2024`) ; Lexicon `graphic_parcels` (campagnes 2022 à 2025, Licence Ouverte) | IGN déjà utilisé par `geodata.py` (WFS par emprise) |
| Natura 2000 (07) | IGN WFS `patrinat_sic:sic`, `patrinat_zps:zps` ; Lexicon `protected_natural_zones` (MNHN / INPN) | |
| BCAE (07) | IGN WFS `HYDROGRAPHY.BCAE.LATEST:bcae_cours_eau` (bandes tampons), `TOURBIERES_ZONES-HUMIDES.BCAE:bcae` (BCAE 2), `PRAIRIES.SENSIBLES.BCAE:prairies_sensibles` | |
| Zones vulnérables nitrates, zones défavorisées (ICHN) | **non trouvées** dans les couches IGN listées ni dans Lexicon | source à choisir (Q-C11) |

### Validation du 07/11/2026 et réalisé (AG12.d, première partie)

- **Validé par l'utilisateur** :
  - Certiphyto, DUER, GNR : tels que proposés ;
  - **TO-DE** : texte de l'article D741-60 (version du 15/06/2025) fourni depuis Légifrance, d'où la fiabilité V ;
  - **PAC 2026** : montants de l'arrêté du 16/09/2026 confirmés, avec les aides animales. Bovins de plus de 16 mois : 51 € (base) ou 94 € (supérieur) par UGB. Ovins : 20,54 € par brebis, plus 2 € sur les 500 premières. Caprins : 13,83 € par chèvre. L'aide redistributive est retenue à 48,50 €/ha, et non 48,58 €, qui était l'estimation du printemps. La valeur du DPB reste saisie (montant TéléPAC).
- **Paramètres** `data/regulatory/tools.json` (25 valeurs datées, sources et fiabilité).
- **Calculettes** (`reglementaire.py`) :
  - **02 Certiphyto** : échéance du certificat, prorogation DEA / DENSA, date conseillée de renouvellement. L'exemple officiel est vérifié : échéance 11/10/2024, validité jusqu'au 10/10/2026 ;
  - **20 DUER** : échéance annuelle à partir de 11 salariés, sinon mise à jour aux changements ;
  - **10 TO-DE** : exonération du mois, totale, dégressive ou nulle ; le taux C est saisi ;
  - **16 Aides PAC** : redistributive, écorégime, bonus haies, jeune agriculteur, bovins, ovins, caprins. Une campagne sans arrêté enregistré est refusée.
- **05 Gazole et GNR** : tarif réduit d'accise affiché, aide exceptionnelle 2026 du mois choisi (plafond en avril). Un mois sans aide affiche « aucune ».
- **Cadre** : un résultat peut citer des paramètres facultatifs (aide d'un mois donné), affichés avec leur source.
- **AG12.d, seconde partie (faite)** : voir ci-dessous.

### Réalisé (AG12.d, seconde partie : 04 carte RPG, 07 zonages)

- **Choix de l'utilisateur** : point choisi d'un **clic sur une carte** ; **résultat avec carte**. Lieu de test :
  45,8295 N ; 0,7870 O, d'après l'outil d'identification de parcelle de Lexicon.
- **Requêtes mises au point**, vérifiées en réel sur le lieu de test :
  - **IGN** : WFS 2.0, emprise en `urn:ogc:def:crs:EPSG::4326` (ordre latitude, longitude), GeoJSON.
    - RPG : parcelles qui touchent le carré de côté deux fois le rayon (7 parcelles, blé tendre d'hiver sous le point).
    - Natura 2000 et BCAE : carré de ± 5 m (le filtre « point » ne répond pas sur Natura 2000).
    - Cours d'eau BCAE : carré de ± 50 m.
  - **Sandre** : WFS 2.0, filtre `fes:Intersects` sur un point et attributs seuls. La réponse fait 1,2 Ko au lieu de 2,4 Mo avec la géométrie. Le lieu de test est en zone FRF_38 ; un point dans les Alpes est hors zone.
- **Service** `agri_geo.py` : RPG autour d'un point avec les libellés des cultures, point dans un polygone, zone vulnérable (GML analysé), zonages au point, cache et délai bornés.
- **Cadre** : entrée de type `point` (latitude, longitude en France métropolitaine) ; résultat avec carte (`Result.map`).
- **Calculettes** :
  - **04 Carte RPG** : parcelle sous le point, parcelles et surfaces par culture dans un rayon de 50 à 1 000 m, carte colorée par groupe de cultures ;
  - **07 Zonages** : zone vulnérable aux nitrates, Natura 2000 (habitats, oiseaux), BCAE 9 (prairies sensibles), BCAE 2 (zones humides et tourbières), BCAE 4 (cours d'eau à proximité), avec liens vers les fiches et l'arrêté.
- **Écran** : carte Leaflet chargée à la demande (photo aérienne IGN), centrée sur la structure. Un clic place le point, et le résultat s'affiche sur la carte.
- **Tests** : faux IGN et faux Sandre, aucun appel réel. Indisponibilité → 503 ; point hors de France refusé.
- **Non couvert** : zones défavorisées (ICHN), faute de source.

### Réalisé (AG12.e : outil de l'assistant)

- **Deux outils de lecture** (`app/services/assistant/tools.py`), donnés à tous les rôles :
  - `list_calculators` : calculettes du type de la structure, avec leurs entrées (clé, type, unité, choix possibles) et un filtre sur un mot ;
  - `run_calculator` : même calcul que l'écran (`calculators.run`). Les valeurs passent en paires clé / valeur, ce qui garde le schéma strict. `prefill` complète les entrées avec les chiffres de la structure. Le résultat rend le résultat principal, le détail, le tableau (30 lignes au plus), les avertissements, la méthode, les paramètres datés avec leur source, et le lien `/outils/<code>`. Rien n'est enregistré.
- **Consigne de l'assistant** : pour un calcul, passer par ces deux outils et reprendre méthode et sources.
- **Jeu d'évaluation** (manuel, hors CI) : deux cas ajoutés, plafond DEP et dose de semis.
- **Tests** sans appel à l'API Claude : même résultat que l'écran, erreur sur une entrée manquante, booléen contrôlé, préremplissage avec origine.

### Zones défavorisées (ICHN), ajout du 07/11/2026

- **Constat**, après vérification de la source signalée :
  - pas de jeu national sur data.gouv.fr ;
  - pas de couche ICHN à l'IGN ;
  - le tableau du ministère par commune décrit le **projet** de zonage 2019, sans les zones de montagne et sans les modificatifs de 2023 et 2026.
- **Choix de l'utilisateur** : les services cartographiques des DDT qui en publient. La réponse est exacte, mais seulement pour ces départements.
- **Référentiel** `data/agri_less_favoured_areas.json` : 13 départements retenus sur 27 jeux trouvés. Seuls les jeux postérieurs à la réforme de 2019 sont gardés, dont le Rhône pour ses seules communes classées en partie (années de 2019 et après).
  - Écartés : Vendée 2016, Cher 2014, Aveyron 2007, Alpes-de-Haute-Provence infracommunal 2004, Cantal (couche sans attributs), doublon GéoFLA de la Corrèze.
  - Par département : service WFS (Géo-IDE), couche, champ du libellé, valeurs « non classé » (« Plaine », « LAC », « non classee ») et page data.gouv.fr.
- **Service** `agri_geo.less_favoured_at` :
  - département du point par la parcelle cadastrale la plus proche (géocodage inverse IGN, index « parcel » ; l'index « address » ne répond pas loin des habitations) ;
  - puis couche de la DDT sur un carré de ± 5 m, attributs seuls ;
  - correction des libellés UTF-8 lus en Latin-1.
- **Calculette 07** : ligne « Zone défavorisée (ICHN) » qui vaut « oui » ou « non », avec le libellé de la DDT et l'année des données, ou « à vérifier » hors des départements couverts (lien vers la page du ministère).
- **Vérifié en réel** :
  - Charente : ZSCS ;
  - Savoie : haute montagne ;
  - Vienne : zone défavorisée simple 2019 ;
  - Hautes-Pyrénées : zone défavorisée simple ;
  - Charente-Maritime : « à vérifier ».
