# Audit « comptabilité agricole » pour Lyvre : volet réglementation

Date : 3 novembre 2026. Rédigé pour l'ajout d'un référentiel « exploitation agricole » à Lyvre. Lyvre gère déjà la partie double, les plans par référentiel, la CA3 mensuelle, les immobilisations, la clôture, le FEC et Factur-X.

## Sources et niveau de confiance

**Sources locales, lues entièrement :**
- **[ANC]** Règlement ANC 2020-04 du 3 juillet 2020 sur les comptes annuels des exploitations agricoles, homologué le 29/12/2020. Il s'applique aux exercices ouverts depuis le 01/01/2021. Il s'agit de la version avec commentaires infra-réglementaires (IR).
- **[CGI]** CGI, art. 63 à 78, « version en vigueur au 03/11/2026 » (export Légifrance). Elle intègre la LF 2025 (loi 2025-127 du 14/02/2025), la LF 2026 (loi 2026-103 du 19/02/2026), le décret 2025-547 du 17/06/2025 et le décret 2026-562 du 29/06/2026.
- **[SIC]** Article SIC n° 384 (mai 2019), Fontanesi et Collard. Il commente le règlement ANC 2019-01, qui a intégré au PCG les règles d'évaluation agricoles.
- **[CSOEC-OBL]** CSOEC, « Exploitants agricoles, connaissez-vous vos obligations comptables et fiscales ? », mise à jour 2026.
- **[CSOEC-SOC]** CSOEC, « Quelle société pour mon exploitation agricole ? », mise à jour juin 2026.
- **[AGIRIS]** Guide Isacompta « Fiscalité des entreprises 2024 ». Il exclut explicitement la fiscalité agricole. Il ne sert ici que pour l'IS, la CFE/CVAE et les régimes TVA non agricoles.

**Vérifications web (novembre 2026) :**
- impots.gouv.fr : suppression du RSI TVA au 01/01/2027, remboursements de crédit de TVA, remboursement forfaitaire agricole.
- BOFiP BOI-TVA-SECT-80-30-60-20 (version archivée 2014, structure toujours valable).
- msa.fr (caisses régionales), presse agricole (Réussir, Terre-net), agriculture.gouv.fr (LF 2026).

**Convention.** Un point marqué **[À VALIDER]** n'a pas pu être vérifié sur un texte officiel à jour. Il est repris en section 8.

**Remarque importante sur les seuils.** Le CGI en vigueur au 03/11/2026 donne pour l'art. 69 : 129 200 € (micro-BA), 421 000 € (réel normal) et 517 000 € (GAEC, art. 71). Ces montants sont issus du décret 2026-562 du 29/06/2026, en vigueur au 01/07/2026. Ce sont aussi les chiffres de la brochure CSOEC de juin 2026. Des sources de mars 2026 (Weblex) donnent encore 120 000 € et 391 000 € : ce sont les seuils 2024-2025 issus de la LF 2024. Le millésime exact d'application (revenus 2026, ou période triennale 2026-2028) reste **[À VALIDER]**. **Conséquence pour Lyvre :** tous les seuils doivent être des paramètres datés (table `parametre_fiscal(code, valeur, date_debut, date_fin, source)`), jamais des constantes.

---

## 1. Régimes d'imposition des bénéfices agricoles (BA) et formes juridiques

### 1.1 Champ du BA

Art. 63 CGI. Sont des BA les revenus de l'exploitation de biens ruraux :
- production forestière, y compris la vente de coupes sur pied ;
- champignonnières, apiculture, aviculture, pisciculture, conchyliculture ;
- obtenteurs de variétés végétales ;
- préparation et entraînement d'équidés, hors spectacle ;
- biomasse et énergie issues majoritairement de l'exploitation : régime réel obligatoire (art. 69 E) ;
- mise à disposition de droits à paiement de base (DPB) PAC ;
- attelages canins ;
- actions de restauration ou de maintien d'écosystèmes sur le périmètre de l'exploitation.

Côté comptable, le champ est défini par l'art. L. 311-1 CRPM (cycle biologique, prolongement de l'acte de production, méthanisation ≥ 50 % de matières agricoles) [ANC art. 111-1].

### 1.2 Micro-BA (art. 64 bis CGI)

- **Champ.** Le micro-BA s'applique aux exploitants dont la moyenne des recettes HT sur 3 années consécutives ne dépasse pas **129 200 €** (art. 69 I). Il s'apprécie pour l'ensemble des exploitations, avec la quote-part des recettes des sociétés et groupements non soumis à l'IS (art. 70).
- **Calcul du bénéfice.** Bénéfice = moyenne des recettes HT de l'année N, N-1 et N-2, moins un **abattement de 87 %**, avec un **minimum de 305 €**. Les plus-values et moins-values sont calculées selon le régime réel. L'abattement est réputé couvrir l'amortissement linéaire.
- **Recettes retenues.** Ce sont les sommes encaissées dans l'année civile, plus les produits prélevés et alloués aux salariés ou au propriétaire en paiement du fermage.
- **Recettes exclues :**
  - cessions d'immobilisations ;
  - remboursements de charges d'entraide ;
  - ICHN (indemnités compensatoires de handicap naturel) ;
  - subventions et primes d'équipement ;
  - redevances tirées du droit de propriété.
- **Création d'activité.** On retient les recettes de N la première année, puis la moyenne N/N-1 l'année suivante.
- **Sortie du réel.** L'année qui suit, les recettes sont diminuées des créances HT du dernier bilan réel.
- **Passage micro vers réel.** Les créances du bilan d'ouverture sont ajoutées au bénéfice, après un abattement de 87 % (art. 72 E bis).
- **Option pour le réel simplifié** (art. 64 bis V et 69 II a). Elle vaut 1 an et se reconduit tacitement. On la formule dans le délai de déclaration de l'année précédente, ou dans celui de la 1re période en cas de création (art. 69 IV).
- **Exclusions :**
  - sociétés à activité agricole créées depuis le 01/01/1997 et imposées selon l'art. 8 (réel obligatoire), sauf l'EARL dont l'associé unique est une personne physique qui dirige l'exploitation (art. 69 D) ;
  - marchands de bestiaux (art. 69 C) ;
  - activités biomasse et énergie, et fiducie (art. 69 E).
- **Obligations.**
  - Tenir un document qui détaille jour par jour les recettes professionnelles, et conserver les factures et justificatifs (art. 64 bis IV).
  - Déclarer sur la 2042 C PRO les recettes de N, N-1 et N-2 et les plus-values ou moins-values (art. 64 bis III) [CSOEC-OBL].
- **Recettes à façon.** Les recettes d'élevage ou de culture portant sur des animaux ou produits appartenant à des tiers sont **multipliées par 3** pour l'appréciation des seuils (art. 69 VI, al. 2).

### 1.3 Réel simplifié (RSA-BA) et réel normal

- **Réel simplifié.** Il s'applique de plein droit quand la moyenne triennale est comprise entre 129 200 € et **421 000 € HT**. Il est ouvert sur option aux exploitants micro (art. 69 II).
- **Réel normal.** Il s'applique de plein droit au-delà de 421 000 € à compter du 1er exercice qui suit la période triennale (art. 69 III). Les exploitants au réel simplifié peuvent opter pour le réel normal (art. 69 III, al. 2).
- **Mesure des recettes.** Pour la limite RS/RN, ce sont des **créances acquises** au sens de l'art. 38-2 bis (art. 69 V). Pour le seuil micro, ce sont des **encaissements** (64 bis).
- **Actualisation.** Les seuils sont revus tous les 3 ans, au rythme de la 1re tranche du barème IR (art. 69 VI).
- **GAEC** (art. 71), si tous les associés travaillent effectivement dans le groupement :
  - si la moyenne des recettes du groupement est ≤ 517 000 €, le seuil réel = 129 200 € × nombre d'associés ;
  - au-delà, le seuil = 60 % × 129 200 € × nombre d'associés ;
  - les seuils de l'art. 75 (50 %, 100 000 €) s'apprécient au niveau du groupement, avec 100 000 € × nombre d'associés exploitants, dans la limite de 4.
- **Règles d'assiette au réel** (art. 72). Principes BIC « avec des modalités adaptées » : faible rotation des capitaux, poids des éléments non amortissables (foncier, améliorations foncières permanentes, parts de coopératives et de SICA), irrégularité des revenus. Le détail figure à l'annexe III, art. 38 sexdecies A à RA.
- **Simplifications du réel simplifié** (art. 74) :
  - **Comptabilité de trésorerie.** On n'enregistre au jour le jour que les encaissements et paiements. Les créances et dettes sont constatées à la clôture. Une option permet de traiter ainsi les frais généraux payés à échéances régulières ≤ 1 an.
  - **Stocks.** Ils sont évalués au prix de revient, ou au cours du jour s'il est inférieur. Sur option, ils peuvent être évalués selon une **méthode forfaitaire** à partir du cours du jour, sauf les matières premières achetées et les avances aux cultures.
  - **Carburants.** Les carburants des déplacements professionnels peuvent être retenus selon un **barème forfaitaire annuel**.
  - **Petits frais en espèces.** Les frais généraux accessoires payés en espèces sont admis sans justificatif dans la limite de **1 ‰ du CA, avec un minimum de 152 €**.
- **Déclaration du réel simplifié.** Elle comprend un compte simplifié du résultat fiscal, un tableau des immobilisations et amortissements et un bilan simplifié (art. 74 A).

**Obligations et formulaires** [CSOEC-OBL] :

