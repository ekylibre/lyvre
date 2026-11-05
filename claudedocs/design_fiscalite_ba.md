# Conception : lot AG6, fiscalité BA (résultat fiscal et dispositifs)

> **Statut** : **validée** (05/11/2026, AGD23), réponses de l'expert-comptable au § 11 :
> - Q-F1 : répartition sur les parts en **pleine propriété et en usufruit**, aucune sur la nue-propriété ; part des droits aux bénéfices saisissable ;
> - Q-F2 : CSG non déductible saisie depuis l'appel MSA ;
> - Q-F3 : DEP extra-comptable, épargne sur compte repéré, substituts saisis ;
> - Q-F4 : barèmes DEP, JA et 73 A de l'audit confirmés (fiabilité R, expert-comptable 05/11/2026) ;
> - Q-F5 : provision 73 A en **1483 / 6873 / 7873** (guide Isacompta du 23/06/2026 et page boostaferme du 04/11/2026, § 6) ;
> - Q-F6 : formulaires 2026 fournis dans `claudedocs/compta_agricole/liasse_BA/` (hors git) : 2139-SD, bilan simplifié et annexes, notice 2139 ; 2143-SD, 2144 à 2154 ;
> - Q-F7 : plus-values et crédits d'impôt **dans AG6** (sous-lot g), seuils en paramètres à valider ;
> - Q-F8, Q-F9 : d'accord.
>
> **AG6.a réalisé (05/11/2026, non commité)**. Contenu :
> - tables `tax_results` (instantané figé) et `tax_result_lines` (lignes saisies) ; colonnes `associates.is_operator`, `young_farmer_since`, `profit_share_bp` (migration `c1d3e5f7a9b0`) ;
> - `app/services/tax_result.py` :
>   - résultat comptable de l'exercice, puis lignes de passage ;
>   - **proposées** : écart de valeur fiscale des stocks (AG4.e) ; abattage sanitaire des reproducteurs (exonération indemnité − valeur nette dans l'exercice de l'abattage, réintégration de la part non réinvestie à l'échéance, au prorata non réinvesti, marquées « à valider ») ;
>   - **saisies** : part de la CSG non déductible, autres réintégrations et déductions (motif obligatoire) ;
>   - **répartition** : droits aux bénéfices des statuts s'ils sont saisis pour tous les associés (alerte si le total n'est pas 100 %), sinon parts en pleine propriété et en usufruit à la clôture, rien sur la nue-propriété ; pas de répartition pour une société à l'IS ;
>   - **figé** au premier calcul après la clôture définitive, recalculé si l'exercice est rouvert ;
> - API `/fiscal-years/<id>/tax-result` (GET), `…/tax-result/lines` (POST, DELETE) ; export `/fiscal-years/<id>/tax-result.xlsx` ; fiche associé : exploitant, première aide JA, droits aux bénéfices (plan agricole) ;
> - écran Compta › **Résultat fiscal** (`/tax-result/`).
>
> Écarts avec la conception :
> - les cases de liasse des lignes viendront avec AG6.f ; l'abattement JA et la DEP s'insèrent en AG6.b et AG6.c ;
> - la réintégration de l'abattage sanitaire non réinvesti est proratisée sur l'indemnité (règle à vérifier).
>
> Tests : `tests/api/test_tax_result.py` (4 tests), `frontend/src/features/tax-result/taxResult.test.tsx` (1 test).
>
> **AG6.b réalisé (05/11/2026, non commité)**. Contenu :
> - barème daté `ba.ja.*` dans `data/regulatory/ba.json` (tranches de 50 700 et 67 600 €, taux 75 %, 50 %, 30 %, et 100 % / 60 % l'exercice de la DJA, 60 mois), valable à partir du 01/01/2026, fiabilité R (confirmé par l'expert-comptable le 05/11/2026) ;
> - `app/services/young_farmer.py` :
>   - éligibilité : exercice clos dans les 60 mois suivant l'octroi ;
>   - base : bénéfice après les retraitements, avant la DEP ; quote-part de l'associé en société ;
>   - exercice de la DJA : dossier « dja » d'AG3 dont la décision tombe dans l'exercice ; abattement au moins égal à la DJA, sans dépasser la base ;
>   - bénéficiaires : exploitant individuel (date du profil) ou associés exploitants avec une date JA ; un associé non exploitant avec une date est signalé ;
> - tableau de passage : ligne « Abattement jeune agriculteur » par bénéficiaire, après les retraitements ; la répartition par associé retire l'abattement du seul associé JA ; colonne à l'écran.
>
> Écarts avec la conception :
> - avec plusieurs associés JA l'exercice de la DJA, le minimum « au moins égal à la DJA » n'est pas appliqué (avertissement) ;
> - sans barème à la date de clôture (exercices clos avant le 01/01/2026), pas d'abattement calculé : saisir les seuils antérieurs dans les paramètres réglementaires.
>
> Tests : `tests/api/test_young_farmer.py` (4 tests).
>
> **AG6.c réalisé (05/11/2026, non commité)**. Contenu :
> - barème daté `ba.dep.*` (seuils 33 287 / 61 642 / 92 464 / 123 284 €, taux 30 / 20 / 10 %, plafond 51 040 €, plafond global 150 000 €, part exonérée 30 % dans 50 000 € dont 40 % pour l'aléa économique, épargne 50 %, 10e exercice, fin au 31/12/2028), fiabilité R ;
> - tables `dep_entries`, `dep_movements`, `dep_substitutes`, colonne `bank_accounts.dep_savings` (migration `d2e4f6a8b0c1`) ;
> - `app/services/dep.py` :
>   - **plafond** sur le bénéfice après l'abattement JA : 100 %, puis 30 / 20 / 10 % par tranches, plafond fixe au-delà du dernier seuil ; × associés exploitants (4 au plus), sans dépasser le bénéfice ; au prorata de la durée de l'exercice ; dans la marge du plafond global ;
>   - **déduction** de l'exercice (refusée au-delà du plafond), ligne de passage − ;
>   - **registre** : DEP par exercice, anciennes DEP, DPI et DPA reprises avec leur année d'origine ; utilisations (réintégrées dans l'exercice, 30 % exonérés en cas d'aléa, dans les plafonds) et réintégrations ; **réintégration proposée au 10e exercice** ;
>   - **épargne** : comptes bancaires repérés (solde à la clôture et à 6 mois) et substituts saisis ; ratio de 50 % ; **après le délai de 6 mois** seulement, défaut d'épargne et réintégration proposée de la fraction qui excède le double de l'épargne (à valider) ;
>   - **valeur ajoutée** (produits 70 à 74 − comptes 60 à 62) comparée aux moyennes des 3 exercices précédents et des 3 exercices clos avant le précédent (baisse de plus de 10 % ou de 15 %) ;
> - tableau de passage : la DEP s'applique après l'abattement JA et se répartit entre les associés ; contrôles de clôture : épargne à constituer (information avant le délai), épargne insuffisante (anomalie après), 10e exercice (information) ;
> - API `/fiscal-years/<id>/dep` (GET, PUT), `…/dep/movements`, `…/dep/substitutes`, `POST /dep/history`, `PUT /bank-accounts/<id>/dep-savings` ; section « DEP » de la page Résultat fiscal.
>
> Écarts avec la conception :
> - le 10e exercice se compte sur les exercices présents dans Lyvre (sinon l'année d'origine + 10) ;
> - l'épargne est lue dans la comptabilité (compte du compte bancaire repéré) ; l'intérêt de retard du défaut d'épargne n'est pas calculé.
>
> Tests : `tests/api/test_dep.py` (4 tests).
>
> **AG6.d réalisé (05/11/2026, non commité)**. Contenu :
> - paramètres datés `ba.cow.*` (plafond 15 000 €, exercices clos du 01/01/2024 au 31/12/2028, minoration 0 / 10 / 20 / 25 % selon l'année de clôture, 6 exercices), fiabilité R ;
> - tables `cow_provisions` et `cow_provision_releases`, colonnes `stock_lines.cow_category` (laitières, allaitantes ; animaux seulement) et `fiscal_years.egalim_contract` (migration `e3f5a7b9c1d2`) ;
> - `app/services/cow_provision.py` :
>   - **éligibilité** : réel, pas d'IS, pas d'option 72 B bis en vigueur, période d'application ; rien n'est proposé sans inventaire des vaches à l'ouverture (premier exercice d'élevage) ;
>   - **proposition** : hausse de valeur brute par catégorie sans compensation, plafond × associés exploitants, minoration sans contrat EGALIM (case par exercice) ;
>   - **écriture gérée** `COW_PROVISION` : dotation D 6873 / C 1483 (1483 créé sous 148) et reprises D 1483 / C 7873 dans la même écriture ; annulation tant que l'exercice est ouvert ;
>   - **reprises** : baisse nette d'effectif imputée à la provision la plus ancienne, au prorata de l'effectif de constitution ; aucune reprise si la valeur du stock reste au moins égale à la constitution ; dérogation motivée (sortie sans reprise) ; au 6e exercice, solde réintégré ou exonéré (effectif ou valeur en hausse stricte) ;
>   - **tableau de passage** : l'exonération du 6e exercice est une déduction extra-comptable ;
>   - **contrôles de clôture** : reprises à passer (anomalie), provision possible (information) ;
> - API `/fiscal-years/<id>/cow-provision` (GET, POST `{constitute}`, DELETE), `…/cow-provision/waivers`, `PUT /fiscal-years/<id>/egalim` ;
> - écrans : catégorie de vaches sur la ligne d'inventaire des animaux ; section « Provision 73 A » de la page Résultat fiscal (catégories, EGALIM, reprises prévues, registre, sorties sans reprise).
>
> Écarts avec la conception :
> - les vaches immobilisées mais fiscalement en stock ne sont pas reprises : seules les lignes d'inventaire marquées comptent ;
> - l'exclusion « déduction de l'art. 70 de la LF 2024 sur le même exercice » n'est pas contrôlée ;
> - l'équivalent-subvention de minimis et le tableau de suivi de l'annexe sur 6 exercices sont reportés à AG6.f (liasse et annexe).
>
> Tests : `tests/api/test_cow_provision.py` (3 tests).
>
> **AG6.e réalisé (05/11/2026, non commité)**. Contenu :
> - paramètres datés `ba.spread.*` (25 000 €, 1,5 × la moyenne, 7 parts, art. 75-0 A), fiabilité R ;
> - tables `ba_history_years` (années antérieures à Lyvre : recettes, recettes accessoires TTC, bénéfice) et `income_spreads`, colonne `accounts.ba_income_class` (accessoire, façon) (migration `f4a6b8c0d2e4`) ;
> - `app/services/ba_regimes.py` :
>   - **recettes par année civile** : produits 70 et 74 hors 747, comptes « façon » × 3, comptes « accessoire » à part ; TTC = HT + TVA collectée (4457) de la même écriture au prorata ; la saisie d'une année l'emporte ;
>   - **moyenne triennale et régime** : seuils datés, GAEC × associés (60 % au-delà de 517 000 €), micro interdit aux sociétés créées depuis 1997 sauf EARL unipersonnelle (69 D) ou en cas d'IS, options RS / RN ; régime de plein droit au premier jour suivant l'exercice et alerte de changement ;
>   - **72 E bis** : premier exercice au réel après le micro, créances d'ouverture (41, 441, écriture d'à-nouveaux) × 13 % en réintégration ;
>   - **simulation** : bénéfice forfaitaire contre résultat fiscal (après JA et DEP), ou résultat de trésorerie hors partie double ;
>   - **revenus accessoires** : moyenne TTC des 3 années civiles avant l'ouverture (année précédente seule les 3 premières années), 50 % et 100 000 € (× associés en GAEC, 4 au plus) ; dépassement : IS de plein droit en société civile (anomalie), BIC / BNC sinon ; part accessoire des produits de l'exercice affichée ;
>   - **75-0 A** : bénéfice avant JA (hors étalements) au-delà de max(25 000 €, moyenne des 3 exercices précédents) s'il dépasse 1,5 × la moyenne ; étalement du 1-a dans la limite proposée, du 1-b (abattage) saisi avec motif ; −6/7 l'exercice d'origine puis +1/7 sur les 6 suivants ; exclu avec 72 B bis, et le 1-a avec 75-0 B ;
>   - **historique 75-0 B** : bénéfices des 3 derniers exercices, total et par associé, moyenne ;
>   - contrôles de clôture : changement de régime (information), revenus accessoires (anomalie IS / information BIC), étalement possible (information) ;
> - tableau de passage : lignes 72 E bis et septièmes avant l'abattement JA ;
> - API `/fiscal-years/<id>/ba-regime`, `PUT /ba-history/<année>`, `PUT /accounts/<id>/ba-income-class`, `/fiscal-years/<id>/income-spreads` (GET, POST, DELETE) ;
> - écrans : panneau « Régime des bénéfices agricoles » dans Structure › Fiscalité (moyennes, simulation, accessoires et repérage des comptes, années antérieures) ; section 75-0 A et historique 75-0 B sur la page Résultat fiscal.
>
> Écarts avec la conception, à valider :
> - les recettes « micro » (encaissements) sont estimées par les produits 70 et 74 datés de l'année ; au réel, les recettes sont celles des écritures de l'année civile (exercice décalé signalé) ;
> - les recettes accessoires ne comptent pas dans les seuils de l'art. 69 ; les seuils du réel normal sont aussi multipliés en GAEC ;
> - les créances du 72 E bis se limitent aux comptes 41 et 441 ;
> - la base de l'abattement JA et de la DEP inclut encore les revenus accessoires (la ventilation BA / BIC est seulement affichée) ;
> - le retour au régime inférieur est signalé sans en contrôler les conditions ; la sortie de 75-0 A à la cessation n'est pas traitée.
>
> Tests : `tests/api/test_ba_regimes.py` (7 tests), `frontend/src/features/organization/BaRegimePanel.test.tsx` (1 test).
>
> **AG6.f réalisé (05/11/2026, non commité)**. Contenu :
> - correspondances `data/liasse/2139_2026.json` (cadre B de la 2139, 2139-A bilan, 2139-B compte de résultat et résultat fiscal) et `data/liasse/2143_2026.json` (cadre B de la 2143, 2144 actif, 2145 passif, 2146 et 2146-bis réunis, 2151 détermination du résultat fiscal), cases lues sur les formulaires 2026 fournis (hors git), comptes proposés d'après le plan agricole, **fiabilité I : à valider par l'expert-comptable** ;
> - `app/services/liasse.py` : formulaire selon le régime BA à la clôture (2139 au réel simplifié, 2143 au réel normal, 2139 par défaut avec alerte ; rien au micro-BA ni à l'IS), millésime le plus récent non postérieur ; règles par case : soldes de comptes (modes des états de Lyvre, mouvements pour la TVA), totaux, éléments du tableau de passage (bénéfice ou déficit comptable, réintégrations, déductions, résultat avant JA, JA, DEP, résultat), sinon case à saisir ; contrôles d'équilibre (actif net = passif, résultat du compte de résultat = résultat du bilan) ;
> - API `GET /fiscal-years/<id>/liasse` ; exports `/fiscal-years/<id>/liasse.xlsx` (une feuille par tableau) et `.pdf` (euros arrondis, origine de chaque montant) ;
> - section « Aide à la liasse » de la page Résultat fiscal (tableaux repliables, contrôles, exports).
>
> Écarts et points à valider :
> - la ligne 1 du cadre B n'a pas de code imprimé : repérée « ligne 1 col. 1 / col. 2 » ;
> - cessions : en 2139, 757 / 657 en exceptionnel (FF / FH) ; en 2143, 7571 / 6571 en ventes d'animaux et autres charges (FL / GC, renvois du formulaire), 7578 / 6578 en exceptionnel ;
> - variation d'inventaire des reproducteurs (EF, FS), cotisations obligatoires et facultatives, taxes foncières, effectifs et surfaces, emprunts fonciers : à saisir ;
> - la rémunération de l'exploitant (644) n'est pas réintégrée automatiquement (FM, WB) : à saisir en ligne de passage pour que le résultat fiscal en tienne compte ;
> - non couverts : 2139-C/D/E, 2139-bis et ter ; 2147 à 2150, 2151-bis/ter, 2152 à 2154, colonnes France / Export de la 2146, plus-values (section V de la 2151) ; pas de saisie des cases manuelles dans Lyvre.
>
> Tests : `tests/api/test_liasse.py` (4 tests, dont la cohérence des fichiers de correspondance).
>
> **AG6.g réalisé (05/11/2026, non commité)**. Contenu :
> - paramètres datés `ba.pv.*` (350 000 / 450 000 €, cession à un JA 450 000 / 550 000 €, 5 ans) et `ba.credit.*` (bio 4 500 € et 40 %, remplacement 60 % dans 14 jours), fiabilité I ; crédit HVE `ba.credit.hve.amount_cents` 2 500 € par exploitation, une seule fois, exercices clos jusqu'au 31/12/2026 (source : actualité de la chambre d'agriculture PACA du 30/04/2026 fournie par l'utilisateur ; texte de la LF 2026 et article du CGI à identifier, limites de cumul avec le crédit bio non traitées), fiabilité I ;
> - tables `capital_gain_choices` et `tax_credits` (migration `a5b7c9d1e3f5`) ;
> - `app/services/capital_gains.py` :
>   - **plus-values** par immobilisation cédée ou mise au rebut dans l'exercice : prix − (coût − amortissements) ; moins de 2 ans : court terme ; au-delà, court terme à hauteur des amortissements et long terme au-delà, moins-value à court terme si le bien est amortissable, à long terme sinon ; sorties du registre 75-0 D écartées ;
>   - **lignes de passage** : plus-value nette à long terme retirée du bénéfice, moins-value nette à long terme réintégrée ; sur option, exonération 151 septies de la plus-value nette à court terme ;
>   - **151 septies** : 5 ans d'activité (date saisie, sinon date de création), moyenne des recettes HT (façon × 3) des 2 années civiles précédant la clôture, taux total ou dégressif, seuils JA sur option ; en société non IS, taux par associé sur sa quote-part de recettes (art. 70), taux moyen pondéré ; partie exonérée et partie imposable de la plus-value à long terme affichées ;
>   - **crédits d'impôt** : bio (ratio des recettes bio saisies sur les recettes de l'exercice, × associés exploitants en GAEC), HVE (date de certification), remplacement (dépenses × taux × jours retenus ÷ jours) ; répartition par associé ; à l'IS, écriture D 444 / C 699 indiquée, non passée ;
> - API `/fiscal-years/<id>/capital-gains` (GET, PUT), `/fiscal-years/<id>/tax-credits` (GET), `…/tax-credits/<type>` (PUT, DELETE) ; section « Plus-values professionnelles » et « Crédits d'impôt » de la page Résultat fiscal.
>
> Écarts et points à valider :
> - mesure des recettes 151 septies (années civiles N-2 et N-1) et taux pondéré entre associés ;
> - imputation de la plus-value à long terme (déduite du bénéfice, report en cadre B § 7 / section V de la 2151, non reportés dans la liasse), étalement sur 3 ans de la plus-value à court terme, report des moins-values à long terme : non gérés ;
> - exclusions de l'art. 151 septies (terrains à bâtir, matériels roulants liés à la DEP) non contrôlées ;
> - crédit bio : plafond de minimis non suivi ; crédits haies et autres : non traités.
>
> Tests : `tests/api/test_capital_gains.py` (3 tests).
>
> **Besoins** : `claudedocs/compta_agri.md`, lot AG6 (AG6.1 à AG6.10).
> **Sources** :
> - `audit_reglementation.md` § 1.2, § 1.3 et § 3 : art. 64 bis, 69, 70, 71, 72 E bis, 73, 73 A, 73 B, 73 C, 75, 75-0 A, 75-0 B, 75-0 D, 151 septies ; barèmes « en vigueur au 03/11/2026 », plusieurs marqués **[À VALIDER]** ;
> - réponses d'expert du § 8 : seuils BA de 2026 (129 200 / 421 000 / 517 000 €), plafond JA de 67 600 € depuis le 01/01/2026, DEP jusqu'au 31/12/2028 (Légifrance LEGIARTI000051765352).
> **Règle** : chaque barème est un **paramètre daté et sourcé** (`data/regulatory/ba.json`), surchargeable dans Administration › Paramètres réglementaires. Aucun article n'est cité sans vérification.
>
> **Données fournies par les lots précédents** :
> - écart de valeur fiscale des stocks (AG4.e, `stock_tax.totals`) ;
> - registre des abattages sanitaires (AG5.c) ;
> - subventions d'investissement et DJA (AG3.d) ;
> - micro-BA, livre des recettes et récapitulatif sur 3 ans (AG1.d) ;
> - options datées : moyenne triennale 75-0 B, blocage 72 B bis, IS, régimes ;
> - associés et parts sociales (module Associés).

