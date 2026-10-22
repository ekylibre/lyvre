# Base documentaire comptable « Lyvre » : PCG 2026, entreprises, associations et rapprochement Qonto

Lyvre doit construire son moteur comptable sur le PCG consolidé au 1er janvier 2026 (règlement ANC n° 2014-03, modifié notamment par le règlement 2022-06). Les règles propres aux associations (règlement ANC n° 2018-06) s'y ajoutent comme une couche distincte.\[1\] Le PCG et la doctrine fiscale imposent à tout logiciel quatre exigences non négociables :
- la partie double ;
- la validation irréversible des écritures ;
- la clôture des périodes ;
- l'export d'un FEC conforme à l'article A47 A-1 du LPF.

## TL;DR

- **Socle commun.** Le moteur doit garantir :
  - la partie double (art. 1031-1 PCG) ;
  - qu'une écriture validée ne peut être ni modifiée ni supprimée (art. 1031-3) ;
  - une clôture qui fige la chronologie (art. 1031-4) ;
  - une pièce justificative citée pour chaque écriture (art. 1032-1) ;
  - un FEC de 18 champs, classés par ordre chronologique de validation.

  Depuis les exercices ouverts en 2025, le règlement 2022-06 réserve le résultat exceptionnel aux événements « majeurs et inhabituels » (art. 513-5). Il fait passer les cessions d'immobilisations en 657/757 et la quote-part de subventions en 747, et il supprime les transferts de charges 791/796/797.
- **Associations.** Il leur faut un plan de comptes et des états propres :
  - fonds propres avec ou sans droit de reprise (102/103) ;
  - fonds dédiés et reportés (19x/689x/789x) ;
  - générosité du public (754x) et cotisations (756x) ;
  - contributions volontaires en nature en classe 8 (86/87) ;
  - CROD et CER en cas d'appel à la générosité du public.

  Les comptes 657, 754 et 756 n'ont pas le même sens dans le PCG et dans le règlement 2018-06. Le paramétrage doit donc dépendre du type d'entité.
- **Qonto.** Chaque transaction produit une écriture en brouillard au compte 512, jamais une écriture validée.
  - L'écriture est lettrée avec sa pièce.
  - Une opération non identifiée passe en 471, à solder avant la clôture.
  - Un virement entre comptes propres passe par le 580.
  - Le `transaction_id` sert de clé d'idempotence.

  Le chatbot renvoie vers un expert-comptable pour tout ce qui dépend du régime fiscal, de la taille de l'entité ou d'un jugement.

---

## Mode d'emploi

Chaque fiche est autonome et contient : un identifiant, l'entité concernée, un résumé, un exemple d'écriture, la référence et les implications pour le logiciel. Le symbole ⚠️ signale une réponse qui dépend de la situation, à renvoyer vers un expert-comptable.

**Sources**
- [PCG26] Règlement ANC 2014-03, version consolidée au 1er janvier 2026 : https://www.anc.gouv.fr/files/anc/files/1_Normes_fran%C3%A7aises/recueil/2026/PCG--1er-janvier-2026.pdf
- [REC-EIC26] Recueil des normes des entreprises industrielles et commerciales, janvier 2026 : https://www.anc.gouv.fr/files/anc/files/1_Normes_fran%C3%A7aises/recueil/2026/Recueil-PCG-Janvier-2026-2-.pdf
- [REC-NL26] Recueil du secteur non lucratif 2026 : https://www.anc.gouv.fr/files/anc/files/1_Normes_fran%C3%A7aises/Reglements/Recueils/Recueil_Secteur-non-lucratif/2026/Recueil-non-lucratif-2026.pdf
- [PDC-ANC] Plan de comptes de l'article 1121-1 : https://www.anc.gouv.fr/files/anc/files/1_Normes_fran%C3%A7aises/Plans%20comptables/Plan-de-comptes-PCG-2025.pdf
- [LPF] Article A47 A-1 : https://www.legifrance.gouv.fr/codes/article_lc/LEGIARTI000027804775
- [BOFIP] BOI-BIC-DECLA-30-10-20-40 : https://bofip.impots.gouv.fr/bofip/2899-PGP.html
- [QONTO] API Qonto : https://docs.qonto.com/api-reference/business-api/transactions-statements/transactions/list-transactions

**Numérotation.** Le règlement 2022-06 a renuméroté le Livre IV du PCG : les anciens articles 911-x, 921-x et 922-x correspondent désormais aux articles 1011-x, 1031-x et 1032-x.\[2\]\[3\] Le BOFiP cite encore l'ancienne numérotation.\[4\]

---

## Points clés pour l'équipe de développement

1. **L'intangibilité est opposable fiscalement.** Selon le BOFiP, un logiciel qui ne garantit pas l'irréversibilité des écritures validées « pourra constituer un élément conduisant à s'interroger sur le caractère régulier et probant de la comptabilité ».\[5\] Les fonctions de suppression ou de modification y sont qualifiées de « prohibées ».\[4\]
2. **Le plan de comptes est unique.** Il est commun aux systèmes de base et abrégé.\[6\] Les comptes en caractères normaux sont obligatoires, ceux en italique facultatifs (art. 1121-1).\[6\]\[7\]\[8\] Le système développé a disparu.\[9\]\[10\]
3. **Le résultat exceptionnel devient résiduel.** Toute règle d'imputation automatique vers les classes 67/77 doit être revue.\[11\]
4. **Trois comptes ont un sens différent selon le référentiel.**

| Compte | PCG 2026 | Règlement 2018-06 (recueil 2026) |
|---|---|---|
| 657 | Valeurs comptables des immobilisations cédées | Aides financières |
| 754 | Ristournes des coopératives | Générosité du public |
| 756 | Gains de change commerciaux | Cotisations\[6\] |

5. **Une transaction bancaire n'est pas une écriture complète.** La nature de la charge et la TVA viennent de la facture.\[12\] Il faut donc séparer la proposition d'écriture de sa validation.

---

# PARTIE A — SOCLE COMMUN (PCG 2026)

### A-01 · Principes comptables fondamentaux
**Entité :** toutes

**Résumé.**
- **Image fidèle** (art. 121-1). On peut déroger à une règle impropre à la donner, avec une justification en annexe (121-3).\[13\]
- **Continuité d'activité** (121-2) et **régularité et sincérité** (121-3).\[13\]
- **Prudence** (121-4) : « Seuls les bénéfices réalisés à la date de clôture d'un exercice peuvent être inscrits dans le résultat » (513-3). Les plus-values latentes ne sont pas comptabilisées (214-20).\[13\]
- **Permanence des méthodes** (121-5). Un changement exige un choix entre méthodes admises et une meilleure information (122-2). Son effet passe en report à nouveau (122-3).\[13\]
- **Indépendance des exercices** : rattachement « sans qu'il soit tenu compte de leur date de paiement ou d'encaissement » (112-3, 511-3, 512-4).\[13\]
- **Non-compensation** : « Aucune compensation ne peut être opérée entre les postes d'actif et de passif » (112-2), ni entre charges et produits (112-3).\[13\]
- **Intangibilité du bilan d'ouverture** : il « correspond au bilan de clôture avant répartition de l'exercice précédent » (112-2).\[13\]
- **Corrections d'erreurs significatives** : elles figurent sur une ligne séparée, hors résultat courant (122-6).\[13\]

**Référence :** PCG art. 112-2, 112-3, 121-1 à 122-6, 513-3 [PCG26]