| Régime | Livres | Déclaration | Délai |
|---|---|---|---|
| Micro-BA | Livre journalier des recettes, pièces | 2042 C PRO (recettes N, N-1, N-2) | Avec la déclaration de revenus |
| Réel simplifié | Livre-journal recettes/dépenses ; livre d'inventaire (compte simplifié, tableau des immobilisations) ; bilan simplifié | **2139-SD** et annexes 2139 A (bilan), B (compte de résultat fiscal), C (capital), D (filiales), E (provisions) | 2e jour ouvré après le 1er mai N+1, +15 jours si expert-comptable ; télédéclaration (EDI-TDFC) obligatoire |
| Réel normal | Livre-journal au jour le jour, livre d'inventaire (inventaire, bilan, compte de résultat), pièces | **2143-SD** et tableaux 2144 à 2154 ; liste des associés ≥ 10 % et des filiales | Idem |

**Exercice.** L'exercice dure normalement 12 mois, avec des dates libres. Sans bilan dans l'année civile, il faut une déclaration « provisoire » [CSOEC-OBL]. Les déclarations BA restent dues en mai N+1, quelle que soit la date de clôture.

### 1.4 Formes juridiques et conséquences

[CSOEC-SOC] ; CGI art. 8, 69 D, 71, 206-3, 239, 239 bis AA, 1655 sexies.

| Forme | Nature | Associés et capital | Imposition par défaut | Option | Régime BA | Liasse |
|---|---|---|---|---|---|---|
| **EI** | Personne physique | — | IR, BA | IS par assimilation EURL/EARL (art. 1655 sexies) | Micro, RS ou RN selon recettes | 2042 C PRO, ou 2139 / 2143 ; si IS : 2065 + 2033 / 2050 |
| **EARL** | Société civile (CRPM L.324-1) | 1 à 10 personnes physiques ; capital minimum 7 500 € ; associés exploitants > 50 % ; rémunération des associés exploitants 1 à 3 SMIC (4 pour les gérants) | Transparente (art. 8), IR | IS (art. 206-3 / 239) | Réel obligatoire depuis 1997, sauf EARL unipersonnelle personne physique dirigeante (micro possible, art. 69 D) | 2139 / 2143 ; associés sur 2042 C PRO |
| **GAEC** | Société civile particulière (CRPM L.323-1), agrément du préfet | 2 à 10 personnes physiques majeures, toutes exploitantes ; capital minimum 1 500 € ; rémunération 1 à 6 SMIC ; **transparence GAEC** (CRPM L.323-13) pour le statut et les aides | Transparente, IR | IS | Seuils × nombre d'associés (art. 71) ; plafonds DEP, 73 A et art. 75 × associés (max 4) ; l'apport d'actifs au GAEC vaut cession (art. 73 E) | 2139 / 2143 |
| **SCEA** | Société civile | ≥ 2 associés, personnes physiques ou morales ; pas de capital minimum | Transparente, IR ; **IS de plein droit** si les recettes BIC/BNC dépassent les seuils de l'art. 75 (et l'ancien art. 75 A) | IS | Réel obligatoire si créée après 1997 | 2139 / 2143 ; 2065 si IS |
| **GFA exploitant** | Société civile (CRPM L.322-1) | ≥ 2 associés | Transparente | IS | Réel obligatoire après 1997 | 2139 / 2143 |
| **SARL de famille** | Commerciale | 1 à 100 associés | IS ; option IR si caractère familial (art. 239 bis AA) | IR | — | 2065 + 2033 / 2050 ; si IR : BA, BIC et BNC déclarés séparément |
| **SA / SAS / SASU agricoles** | Commerciale | — | **IS de plein droit** | IR temporaire, 5 ans (art. 239 bis AB) **[À VALIDER : conditions pour une SAS agricole]** | — | 2065 + liasse 2033 (RSI) ou 2050 (RN), plus comptes annuels déposés au greffe ; le **règlement ANC 2020-04 s'impose** (IR 3 de l'art. 111-1) |

**Points clés :**
- **Champ comptable de l'ANC 2020-04.** Il vise les entités **légalement tenues d'établir des comptes annuels** dont l'activité principale est agricole : sociétés commerciales, sociétés civiles tenues à cette obligation, et en pratique les exploitants au réel normal. Il exclut la simple reddition de comptes de l'art. 1856 C. civ. [ANC art. 111-1 et IR 3]. Les imprimés fiscaux BA (2139/2143) suivent eux-mêmes la nomenclature agricole [CSOEC-OBL].
- **Associés de sociétés transparentes.** Chacun déclare sa quote-part sur la 2042 C PRO. Les seuils personnels s'apprécient avec la quote-part des recettes sociales (art. 70). Les plus-values 151 septies d'une société civile agricole sont calculées associé par associé (art. 70, al. 2).
- **Passage à l'IS** (apport à une société IS, option IS, transformation). Le 75-0 C permet d'étaler l'IR afférent sur 5 ans : DEP non utilisées, étalements 75-0 A, excédent de moyenne triennale, profits latents sur avances aux cultures et stocks bloqués.
- **Rachat ou transmission de parts.** Pour un associé d'une société art. 8 au réel obligatoire, l'imposition immédiate de sa quote-part est possible (art. 73 D).

### 1.5 Ce que Lyvre doit implémenter (régimes et formes)

- **Données de l'entité :**
  - forme juridique (EI, EARL, EARL uni, GAEC, SCEA, GFA, SARL famille, SAS, SA) ;
  - régime d'imposition (IR, IS) ;
  - régime BA (micro, RS, RN) avec dates d'effet ;
  - options datées (RS sur option, RN sur option, IS, 75-0 B, 72 B bis), avec date d'exercice, durée et date limite de renonciation ;
  - date de création ;
  - liste des associés : exploitant oui/non, % des droits aux bénéfices, date d'entrée/sortie, qualité JA (DJA, date d'octroi), retraité ;
  - nombre d'associés exploitants, utilisé comme multiplicateur plafonné à 4.
- **Calculs :**
  - moyenne triennale des recettes : encaissements HT pour le micro, créances acquises pour RS/RN ;
  - ×3 pour les opérations à façon ;
  - prise en compte des quotes-parts de sociétés (art. 70) ;
  - multiplicateur GAEC (517 000 €, 60 %) ;
  - **alerte de changement de régime** à N+1 ;
  - bénéfice micro (87 %, minimum 305 €) avec ventilation des recettes exclues ;
  - réintégration des créances au passage micro vers réel (art. 72 E bis) ;
  - répartition du résultat fiscal entre associés.
- **États :**
  - liasses 2139 (A à E) et 2143 (2144 à 2154) en export EDI-TDFC, ou au moins en tableaux de correspondance ;
  - liasses IS 2033 / 2050 pour les sociétés à l'IS (déjà au moins partiellement dans Lyvre pour les sociétés PCG) ;
  - état « quote-part par associé » pour les 2042 C PRO ;
  - pour le micro : livre des recettes journalier et récapitulatif des recettes N, N-1, N-2.
- **Contrôles :**
  - micro interdit pour les sociétés créées après 1997, sauf EARL uni (69 D) ;
  - micro interdit pour 69 C et 69 E ;
  - cohérence entre forme et nombre d'associés (GAEC 2-10, EARL 1-10) ;
  - rappel des dates limites d'option et de renonciation.

---

## 2. Spécificités comptables : règlement ANC 2020-04 (et ANC 2019-01 intégré au PCG)

### 2.1 Architecture des textes

- **ANC 2019-01** (8 février 2019) a modifié le PCG (règlement 2014-03) pour les **règles de comptabilisation et d'évaluation** des activités agricoles [SIC] :
  - classement des biens vivants ;
  - coûts d'entrée ;
  - coût standard et prix de détail pour les stocks ;
  - avances aux cultures ;
  - sous-activité ;
  - cession des biens vivants en résultat d'exploitation.
- **ANC 2020-04** (Livre V, Titre 3 du règlement 2014-03) fixe les **modèles de comptes annuels**, le **plan de comptes agricole** et le **fonctionnement de certains comptes**. Il renvoie au PCG pour tout le reste (art. 111-2). Le PCGA de 1986 est abandonné à terme.
- Selon le [SIC], d'autres chantiers restent ouverts : fonds agricole, améliorations du fonds, entraide, sous-activité.
- La numérotation exacte des articles du PCG issus du 2019-01 (série 618-x) est **[À VALIDER]**.

### 2.2 Plan de comptes spécifique, liste exhaustive de l'ANC 2020-04 (art. 131-1)

**Classe 1**
- 1641 Emprunts fonciers ; 1642 Autres emprunts à moyen et long terme ; 1643 Emprunts à court terme
- 172 Dettes rattachées à des participations à des organismes professionnels agricoles (hors établissements de crédit)

**Classe 2**
- 2071 Fonds agricole résiduel (sous 207 Fonds commercial)
- 212 Agencements et aménagements de terrains : 2121 Amortissables, 2125 Non amortissables
- 217 Améliorations des sols et des milieux
- 231 Immobilisations corporelles en cours, avec les subdivisions 2341 Animaux reproducteurs, 2343 Animaux de service, 2346 Plantations pérennes, 2347 Autres végétaux immobilisés. Le texte les place sous 231 ; logiquement elles relèvent de 234. Racine exacte **[À VALIDER]**.
- **24 Immobilisations corporelles (biens vivants)** : 241 Animaux reproducteurs, 243 Animaux de service, 246 Plantations pérennes, 247 Autres végétaux immobilisés. Les plantations forestières vont en 247 (IR art. 121-2).
- 262 Participations à des organismes professionnels agricoles : 2621 Coopératives agricoles (hors CUMA), 2622 CUMA, 2624 SICA, 2628 Autres
- 2672 Créances rattachées à ces participations : 26721, 26722, 26724, 26728
- 2715 Parts dans les établissements de crédit (Crédit Agricole, etc.)
- 2723 Certificats de fonds de développement coopératif
- 284 Amortissements des immobilisations corporelles (biens vivants)
- 294 Dépréciations des immobilisations corporelles (biens vivants)
- 2962 Dépréciations des participations à des organismes professionnels agricoles