---

## 1. Ce qui existe et ce qui manque

- **Existe** :
  - seuils BA et revenus accessoires en paramètres (`ba.micro.*`, `ba.normal.*`, `ba.gaec.*`, `ba.accessory.*`) ;
  - récapitulatif et alerte de sortie du micro-BA (`micro_ba.summary`, échéancier) ;
  - profil fiscal daté (régimes BA, IR / IS) ;
  - date d'installation aidée de l'exploitant individuel (`agri_profile.young_farmer_since`) ;
  - parts sociales par associé.
- **Manque** :
  - le **résultat fiscal** et le tableau de passage (aucun calcul extra-comptable) ;
  - sur l'associé : qualité d'**exploitant**, **date d'octroi de la première aide JA**, **part des droits aux bénéfices** si elle diffère des parts (AG0.3) ;
  - un compte bancaire repéré comme **épargne DEP** ;
  - les barèmes DEP, JA, 73 A, et les seuils de plus-values et de crédits d'impôt en paramètres.

---

## 2. Choix structurants

1. **Un résultat fiscal par exercice** (`tax_results`) : résultat comptable (classes 6 et 7), puis lignes de passage.
   - **Réintégrations et déductions extra-comptables**, sans écriture :
     - proposées par Lyvre : DEP, abattement JA, écart de valeur fiscale des stocks, étalement 75-0 A, exonération 75-0 D, part de la CSG non déductible ;
     - ou saisies avec un motif.
   - Le résultat fiscal est **figé** quand l'exercice est clôturé, et il se recalcule tant que l'exercice est ouvert.