**Implications pour le logiciel.**
- Les à-nouveaux de N+1 doivent être égaux au bilan de clôture N. Aucune saisie manuelle dans le journal AN.
- Pas de compensation automatique entre clients et fournisseurs : un 411 créditeur est reclassé en 419 dans les états.
- Registre versionné des méthodes (amortissement, CMP ou PEPS, frais d'acquisition), qui alimente l'annexe.

### A-02 · Organisation, documentation, chemin de révision
**Entité :** toutes

**Résumé.**
- Comptabilité tenue en euros et en français (Code de commerce L123-22 ; PCG 1011-1).\[14\]\[15\]
- Documentation des procédures (1011-2).\[16\]
- L'organisation doit permettre de reconstituer les comptes à partir des pièces justificatives, et inversement de retrouver les pièces à partir des comptes (chemin de révision, 1011-3, ex-911-3).\[3\]\[16\]\[17\]
- En comptabilité informatisée, la documentation des traitements doit être accessible (1011-4).\[16\]

**Référence :** PCG art. 1011-1 à 1011-4 [PCG26] ; [BOFIP]

**Implications pour le logiciel.**
- Pour un logiciel open source, la documentation versionnée fait partie de la conformité : schéma de données, règles d'imputation, validation, clôture.
- Chaque ligne est reliée à sa pièce, à sa source d'import (identifiant Qonto) et à la règle appliquée.
- Navigation descendante possible : état → écriture → pièce.

### A-03 · Livres obligatoires et partie double
**Entité :** toutes

**Résumé.**
- « Toute entité tient un livre journal et un grand livre ». Des documents informatiques peuvent en tenir lieu s'ils sont « identifiés, numérotés et datés dès leur établissement par des moyens offrant toute garantie en matière de preuve » (1021-1).\[18\]\[19\]\[20\]
- Enregistrement jour par jour, ou par récapitulation au moins mensuelle si les justificatifs sont conservés (1031-2).\[15\]\[20\]\[21\]\[22\]
- Inventaire au moins annuel (Code de commerce L123-12).\[23\]
- Partie double : chaque écriture « établit une équivalence entre ce qui est porté au débit et ce qui est porté au crédit » (1031-1).\[24\]

**Exemple :** D 6064 : 100,00 / D 44566 : 20,00 / C 401 : 120,00

**Référence :** PCG art. 1021-1, 1031-1, 1031-2 [PCG26] ; Code de commerce L123-12, R123-173

**Implications pour le logiciel.**
- Journaux paramétrables avec un code unique, repris dans le champ JournalCode du FEC : ACH, VTE, BQ-QONTO, OD, AN, CVN.
- Contrôles bloquants :
  - débit = crédit, avec des montants stockés en centimes entiers ;
  - au moins 2 lignes par écriture ;
  - aucun montant négatif.
- Éditions : journal, grand-livre, balance à 6 colonnes, reproductibles après clôture.

### A-04 · Pièces justificatives
**Entité :** toutes

**Résumé.**
- « Tout enregistrement comptable précise l'origine, le contenu et l'imputation de chaque donnée, ainsi que les références de la pièce justificative qui l'appuie » (1032-1).\[25\]\[26\]\[27\]\[28\]
- La pièce est datée et conservée sur un support « assurant la fiabilité, la conservation et la restitution en clair de son contenu ».\[27\]
- Une pièce récapitulative quotidienne est admise pour des opérations de même nature (1032-2).\[15\]\[27\]

**Référence :** PCG art. 1032-1, 1032-2 [PCG26] ; Code de commerce R123-174 ; [BOFIP] § 70

**Implications pour le logiciel.**
- Champs PieceRef et PieceDate obligatoires.
- Validation impossible sans pièce, sauf pour les écritures internes justifiées.
- Pièces stockées de façon immuable, avec empreinte (hash).
- Les transactions Qonto sans justificatif sont signalées via `attachment_ids` et `attachment_required`.\[29\]

### A-05 · Validation et irréversibilité
**Entité :** toutes

**Résumé.**
- Le caractère définitif est assuré « par une procédure de validation, qui interdit toute modification ou suppression de l'enregistrement » (1031-3, ex-921-3).\[30\]
- Le BOFiP distingue trois phases : brouillard, validation (« figer les différents éléments de l'écriture de façon telle que toute modification ultérieure […] soit impossible »), puis après-validation.\[4\]\[25\]
- Le journal n'est « régulier, sincère et probant qu'après validation ».\[4\]
- Pour corriger, on passe une contrepassation ou une écriture complémentaire.\[31\]

**Exemple :** D 6064 : 100,00 / C 6063 : 100,00 (correction d'imputation)

**Référence :** PCG art. 1031-3 [PCG26] ; [BOFIP] § 80 à 110

**Implications pour le logiciel.**
- Cycle de vie : BROUILLARD → VALIDÉE, sans retour possible.
- Aucun UPDATE ni DELETE sur une écriture validée (contrainte applicative et trigger SQL).
- Journal d'audit en ajout seul, chaîné par hash.
- Numéro continu EcritureNum attribué à la validation.
- Avertissement avant validation et bouton « Contrepasser ».\[5\]
- Les imports bancaires ne sont jamais validés automatiquement.

### A-06 · Procédure de clôture
**Entité :** toutes

**Résumé.**
- « Une procédure de clôture destinée à figer la chronologie et à garantir l'intangibilité des enregistrements est mise en œuvre au plus tard avant l'expiration de la période suivante » (1031-4).\[2\]\[32\]
- Une opération relevant d'une période clôturée « est enregistrée à la date du premier jour de la période non encore clôturée, avec mention expresse de sa date de survenance ».\[24\]\[32\]
- La réouverture d'un exercice clôturé est interdite (BOFiP).\[5\]

**Référence :** PCG art. 1031-4 [PCG26] ; [BOFIP]

**Implications pour le logiciel.**
- Chaque période mensuelle est OUVERTE ou CLÔTURÉE. Conditions de clôture :
  - toutes les écritures sont validées ;
  - la période précédente est clôturée ;
  - les comptes 471-473 et 580 sont soldés ;
  - le rapprochement bancaire est fait.
- Pas de réouverture possible.
- Un import tardif est redaté au premier jour ouvert, en conservant sa date réelle.
- Clôture annuelle : solde des classes 6 et 7 vers le compte 12, puis à-nouveaux. L'affectation du résultat suit la décision de l'assemblée.

### A-07 · Conservation et FEC
**Entité :** toutes (⚠️ le FEC a des variantes BNC, BA et trésorerie)

**Résumé.**
- **Conservation** : 10 ans pour les documents comptables et les pièces (Code de commerce L123-22), et au moins 6 ans au titre fiscal (LPF L102 B).\[14\]\[15\]\[20\]\[33\]
- **FEC** : un fichier unique par exercice, « dans lequel les écritures sont classées par ordre chronologique de validation ».\[34\]
  - Il reprend les écritures après inventaire, « hors écritures de centralisation et hors écritures de solde des comptes de charges et de produits ».\[34\]
  - Les à-nouveaux portent les premiers numéros.\[34\]
  - Ses 18 champs : JournalCode, JournalLib, EcritureNum, EcritureDate, CompteNum, CompteLib, CompAuxNum, CompAuxLib, PieceRef, PieceDate, EcritureLib, Debit, Credit, EcritureLet, DateLet, ValidDate, Montantdevise, Idevise.\[35\]\[36\]
  - Nom du fichier : SirenFECAAAAMMJJ, avec les noms des champs en première ligne.\[37\]
  - Sanction (art. 1729 D, I du CGI) : en cas de défaut de présentation du FEC, « une amende égale à 5 000 € ou, en cas de rectification et si le montant est plus élevé, d'une majoration de 10 % des droits mis à la charge du contribuable ». Selon une mise à jour du BOFiP du 15 décembre 2021 (résumée par les Éditions Francis Lefebvre), l'amende s'applique « une seule fois par contrôle, quel que soit le nombre d'exercices contrôlés ».

**Référence :** Code de commerce L123-22 ; LPF L47 A, A47 A-1 [LPF] ; BOI-CF-IOR-60-40-20

**Implications pour le logiciel.**
- Aucune purge des données pendant 10 ans.
- Archive par exercice : FEC, livres en PDF/A, pièces, audit.
- FEC testé en intégration continue (outil Test Compta Demat de la DGFiP).
- CompteNum doit être conforme au PCG.\[36\]
- La somme des classes 6 et 7 doit être égale au résultat.\[38\]
- ⚠️ Faire confirmer par un expert l'inclusion de la classe 8 des associations.

### A-08 · Structure du plan de comptes
**Entité :** toutes

**Résumé.**
- 8 classes de comptes à deux chiffres (art. 1111-1) : 1 Capitaux, 2 Immobilisations, 3 Stocks, 4 Tiers, 5 Financiers, 6 Charges, 7 Produits, 8 Comptes spéciaux.\[39\]\[40\]
- « Chaque compte à deux chiffres et plus peut être subdivisé en tant que de besoin » (1131-1). Une subdivision commence par le numéro du compte qu'elle détaille.\[7\]\[8\]\[39\]\[41\]
- Comptes 28 : amortissements. Comptes 29, 39, 49 et 59 : dépréciations.\[6\]\[39\]
- Selon le tableau de correspondance du CNOEC (avril 2024), avec la réforme 2022-06 « environ 150 comptes ont été supprimés ; environ 100 comptes ont vu leur libellé modifié ou leur numéro de compte modifié ; une dizaine de nouveaux comptes ont été créés ».

**Référence :** PCG art. 1111-1, 1121-1, 1131-1 [PCG26] ; [PDC-ANC]

**Implications pour le logiciel.**
- Référentiels livrés sous forme de données versionnées (`pcg-2026`, `anc-2018-06-2026`). Chaque compte porte : caractère obligatoire, sens, rubrique, lettrable, TVA, dates de validité.
- Un compte créé par l'utilisateur doit hériter d'un compte existant.
- Les comptes 675, 775, 777, 791, 796, 797 et 4431 sont interdits pour les exercices ouverts depuis 2025.\[8\]\[9\]\[42\]

### A-09 · Règlement ANC 2022-06 (exercices ouverts depuis le 1er janvier 2025)
**Entité :** toutes

**Résumé.**
- **Résultat exceptionnel (513-5)** : il comprend les produits et charges « directement liés à un événement majeur et inhabituel ».\[13\]\[43\]\[44\]
  - Un événement est majeur s'il peut influencer le jugement des utilisateurs des comptes.\[13\]\[45\]
  - Il est inhabituel s'il n'est pas lié à l'exploitation normale et courante.\[46\] Il est présumé l'être s'il ne s'est pas produit lors des derniers exercices et n'est pas susceptible de se reproduire.\[13\]
  - Les indemnités qui compensent des charges d'exploitation restent en exploitation.\[13\]\[47\]
  - Les écritures purement fiscales (provisions réglementées, dérogatoires) restent en exceptionnel.\[13\]\[46\]\[48\]
- **Nouveaux comptes :**

| Avant 2025 | Depuis 2025 |
|---|---|
| 675 / 775 | 657 / 757 |
| 6756 / 7756 | 6671 / 7671 |
| 777 | 747 |
| 6711 / 6712 | 6581 / 6582 |
| 791 / 796 / 797 | supprimés ; comptes par nature (649, 7587) ou crédit de la charge |

- **États** : bilan en tableau et compte de résultat en liste. L'annexe comporte des tableaux normés et un commentaire de chaque élément exceptionnel.\[9\]\[49\]\[50\]\[51\]

**Exemple (cession : brut 3 000, amortissements 2 000, prix 1 200 HT)**
- D 28183 : 2 000 / D 657 : 1 000 / C 2183 : 3 000
- D 462 : 1 440 / C 757 : 1 200 / C 44571 : 240 (⚠️ TVA selon le bien)

**Référence :** Règlement ANC 2022-06 du 4 novembre 2022 ; PCG art. 513-5 [PCG26] ; FAQ CNCC-CNOEC (décembre 2025)

**Implications pour le logiciel.**
- Assistant de migration des règles d'imputation et des à-nouveaux.
- Toute saisie en 67/77 (hors 672/772) déclenche une alerte et exige une justification, reprise en annexe.
- ⚠️ Le chatbot ne tranche jamais la qualification d'exceptionnel.

### A-10 · Immobilisations, amortissements, dépréciations
**Entité :** toutes

**Résumé.**
- **Conditions d'inscription à l'actif** : avantages économiques futurs probables (pour le règlement 2018-06, un potentiel de service) et coût évaluable de façon fiable (212-1).\[13\]
- **Coût d'entrée** : prix net des remises, taxes non récupérables et coûts directement attribuables (213-8).\[13\]
- **Options** :
  - les éléments non significatifs peuvent être passés en charges (212-6) ;\[13\]
  - méthodes de référence : frais d'acquisition incorporés au coût, frais de constitution en charges (212-9), frais de développement activés (212-3) ;\[13\]
  - crédit-bail : loyers en charges (212-5).\[13\]
- **Amortissement** :
  - selon un plan fixé à l'entrée ;\[13\]
  - à partir de la mise en service (214-12) ;\[13\]
  - même en l'absence de bénéfice (214-11) ;\[13\]
  - linéaire par défaut.\[13\]
- **Petites entreprises** : elles peuvent retenir les durées d'usage fiscales (214-13).\[13\]
- **Composants** : amortis séparément si leurs rythmes diffèrent (214-9).\[13\]
- **Amortissements dérogatoires** : en provisions réglementées, compte 145 (214-8).\[13\]
- **Dépréciation** : sur indice de perte de valeur à la clôture (214-15). Celle du fonds commercial n'est jamais reprise (214-19).\[13\]

**Exemples**
- Achat : D 2183 : 1 500 / D 44562 : 300 / C 404 : 1 800
- Dotation : D 68112 : 500 / C 28183 : 500
- Dérogatoire : D 68725 : 200 / C 145 : 200

**Référence :** PCG art. 211-1 à 214-21 [PCG26]

**Implications pour le logiciel.**
- Registre des immobilisations relié à l'écriture et à la pièce.
- Alerte si un compte 2x est saisi avec le compte de TVA 44566.
- Calcul linéaire au prorata temporis, avec double plan comptable et fiscal ; l'écart alimente le compte 145.
- Dotations générées en brouillard.
- ⚠️ Le dégressif, les dérogatoires et le seuil des biens de faible valeur relèvent d'un expert.

### A-11 · Stocks, créances, provisions
**Entité :** toutes

**Résumé.**
- **Stocks** :
  - évalués au coût, hors pertes (213-30) ;\[13\]
  - par CMP ou PEPS (213-34), le LIFO étant exclu ;\[13\]
  - dépréciés si la valeur actuelle est inférieure au coût (214-22).\[13\]
- **Créances** : une créance douteuse est transférée en 416 et dépréciée sur son montant HT (491). Une créance irrécouvrable passe en 654.
- **Provisions** :
  - un passif est une obligation « dont il est probable ou certain qu'elle provoquera une sortie de ressources […] sans contrepartie au moins équivalente » (321-1) ;\[13\]
  - la provision est un passif d'échéance ou de montant imprécis (321-5), évalué à la meilleure estimation (323-2) ;\[13\]
  - un passif éventuel est mentionné en annexe seulement (322-5).\[13\]

**Exemples**
- Stock final : D 37 : 10 000 / C 6037 : 10 000
- Client douteux : D 416 : 1 200 / C 411 : 1 200, puis D 68174 : 500 / C 491 : 500
- Litige : D 6815 : 5 000 / C 1511 : 5 000

**Référence :** PCG art. 213-30 à 214-25, 321-1 à 324-1 [PCG26]

**Implications pour le logiciel.**
- Assistant de clôture des stocks.
- Comptes auxiliaires et lettrage (champs EcritureLet et DateLet).
- Balance âgée.
- Tableau des provisions pour l'annexe.
- ⚠️ Les montants de provisions et la TVA sur créances irrécouvrables relèvent d'un expert.

### A-12 · Régularisations de fin d'exercice
**Entité :** toutes

**Résumé.** Le rattachement des charges et produits à l'exercice impose plusieurs comptes de régularisation :
- charges constatées d'avance (486, art. 211-8) ;\[6\]\[13\]
- produits constatés d'avance (487, art. 321-7) ;\[6\]\[13\]
- factures non parvenues (408/44586) ;\[6\]
- factures à établir (418/44587) ;\[6\]
- charges à payer de personnel (428/438).\[6\]

Ces écritures sont extournées à l'ouverture de l'exercice suivant.

**Exemples**
- Assurance de 1 200 payée le 1er octobre : D 486 : 900 / C 616 : 900
- Facture non parvenue : D 6061 : 200 / D 44586 : 40 / C 408 : 240
- Facture à établir : D 418 : 1 200 / C 706 : 1 000 / C 44587 : 200

**Référence :** PCG art. 211-8, 321-7, 511-3, 512-4 [PCG26]

**Implications pour le logiciel.** Les écritures marquées « à extourner » sont contrepassées automatiquement en brouillard au 1er jour de N+1, avec un calcul prorata temporis.

### A-13 · Opérations en devises
**Entité :** toutes

**Résumé.**
- Immobilisations et stocks : conversion au cours du jour (420-1).\[13\]
- Créances et dettes : réévaluation au dernier cours à la clôture (420-5).\[13\]
  - Une perte latente va en 476 et est provisionnée (1515).\[13\]\[52\]
  - Un gain latent va en 477, sans passer en résultat.\[13\]\[52\]
- Liquidités : l'écart passe en résultat (420-7).\[13\]
- Écarts réalisés : 656/756 pour les opérations commerciales, 666/766 pour les opérations financières.\[6\]
- Cours de référence : ceux de la Banque de France (410-1).\[13\]

**Exemple :** D 476 : 50 / C 401 : 50 ; puis D 6865 : 50 / C 1515 : 50

**Référence :** PCG art. 410-1, 420-1 à 420-8 [PCG26]

**Implications pour le logiciel.**
- Conserver Montantdevise et Idevise.
- Pour un paiement par carte Qonto en devise, porter au 512 le montant en euros débité. Qonto fournit `local_amount` et `local_currency`.\[53\]

### A-14 · TVA (comptes 445x)
**Entité :** entités assujetties (⚠️ associations : voir C-09)

**Résumé.**
- **Comptes principaux** :
  - TVA collectée : 44571 ;\[6\]
  - TVA déductible : 44566 pour les biens et services, 44562 pour les immobilisations ;\[6\]
  - liquidation vers 44551 (à décaisser) ou 44567 (crédit).\[6\]
- **Autres comptes** : 4452 (autoliquidation intracommunautaire), 44581 (acomptes au régime simplifié), 44583 (remboursement demandé), 44586/44587 (régularisations).\[6\]
- **Exigibilité** :
  - biens : à la livraison, et dès l'encaissement des acomptes depuis 2023 ;\[54\]\[55\]
  - services : à l'encaissement, sauf option pour les débits (CGI art. 269, 2, c).\[56\]\[57\]\[58\]
- ⚠️ Le régime (franchise, simplifié, réel) dépend du chiffre d'affaires.

**Exemple (liquidation)**
- D 44571 : 2 000 / C 44566 : 1 200 / C 44551 : 800
- Paiement : D 44551 : 800 / C 512 : 800

**Référence :** [PDC-ANC] ; CGI art. 269 ; BOI-TVA-BASE-20-20

**Implications pour le logiciel.**
- Codes TVA paramétrables : taux, compte, exigibilité, autoliquidation.
- Contrôles :
  - base × taux = montant de TVA ;
  - alerte si un compte 6 ou 7 soumis à TVA n'a pas de TVA ;
  - comptes 4456 et 4457 bloqués en franchise ou en cas de non-assujettissement.
- Préparation des déclarations CA3 et CA12, puis verrouillage de la période.
- Le `vat_amount` de Qonto n'est qu'une suggestion : la facture fait foi.

### A-15 · Clôture d'exercice et documents de synthèse
**Entité :** toutes (associations : voir C-07)

**Résumé.**
- **Travaux de clôture**, dans l'ordre :
  1. rapprochements bancaires ;
  2. lettrage ;
  3. solde des comptes 471-473 et 580 ;
  4. régularisations ;
  5. stocks ;
  6. amortissements ;
  7. provisions ;
  8. écarts de conversion ;
  9. TVA ;
  10. impôt sur les sociétés (695/444) ;
  11. fonds dédiés et classe 8 pour les associations ;
  12. établissement des états ;
  13. clôture et à-nouveaux.
- **Documents de synthèse** : le bilan, le compte de résultat et l'annexe « forment un tout indissociable » (112-1). L'annexe ne remplace pas une inscription dans les comptes (112-4).\[13\]\[59\]
- **Modèles** : système de base 821-1 et 821-2 ; système abrégé 822-1 et 822-2.\[10\]\[13\]
- **Allègements** :
  - micro-entreprises : dispense d'annexe possible (811-7) ;\[60\]\[61\]
  - petites entreprises : système abrégé (811-5).\[62\]\[63\]

| Catégorie (Code de commerce D123-200) | Total du bilan | Chiffre d'affaires net | Salariés |
|---|---|---|---|
| Micro-entreprise | 450 000 € | 900 000 € | 10 |
| Petite entreprise | 7 500 000 € | 15 000 000 € | 50 |
| Moyenne entreprise | 25 000 000 € | 50 000 000 € | 250 |

Ces seuils s'apprécient en ne dépassant pas deux des trois critères, pour les exercices ouverts depuis 2024.\[64\]\[65\]\[66\]

**Référence :** PCG art. 112-1 à 112-4, 811-5, 811-7, 821-1 à 822-2 [PCG26] ; Code de commerce L123-16, L123-16-1, D123-200

**Implications pour le logiciel.**
- Assistant de clôture guidé. La clôture est refusée si les comptes 471-473 ou 580 ne sont pas soldés ou s'il reste des écritures non validées.\[67\]\[68\]
- Catégorie d'entreprise calculée à partir d'une table de seuils paramétrable.
- Contrôles de bouclage : actif = passif, et résultat du compte de résultat = résultat du bilan.
- ⚠️ La liasse fiscale est hors périmètre.

---

# PARTIE B — ENTREPRISES INDUSTRIELLES ET COMMERCIALES

### B-01 · Ce que le recueil EIC 2026 ajoute au PCG
**Entité :** entreprises commerciales et industrielles

**Résumé.** Le recueil intègre le règlement 2014-03 à jour jusqu'aux règlements 2025-01 et 2025-02 (dont 2022-06, 2023-05 sur les solutions informatiques, 2023-08 sur les fusions, et 2024-07).\[69\] Il y ajoute :
- la doctrine de l'ANC, classée en IR1 (contexte), IR2 (champ d'application), IR3 (mise en œuvre), IR4 (exemples) et IR5 (schémas d'écritures) ;\[1\]\[69\]
- un Livre V d'adaptations sectorielles : logement social, exploitations agricoles (2020-04), coopératives agricoles (2021-01), fonds de pérennité, commissaires de justice (2025-03, 2025-04) ;\[69\]
- des avis non repris dans un règlement.\[69\]

**Référence :** [REC-EIC26]

**Implications pour le logiciel.**
- RAG : indexer en priorité les commentaires IR3 et IR5.
- Distinguer en métadonnées le texte réglementaire et la doctrine.
- Les secteurs du Livre V sont hors périmètre et doivent être renvoyés vers un expert.

### B-02 · Contrats à long terme
**Entité :** entreprises commerciales et industrielles

**Résumé.**
- Contrats couvrant au moins deux exercices : méthode à l'avancement (préférentielle) ou à l'achèvement.
- Une perte à terminaison probable est provisionnée immédiatement (322-9).\[13\]
- Les écarts entre avancement et facturation vont en 418 ou en 487.

**Référence :** PCG Titre VI, chapitre II, section 2 [PCG26] ; [REC-EIC26] p. 257-263

**Implications pour le logiciel.** ⚠️ Pas d'automatisation en V1 : OD guidée et axe analytique « affaire ».

### B-03 · Achats, ventes, facturation électronique, capitaux propres
**Entité :** entreprises commerciales et industrielles

**Résumé.**
- Achats nets des remises figurant sur la facture\[13\] ; rabais, remises et ristournes hors facture en 609/619/629.\[6\]
- Ventes en 70x et remises accordées en 709. Escomptes en 665/765.\[6\]
- Capitaux propres :
  - capital (101), réserves (106), report à nouveau (110/119), résultat (120/129) ;\[6\]
  - subventions d'investissement (131), reprises par 139/747 ;\[6\]
  - provisions réglementées (14x) ;\[6\]
  - compte de l'exploitant (108) pour l'entrepreneur individuel.\[6\]

**Exemples**
- Vente : D 411 : 1 200 / C 707 : 1 000 / C 44571 : 200
- Encaissement Qonto : D 512 : 1 200 / C 411 : 1 200
- Reprise de subvention : D 139 : 2 000 / C 747 : 2 000

**Référence :** [PDC-ANC] ; PCG art. 213-31, 311-1, 312-1 [PCG26] ; economie.gouv.fr

**Implications pour le logiciel.**
- Factures numérotées en continu.
- ⚠️ Facturation électronique, selon la page economie.gouv.fr « Tout savoir sur la facturation électronique pour les entreprises » :
  - 1er septembre 2026 : « obligation de recevoir des factures électroniques pour toutes les entreprises », et obligation d'émettre pour les grandes entreprises et les ETI ;
  - 1er septembre 2027 : « obligation d'émettre des factures électroniques pour les petites et moyennes entreprises (PME) et les micro-entreprises » ;
  - la même page indique que « plus de 10 millions d'acteurs économiques sont concernés ».
  
  Lyvre doit importer les formats Factur-X, UBL et CII comme pièces natives.
- Affectation du résultat guidée, avec le procès-verbal d'assemblée en pièce. ⚠️ La réserve légale dépend de la forme sociale.

---

# PARTIE C — ASSOCIATIONS (RÈGLEMENT ANC 2018-06)

### C-01 · Champ d'application
**Entité :** associations

**Résumé.** Le règlement s'applique aux personnes morales de droit privé non commerçantes à but non lucratif tenues d'établir des comptes annuels, qu'elles exercent ou non une activité économique (art. 111-1). Le PCG s'applique à défaut de disposition spécifique (111-2).\[1\]

L'obligation d'établir des comptes naît notamment :
- d'une activité économique au-delà de certains seuils (L612-1) ;\[1\]
- de plus de 153 000 € de subventions publiques en numéraire (L612-4, D612-5) ;\[70\]
- de plus de 153 000 € de dons ouvrant droit à un avantage fiscal ;\[71\]
- d'un appel à la générosité du public (loi n° 91-772).\[1\]

**Référence :** Règlement 2018-06 art. 111-1, 111-2 [REC-NL26] ; Code de commerce L612-1, L612-4

**Implications pour le logiciel.**
- Le type « Association / Fondation / Fonds de dotation » charge le plan de comptes, les états et les assistants propres au règlement 2018-06.
- Alerte sur le cumul des subventions et des dons (⚠️ la qualification revient à un expert).

### C-02 · Fonds propres associatifs
**Entité :** associations

**Résumé.** Les fonds propres comprennent (131-1, 131-2, 331-1) :
- les fonds sans droit de reprise (102), mis à disposition définitivement ;\[1\]
- les fonds avec droit de reprise (103), mis à disposition sous condition ;\[1\]
- les écarts de réévaluation (105) et les réserves, dont la réserve pour projet de l'entité (1068) ;\[1\]
- le report à nouveau et le résultat ;\[1\]
- les dotations consomptibles (108) ;\[1\]
- les subventions d'investissement et les provisions réglementées.\[1\]

Le résultat s'appelle « excédent » ou « déficit » (131-3) et n'est jamais distribué.\[1\]

**Exemple :** D 512 : 20 000 / C 103 : 20 000 (apport avec droit de reprise)

**Référence :** Règlement 2018-06 art. 131-1 à 131-3, 331-1 [REC-NL26]

**Implications pour le logiciel.**
- Libellés « Fonds propres » et « Excédent/Déficit ».
- Comptes 101 et 457 interdits. Le compte 108 a un sens différent de celui du PCG.
- Toute écriture au 103 exige une convention d'apport.\[1\]

### C-03 · Fonds dédiés
**Entité :** associations

**Résumé.**
- À la clôture, la part non utilisée des ressources dédiées par des tiers financeurs à des projets définis est inscrite au passif en 19x, en contrepartie d'une charge 689x (132-1, 132-2). Elle est ensuite reprise par 789x au rythme de réalisation du projet (132-3).\[1\]
- Comptes par origine :
  - subventions : 194 / 6894 / 7894 ;\[1\]\[72\]
  - contributions financières : 195 / 6895 / 7895 ;\[1\]\[72\]
  - générosité du public : 196 / 6896 / 7896.\[1\]\[73\]
- Un projet défini participe à une partie spécifique de l'objet social et ses charges sont individualisables. Une collecte dont l'objet se confond avec l'objet social ne peut pas aller en fonds dédiés.\[1\]
- L'annexe présente un tableau par projet (431-6). Un transfert vers un autre projet exige l'accord du financeur (132-4).\[1\]\[74\]

**Exemple (subvention de 30 000, dont 18 000 utilisés)**
- D 441 : 30 000 / C 741 : 30 000
- D 6894 : 12 000 / C 194 : 12 000
- En N+1 : D 194 / C 7894

**Référence :** Règlement 2018-06 art. 132-1 à 132-4, 431-6 [REC-NL26]

**Implications pour le logiciel.**
- Axe « Projet » obligatoire.
- Assistant de calcul du report : ressources − charges affectées.
- Interdiction d'un compte 19x débiteur ou sans projet.
- ⚠️ Qualifier un « projet défini » relève du jugement.

### C-04 · Legs, donations, assurances-vie, fonds reportés
**Entité :** associations, fondations

**Résumé.**
- **Date de comptabilisation** :
  - legs : à l'acceptation, ou à l'entrée en jouissance, après levée des conditions suspensives (213-5) ;\[1\]
  - donations : à la signature de l'acte (213-4) ;\[1\]
  - assurances-vie : à la réception des fonds (213-3) ;\[1\]
  - auparavant, en engagements reçus (213-6).\[1\]
- **Comptes** :
  - espèces et titres cotés : 461 ;\[1\]
  - biens destinés à être cédés : 24, non amortis (213-11) ;\[1\]
  - dettes : 466 ;\[1\]
  - charges imposées par le testateur : provision 152.\[1\]
- **Contrepartie** : fonds propres si le testateur l'a stipulé, sinon produit 7543 (213-9).\[1\]
- **Fonds reportés** : la part non encore encaissée ou réalisée va en 191 par 6891, puis est reprise par 7891 (213-12, 213-13). Le compte 191 n'est jamais débiteur.\[1\]

**Référence :** Règlement 2018-06 art. 213-1 à 213-17 [REC-NL26]

**Implications pour le logiciel.**
- Suivi par dossier de legs et modèles d'écritures.
- Contrôles : 191 jamais débiteur, aucune dotation aux amortissements sur le compte 24.
- ⚠️ Recourir systématiquement à un expert-comptable ou à un notaire.

### C-05 · Contributions volontaires en nature (classe 8)
**Entité :** associations

**Résumé.**
- Concernent le bénévolat, les mises à disposition gratuites et les dons en nature consommés en l'état (211-1).\[1\]
- Valorisées si elles sont essentielles à la compréhension de l'activité et si l'association peut les recenser et les valoriser (211-2).\[1\]
- **Au crédit** : 870 Dons en nature, 871 Prestations en nature, 875 Bénévolat.\[1\]\[75\]
- **Au débit** : 860 Secours en nature, 861 Mises à disposition gratuites de biens, 862 Prestations, 864 Personnel bénévole.\[1\]\[75\]
- Présentées « au pied du compte de résultat […] en deux colonnes de totaux égaux » (211-3).\[1\]
- À défaut de valorisation, l'annexe en explique les motifs et décrit leur nature et leur importance (211-4).\[1\]

**Exemple :** D 864 : 7 500 / C 875 : 7 500 (500 heures à 15 €)

**Référence :** Règlement 2018-06 art. 211-1 à 211-4, 431-10 [REC-NL26]

**Implications pour le logiciel.**
- Journal CVN hors résultat et hors bilan, avec le contrôle Σ86 = Σ87.
- Registre des heures et des taux de valorisation.
- Aucune imputation depuis Qonto.

### C-06 · Cotisations, dons, mécénat, subventions
**Entité :** associations

**Résumé.**
- **Cotisations** (7561 sans contrepartie, 7562 avec contrepartie) : à l'encaissement, sauf droit de recouvrement né d'un appel de cotisation. La méthode retenue figure en annexe (142-1).\[1\]
- **Mécénat** (7542) : à la signature de la convention (142-6).\[1\]
- **Parrainage** (7063) : à la réalisation (142-5).\[1\]
- **Subventions d'exploitation** (741) : à la notification. La part pluriannuelle passe en produits constatés d'avance (142-8).\[1\]
- **Concours publics** : 73 (142-9).\[1\]
- **Contributions financières** : 7551 (142-4).\[1\]
- **Abandons de frais des bénévoles** : charge contre 4681, puis D 4681 / C 75412 (141-4).\[1\]

**Exemples**
- Don : D 512 : 50 / C 75411 : 50
- Cotisation : D 512 : 30 / C 7561 : 30

**Référence :** Règlement 2018-06 art. 141-1 à 142-9 [REC-NL26]

**Implications pour le logiciel.**
- Règles d'imputation Qonto propres aux associations.
- Comptes auxiliaires « adhérent » et « donateur ».
- Suivi des subventions par financeur (annexe 431-9).\[1\]
- ⚠️ Relier chaque reçu fiscal au don correspondant.

### C-07 · Générosité du public, CROD, CER, états
**Entité :** associations faisant appel à la générosité du public

**Résumé.**
- Les entités relevant des articles 3 et 4 de la loi n° 91-772, ainsi que les fonds de dotation faisant appel à la générosité du public, incluent en annexe (432-1) :\[1\]
  - un compte de résultat par origine et destination (CROD, 432-2 à 432-16) ;\[1\]
  - un compte d'emploi annuel des ressources (CER, 432-17) ;\[1\]
  - un tableau de variation des fonds propres (432-22).\[1\]
- Le CROD ventile les charges entre missions sociales, recherche de fonds et fonctionnement.\[1\]\[76\]
- L'article 432-1 ne fixe pas de seuil chiffré : il renvoie à la loi de 1991 et à son décret.
- Pour toutes les associations, le bilan (421-1) comporte une rubrique « Fonds reportés et dédiés ».\[77\] L'annexe (431-1 à 431-13) couvre notamment les fonds dédiés, les CVN, les subventions par autorité et les rémunérations des trois plus hauts cadres.\[1\]

**Référence :** Règlement 2018-06 art. 421-1, 422-1, 431-1 à 432-22 [REC-NL26]

**Implications pour le logiciel.**
- Axe « Destination » avec clés de répartition documentées.
- Contrôle : le résultat du CROD doit égaler le résultat par nature.
- États et annexe propres au règlement 2018-06.

### C-08 · Plan de comptes associatif
**Entité :** associations

**Résumé.**
- Le plan associatif reprend le PCG, complété par les comptes de l'article 320-2 : 102, 103, 1068, 108, 152, 191, 194-196, 204, 24, 461, 466, 4681, 653, 657 (aides financières), 689x, 7063, 7073, 73, 753, 754x, 755x, 756x, 789x, 86, 87.\[1\]\[75\]\[76\]
- Le recueil renvoie encore à l'article 932-1 du PCG, devenu l'article 1121-1.\[1\]

**Référence :** Règlement 2018-06 art. 310-1, 320-1, 320-2 [REC-NL26]

**Implications pour le logiciel.**
- Deux référentiels distincts, jamais mélangés dans un même dossier.
- ⚠️ Pour une association, l'imputation des cessions (657 dans le PCG) et des gains de change (756 dans le PCG) doit être arbitrée par un expert. Aucun choix par défaut ne doit être codé.

### C-09 · Fiscalité et TVA des associations
**Entité :** associations (⚠️)

**Résumé.** Une association à gestion désintéressée et à activité non lucrative n'est en principe pas soumise aux impôts commerciaux (BOI-IS-CHAMP-10-50). Si elle est assujettie, en tout ou partie, la fiche A-14 s'applique.

**Implications pour le logiciel.**
- Paramètre d'assujettissement : oui, non ou partiel.
- Si non : charges enregistrées TTC et comptes 4456 et 4457 bloqués.
- Si partiel : axe « secteur » et prorata à définir avec un expert.

---

# PARTIE D — RAPPROCHEMENT BANCAIRE ET IMPUTATION DES TRANSACTIONS QONTO

### D-01 · Le relevé bancaire, une pièce justificative
**Entité :** toutes

**Résumé.**
- Le rapprochement vérifie que le solde du compte 512 concorde avec celui du relevé et explique chaque écart.
- Le relevé justifie la trésorerie ; la facture justifie la nature de l'opération.
- Prévoir un sous-compte 512 et un journal par compte Qonto (512100, 512110…).

**Référence :** PCG art. 1011-3, 1032-1 [PCG26]

**Implications pour le logiciel.**
- État de rapprochement archivé à chaque clôture.
- Contrôle de continuité via `settled_balance` : solde précédent ± montant = solde suivant.

### D-02 · Import des transactions Qonto
**Entité :** toutes

**Résumé.**
- **Filtres** : l'API liste les transactions par `bank_account_id` ou `iban`, avec les filtres `settled_at_from/to`, `updated_at`, `side`, `status[]` et `operation_type[]`. Le paramètre `includes[]` ajoute les justificatifs et la TVA.\[78\]\[79\]\[80\]
- **Champs utiles** :
  - identification et montant : `transaction_id`, `amount_cents` (toujours positif), `side` ;\[78\]\[81\]
  - statut et date : `settled_at` (vide si en cours), `status` (pending, declined, reversed, completed) ;\[81\]
  - description : `operation_type`, `label`, `reference` ;\[29\]
  - devise : `local_amount` et `local_currency` ;\[29\]\[53\]
  - TVA : `vat_amount` et `vat_rate` ;\[29\]
  - justificatifs : `attachment_ids` et `attachment_required` ;\[29\]
  - soldes et contrepartie : `settled_balance` et `counterparty_iban`.\[29\]
- Les URL des justificatifs expirent après 30 minutes.\[79\]
- La synchronisation est incrémentale sur `updated_at`. L'horodatage n'est enregistré qu'après succès.\[79\]

**Référence :** Documentation de l'API Qonto [QONTO]

**Implications pour le logiciel.**
- `transaction_id` sert de clé unique.
- Traitement selon le statut :
  - `completed` : génère une écriture ;
  - `pending` : reste en prévisionnel ;
  - `declined` : ignorée ;
  - `reversed` déjà comptabilisée : écriture inverse.
- Date comptable : `settled_at`, convertie de l'UTC à l'heure de Paris.\[81\] Si la période est clôturée, appliquer A-06.\[32\]
- Une modification dans Qonto d'une transaction déjà validée ne met à jour que les métadonnées. Toute correction passe par une contrepassation.
- Les justificatifs sont téléchargés immédiatement, hachés et stockés.\[79\]

### D-03 · Imputation automatique
**Entité :** toutes

**Résumé.**
- **Ordre de proposition** :
  1. lettrage avec une facture ou un tiers (401/411) ;
  2. règle de l'utilisateur (libellé ou IBAN) ;
  3. catégorie Qonto ;
  4. à défaut, compte 471.
- **Schémas courants** :
  - fournisseur : D 401 / C 512 ;
  - client : D 512 / C 411 ;
  - frais Qonto : D 627 / C 512 ;
  - TVA : D 44551 / C 512 ;
  - URSSAF : D 431 / C 512 ;
  - salaires : D 421 / C 512 ;
  - emprunt : D 164 + D 6611 / C 512 ;
  - association : D 512 / C 75411 ou 7561.
- Pour une carte, il est recommandé de passer la facture (6xx/44566/401) puis le règlement (401/512).

**Implications pour le logiciel.**
- Moteur de règles déterministe et versionné, qui conserve la règle appliquée.
- Les suggestions d'IA affichent un score et exigent une validation humaine.\[82\]
- Contrôles : pièce présente ou motif explicite, TVA compatible avec le régime, pas de double déduction, compte autorisé.

### D-04 · Comptes d'attente 471 à 473
**Entité :** toutes

**Résumé.**
- Les opérations impossibles à imputer avec certitude, ou qui exigent une information complémentaire, sont inscrites provisoirement en 471-473.\[83\]
- Ancien art. 944-47 du PCG (avant la réforme 2022-06) : « Ce procédé de comptabilisation ne sera utilisé qu'à titre exceptionnel. Toute opération portée au compte 47 sera imputée au compte définitif dans les moindres délais possibles. »
- Cette version visait les subdivisions « 471 à 475 » et prévoyait que ces opérations « sont reclassées en fin d'exercice parmi les comptes figurant au modèle de bilan ». Le plan de comptes 2026 de l'ANC ne mentionne plus que « 471 à 473 Comptes d'attente ».

**Exemple**
- D 471 : 89,90 / C 512 : 89,90
- Puis : D 6xx : 74,92 / D 44566 : 14,98 / C 471 : 89,90

**Référence :** PCG Titre XII, comptes 47 [PCG26] ; [PDC-ANC]. Texte cité d'après l'ancien art. 944-47 (reproduit sur pcg.fr) ; la rédaction 2026 reste à vérifier dans le PDF de l'ANC.

**Implications pour le logiciel.**
- 471 pour les débits à identifier, 472 pour les crédits.
- Suivi de l'ancienneté et relances à J+7 et J+30.
- Clôture d'exercice bloquée si les comptes 471-473 ne sont pas soldés.\[67\]\[68\]

### D-05 · Virements internes (580)
**Entité :** toutes

**Résumé.** Les comptes 58 sont des comptes de passage, soldés en fin d'opération. Ils centralisent sans double emploi les virements entre comptes de trésorerie de l'entité.\[84\]\[85\]

**Exemple**
- BQ-QONTO : D 580 : 5 000 / C 512100 : 5 000
- BQ-AUTRE : D 512200 : 5 000 / C 580 : 5 000

**Référence :** PCG Titre XII, comptes 58 (ex-art. 945-58) [PCG26]

**Implications pour le logiciel.**
- Si l'IBAN de la contrepartie appartient à l'entité, l'opération est imputée en 580.
- Lettrage automatique des deux mouvements.\[86\]
- Le 580 doit être à zéro à chaque clôture\[87\]\[88\] ; sinon, un relevé manque.

### D-06 · Bonnes pratiques de rapprochement
**Entité :** toutes

**Résumé.** Rapprocher au moins chaque mois, avant chaque déclaration de TVA et avant chaque clôture :
1. synchroniser ;
2. vérifier la continuité des soldes ;
3. collecter les justificatifs ;
4. lettrer ;
5. solder les comptes 471 et 580 ;
6. comparer avec le relevé PDF archivé ;
7. valider puis clôturer.

**Implications pour le logiciel.**
- Indicateurs : taux de justificatifs, taux de lettrage, ancienneté des 471.
- Cas à gérer : remboursements par carte, frais de change, lettrage multiple.

---

# SYNTHÈSE : ENTREPRISE OU ASSOCIATION

| Thème | Entreprise | Association / fondation |
|---|---|---|
| Référentiel | PCG (ANC 2014-03) | ANC 2018-06, puis le PCG (111-2) |
| Obligation de comptes | Tout commerçant (L123-12) | Selon les seuils (activité économique, subventions ou dons > 153 000 €, générosité du public) |
| Haut de bilan | Capitaux propres (101, réserves) | Fonds propres (102/103, 1068, 108) |
| Résultat | Bénéfice ou perte, distribuable | Excédent ou déficit, non distribuable |
| Ressources affectées | Produits constatés d'avance | Fonds dédiés (194-196), fonds reportés (191) |
| Produits spécifiques | Ventes (70), subventions (74) | 756x, 754x, 755x, 73 |
| Classe 8 | Marginale | CVN (86/87) au pied du compte de résultat |
| États | Base ou abrégé | Modèles 2018-06, annexe 431-x, CROD et CER |
| Comptabilité analytique | Facultative | Quasi indispensable |
| TVA | En principe assujettie | En principe non assujettie ⚠️ |

---

# GLOSSAIRE

- **À-nouveaux** : reprise des soldes du bilan à l'ouverture de l'exercice.
- **Brouillard** : écriture provisoire, encore modifiable.
- **CCA / PCA** : charges et produits constatés d'avance (486/487).
- **CER** : compte d'emploi annuel des ressources collectées auprès du public.
- **Chemin de révision** : lien entre la pièce et les états, dans les deux sens.
- **Clôture** : procédure qui fige la chronologie des écritures.
- **Contrepassation** : écriture inverse qui annule une écriture.
- **CROD** : compte de résultat par origine et destination.
- **CVN** : contributions volontaires en nature.
- **FEC** : fichier des écritures comptables.
- **Fonds dédiés** : ressources affectées à un projet défini et non encore utilisées.
- **Fonds reportés** : legs et donations non encore encaissés ou réalisés.
- **Lettrage** : rapprochement entre une facture et son règlement.
- **Résultat exceptionnel** : résultat lié à un événement majeur et inhabituel, ou issu d'écritures fiscales.
- **Validation** : acte qui rend une écriture définitive.

---

# FAQ UTILISATEURS (amorce du chatbot)

1. **Puis-je modifier une écriture validée ?** Non (art. 1031-3 PCG).\[30\] Passez une contrepassation puis l'écriture correcte.
2. **Pourquoi ma saisie dans un mois clôturé est-elle redatée ?** Elle est enregistrée au premier jour ouvert, avec sa date réelle (art. 1031-4).\[24\]\[32\]
3. **Les transactions Qonto sont-elles comptabilisées automatiquement ?** Elles sont proposées en brouillard. Vous les vérifiez, joignez la pièce et validez.
4. **Que faire d'un prélèvement inconnu ?** Le passer en 471, puis le reclasser vite. Le compte doit être soldé avant la clôture.\[68\]\[89\]
5. **Comment enregistrer un virement entre deux comptes de l'entreprise ?** Par le compte 580, qui revient à zéro.\[90\]
6. **Combien de temps conserver les pièces ?** Dix ans (Code de commerce L123-22).\[14\]\[15\]\[20\]
7. **Qu'est-ce que le FEC ?** Le fichier de toutes les écritures de l'exercice (art. A47 A-1 du LPF), exigé dès le début d'un contrôle fiscal.\[35\]\[36\]
8. **Où enregistrer la vente d'un véhicule depuis 2025 ?** Le prix en 757 et la valeur nette comptable en 657.\[42\] ⚠️ Pour une association, voir C-08.
9. **Une amende est-elle une charge exceptionnelle ?** En général non : comptes 6581 ou 6582 (art. 513-5).
10. **Dois-je établir une annexe ?** Les micro-entreprises peuvent s'en dispenser (art. 811-7).\[60\]\[61\]\[91\]
11. **Quand la TVA sur mes prestations est-elle due ?** À l'encaissement, sauf option pour les débits.\[57\]\[92\] ⚠️ Faites valider votre régime par un expert.
12. **La TVA affichée par Qonto suffit-elle ?** Non, la facture fait foi.
13. **Dois-je recevoir des factures électroniques ?** Oui. Depuis le 1er septembre 2026, economie.gouv.fr indique une « obligation de recevoir des factures électroniques pour toutes les entreprises ». L'obligation d'émettre s'appliquera aux PME et aux micro-entreprises au 1er septembre 2027.
14. **(Association) Comment comptabiliser une cotisation ?** En 7561 ou 7562, à l'encaissement, avec la méthode indiquée en annexe (art. 142-1).\[1\]
15. **(Association) Une subvention n'est pas dépensée à la clôture : que faire ?** S'il s'agit d'un projet défini : D 6894 / C 194, puis D 194 / C 7894 (art. 132-1 à 132-3).\[72\]
16. **(Association) Faut-il valoriser le bénévolat ?** Oui, s'il est essentiel et mesurable : D 864 / C 875 (art. 211-2).\[1\]
17. **(Association) Un bénévole renonce à ses frais : comment faire ?** Charge contre 4681, puis D 4681 / C 75412 (art. 141-4).\[1\]
18. **(Association) Quand comptabiliser un legs ?** À l'acceptation, après levée des conditions suspensives (art. 213-5).\[1\] ⚠️ Faites-vous accompagner par un expert.
19. **(Association) Quand faut-il un commissaire aux comptes ?** Notamment au-delà de 153 000 € de subventions publiques (L612-4).\[70\] ⚠️ À confirmer avec un expert.
20. **Lyvre produit-il la liasse fiscale ?** Non : la balance, les états et le FEC seulement.

---

# LIMITES ET POINTS À SOUMETTRE À UN EXPERT-COMPTABLE

- **Citations du Livre IV à confirmer.** Les textes du Livre IV du PCG 2026 (articles 1011-x, 1031-x, 1032-x, comptes 47 et 58) ont été recoupés via la chronique CNCC EC 2025-09, le BOFiP et une reproduction en ligne du PCG 2026, faute d'avoir pu extraire entièrement le PDF de l'ANC (183 pages). Ils sont à confirmer avant leur intégration au corpus.
- **Conflits de numérotation.** Les conflits entre PCG et règlement 2018-06 (657, 754, 756) et le renvoi du recueil non lucratif à l'ancien article 932-1 sont à arbitrer.
- **En-têtes incohérents du recueil non lucratif.** Il mentionne à la fois « 1er janvier 20XX » et « règlements applicables au 1er janvier 2025 ». C'est la version datée du 1er janvier 2026 en pied de page qui a été utilisée.
- **Seuils non vérifiés.** Le seuil de 153 000 € figure dans le Code de commerce. D'autres seuils de dons cités par des sites commerciaux n'ont pas été vérifiés sur une source primaire et ne doivent pas être codés.
- **Questions réservées à l'expert.** La fiscalité et les jugements comptables (exceptionnel, provisions, projet défini, destinations, legs) sont toujours renvoyés vers un expert.
- **Évolutions de l'API Qonto.** L'API peut changer : prévoir des tests de contrat.

## Sources

1. <https://www.anc.gouv.fr/files/anc/files/1_Normes_fran%C3%A7aises/Reglements/Recueils/Recueil_Secteur-non-lucratif/2026/Recueil-non-lucratif-2026.pdf>
2. [Chronique Commission des études comptables Juillet 2025 www.cncc.fr 1/5](https://doc.cncc.fr/docs/comptes-annuels-societe-cotee-pr/attachments/chronique-ec-2025-09)
3. [Piste d'audit fiable et facturation électronique : les règles](https://compta-online.com/le-chemin-de-revision-ao391)
4. [BIC - Obligations déclaratives - Obligations fiscales et comptables dans le cadre du régime du réel normal d'imposition - Conservation et représentation des livres, documents et pièces comptables dans le cadre d'une comptabilité informatisée](https://bofip.impots.gouv.fr/bofip/2899-PGP.html)
5. [RF comptable : information comptable, juridique, financière pour la profession comptable](https://rfcomptable.grouperf.com/lien_bofip/index.php?mode=article&id=2899-PGP&datePlan=2013-11-18&bg=3376&bd=3377&niv=6)
6. [Plan de comptes prévu à l’article 1121-1 du règlement ANC n° 2014-03 relatif](https://www.anc.gouv.fr/files/anc/files/1_Normes_fran%C3%A7aises/Plans%20comptables/Plan-de-comptes-PCG-2025.pdf)
7. [78 9 45 6 12 0 . = x - + / 3 PLAN COMPTABLE GÉNÉRAL 2025 GUIDE PÉDAGOGIQUE](https://www.groupe-fiba.fr/wp-content/uploads/2025/02/Guide-PCG-2025-et-tableau-de-correspondance-PDC-compresse.pdf)
8. [TABLEAU DE CORRESPONDANCE PLAN DE COMPTES ACTUEL/PLAN](https://www.simax.fr/wp-content/uploads/PCG-2025.pdf)
9. [Réforme du Plan Comptable Général (PCG) : conformité 2026](https://www.l-expert-comptable.com/a/7298-la-reforme-du-plan-comptable-general.html)
10. [Foire aux questions Application du règlement ANC n°2022 ...](https://doc.cncc.fr/docs/questionsreponses-relatives-a-la/attachments/faq-cncc-cnoec-reglement-n2022-06-relatif-a-la-modernisation-des-etats-financiers-presentation-des-comptes-annuels)
11. [L'ANC a adopté le projet de règlement 2022-06 sur la modernisation des états financiers](https://www.hudellet-arres.fr/lanc-a-adopte-le-projet-de-reglement-2022-06-sur-la-modernisation-des-etats-financiers/)
12. [Upload an attachment to a transaction - Qonto](https://docs.qonto.com/api-reference/business-api/expense-management/attachments-in-transactions/upload-an-attachment-to-a-transaction)
13. <https://www.anc.gouv.fr/files/anc/files/1_Normes_fran%C3%A7aises/recueil/2026/PCG--1er-janvier-2026.pdf>
14. [Article L123-22 du Code de commerce sur Pappers Justice](https://justice.pappers.fr/loi/LEGITEXT000005634379/article/LEGIARTI000006219327)
15. [BIC - Régimes d'imposition et obligations déclaratives - Obligations fiscales et comptables dans le cadre du régime du réel normal d'imposition - Tenue de la comptabilité](https://bofip.impots.gouv.fr/bofip/2834-PGP.html/identifiant=BOI-BIC-DECLA-30-10-20-10-20120912)
16. [ORGANISATION DE LA COMPTABILITE - Principes généraux](https://www.pcg.fr/recueil-4111000-plan-comptable-sec-1-principes-generaux-comptables.php)
17. [911-3. Chemin de révision - Plan Comptable Général 2024](https://www.plancomptable.com/articles/chemin-revision.htm)
18. [1021-1. Livres comptables](https://www.plancomptable.com/organisation-comptabilite/livres-comptables/obligation-de-tenue/)
19. [m Lorganisation de la comptabilite dune asbl cas de la communaute des hommes daffaires du4](https://www.memoireonline.com/04/10/3342/m_Lorganisation-de-la-comptabilite-dune-asbl-cas-de-la-communaute-des-hommes-daffaires-du4.html)
20. [Obligations fiscales et comptables dans le cadre du régime du r](https://bofip.impots.gouv.fr/export/pdf/4862)
21. [Journal, grand livre et balance comptable : le guide](https://www.ecriturecomptable.fr/articles/journal-grand-livre-balance-comptable-controles)
22. [Enregistrement par jour et par opération - Plan Comptable Général 2026 - PlanComptable.com](https://www.plancomptable.com/organisation-comptabilite/enregistrement/principes-generaux/enregistrement-par-jour-et-par-operation/)
23. [Livre de recettes SCI : les registres obligatoires en 2026](https://sci-ai.app/registres-comptables-sci)
24. [Titre IX](https://www.comptanat.fr/pcg/titre9.htm)
25. [BIC - Obligations déclaratives - Obligations fiscales et comptables dans le cadre du régime du réel normal d'imposition - Conservation et représentation des livres, documents et pièces comptables dans le cadre d'une comptabilité informatisée](https://bofip.impots.gouv.fr/bofip/2899-PGP.html/identifiant=BOI-BIC-DECLA-30-10-20-40-20180720)
26. [922-1. Mentions minimales d'un enregistrement - Plan Comptable Général 2024](https://www.plancomptable.com/articles/mentions-minimales-enregistrement.htm)
27. [Pieces justificatives - Plan Comptable Général 2026 - PlanComptable.com](https://www.plancomptable.com/organisation-comptabilite/enregistrement/pieces-justificatives/)
28. [BIC - Obligations déclaratives - Obligations fiscales et comptables dans le cadre du régime du réel normal d'imposition - Conservation et représentation des livres, documents et pièces comptables dans le cadre d'une comptabilité informatisée](https://bofip.impots.gouv.fr/bofip/2899-PGP)
29. [Transaction - Qonto](https://docs.qonto.com/api-reference/sdk-libraries/interfaces/Transaction)
30. [Enregistrement définitif - Plan Comptable Général 2026 - PlanComptable.com](https://www.plancomptable.com/organisation-comptabilite/enregistrement/principes-generaux/enregistrement-definitif/)
31. [Chapitre 23. La clôture et la réouverture des comptes](https://shs.cairn.info/comptabilite-financiere-comptabilite-generale-cours-memos-entrainements-corriges-lmd--9782216158676-page-605?lang=fr)
32. [Procédure de clôture - Plan Comptable Général 2026 - PlanComptable.com](https://www.plancomptable.com/organisation-comptabilite/enregistrement/principes-generaux/procedure-de-cloture/)
33. [BIC - Régimes d'imposition et obligations déclaratives - Obligations fiscales et comptables dans le cadre du régime du réel normal d'imposition - Conservation et représentation des livres, documents et pièces comptables dans le cadre d'une comptabilité manuelle](https://bofip.impots.gouv.fr/bofip/2837-PGP.html/identifiant=BOI-BIC-DECLA-30-10-20-30-20131018)
34. [Article A47 A-1 - Livre des procédures fiscales - Légifrance](https://www.legifrance.gouv.fr/codes/article_lc/LEGIARTI000027804775)
35. [Fichier des écritures comptables (FEC) : composition et utilisation](https://libeo.io/blog/fichier-des-ecritures-comptables)
36. [FEC et contrôle fiscal : les anomalies visées](https://fr.doo.finance/blog/fec-controle-fiscal-anomalies-pme)
37. [Arrêté du 29 juillet 2013 portant modification des dispositions de l'article A. 47 A-1 du livre des procédures fiscales relatif aux normes de copies des fichiers sur support informatique - Légifrance](https://www.legifrance.gouv.fr/jorf/id/JORFTEXT000027788276)
38. [Article A 47 A-1 du LPF : forme et contenu du FEC](https://www.fec-expert.fr/format-fec-caracteristiques-remise/a47a1-lpf-forme-contenu-fec.html)
39. [Règles d’établissement d’un plan de comptes - Plan Comptable Général 2026 - PlanComptable.com](https://www.plancomptable.com/plan-de-comptes/regles-etablissement-plan-de-comptes/)
40. [Section 1. Cadre comptable - Plan Comptable Général 2024](https://www.plancomptable.com/titre-IV/titre-IV_chapitre-III_section-1.htm)
41. [Principes généraux - Plan Comptable Général 2026 - PlanComptable.com](https://www.plancomptable.com/plan-de-comptes/regles-etablissement-plan-de-comptes/principes-generaux/)
42. [Comptabiliser une cession d'immo : 657 et 757 (2026)](https://www.l-investisseur-long-terme.fr/plan-comptable/ecriture-comptable/cession-immobilisation/)
43. [Règlement ANC n° 2022-06 relatif à la modernisation des états financiers : 2ème partie](https://www.auditsi.eu/?p=10808)
44. [Modernisation des états financiers : ce que changent les règlements ANC n°2022-06 et n°2023-06 - FNR Revicoop](https://fnr.coop/modernisation-des-etats-financiers-ce-que-changent-les-reglements-anc-n2022-06-et-n2023-06/)
45. [Modernisation des états financiers](https://valoxy.org/blog/la-modernisation-des-etats-financiers/)
46. [Nouveau règlement de l'ANC 2022-06 sur la modernisation des états financiers : quels sont les impacts pour les entreprises en 2025 ?](https://formation.lefebvre-dalloz.fr/actualite/nouveau-reglement-de-lanc-2022-06-sur-la-modernisation-des-etats-financiers-quels-sont-les-impacts-pour-les-entreprises)
47. [Version 1er janvier 2025 Page 1 sur 178 AUTORITÉ DES NORMES COMPTABLES](https://www.anc.gouv.fr/files/anc/files/1_Normes_fran%C3%A7aises/Plans%20comptables/PCG--1er-janvier-2025.pdf)
48. [Les modifications du Plan Comptable](https://valoxy.org/blog/le-plan-comptable-modifie/)
49. [Modernisation des états financiers (ANC 2022-06)](https://kpmg.com/mc/fr/home/newsletters/newsletters-2025-no4/kpmg-monaco_newsletter-2025-no4_modernisation_etats_financiers_anc_2022-06.html)
50. [Réforme du Plan Comptable Général 2025](https://institut-isbl.fr/reforme-du-plan-comptable-general-2025/)
51. [Réforme des états financiers 2025 sous PCG : mesurez les impacts ! - BM&A](https://bma-groupe.com/conseil-et-supports-operationnels/reforme-des-etats-financiers-2025-sous-pcg-mesurez-les-impacts/)
52. [Compte 47 - Comptes transitoires ou d'attente](https://www.pennylane.com/fr/fiches-pratiques/plan-comptable/compte-47-comptes-transitoires-ou-d-attente)
53. [Retrieve a transaction - Qonto](https://docs.qonto.com/api-reference/business-api/transactions-statements/transactions/retrieve-a-transaction)
54. [Précisions BOFiP sur la TVA exigible lors des acomptes sur des livraisons de biens](https://www.anyti.me/fr/actualites/les-precisions-de-l-administration-sur-l-exigibilite-de-la-tva-lors-des-acomptes-sur-des-livraisons-de-biens/1530)
55. [TVA : Encaissements ou Débits ? Le Guide 2026](https://www.bmfiduciaire.fr/tva-encaissements-ou-debits/)
56. [Fait générateur et exigibilité - RF Blog - La Revue Fiduciaire](https://www.revue-fiduciaire.com/blog/fait-generateur-et-exigibilite/)
57. [TVA sur les débits : l’option pour le paiement de la TVA d’après les débits face à la facturation électronique et au CIBS](https://www.squairlaw.com/fr/blog/tva-sur-les-debits-loption-pour-le-paiement-de-la-tva-dapres-les-debits-face-a-la-facturation-electronique-et-au-cibs)
58. [RF comptable : information comptable, juridique, financière pour la profession comptable](https://rfcomptable.grouperf.com/lien_bofip/index.php?mode=article&id=998-PGP&datePlan=2022-01-05&bg=4937&bd=4938&niv=5)
59. [112-1. Etablissement des comptes annuels - Plan Comptable Général 2024](https://www.plancomptable.com/articles/etablissement-comptes-annuels.htm)
60. [Seuil annexe comptable 2026 : obligations et dispenses](https://www.nexco-expertise.com/seuil-annexe-comptable)
61. [Etablissement de l'annexe pour des micro-entreprises - Plan Comptable Général 2026 - PlanComptable.com](https://www.plancomptable.com/comptes-annuels/etablissement/presentation-des-comptes-annuels/etablissement-annexe-pour-micro-entreprises/)
62. [MSC](https://www.mscexpertise.fr/breves/2024-03-11_11_3.html?start=1060&format=print)
63. [Présentation en conformité avec le système de base et présentation simplifiée - Plan Comptable Général 2026 - PlanComptable.com](https://www.plancomptable.com/comptes-annuels/etablissement/presentation-des-comptes-annuels/systeme-de-base-et-simplifiee/)
64. [Nouveaux seuils de tailles d’entreprises : conséquences sur le mode de publication des bilans - Actu-Juridique](https://www.actu-juridique.fr/breves/entreprise/nouveaux-seuils-de-tailles-dentreprises-consequences-sur-le-mode-de-publication-des-bilans/)
65. [Bilans des entreprises : ce qui change en 2024](https://www.pouey.com/modifications-des-seuils-de-publication/)
66. [Annexe aux comptes annuels 2026 : obligations et contenu](https://www.keobiz.fr/le-mag/annexe-aux-comptes-annuels/)
67. [BLOG - COMPTABLE INFLUENT-GSC: Le compte d’attente (471) : définition, utilité et fonctionnement](https://espacepedagogiquegsc.blogspot.com/2016/08/le-compte-dattente-471-definition.html)
68. [Solder un compte d'attente : guide comptable pratique](https://www.guidesbusiness.com/comment-solder-le-compte-d-attente-efficacement-en-comptabilite)
69. <https://www.anc.gouv.fr/files/anc/files/1_Normes_fran%C3%A7aises/recueil/2026/Recueil-PCG-Janvier-2026-2-.pdf>
70. [Association subventionnée montant mini commissaire aux comptes obligatoire ?](https://www.conseil-cac.com/association-subventionnee-montant-mini-commissaire-aux-comptes-obligatoire--_ad45916.html)
71. [Revue fiduciaire : actualité et information juridique, comptable, fiscale, sociale](https://revuefiduciaire.grouperf.com/guide/ASSOCIATIONS/2019/20101021101517528.html)
72. [Bilan comptable association : présentation obligatoire - Optigest+](https://optigestplus.org/2025/10/27/bilan-comptable-association-presentation-obligatoire/)
73. [1 AUTORITE DES NORMES COMPTABLES RÈGLEMENT N° 2018-06 du 5 décembre 2018](https://www.associatheque.fr/fr/fichiers/bao/texte-loi-reglement-anc-2018.pdf)
74. [RÈGLEMENT N° 2018-06 du 5 décembre 2018 Relatif ... - ANC](https://www.anc.gouv.fr/files/anc/files/1_Normes_fran%C3%A7aises/Reglements/2018/Reglt_2018_06/Reglt_2018_06_Asso_version_commentaires-janv-2023.pdf)
75. [Plan comptable associations](https://www.orcom.fr/wp-content/uploads/2025/04/Plan_comptable_Associations_2025.pdf)
76. [AUTORITE DES NORMES COMPTABLES page n° 1/41 AUTORITE DES NORMES COMPTABLES](https://www.anc.gouv.fr/files/anc/files/1_Normes_fran%C3%A7aises/Reglements/2018/Reglt_2018_06/Reglt_2018-06_Association.pdf)
77. [RÈGLEMENT N° 2018-06 du 5 décembre 2018 Relatif aux ...](https://www.votre-expert-des-associations.fr/wp-content/uploads/Reglt_2018_06_Asso_version_commentaires-dec-2020.pdf)
78. [List transactions - Qonto](https://docs.qonto.com/api-reference/business-api/transactions-statements/transactions/list-transactions)
79. [How to sync transactions and attachments - Qonto](https://docs.qonto.com/get-started/business-api/use-cases/sync-transactions)
80. [🎃 New adapter: Qonto business banking (read-only) · Issue #1013 · HelpCode-ai/anythingmcp · GitHub](https://github.com/HelpCode-ai/anythingmcp/issues/1013)
81. [Retrieving Qonto’s transactions via the API and converting the CSV format to match our accounting tool](https://dev.classmethod.jp/articles/retrieve-qontos-transactions-via-api/)
82. [Les solutions de Qonto pour simplifier la comptabilité d'entreprise](https://qonto.com/fr/pre-accounting)
83. [Comptes transitoires ou d'attente (comptes 47) - Plan Comptable Général 2026 - PlanComptable.com](https://www.plancomptable.com/comptes/bilan/classe-4/47-comptes-transitoires-ou-attente/)
84. [Section 5. Comptes financiers (Classe 5) - Plan Comptable Général 2024](https://plancomptable.com/pc99/titre-IV/titre-IV_chapitre-IV_section-5.htm)
85. [Comptes de la classe 58, Virements internes, du PCG](https://www.pcg.fr/classe-58-virements-internes-du-plan-comptable.php)
86. [Comptabiliser un virement interne - L'utilisation du compte 580](https://www.calebgestion.com/cours_comptabilite/c39_virements_internes.htm)
87. [Compte 580 : générateur d'écritures de virement interne](https://www.compta-online.com/comptabilisation-des-virements-internes-et-compte-580-ao1919)
88. [Compte 58 - Virements internes](https://www.maxcompta.com/blogs/blog-plan-comptable/compte-58-virements-internes)
89. [Compte 471 - Comptes d'attente](https://www.pennylane.com/fr/fiches-pratiques/plan-comptable/compte-471-comptes-d-attente)
90. [Écriture comptable virement compte à compte : quel compte utiliser ?](https://www.compta-online.com/virement-banque-banque-t11414)
91. [Etablissement et présentation des comptes annuels - Plan Comptable Général 2026 - PlanComptable.com](https://www.plancomptable.com/comptes-annuels/etablissement/presentation-des-comptes-annuels/)
92. [TVA déductible sur les débits et sur les encaissements](https://www.compta-online.com/tva-deductible-sur-les-debits-sur-les-encaissements-t5146)