**Classe 3**
- 311 Stocks des activités agricoles :
  - 3111 Approvisionnements : 31111 Engrais et amendements, 31112 Semences et plants, 31113 Produits de défense des végétaux, 31114 Aliments du bétail, 31115 Produits de défense des animaux, 31116 Produits de reproduction animale
  - 3112 Animaux (cycle long) ; 3113 Animaux (cycle court)
  - 3114 Végétaux (cycle long) : 31141 Avances aux cultures, 31142 Pépinières, 31148 Autres végétaux
  - 3115 Végétaux (cycle court) : 31151 Avances aux cultures, 31152 Pépinières, 31158 Autres végétaux
- 331 Produits en cours :
  - 3311 Cycle long : 33111 Vins, 33112 Alcools
  - 3312 Cycle court : 33121 Produits végétaux, 33122 Produits animaux, 33123 Vins, 33124 Alcools, 33125 Autres produits transformés, 33126 Autres biens (activités annexes)
- 351 Produits intermédiaires : 3511 Activité agricole (35111 végétaux, 35112 animaux, 35113 transformés)
- 355 Produits finis : 3551 Activité agricole (35511 végétaux, 35512 animaux, 35513 transformés)

**Classe 4**
- 402 Fournisseurs, soldes après compensation ; 412 Clients, soldes après compensation
- 4311 Mutualité sociale agricole
- 4552 Associés « comptes bloqués » (principal) ; 45582 intérêts courus correspondants
- 461 Caisse de péréquation des prix
- **472 Opérations de compensation (convention de compte courant)**
- 4952 / 4953 / 4954 Dépréciations : opérations faites en commun (GAEC partiels, GIE / banques de travail, autres communautés)
- 497 Caisse de péréquation des prix (dépréciation)

**Classe 6**
- 6011 Achats stockés, activité agricole : 60111 Engrais et amendements, 60112 Semences et plants, 60113 Produits de défense des végétaux, 60114 Aliments du bétail, 60115 Produits vétérinaires, 60116 Produits de reproduction animale, **60117 Achats d'animaux (biens vivants non immobilisés)**
- 6051 Achats de travaux et services incorporés à la production agricole
- 6061 Fournitures non stockables : 60611 Eau, 60612 Gaz, 60613 Électricité, 60614 Carburants et lubrifiants, 60615 Eau d'irrigation
- 6131 Fermages et loyers du foncier ; 6132 Locations de matériel ; 6134 Locations d'animaux
- 6141 / 6142 / 6144 Charges locatives du foncier, du matériel, des animaux
- 634 Taxes spécifiques sur les produits de l'exploitation : 6341 végétaux, 6342 animaux, 6343 transformés, 6344 animaux, 6348 autres
- 6411 Salaires : 64111 Permanents, 64115 Temporaires ou occasionnels, 64116 Associés d'exploitation, 64117 Administrateurs, gérants, associés
- 6451 Cotisations MSA
- **657 Valeur comptable des biens vivants immobilisés (cédés)**
- 68114 Dotations aux amortissements des biens vivants immobilisés ; 68164 Dotations pour dépréciation des biens vivants immobilisés

**Classe 7**
- 701 Ventes de produits finis : 7011 végétaux, 7012 animaux, 7013 transformés, 7014 animaux
- 704 Travaux : 7041 Travaux à façon, **7042 Produits sur contrat d'intégration** (CRPM L.326-1)
- 713 Variation des stocks :
  - 71331 Produits en cours : 713311 cycle long, 713312 cycle court
  - 71355 Produits finis : 713551 animaux cycle long, 713552 animaux cycle court, 713553 végétaux cycle long, 713554 végétaux cycle court
- 7221 Production immobilisée hors biens vivants ; 7222 Production immobilisée biens vivants ; 724 Biens vivants immobilisés
- **73 Production autoconsommée** (prélèvements de l'exploitant, de la famille, des salariés : art. 132-3)
- 74 Subventions d'exploitation :
  - **741 Remboursement forfaitaire de TVA**
  - 742 Indemnités liées à la production agricole
  - 743 Subventions aux produits
  - 744 Subventions aux structures
  - 745 Subventions au revenu
  - 748 Autres
- **757 Produits de cessions des biens vivants immobilisés**

**Fonctionnement des comptes :**
- **Art. 132-1.** Les opérations des conventions de compte courant (entraide, échanges de travaux) passent en 472, avec une subdivision par convention. À la clôture, chaque subdivision est soldée en 402 ou en 412.
- **Art. 132-2.** Les produits de contrats d'intégration vont en 7042.
- **Art. 132-3.** La production autoconsommée va au crédit du 73.

**Remarques pour l'implémentation :**
- Le plan agricole se superpose au PCG. Les comptes PCG non cités restent valables : 131/139 subventions d'investissement, 14x provisions réglementées, 108 compte de l'exploitant, 646 cotisations personnelles de l'exploitant, etc.
- La **cession d'un bien vivant immobilisé** est en **résultat d'exploitation** (757 / 657), et non en exceptionnel (675/775) comme pour les autres immobilisations [SIC]. Le compte de résultat modèle comporte d'ailleurs les lignes « Produits de cession sur biens vivants immobilisés » et « Valeur comptable des biens vivants immobilisés cédés ».
- **Ventilation des aides PAC en 742-748.** L'ANC ne la précise pas. Mapping proposé **[À VALIDER]** :
  - aides découplées (aide au revenu de base, paiement redistributif, éco-régime, aide JA) → 745 ;
  - aides couplées animales et végétales → 743 ;
  - ICHN, MAEC, aides bio → 744 ou 748 ;
  - indemnités calamités, assurance récolte, FMSE → 742 ;
  - subventions d'équipement → 131.

### 2.3 Modèles de comptes annuels (art. 121-1 à 121-4)

**Bilan actif :**
- Immobilisations corporelles hors biens vivants : Terrains / Aménagements fonciers / **Améliorations des sols et des milieux** / Constructions / ITMO / Autres.
- Immobilisations corporelles biens vivants : **Animaux reproducteurs / Animaux de service / Plantations pérennes / Autres végétaux immobilisés**.
- Incorporelles : la ligne « Fonds commercial et Fonds agricole résiduel » est détaillée si besoin.
- Actif circulant : **Biens vivants et en-cours (cycle long)** (Animaux / Avances aux cultures / Autres végétaux / Vins et alcools / Autres en-cours) et **(cycle court)** (Animaux / Avances aux cultures / Autres végétaux / En-cours), puis Stocks (Approvisionnements et marchandises / Produits), Créances « clients » et « autres clients » (soldes de compensation).

**Bilan passif.** Il existe deux modèles :
- **Entreprise individuelle** : Capital individuel, écart de réévaluation, résultat, subventions d'investissement, provisions réglementées.
- **Société** : modèle PCG.
- Dans les deux, la ligne « Dettes autres fournisseurs (conventions de compte courant) » est distincte.

**Compte de résultat.** CA = Ventes de marchandises + **Ventes d'animaux (hors biens vivants immobilisés)** + Autre production vendue. Viennent ensuite les lignes :
- Produits de cession sur biens vivants immobilisés ;
- Production stockée (biens vivants non immobilisés, en-cours, produits) ;
- Production immobilisée, biens vivants et hors biens vivants ;
- **Production autoconsommée** ;
- Indemnités et subventions d'exploitation.

Côté charges :
- **Achats d'animaux** ;
- **Valeur comptable des biens vivants immobilisés cédés** ;
- les mentions « dont quotes-parts sur opérations faites en commun » et « dont rémunération du travail de l'exploitant ».

**Annexe.** Elle contient en plus le **tableau des biens vivants et en-cours de production** (art. 121-4) :
- cycle long et cycle court × (Animaux / Végétaux / En-cours) ;
- valeur nette à l'ouverture et à la clôture ;
- éventuellement l'évolution en **unités physiques** (têtes, hectares).

### 2.4 Règles d'évaluation et de classement (ANC 2019-01 / PCG, commentées par [SIC])

- **Biens vivants immobilisés ou en stock.** Un bien vivant (animal ou végétal) est **immobilisé** lorsqu'il devient certain ou quasi certain qu'il restera **durablement** dans l'entité comme **moyen de production** : reproducteurs, animaux de service, plantations pérennes (vignes, vergers). Sont **exclus** de l'actif immobilisé les biens vivants **destinés à être vendus** et ceux dont la **durée d'exploitation est inférieure à 12 mois**.
  - **Rupture avec la pratique IR** : les exploitants à l'IR inscrivaient le plus souvent leur cheptel en stock [SIC].
  - **Option fiscale.** Le classement fiscal des reproducteurs, en stock ou immobilisé, reste une **option fiscale** (annexe III, 38 sexdecies) **[À VALIDER]**. Il peut donc exister des divergences comptable/fiscal à suivre pour les entités soumises à l'ANC.
- **Inventaire par lots.** Les biens vivants d'une même espèce, d'une même classe d'âge et de même destination peuvent former **un seul lot** [SIC]. Lyvre doit gérer des immobilisations « par lot » avec une quantité (têtes) et des entrées/sorties partielles.
- **Coût d'entrée des biens vivants produits ou nés dans l'entité.** On peut appliquer la méthode retenue pour les stocks (coût standard ou prix de vente au détail) si l'entité produit des biens similaires pour la vente (renvoi à l'art. 213-14 PCG).
- **Passage de l'en-cours à l'immobilisation.** L'animal en croissance destiné à la reproduction est en immobilisation en cours (2341). Il passe en 241 à l'entrée en production, via 7222 / 724.
- **Stocks :**
  - **Coût standard** (art. 213-35 PCG) : on peut s'appuyer sur les **barèmes standards** (chambres d'agriculture, instituts techniques), en vérifiant qu'ils ne s'écartent pas trop des conditions propres de l'entité.
  - **Méthode du prix de détail** pour les produits prêts à la vente : cours du jour à la clôture, s'il est un bon indicateur du prix final, **moins une décote** (marge brute et frais de commercialisation) **adaptée à chaque catégorie** de stock [SIC].
  - **Sous-activité** : à exclure du coût de production (PCG ; chantier ANC en cours).