2. **Ordre de calcul**, imposé par les textes :
   - résultat comptable ± retraitements (stocks, CSG, plus-values exonérées, 75-0 D, 75-0 A) ;
   - puis **abattement JA** ;
   - puis **DEP** (calculée sur le bénéfice après abattement JA) ;
   - puis le résultat fiscal, réparti par associé.
3. **Répartition par associé** (sociétés soumises à l'IR) : au prorata des **droits aux bénéfices** de chaque associé à la clôture, égaux par défaut à ses parts en **pleine propriété et en usufruit**, la nue-propriété n'en recevant aucune (Q-F1) ; la part se saisit quand les statuts en disposent autrement. L'abattement JA se calcule **par associé JA** sur sa quote-part. Le résultat sert aux 2042 C PRO.
4. **Les dispositifs pluriannuels ont un registre** par exercice d'origine, rapproché à chaque clôture :
   - DEP : montant, épargne, utilisations, réintégrations, échéance ;
   - provision 73 A : dotation, reprises par ancienneté, échéance ;
   - étalement 75-0 A : septièmes restant à imposer.
5. **Pas d'écriture pour l'extra-comptable** ; seule la **provision 73 A** est comptable (provision réglementée).
6. **Pas d'EDI-TDFC** : l'aide à la liasse produit un état « case → montant » à recopier, en PDF et en XLSX (AG6.8).
7. **Au micro-BA**, pas de tableau de passage. Le bénéfice forfaitaire (moyenne des recettes, abattement de 87 %, minimum de 305 €) vient de `micro_ba`, et le simulateur le compare au réel (AG6.2).

---

## 3. Résultat fiscal et tableau de passage (AG6.3)

| Ligne | Origine | Sens |
|---|---|---|
| Résultat comptable | balance de l'exercice | — |
| Écart de valeur fiscale des stocks (forfaitaire, 72 B bis) | AG4.e | ± |
| Exonération de l'indemnité d'abattage sanitaire (indemnité − valeur nette) | AG5.c, exercice de l'abattage | − |
| Réintégration de la part non réinvestie à 2 ans | AG5.c, exercice de l'échéance | + |
| Étalement 75-0 A (revenu exceptionnel ÷ 7) | registre AG6.e | − puis + (septièmes) |
| Part de la CSG non déductible | saisie depuis l'appel MSA, ou proposée (Q-F2) | + |
| Plus-values exonérées (151 septies) | simulation AG6.g, retenue par l'utilisateur | − |
| Autres réintégrations ou déductions | saisies, avec motif | ± |
| **Abattement JA** | AG6.b, par associé JA | − |
| **DEP** de l'exercice / réintégrations | AG6.c | − / + |
| **Résultat fiscal** (bénéfice ou déficit) | | |

- Chaque ligne garde sa **case de liasse** (2139 B ou 2143), alimentée par AG6.f.
- Écran **Compta › Résultat fiscal** (`/tax-result/`, plan agricole, réel) : tableau de passage, détail par associé, liens vers les registres, export.

---

## 4. Abattement jeune agriculteur (AG6.5, art. 73 B)

- **Données** :
  - exploitant individuel : `young_farmer_since` du profil ;
  - associé JA : date d'octroi de la première aide, exercice d'inscription de la DJA (repris du dossier DJA d'AG3, modifiable).
- **Période** : exercices clos dans les **60 mois** suivant l'octroi.
- **Barème daté** (`ba.ja.*`) :
  - 75 % si le bénéfice est au plus 50 700 € ;
  - sinon 50 % jusqu'à 50 700 € et 30 % de 50 700 à 67 600 € ;
  - rien au-delà ;
  - **exercice d'inscription de la DJA** : 100 % jusqu'à 50 700 €, puis 60 % jusqu'à 67 600 €, au moins égal à la DJA.
- **Base** : bénéfice (quote-part de l'associé JA en société), hors profits à taux réduit ; calculé avant la DEP et les déficits.
- Le résultat est une ligne de passage par associé.

---

## 5. DEP (AG6.4, art. 73)

- **Plafond** (barème daté `ba.dep.*`, exercice de 12 mois, proratisé sinon) : tranches du bénéfice après l'abattement JA.
  - Associés exploitants : × nombre d'exploitants (4 au plus), sans dépasser le bénéfice.
  - Plafond global : 150 000 € × exploitants, moins les déductions non encore rapportées.
- **Saisie** : montant de la DEP de l'exercice ≤ plafond ; ligne de passage −.
- **Registre par exercice d'origine** (`dep_entries`) :
  - montant déduit ;
  - épargne affectée ;
  - utilisations datées : dépense, aléa, part exonérée de 30 % (plafonds `ba.dep.exempt_*`) ;
  - réintégrations ;
  - **échéance du 10e exercice**.
  - Les anciennes **DPI / DPA** se reprennent dans le même registre, avec leur exercice d'origine et un type.
- **Épargne** :
  - compte bancaire repéré « épargne DEP » (case sur le compte de trésorerie), solde lu à la clôture et à la date limite (6 mois) ;
  - **substituts** saisis : stocks de fourrage, stocks à rotation lente ;
  - **contrôle du ratio** : épargne ≥ 50 % et ≤ 100 % des déductions non rapportées. Sinon **anomalie**, et réintégration proposée de la fraction qui excède le double de l'épargne.
- **Aléa économique** : valeur ajoutée de l'exercice comparée à la moyenne des 3 exercices précédents (baisse de plus de 10 %) et des 3 exercices clos avant le précédent (plus de 15 %), calculée depuis les comptes selon la formule de l'art. 73 II-2 d. Elle est affichée pour l'attestation de l'expert-comptable.
- **Échéancier** : DEP à réintégrer au 10e exercice ; épargne à constituer dans les 6 mois de la clôture.

---

## 6. Provision pour hausse de valeur des vaches (AG6.6, art. 73 A)

Sources lues le 05/11/2026 :
- guide Isacompta Connect « Gestion de la provision pour augmentation du stock de vaches », mis à jour le 23/06/2026 d'après le BOFiP du 22/04/2026 (PDF fourni, hors git) ;
- boostaferme, « Provision stocks vaches 73 A », mise à jour le 04/11/2026, qui cite BOI-BA-BASE-20-30-20-20 (22/04/2026) et l'art. 73 A du CGI (version du 21/02/2026).

Le dispositif :
- **Champ** : exercices clos du 01/01/2024 au 31/12/2028 (paramètre) ; exploitants au réel, à l'IR, GAEC et EARL non soumis à l'IS.
  - Exclus : micro-BA, IS, option 72 B bis, premier exercice d'élevage de vaches, ancienne déduction de l'art. 70 de la LF 2024 sur le même exercice.
  - Animaux : vaches **laitières et allaitantes en stock**, ou immobilisées en comptabilité si elles sont fiscalement des stocks. Génisses, taureaux et broutards sont exclus.
- **Montant** : hausse de la **valeur brute** entre l'ouverture et la clôture, **par catégorie, sans compensation** (une baisse d'une catégorie ne réduit pas la hausse de l'autre).
  - Plafond de 15 000 € par exercice, × associés exploitants (4 au plus) en GAEC ou EARL non IS.
  - **Sans contrat pluriannuel** (EGALIM) à la clôture : montant × (1 − 10 % en 2025, 20 % en 2026, 25 % à partir de 2027), dans la limite du plafond non minoré.
  - La hausse non provisionnée n'est pas reportable. Lyvre propose le montant, sans fixation libre.
- **Comptable** (Q-F5) : provision réglementée **D 6873 / C 1483**, écriture gérée de clôture, au plus tard avant la date limite de déclaration ; reprise **D 1483 / C 7873**. Le compte 1483 est créé sous 148 s'il manque (1433 réservé aux plans qui l'emploient ; 143 « hausse de prix » est interdit aux exploitants, art. 72 C). Sous-compte par exercice d'origine possible.
- **Registre par exercice d'origine** : provision, effectif et valeur à la clôture de constitution.
- **Reprises**, à chaque clôture des 6 exercices suivants :
  - reprise = provision ÷ effectif à la clôture de constitution × vaches sorties de l'exercice, sur la provision **la plus ancienne d'abord** ;
  - **pas de reprise**, motif justifié, si la valeur du stock reste au moins égale à celle de la clôture de constitution, si la sortie est remplacée par une entrée avant la clôture ou le dépôt, ou en cas d'abattage ordonné par l'administration ;
  - **6e exercice** : le solde est réintégré, sauf **exonération définitive** si l'effectif **ou** la valeur du stock est plus élevé qu'à la constitution (une égalité ne suffit pas).
- **Annexe** : tableau de suivi sur 6 exercices (constitution, reprises, solde), et la provision au tableau des provisions de la liasse.
- **De minimis** : l'équivalent-subvention de l'avantage de trésorerie (économie d'impôt actualisée sur 6 ans) est affiché pour information, à reporter au suivi des aides de minimis ; pas de calcul de l'impôt du foyer.

## 7. Régimes, moyennes, revenus accessoires (AG6.1, AG6.2, AG6.7)

- **Moyennes triennales** des recettes :
  - micro : encaissements (existant) ; réel : créances acquises (comptes 70 à 74 hors cessions) ;
  - recettes à façon × 3 (comptes repérés) ; GAEC : seuils × associés (`ba.gaec.*`) ;
  - **alerte de changement de régime** à N+1 (micro → réel simplifié → réel normal), avec la date d'effet.
- **Passage du micro au réel** (art. 72 E bis) : créances du bilan d'ouverture × (1 − 87 %), ligne de passage proposée le premier exercice au réel.
- **Simulation micro ou réel** (AG6.2) : bénéfice forfaitaire contre résultat réel estimé, date limite d'option.
- **Revenus accessoires** (art. 75) :
  - comptes ou catégories de produits repérés BIC / BNC ;
  - ratio sur les 3 années civiles précédant l'exercice, en TTC (50 % des recettes agricoles, 100 000 € × associés en GAEC) ;
  - **alerte d'IS de plein droit** pour une société civile en dépassement ;
  - ventilation BA / BIC du résultat.
- **Moyenne triennale 75-0 B** : historique des BA par associé fourni ; l'option joue au niveau du foyer (Q-F8).
- **Étalement 75-0 A** : revenu exceptionnel proposé (au-delà de 25 000 € ou de la moyenne des 3 exercices, si le bénéfice dépasse 1,5 × cette moyenne), registre des septièmes.

---

## 8. Aide à la liasse 2139 / 2143 (AG6.8)

- **Correspondance datée** comptes → cases (`data/liasse/2139_<année>.json`, `2143_<année>.json`), construite **depuis les formulaires officiels du millésime** (comme la CA12A), validée par l'expert-comptable (Q-F6).
- **Export** : tableaux A à E (2139) et 2144 à 2154 (2143), cases et montants, PDF et XLSX, avec les lignes de passage en 2139 B / 2143.
- **IS** : liasse 2033 ou 2050 du référentiel société (existant pour le lot T), non traitée ici.

---

## 9. Plus-values et crédits d'impôt (AG6.9, AG6.10)

- **Plus-values** : par immobilisation cédée, court terme et long terme (amortissements, durée de détention de plus de 2 ans), et **simulation de l'exonération 151 septies** selon les recettes (seuils datés `ba.pv.*`, **à valider**) ; le résultat retenu devient une ligne de passage.
- **Crédits d'impôt** (bio, HVE, remplacement pour congés) : conditions et montants en paramètres datés (**à valider**), calcul et répartition par associé ; écriture proposée D 444 / C 699 pour une société à l'IS seulement.

---

## 10. Données, API, écrans

- **Tables** :
  - `tax_results` (exercice, résultat comptable, résultat fiscal, figé) ;
  - `tax_result_lines` (type, montant, sens, case de liasse, motif, associé) ;
  - `dep_entries` et `dep_movements` ;
  - `cow_provisions` et `cow_provision_movements` ;
  - `income_spread_entries` (75-0 A) ;
  - colonnes `associates.is_operator`, `young_farmer_since`, `profit_share_bp` ;
  - `bank_accounts.dep_savings` ;
  - `stock_lines.cow_category` (laitières, allaitantes) ;
  - `fiscal_years.egalim_contract`.
- **Services** : `tax_result.py`, `young_farmer.py`, `dep.py`, `cow_provision.py`, `ba_regimes.py`, `liasse.py`, `capital_gains.py`.
- **Écrans** :
  - Compta › **Résultat fiscal** ;
  - registres DEP et 73 A ;
  - réglages JA sur la fiche associé ;
  - case « épargne DEP » sur le compte bancaire ;
  - simulation micro ou réel dans Structure › Fiscalité ;
  - export de liasse.

---

## 11. Questions (réponses du 05/11/2026 en tête du document)

- **Q-F1 Répartition par associé** (réponse : pleine propriété et usufruit, rien sur la nue-propriété) : au prorata des parts sociales en pleine propriété à la clôture, avec une **part des droits aux bénéfices** saisissable par associé quand les statuts en disposent autrement. Est-ce suffisant ? Et pour l'usufruit et la nue-propriété ?
- **Q-F2 CSG non déductible** : faut-il saisir le montant depuis l'appel ou le relevé MSA (proposition) ? Ou le calculer (taux non déductible × assiette des cotisations personnelles, compte 646) ?
- **Q-F3 DEP** :
  - déduction **extra-comptable seulement**, sans écriture (proposition) ?
  - épargne lue sur un compte bancaire repéré, et substituts (fourrage, stocks à rotation lente) saisis : est-ce conforme à ta pratique ?
- **Q-F4 Barèmes 2026 de l'audit, à confirmer avant saisie en paramètres** :
  - DEP : tranches 33 287 / 61 642 / 92 464 / 123 284 €, plafond de 51 040 €, plafond global de 150 000 €, part exonérée de 50 000 € dont 40 % pour l'aléa économique ;
  - JA : 50 700 / 67 600 €, taux 75 %, 50 %, 30 %, et 100 % / 60 % l'exercice de la DJA ;
  - 73 A : 15 000 €, minorations de 10, 20 et 25 %.
  - Sources à me donner, ou à prendre sur Légifrance (articles 73, 73 A, 73 B) ?
- **Q-F5 Provision 73 A** : en **148 / 6873 / 7873** (provision réglementée relative aux stocks, proposition), ou en 143 / 6872 / 7872 comme le dit l'audit ?
- **Q-F6 Liasse** : puis-je lire les formulaires 2139-SD, 2139 A à E, 2143-SD et 2144 à 2154 du millésime 2026 sur impots.gouv pour construire la correspondance des cases (tu la valides ensuite) ? Ou préfères-tu me les fournir ?
- **Q-F7 Plus-values et crédits d'impôt** : seuils et montants à valider (151 septies : 350 000 / 450 000 € ; cession à un JA ; crédit bio : 4 500 € ou 6 000 € ; HVE ; remplacement). Les fais-tu dans AG6, ou plus tard ?
- **Q-F8 Moyenne triennale 75-0 B** : Lyvre fournit seulement l'historique des BA par associé, l'option jouant au niveau du foyer. D'accord ?
- **Q-F9 Jeune agriculteur en société** : date d'octroi de la première aide et exercice d'inscription de la DJA portés **sur l'associé** (exploitant). La DJA de la société (AG3) sert-elle de montant de référence pour le « au moins égal à la DJA » ?

---

## 12. Sous-lots

| Sous-lot | Contenu | Dépend de |
|---|---|---|
| **AG6.a** | Résultat fiscal et tableau de passage : lignes de stocks (AG4.e), 75-0 D (AG5.c), CSG, saisies ; associés exploitants et droits aux bénéfices ; répartition par associé ; écran et export | — |
| **AG6.b** | Abattement JA (EI et par associé), barème daté | AG6.a |
| **AG6.c** | DEP : plafond, registre, épargne et ratio, utilisations, aléa (valeur ajoutée), réintégrations, DPI/DPA, échéances | AG6.b |
| **AG6.d** | Provision 73 A : catégories de vaches à l'inventaire, EGALIM, dotation 6873 / 1483, reprises par ancienneté et dérogations, 6e exercice et exonération, annexe de suivi | AG4 |
| **AG6.e** | Régimes : moyennes, alertes, 72 E bis, simulation micro ou réel, revenus accessoires et alerte d'IS, 75-0 A, historique pour 75-0 B | AG6.a |
| **AG6.f** | Aide à la liasse 2139 / 2143, depuis les formulaires 2026 fournis | AG6.a |
| **AG6.g** | Plus-values 151 septies et crédits d'impôt (dans AG6, seuils à valider) | — |

Ordre proposé : a → b → c ; d ∥ e ; f ; g.