- **Avances aux cultures.** Ce sont les produits végétaux en terre à la clôture qui n'ont pas atteint un stade permettant leur commercialisation.
  - **Méthode** : coût standard (barèmes) admis ; **prix de détail interdit** [SIC].
  - **Fiscalement** (art. 72 A), au prix de revient, avec la liste limitative des frais : semences, engrais, amendements, traitements ; main-d'œuvre des façons culturales, de l'amendement et des semis ; frais de matériel (carburants, entretien, réparations, amortissements, travaux par des tiers).
  - **Comptes** : 31141 / 31151.
- **Méthode forfaitaire fiscale** du réel simplifié (art. 74 b). Elle part du cours du jour à la clôture, avec une décote forfaitaire. Les taux de décote couramment cités (−20 % produits végétaux, −30 % animaux, ou l'inverse) figurent à l'annexe III / BOFiP BOI-BA-BASE-20-30 et sont **[À VALIDER]**. La méthode ne s'applique ni aux approvisionnements achetés ni aux avances aux cultures.
- **Blocage des stocks à rotation lente** (art. 72 B bis). Sur option, valable 5 ans et reconduite tacitement, les stocks de produits ou d'animaux sont maintenus jusqu'à leur vente à la valeur de la clôture de l'exercice qui précède l'option. Fréquent en viticulture, cognac, élevage. Exclusif de 75-0 A et 75-0 B ; soumis au régime de minimis. Lyvre doit tenir **deux valeurs de stock** (comptable et fiscale bloquée) et la différence extra-comptable.
- **Améliorations foncières.** 2125 non amortissables (améliorations permanentes) ou 2121 amortissables ; 217 Améliorations des sols et des milieux (nouvelles pratiques culturales). Le traitement reste un chantier ANC en cours [SIC, CSOEC-OBL].
- **Fonds agricole** (CRPM L.311-3). C'est le compte 2071 « Fonds agricole résiduel ». Son traitement complet reste un chantier ANC.
- **DPB (droits à paiement de base).** L'ANC 2020-04 ne les traite pas. Pratique : immobilisation incorporelle (205 ou 207x) au coût d'acquisition, en général non amortie, avec un test de dépréciation **[À VALIDER]**. Leur mise à disposition est un BA (art. 63). Les **quotas laitiers** sont supprimés depuis 2015 ; les autres droits de production, s'ils existent, suivent la même logique d'incorporel.
- **Contrats de vente et d'intégration.** 7042 pour les contrats d'intégration. Les contrats pluriannuels EGALIM (CRPM L.631-24 s.) conditionnent la provision 73 A (voir 3.5). Lyvre doit pouvoir stocker l'indicateur « contrat EGALIM en cours à la clôture ».
- **Entraide et conventions de compte courant.** Voir 472 / 402 / 412 ci-dessus. En micro, les remboursements de charges d'entraide sont exclus des recettes.

### 2.5 Ce que Lyvre doit implémenter (comptable)

- **Référentiel « agricole_anc2020 »** : plan de comptes ci-dessus superposé au PCG, avec le libellé, le sens normal du solde et le mapping vers les postes du bilan et du compte de résultat agricoles et des liasses 2139/2143.
- **États** :
  - bilan agricole (actif à deux rubriques biens vivants, cycle long/court ; passif EI ou société) ;
  - compte de résultat agricole avec les lignes spécifiques ;
  - annexe avec le **tableau des biens vivants** (valeurs nettes à l'ouverture et à la clôture, unités physiques facultatives).
- **Immobilisations biologiques** :
  - nature (reproducteur, service, plantation pérenne, autre végétal) ;
  - gestion **par lot** (espèce, classe d'âge, quantité) ;
  - immobilisations en cours (234x) puis mise en service ;
  - amortissement (284 / 68114) et dépréciation (294 / 68164) ;
  - **cession en 757 / 657** en résultat d'exploitation ;
  - mortalité et sinistres.
- **Inventaire des stocks agricoles** :
  - quantités × valeur unitaire par catégorie (approvisionnements 3111x, animaux 3112/3113, végétaux 3114/3115, en-cours 331x, produits 351x/355x) ;
  - méthodes : coût réel, coût standard par barème, prix de détail avec décote, forfaitaire fiscale ;
  - écriture automatique de variation (6031 / 713x) ;
  - **double valorisation** comptable et fiscale (72 B bis, méthode forfaitaire) avec écart reporté en extra-comptable.
- **Avances aux cultures** : fiche culture-parcelle (surface, intrants, façons culturales, mécanisation), calcul selon la liste de l'art. 72 A, écriture 31141/31151 ↔ 713311/713312.
- **Autoconsommation** (73) et **avantages en nature** prélevés (micro : à ajouter aux recettes).
- **Conventions d'entraide** : sous-comptes 472, solde automatique en 402/412 à la clôture.
- **Contrôles** :
  - aucun animal destiné à la vente en 24x ;
  - aucun stock 3112 « reproducteur » si l'entité est soumise à l'ANC 2020-04 et qu'il est quasi certain que l'animal restera durablement (alerte, non bloquant) ;
  - cession d'un bien vivant passée en 775 au lieu de 757 ;
  - 472 non soldé à la clôture.

---

## 3. Dispositifs fiscaux agricoles (réel)

### 3.1 Déduction pour épargne de précaution, DEP (art. 73 CGI)

- **Plafond par exercice de 12 mois** (montants actualisés chaque année selon l'IPC hors tabac, art. 73 I-4 ; valeurs en vigueur au 03/11/2026), en fonction du **bénéfice imposable** :

| Bénéfice B | Plafond DEP |
|---|---|
| B < 33 287 € | 100 % de B |
| 33 287 ≤ B < 61 642 € | 33 287 + 30 % × (B − 33 287) |
| 61 642 ≤ B < 92 464 € | 41 794 + 20 % × (B − 61 642) |
| 92 464 ≤ B < 123 284 € | 47 957 + 10 % × (B − 92 464) |
| B ≥ 123 284 € | 51 040 € |

- **GAEC et EARL non IS.** Plafonds × nombre d'associés exploitants (max 4), sans dépasser le bénéfice.
- **Plafond global.** 150 000 € (× associés exploitants, max 4) moins les déductions non encore rapportées (I-2).
- **Ordre de calcul.** La DEP s'applique **après** les abattements 44 duodecies, terdecies, quaterdecies et **73 B (JA)** (I-3).
- **Épargne obligatoire :**
  - Dans les **6 mois** de la clôture, et au plus tard à la date limite de dépôt, il faut inscrire sur un **compte courant bancaire dédié** une somme comprise entre **50 % et 100 %** de la déduction. Ce compte est inscrit à l'actif et ne retrace que ces opérations.
  - À tout moment, l'épargne doit être **≥ 50 %** des déductions non rapportées et **≤ 100 %** de celles-ci.
  - **Substituts d'épargne** : les coûts d'acquisition ou de production de **stocks de fourrage** consommés par le cheptel, ou de **stocks de produits ou d'animaux à rotation > 1 an** (viticulture notamment), engagés dans l'exercice. En cas de vente de ces stocks, une quote-part du produit doit être versée sur le compte.
  - Les coopérateurs ou adhérents d'une OP peuvent utiliser un compte de créances spécifique.
- **Utilisation et réintégration :**
  - **10 exercices** pour faire face à des dépenses professionnelles. La réintégration a lieu dans l'exercice d'utilisation ou le suivant.
  - **Imposition réduite à 70 %** (30 % exonérés) si la somme est utilisée l'exercice de survenance d'un aléa, ou le suivant. Aléas visés : maladie animale ou végétale ou incident environnemental (L.361-3 CRPM ; depuis la LF 2026, également tout programme national ou européen d'indemnisation, II-2 e), aléa climatique assurable, calamité agricole, **aléa économique**.
  - **Aléa économique** : baisse de la valeur ajoutée de plus de 10 % par rapport à la moyenne des 3 exercices précédents, ou de plus de 15 % par rapport aux 3 exercices clos avant l'exercice précédent. Il faut une assurance L.361-4 et une **attestation d'expert-comptable**.
  - **Plafonds de la part exonérée** : 50 000 € par exercice, dont 40 % au maximum pour l'aléa économique, × associés (max 4).
  - **Non-utilisation** : réintégration au **10e exercice** suivant.
  - **Défaut d'épargne** : la fraction qui excède le double de l'épargne est réintégrée, majorée de l'intérêt de retard (art. 1727).
- **Formule de la valeur ajoutée** (II-2 d). VA = (ventes + variations d'inventaire + production immobilisée et autoconsommée + indemnités et subventions d'exploitation) − (coût d'achat des marchandises vendues + consommations en provenance de tiers), le tout HT.
- **Autres règles :**
  - l'art. 151 septies est exclu pour les matériels roulants acquis lors d'un exercice de réintégration et cédés dans les 2 ans (II-4) ;
  - transmission à titre gratuit, apport en société, fusion : continuité possible (III) ;
  - étalement IR à la cessation : 163-0 A, ou 75-0 C ;
  - DEP interdite pour les revenus biomasse et énergie seuls (V), pour les revenus accessoires de l'art. 75 ;
  - régime de minimis (VI).
- **Durée.** Le CSOEC indique une application « du 01/01/2019 au 31/12/2028 ». La LF 2026 a prorogé et élargi la DEP (agriculture.gouv.fr). Date de fin exacte **[À VALIDER]**.
- **Socialement**, la DEP n'est plus déductible de l'assiette MSA depuis la réforme 2026 (voir § 5).
- **Anciennes DPI/DPA** (72 D, 72 D bis, abrogés au 31/12/2018). Les soldes non encore rapportés suivent les anciennes règles. Lyvre doit pouvoir reprendre un **stock historique** de déductions avec leur exercice d'origine.

**Pour Lyvre :**
- calculateur de plafond (barème paramétré par millésime) ;
- registre des DEP par exercice d'origine (montant, épargne affectée, utilisations, réintégrations, part exonérée, échéance du 10e exercice) ;
- contrôle du ratio d'épargne (50-100 %) à chaque clôture ;
- compte bancaire « DEP » tagué ;
- calcul de la VA sur 3 et 4 exercices ;
- alerte à l'échéance ;
- report en extra-comptable (déduction et réintégration) vers les 2139 B / 2143.

### 3.2 Lissage et étalement

- **Moyenne triennale** (art. 75-0 B). Sur option, le BA retenu pour l'IR = moyenne des BA de N, N-1 et N-2 (reports déficitaires exclus).
  - L'option vaut 3 ans et se reconduit tacitement. Après une renonciation, il faut attendre 3 ans pour opter à nouveau.
  - Elle est interdite les 2 premières années de réel et l'année de cession ou cessation, mais permise l'année d'apport en société.
  - Elle est exclusive de 75-0 A a).
  - En sortie, l'excédent du BA sur la moyenne est taxé au taux marginal.
  - Elle s'applique au niveau de l'**associé personne physique** (impôt progressif). Lyvre fournit l'historique des BA, la déclaration est faite par le foyer.
- **Étalement des revenus exceptionnels** (art. 75-0 A). Sur option, le revenu exceptionnel est rattaché par **septièmes** (exercice de réalisation + 6 suivants). Est exceptionnel :
  - a) la fraction du bénéfice qui dépasse 25 000 €, ou la moyenne des 3 exercices précédents si elle est supérieure, lorsque le bénéfice dépasse 1,5 × cette moyenne, à conditions d'exploitation comparables ;
  - b) l'indemnité d'abattage sanitaire (L.221-2 CRPM) moins la valeur en stock ou en compte d'achats des animaux abattus.
  - Le solde restant à imposer devient imposable à la cessation, sauf apport ou transmission avec engagement.
- **Abattage sanitaire du cheptel reproducteur** (art. 75-0 D, LF 2026, IR 2025 à 2027). La différence entre l'indemnité et la VNC des animaux reproducteurs abattus est **exonérée**. La fraction non réinvestie dans la reconstitution du cheptel sous **2 ans** est réintégrée. La LFSS 2026 exonère aussi ces indemnités de cotisations sociales.
- **Étalement de l'IR à la cessation** (art. 75-0 C, passage à l'IS) : voir 1.4.
- **Indemnités d'assurance climatique** (art. 72 B). Une indemnité acquise sur un exercice mais qui couvre une perte d'un exercice ultérieur est imposable à l'exercice de constatation de la perte. Le décalage est à gérer en produits constatés d'avance ou en extra-comptable.

### 3.3 Abattement jeunes agriculteurs (art. 73 B) et DJA (art. 73 C)

- **Champ.** Exploitants au réel bénéficiaires des aides à l'installation (L.330-1 CRPM). L'abattement porte sur les **60 premiers mois** depuis l'octroi de la 1re aide.
- **Taux** (seuils issus du décret 2025-547) :
  - **75 %** si le bénéfice est ≤ **50 700 €** ;
  - sinon **50 %** jusqu'à 50 700 € et **30 %** de 50 700 à **67 600 €** ;
  - au-delà de 67 600 € : rien.
- **Exercice d'inscription de la DJA en comptabilité** : 100 % jusqu'à 50 700 € et 60 % au-delà, jusqu'à 67 600 €. Le montant de l'abattement est au moins égal à la DJA.
- **Modalités.**
  - L'abattement s'applique avant les déficits reportables.
  - Il ne s'applique pas aux profits à taux réduit et ne se cumule pas avec d'autres abattements.
  - Il est possible sur les exercices non prescrits clos avant l'attribution.
  - Seuils actualisés tous les 3 ans ; RGEC 2022/2472.
- **Écart entre sources.** La brochure CSOEC 2026 cite un plafond de 58 552 € alors que le CGI donne 67 600 €. Le CGI fait foi **[À VALIDER]** : millésime d'application du décret 2025-547.
- **DJA** (art. 73 C). Si elle est affectée à des immobilisations, elle suit l'art. 42 septies : subvention d'équipement réintégrée au rythme des amortissements (131 / 139 / 777). Sinon, elle est imposable et couverte par l'abattement majoré.
- **Socialement**, l'abattement JA est **réintégré** dans l'assiette MSA depuis 2026.
- **Pour Lyvre** : date d'octroi, échéance des 60 mois, calcul par tranches, lien avec l'exercice d'inscription de la DJA, report extra-comptable par associé JA (en GAEC ou EARL, l'abattement est calculé sur la quote-part de l'associé JA).

### 3.4 Provisions spécifiques

- **Provision pour hausse des prix interdite** aux exploitants agricoles (art. 72 C).
- **Provision pour augmentation de la valeur des stocks de vaches laitières et allaitantes** (art. 73 A ; LF 2025 et LF 2026 ; exercices clos du 01/01/2024 au 31/12/2028) :
  - **Champ.** Exploitants au réel n'ayant pas opté pour 72 B bis, pour les vaches **en stock**, non immobilisées.
  - **Montant.** La hausse de valeur entre l'ouverture et la clôture, par catégorie (laitières, allaitantes), dans la limite de **15 000 €** par exercice (× associés, max 4, en GAEC ou EARL non IS).
  - **Sans contrat pluriannuel EGALIM** à la clôture : montant et plafond minorés de 10 % (exercice clos en 2025), **20 % (2026)** et 25 % (depuis 2027).
  - **Reprise.** À la sortie d'un animal, on reprend la provision ÷ nombre d'animaux en stock, provisions les plus anciennes d'abord. Pas de reprise si la valeur du stock est maintenue, si l'animal est remplacé avant la clôture ou le dépôt, ou en cas d'abattage administratif.
  - **Reprise au plus tard au 6e exercice**, exonérée si le nombre ou la valeur du stock a augmenté.
  - Exclusive de la déduction de l'art. 70 de la LF 2024 ; de minimis.
  - **Compte** : 14x provision réglementée (dotation 6872 / reprise 7872).
  - **Lyvre** : registre par exercice d'origine, effectifs, valeurs, imputation FIFO, contrôle des plafonds.
- **À-valoir social** (art. 72 F). L'à-valoir MSA (L.731-22-1 CRPM) est déductible l'année de versement. S'il n'est pas versé à la clôture, il est déductible dans la limite de 20 % de la hausse du résultat, à condition d'être versé dans les 6 mois et avant le dépôt. Il est réintégré dans l'assiette sociale.
- **IJ AT-MP des exploitants** (art. 72 A bis) : exonérées à 50 %.

### 3.5 Revenus accessoires (art. 75 ; 75 A abrogé)

- **Règle.** Les recettes **BIC et BNC accessoires** (agritourisme, travaux pour tiers, négoce, photovoltaïque et éolien depuis l'abrogation du 75 A au 01/01/2018, etc.) peuvent être incluses dans le BA si, en moyenne sur les **3 années civiles précédant l'ouverture de l'exercice**, elles ne dépassent **ni 50 % des recettes agricoles, ni 100 000 €**.
  - Montants **TTC, remboursements de frais inclus**.
  - Les 3 premières années d'activité : appréciation sur l'année civile précédente.
  - Recettes des sociétés non IS dont l'exploitant est membre : non prises en compte.
  - GAEC : 100 000 € × associés (max 4).
  - Application aux exercices clos jusqu'au **31/12/2028**, prorogation LF 2026.
- **Conséquences.**
  - Ces revenus n'ouvrent droit ni à la DEP, ni à l'abattement JA, ni à l'étalement 75-0 A.
  - Leurs déficits ne s'imputent pas sur le revenu global.
  - Non cumulable avec le micro-BIC (50-0) ni le micro-BNC (102 ter).
- **En société civile** (SCEA, GFA, EARL, GAEC), le dépassement entraîne l'**assujettissement à l'IS** (art. 206-2) [CSOEC-SOC]. C'est un **contrôle critique**.
- **Lyvre** : tag « activité accessoire BIC/BNC » sur les comptes et analytiques de produits, calcul des ratios sur 3 ans glissants (TTC), alerte de dépassement, ventilation BA / BIC dans le résultat fiscal.

### 3.6 Plus-values professionnelles (art. 151 septies, 151 octies, 238 quindecies)

- **Régime général.** Les plus-values sont exonérées si l'activité est exercée depuis au moins 5 ans et que les recettes ne dépassent pas certains seuils. Pour les **activités agricoles** (seuils relevés par la LF 2024), la pratique cite **[À VALIDER]** :
  - exonération **totale** si recettes ≤ **350 000 €** ;
  - exonération **partielle** jusqu'à **450 000 €**.
- **Cession à un jeune agriculteur** (LF 2025, art. 70) : exonération totale jusqu'à **450 000 €** ; seuil de l'exonération partielle **[À VALIDER]**, 550 000 € probable.
- **Seuils LF 2026.** Ils sont inchangés par rapport à 2025 (agriculture.gouv.fr).
- **Appréciation des recettes :**
  - opérations à façon ×3 (art. 69 VI) ;
  - en société civile agricole non IS, appréciation au niveau de chaque associé, selon sa quote-part de recettes (art. 70) ;
  - matériels roulants liés à la DEP exclus (73 II-4).
- **Échanges de terres** (art. 72 E). La plus-value est différée, et le prix et la date d'origine sont conservés.
- **Terres et peuplements forestiers non professionnels** (art. 76 A) : régime des plus-values privées.
- **Lyvre** : registre des immobilisations avec la date d'affectation, le régime court/long terme (amortissements / > 2 ans), le calcul 151 septies paramétré, et l'indicateur « terres inscrites au bilan », qui est une option de l'exploitant [CSOEC-OBL].

### 3.7 Aides PAC : rattachement fiscal

- **Au réel**, les aides sont rattachées à l'exercice où le **droit est acquis** (créance certaine dans son principe et son montant). Cela concerne en pratique les aides découplées de la campagne N, dont l'acompte est versé en octobre N et le solde en décembre N ou plus tard **[À VALIDER]** : doctrine BOI-BA-BASE-20-10-20.
- **En micro**, les aides sont des recettes l'année d'**encaissement**, sauf les ICHN et les subventions d'équipement, qui sont exclues.
- **Subventions d'équipement** : 131 / 139, réintégration au rythme de l'amortissement (art. 42 septies).
- **Indemnités d'assurance climatique** : art. 72 B (voir 3.2).
- **Lyvre** : nature de l'aide → compte 74x ou 131 ; date d'acquisition du droit (campagne) ou date d'encaissement ; génération de la créance à la clôture pour les aides acquises non encaissées (RS : créances constatées à la clôture).

### 3.8 Crédits d'impôt agricoles

- **Crédit d'impôt agriculture biologique** (art. 244 quater L). Il faut ≥ 40 % des recettes issues de l'AB. Montant : 4 500 €/an, avec transparence GAEC. La LF 2026 l'a prorogé, et il fonctionne comme crédit d'impôt depuis le 01/01/2026, avec régularisation juridique prévue en LF 2027. Le montant final (4 500 € ou 6 000 €, ce dernier voté en 1re lecture) et l'échéance (2027 ou 2028) sont **[À VALIDER]**.
- **Crédit d'impôt HVE** (certification haute valeur environnementale). Prorogé par la LF 2026 (agriculture.gouv.fr) ; montant **[À VALIDER]** (2 500 € à l'origine).
- **Crédit d'impôt remplacement pour congés** (art. 200 undecies). 60 % des dépenses de remplacement, dans une limite de 14 jours. Une hausse à 100 % pour les 17 premiers jours, puis 75 %, avait été proposée au PLF 2026 ; adoption **[À VALIDER]**.
- **Crédit d'impôt haies** (4 500 €) : réintroduit par amendement au PLF 2026 ; adoption **[À VALIDER]**.
- **Lyvre** : calculateur ou formulaire 2079-xx (crédit bio : ratio de recettes AB), comptabilisation (créance 444 / produit 699 ou 7x selon le régime IR/IS), répartition par associé en société transparente.

### 3.9 Autres règles d'assiette

- **Petits frais en espèces et barème carburant** : réel simplifié uniquement (art. 74 c, d).
- **Bois et forêts** (art. 76). Le BA forestier est égal au revenu cadastral. Des régimes de faveur s'appliquent aux plantations et à la futaie irrégulière. Le crédit carbone « label bas-carbone » suit le même régime. Ces données sont **hors comptabilité** de l'exploitation, mais à prévoir comme état annexe si un client a des bois.
- **Bail à portion de fruits ; changement d'exploitant** (art. 77, version abrogée) : à ignorer.

---

## 4. TVA agricole

### 4.1 Champ et régimes

- **Remboursement forfaitaire agricole, RFA** (art. 298 quater). Exploitants **non assujettis** :
  - **Seuil.** Moyenne des recettes ≤ **46 000 €** sur 2 années civiles consécutives ; GAEC : × nombre d'associés, par exemple 138 000 € pour 3 associés.
  - **Principe.** L'exploitant ne facture pas de TVA et ne déduit rien. Il demande un remboursement forfaitaire calculé sur les ventes à des **assujettis**, à l'export et en livraisons intracommunautaires.
  - **Taux** : **5,59 %** pour le lait, les animaux de basse-cour, les œufs, les animaux de boucherie et de charcuterie, les céréales et les oléo-protéagineux ; **4,43 %** pour les autres produits.
  - **Déclaration.** Formulaire **3520-SD**, avec les **attestations d'achats annuelles** des clients. À déposer **au plus tard le 31/12 de l'année suivant celle de naissance du droit** (dépôt conseillé avant le 1er mars).
  - **Exclusions.** Ventes selon des usages commerciaux (magasin, marchés avec personnel, produits transformés…) et certaines ventes d'animaux vivants à des particuliers.
  - **Compte.** **741 Remboursement forfaitaire de TVA**.
- **Régime simplifié de l'agriculture, RSA** (art. 298 bis, 1693 bis). Il est **obligatoire** au-delà de **46 000 € HT** de moyenne sur 2 années consécutives [CSOEC-OBL]. Il l'est aussi, quel que soit le CA, pour certaines activités et formes : marchands de bestiaux, sociétés commerciales, coopératives… (art. 298 bis III) **[À VALIDER : liste exacte]**. Il est accessible sur option en deçà, pour une durée **[À VALIDER]** (3 ou 5 ans).
- **Activités non agricoles** (BIC accessoires, etc.). Elles relèvent du régime de droit commun, avec un secteur distinct **[À VALIDER : tolérance des recettes accessoires < 50 000 € intégrées au RSA]**.
- **Suppression du RSI TVA au 01/01/2027** (LF 2025, art. 38). **Le RSA n'est pas concerné.** L'avis impots.gouv.fr du 22/09/2026 le dit explicitement : « La mesure ne s'applique pas au régime simplifié de l'agriculture (RSA) » et « Le régime de TVA applicable aux exploitants agricoles est inchangé ». En revanche, les **activités accessoires non agricoles** d'un exploitant qui relevaient du RSI basculent au réel normal : CA3 trimestrielle si CA ≤ 1 M€, sinon mensuelle. C'est à prévoir pour les secteurs distincts.

### 4.2 RSA : déclarations et paiement (art. 1693 bis ; ann. IV art. 39 ; BOI-TVA-SECT-80-30-60-20)

**Système A, de droit commun : acomptes trimestriels et déclaration annuelle**
- **Échéances.** Acomptes au plus tard les **5 mai, 5 août, 5 novembre et 5 février N+1**, avec le **bulletin 3525 bis**. Le bulletin indique le CA du trimestre, l'acompte et le taux principal.
- **Montant.** Chaque acompte est **au moins égal à 1/5 de l'impôt dû au titre de l'année précédente** (ou du dernier exercice). La somme des 4 acomptes vaut donc 80 %, le solde est payé avec la déclaration annuelle.
- **Dispense.** Pas d'acomptes si l'impôt de l'année précédente, avant déduction de la TVA sur immobilisations, est **< 1 000 €** (art. 1693 bis I, al. 3).
- **Nouveaux assujettis.** Ils fixent eux-mêmes leurs acomptes la 1re période, chacun devant représenter plus de 70 % de l'impôt réel du trimestre (art. 1693 bis II). Certaines sources citent « 70 % » pour tous les acomptes ; c'est une confusion.
- **Suspension.** Possible si les acomptes déjà versés couvrent l'impôt de l'année. Il faut alors déposer des bulletins « 0 ». Si l'impôt final dépasse les acomptes de **plus de 30 %**, s'appliquent l'intérêt de retard (1727) et la majoration (1731).
- **Déclaration annuelle 3517-AGR-SD (CA12A).** Au plus tard le **2e jour ouvré suivant le 1er mai N+1**, même en cas de cessation.
- **Option pour l'exercice comptable** (CA12AE, art. 298 bis I-1° ; ann. II art. 260 J). Déclaration avant le **5 du 5e mois** suivant la clôture. Acomptes les 5 février, mai, août et novembre, rattachés selon le tableau du BOFiP (période intercalaire). Option à formuler avant le début du premier exercice concerné.
- **GAEC.** Un seul bulletin pour le groupement.

**Système B, sur option : déclarations trimestrielles ou mensuelles (« régime de l'effectif »)**
- **Forme.** Option **quinquennale**, reconduite tacitement, sur déclarations **CA3 (3310-CA3)**. L'**exercice TVA coïncide alors avec l'année civile** [CSOEC-OBL].
- **Option mensuelle.** Par lettre recommandée. Effet au 01/01 N si elle est notifiée avant la date limite de la CA12A (≈ 5 mai N), avec une déclaration récapitulative depuis janvier. Sinon, effet au 01/01 N+1.
- **Renonciation.** Avant le 31 janvier pour le mensuel, et avant le 5 février pour le trimestriel, l'année du retour à l'annuel.
- **Contrainte.** Option non ouverte aux exploitants sous le régime de l'art. 298 bis A **[À VALIDER : régime forfait-ristourne, très résiduel]**.
- **Dates de dépôt des CA3 agricoles.** Selon le BOFiP 2014 (mensuel), entre le 15 et le 24 du mois suivant. Sur la page impots.gouv.fr des remboursements, les déclarations trimestrielles RSA sont déposées les « 5 mai, 5 août, 5 novembre ». Calendrier exact du trimestriel agricole **[À VALIDER]**.

**Remboursement des crédits de TVA en RSA** (impots.gouv.fr, page « Remboursement de crédit de TVA »)

| Situation | Seuil | Calendrier | Formulaire |
|---|---|---|---|
| Annuel, régime des acomptes | ≥ **150 €** | Avec la CA12A (2e jour ouvré après le 1er mai) ou CA12AE (5e jour du 5e mois après la clôture) | 3517-AGR |
| Annuel, déclarations trimestrielles | ≥ 150 € | Avant le 5 février N, avec la déclaration du 4e trimestre | 3519 |
| Annuel, déclarations mensuelles | ≥ 150 € | En janvier N, avec la déclaration de décembre | 3519 |
| **Trimestriel**, option trimestrielle | ≥ **760 €** | 5 mai, 5 août ou 5 novembre | 3519 |
| Mensuel, option mensuelle | ≥ 760 € | Chaque mois | 3519 |
| **Régime des acomptes trimestriels** | — | **Aucun remboursement infra-annuel** | — |

Corollaire : un exploitant qui investit beaucoup a intérêt à opter pour le trimestriel ou le mensuel. Lyvre devrait le signaler.

**Télédéclaration et télépaiement** obligatoires. Majoration de 0,2 % en cas de non-recours aux procédures électroniques [CSOEC-OBL].

### 4.3 Livres TVA obligatoires au RSA [CSOEC-OBL]

- **Livre des ventes** : ventilation des encaissements entre opérations exonérées, acquisitions intracommunautaires, exportations et opérations imposables, avec la **répartition par taux**.
- **Livre des achats** : acquisitions et taxes ventilées entre **immobilisations** et **autres achats**. **Tous les achats** y figurent, y compris ceux qui n'ouvrent pas droit à déduction.

### 4.4 Taux applicables aux produits agricoles

Synthèse **[À VALIDER intégralement]** ; les sources BOFiP consultées sont en partie archivées (CGI art. 278-0 bis A, 278 bis, 279 ; BOI-TVA-LIQ-30-10-20 / 30).

| Taux | Produits ou opérations (indicatif) |
|---|---|
| **5,5 %** | Produits destinés à l'**alimentation humaine** : lait, œufs, viandes, fruits et légumes, céréales et farines alimentaires, miel… (278-0 bis A). **Animaux vivants de boucherie et de charcuterie** : le BOFiP récent indique 5,5 % lorsqu'ils sont destinés à l'alimentation humaine, des versions plus anciennes indiquent 10 %, **point à trancher**. Produits à double usage humain/animal (lait, farine de blé) : 5,5 %. |
| **10 %** | Produits d'origine agricole, de la pêche, de la pisciculture et de l'aviculture **non transformés** et non destinés à l'alimentation humaine : fleurs, plants, laine, cuirs bruts, paille, **bois de chauffage**… (278 bis 3°). **Aliments du bétail** pour animaux de rente (278 bis 4°). Engrais et phytos **utilisables en agriculture biologique** **[À VALIDER]**. Certains travaux agricoles et forestiers **[À VALIDER]**. |
| **20 %** | **Vins et alcools**. **Équidés** hors boucherie (depuis 2013). Aliments pour animaux de compagnie. **Engrais, amendements et produits phytopharmaceutiques** hors usage AB (depuis 2014) **[À VALIDER]**. Matériel. Prestations de services de droit commun. Produits transformés non alimentaires. |

**Pour Lyvre** : table « nature de produit agricole → taux TVA par défaut » datée, avec contrôle de cohérence entre compte de vente (7011 / 7012 / 7014 / 7013) et taux. Exemple d'alerte : vin vendu à 5,5 %.

### 4.5 Ce que Lyvre doit implémenter (TVA)

- **Paramètre TVA de l'entité** : non assujetti (RFA) / RSA acomptes / RSA trimestriel / RSA mensuel / réel normal (secteur non agricole) ; exercice TVA civil ou comptable ; dates d'option et d'échéance quinquennale.
- **RFA** :
  - suivi des ventes éligibles par client assujetti et par taux (5,59 / 4,43) ;
  - collecte des attestations d'achats ;
  - calcul et export du 3520-SD ;
  - comptabilisation en 741 (créance 44x, produit 741) ;
  - contrôle du seuil de 46 000 € sur 2 ans, avec alerte de passage obligatoire au RSA.
- **RSA acomptes** :
  - calcul automatique de l'acompte minimal (1/5 de l'impôt N-1) ;
  - échéancier 5/05, 5/08, 5/11, 5/02 ;
  - bulletin 3525 bis ;
  - dispense < 1 000 € ;
  - simulation de suspension, contrôle de l'écart > 30 % ;
  - **CA12A (3517-AGR)** annuelle à partir des livres, avec imputation des acomptes, crédit remboursable ≥ 150 €, version CA12AE pour un exercice décalé et périodes intercalaires.
- **RSA effectif** : réutiliser le moteur CA3 existant de Lyvre (mensuel, et trimestriel à ajouter), avec demande de remboursement 3519 (seuils 760 € / 150 €).
- **Livres** : livre des ventes (ventilation exonéré / intracommunautaire / export / taxable × taux) et livre des achats (immobilisations / autres, y compris non déductibles).
- **Comptabilité de trésorerie (RS) et TVA.** Les livraisons de biens restent exigibles à la livraison. Les écritures « encaissement » doivent donc pouvoir porter la TVA due à la date de livraison : rapprochement de facture **[À VALIDER : tolérances de l'exigibilité en RSA]**.

---

## 5. Cotisations sociales MSA des non-salariés agricoles (NSA)

- **Réforme de l'assiette au 01/01/2026** (alignement sur les travailleurs indépendants, CSS L.131-6 ; CRPM L.731-14 s. ; décret du 25/07/2025 **[À VALIDER : références]**). L'assiette est **unifiée** pour les cotisations et la CSG/CRDS (fin de l'assiette « super-brute »). Calcul :
  1. Partir du **résultat fiscal BA**.
  2. **Réintégrer** les dispositifs fiscaux non admis socialement :
     - blocage des stocks à rotation lente (72 B bis) ;
     - **à-valoir social** (72 F) ;
     - **abattement JA** (73 B) ;
     - **DEP**, et DPI/DPA en cours ;
     - cotisations sociales personnelles et CSG déductible (logique « super-brute » neutralisée) **[À VALIDER]**.
  3. Appliquer un **abattement forfaitaire de 26 %**, encadré par un plancher (1,76 % du PASS) et un plafond (130 % du PASS).
  4. **Exclusions maintenues** : DJA, plus-values exonérées, indemnités d'abattage.
- **Dividendes.** En société IS, les dividendes des NSA au-delà de 10 % du capital, des primes et des comptes courants restent dans l'assiette.
- **Options d'assiette maintenues** :
  - **moyenne triennale** (N-3, N-2, N-1), de droit commun ;
  - **annuelle N-1**, sur option ;
  - assiette forfaitaire pour les nouveaux installés ;
  - régime transitoire 2026-2027 : assiette reconstituée à partir des revenus 2023 et 2024.
- **Déclaration des revenus professionnels (DRP).** Annuelle, au printemps : campagne 2026 sur les revenus 2025, par télédéclaration MSA. La réforme prévoit un **formulaire unique** fiscal et social. Date limite et calendrier de mise en œuvre de ce formulaire **[À VALIDER]** (fixés par caisse). Sans déclaration : **taxation provisoire sur une assiette forfaitaire « sanction »**, puis régularisation.
- **Recouvrement :**
  - **appels provisionnels** sur les derniers revenus connus (1er appel ≈ fin mars, environ 30 % des cotisations ; 2e appel ≈ juin) ;
  - **émission annuelle** et régularisation au plus tard fin novembre (exemple MSA Côtes Normandes 2026 : 2e appel le 25/06, solde 2025 le 25/11) ;
  - **prélèvement mensuel** sur option ;
  - les dates sont fixées par chaque caisse.
- **Cotisations dues** : AMEXA (maladie), IJ AMEXA, AVI / AVA (retraite de base), RCO (complémentaire), ATEXA (AT-MP, forfaitaire), PF (prestations familiales), CSG/CRDS, formation (VIVEA). Barème annuel MSA. La retraite de base est calculée sur les 25 meilleures années depuis 2026.
- **Cotisations de solidarité** pour les petites exploitations sous le seuil d'assujettissement (AMA / SMA).
- **Comptabilisation** :
  - exploitant en EI : 646 « Cotisations personnelles de l'exploitant » (PCG) ; 4311 MSA ;
  - salariés : 6451 « Cotisations MSA » ;
  - la **CSG/CRDS non déductible** (2,4 % + 0,5 %) est réintégrée fiscalement ;
  - l'à-valoir est à suivre distinctement.
- **Pour Lyvre** :
  - **état « assiette sociale MSA »** : du résultat fiscal BA aux réintégrations, puis à l'abattement de 26 % borné ; par associé exploitant en société ; calcul triennal ou N-1 selon l'option ;
  - aide à la DRP ;
  - échéancier des appels (paramétrable par caisse) ;
  - ventilation des cotisations payées : déductible / CSG non déductible ;
  - pas de calcul de cotisations définitif, car il dépend du barème et des taux propres à la caisse.

---

## 6. Obligations comptables générales

### 6.1 Livres et pièces

| Régime | Obligations | Texte |
|---|---|---|
| Micro-BA | Document détaillant jour par jour les recettes professionnelles ; factures et pièces des recettes | CGI 64 bis IV |
| Réel simplifié | Livre-journal recettes/dépenses (**comptabilité de trésorerie**) ; créances et dettes à la clôture ; livre d'inventaire (compte simplifié du résultat fiscal, tableau des immobilisations et amortissements) ; bilan simplifié ; pièces des recettes, dépenses et stocks | CGI 74, 74 A ; [CSOEC-OBL] |
| Réel normal | Livre-journal au jour le jour, grand livre, livre d'inventaire (inventaire, bilan, compte de résultat), pièces ; **comptabilité d'engagement** | C. com. L.123-12 s. ; CGI 72 ; [CSOEC-OBL] |
| Sociétés tenues d'établir des comptes annuels | Comptes annuels selon l'ANC 2020-04, dépôt au greffe (sociétés commerciales) | ANC 2020-04 ; C. com. |

- **Conservation.** 10 ans pour les livres et pièces comptables (C. com. L.123-22) ; 6 ans pour le droit de communication et de contrôle fiscal (LPF L.102 B).
- **Exercice.** 12 mois en principe (voir 1.3).

### 6.2 FEC (LPF L.47 A ; art. A.47 A-1)

- Obligatoire pour tout contribuable **tenant une comptabilité informatisée** soumis à un contrôle, BA réel compris.
- **Point spécifique.** Les titulaires de BA ou de BNC qui tiennent une **comptabilité de trésorerie** (BA au réel simplifié, art. 74 a) relèvent du **II de l'art. A.47 A-1**. Leur FEC a une structure propre : champs supplémentaires de date de règlement, mode de règlement, nature de l'opération et identifiant client **[À VALIDER : liste et ordre exacts des champs]**.
- **Lyvre** génère déjà un FEC PCG. Il faut ajouter la **variante « trésorerie BA/BNC »**, sélectionnée par le régime de l'entité.

### 6.3 Facturation électronique et e-reporting (CGI art. 289 bis, 290 ; réforme 2024-2027)

**Calendrier** (inchangé ; aucune dérogation sectorielle agricole) :
- **01/09/2026** : **réception** obligatoire pour **tous les assujettis**, exploitants au RSA ou au réel inclus. Émission et e-reporting obligatoires pour les grandes entreprises et les ETI.
- **01/09/2027** : **émission** et **e-reporting** pour les PME, TPE et micro-entreprises, donc la quasi-totalité des exploitations assujetties.

**E-reporting** :
- ventes B2C (vente directe à la ferme, marchés) et opérations internationales ;
- données de paiement pour les prestations de services ;
- **périodicité** liée au régime TVA. Après la suppression du RSI, l'avis DGFiP prévoit : mensuel pour le réel normal trimestriel, par décade pour le réel normal mensuel. Pour le RSA, une source sectorielle indique un rythme **mensuel** **[À VALIDER : périodicité RSA dans le décret]**.

**Exploitants au RFA.** Non assujettis à la TVA, ils sont a priori **hors du champ de l'obligation d'émission**. Les sources divergent sur la réception et sur le traitement de leurs flux **[À VALIDER — point important]**.

**Autofacturation.** Elle est très courante : coopératives, négociants et laiteries émettent les factures au nom du producteur (mandat, art. 289 I-2 CGI). Lyvre doit :
- accepter des **autofactures reçues** via la plateforme agréée comme **factures de vente** du producteur, avec acceptation ou contestation ;
- gérer les mentions obligatoires (« autofacturation ») ;
- traiter les **décomptes de coopérative** : apports, acomptes, compléments de prix, ristournes, parts sociales retenues.

**Mentions nouvelles** : SIREN du client, adresse de livraison, nature (biens / services / mixte), option de paiement de la TVA d'après les débits, etc.

**Lyvre** :
- adapter le Factur-X existant (profils, codes TVA agricoles 5,5 / 10 / 20, RFA « non assujetti ») ;
- connecteur PA (plateforme agréée) ;
- e-reporting B2C agrégé par jour et par taux pour la vente directe ;
- gestion des autofactures.

### 6.4 Autres

- **CFE.** Les activités agricoles en sont **exonérées** (CGI 1450) ; les activités accessoires BIC non. **[À VALIDER]** pour l'agritourisme.
- **IS des sociétés agricoles.** Acomptes 15/03, 15/06, 15/09, 15/12 ; solde au 15 du 4e mois (2572) [AGIRIS]. Seuils RSI/RN IS applicables aux sociétés agricoles **[À VALIDER]**.

---

## 7. Synthèse des fonctionnalités à développer (vue logiciel)

| Domaine | Données | Calculs | États | Contrôles |
|---|---|---|---|---|
| Paramétrage | Forme, IR/IS, régime BA, régime TVA, options datées, associés (exploitant, JA, % droits), nombre d'associés exploitants | Moyennes triennales et biennales, multiplicateurs GAEC, ×3 façon | Fiche fiscale de l'entité, échéancier des options | Incompatibilités de régime (69 C, 69 D, 69 E), dates de renonciation |
| Plan et états | Référentiel ANC 2020-04 complet | Mapping des postes | Bilan, compte de résultat, annexe agricoles ; tableau des biens vivants ; 2139 A-E / 2143 (2144-2154) ; 2033 / 2050 si IS | Comptes 472 soldés ; cessions de biens vivants en 757 / 657 |
| Biens vivants | Lots (espèce, âge, têtes), nature 241 / 243 / 246 / 247, en-cours 234x | Amortissements, dépréciations, mise en service, cessions et mortalité | Tableau des immobilisations biologiques | Animal destiné à la vente en 24x |
| Stocks et avances aux cultures | Inventaire quantités, barèmes, cours du jour, fiche culture | Coût standard, prix de détail avec décote, forfait fiscal, art. 72 A, variation 713x | Inventaire valorisé, double valeur comptable et fiscale | Méthode interdite (prix de détail sur avances aux cultures) |
| Dispositifs fiscaux | Registres DEP, provision 73 A, DPI/DPA historiques, 75-0 A, 75-0 D, DJA | Plafonds DEP, ratio d'épargne, VA, 73 B par tranches, 73 A plafonné et minoré, reprises FIFO | Tableau de passage résultat comptable → fiscal (2139 B / 2143 « extra-comptable ») ; répartition par associé | Échéances (10e exercice, 6e exercice, 60 mois JA), défaut d'épargne |
| Accessoires | Tag des comptes BIC / BNC | Ratio 50 % / 100 000 € sur 3 ans TTC | Ventilation BA / BIC | **Alerte d'IS forcé** en société civile |
| PAC | Nature de l'aide, campagne, date du droit | Créance à la clôture | Tableau des aides | Mapping 74x et 131 |
| TVA | RFA / RSA / options, acomptes | Acomptes 1/5, dispense < 1 000 €, CA12A / CA12AE, CA3, 3519, 3520 RFA | Livres des ventes et achats, 3525 bis, 3517-AGR, 3520 | Seuil de 46 000 €, écart > 30 %, taux par nature |
| MSA | Option triennale ou N-1, associés NSA | Assiette réformée 2026 | Aide à la DRP, échéancier | — |
| Obligations | Régime de comptabilité (trésorerie ou engagement) | — | FEC PCG ou FEC trésorerie BA (A.47 A-1 II) ; livre des recettes micro | — |
| E-facturation | Statut assujetti / RFA, mandats d'autofacturation | — | Factur-X, e-reporting B2C | Réception au 01/09/2026, émission au 01/09/2027 |

---

## 8. Incertitudes et points à faire valider par un expert-comptable

1. **Millésime d'application des seuils de l'art. 69 et 71** (129 200 / 421 000 / 517 000 €, décret 2026-562 en vigueur le 01/07/2026), par rapport aux 120 000 / 391 000 / 480 000 € encore cités début 2026. Quelle période triennale et quelle année d'imposition ?
2. **Seuils de l'abattement JA** (art. 73 B) : 50 700 / 67 600 € dans le CGI, contre 58 552 € dans la brochure CSOEC 2026. Date d'application du décret 2025-547.
3. **Barème DEP 2026** (33 287 € … 51 040 €) : vérifier qu'il s'agit bien de l'actualisation applicable aux exercices clos en 2026. Vérifier aussi la date de fin du dispositif après la LF 2026 (31/12/2028 ?).
4. **Taux de décote de la méthode forfaitaire** des stocks (art. 74 b ; −20 % / −30 %) et articles de l'annexe III correspondants.
5. **Classement fiscal des animaux reproducteurs** (option stock ou immobilisation) face à l'obligation comptable d'immobiliser de l'ANC 2019-01. Traitement des divergences et du passage de l'ancien au nouveau.
6. **Racine des comptes 2341-2347** (231 ou 234) dans le texte ANC 2020-04, et numérotation des articles du PCG issus du règlement 2019-01.
7. **Mapping des aides PAC** (aide au revenu de base, redistributif, éco-régime, couplées, ICHN, MAEC, bio) vers 742-748, et règle fiscale de rattachement (droit acquis) au réel.
8. **Traitement comptable des DPB** (incorporel amortissable ou non, dépréciation).
9. **Taux de TVA** :
   - animaux vivants de boucherie (5,5 % ou 10 %) ;
   - engrais et phytos (20 %, ou 10 % s'ils sont utilisables en AB) ;
   - travaux agricoles et forestiers ;
   - bois de chauffage ;
   - liste des opérations exclues du RFA.
10. **RSA** :
    - durée de l'option pour le RSA en deçà de 46 000 € ;
    - liste des assujettis obligatoires (art. 298 bis III) ;
    - calendrier exact des CA3 trimestrielles agricoles ;
    - traitement TVA des recettes accessoires non agricoles (secteur distinct, tolérance) ;
    - impact de la suppression du RSI (01/01/2027) sur ces secteurs.
11. **E-invoicing des exploitants au RFA** (obligation de réception, e-reporting) et **périodicité d'e-reporting** des exploitants au RSA.
12. **Seuils 151 septies agricoles** (350 000 / 450 000 € ; cession à JA 450 000 / 550 000 €) et maintien en 2026.
13. **Crédits d'impôt 2026** : bio (4 500 ou 6 000 €, échéance 2027 ou 2028), HVE (montant, durée), remplacement (60 % ou 100 / 75 %), haies. Le texte promulgué de la loi 2026-103 est à relire.
14. **Assiette MSA réformée** :
    - liste exacte des réintégrations ;
    - plancher et plafond de l'abattement de 26 % ;
    - régime transitoire 2026-2027 ;
    - date de mise en place du formulaire unique fiscal et social ;
    - dates limites de la DRP par caisse.
15. **Structure du FEC « comptabilité de trésorerie » BA** (A.47 A-1 II) : champs et ordre exacts.
16. **Formulaire 2342** : son usage actuel (sociétés BA ?) n'a pas pu être confirmé. Vérifier aussi la liste à jour des annexes 2139 / 2143 pour le millésime 2026.
17. **Sociétés agricoles à l'IS** : seuils RSI / RN IS applicables. L'ANC 2020-04 est-il obligatoire pour une EARL ou une SCEA à l'IS ou au réel normal (obligation légale de comptes annuels) ?
18. **Exigibilité de la TVA** en comptabilité de trésorerie au RSA (livraisons de biens) et tolérances éventuelles.
19. **CFE** des activités accessoires (agritourisme, photovoltaïque) et exonération agricole (art. 1450).
