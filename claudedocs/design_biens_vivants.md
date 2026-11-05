# Conception : lot AG5, biens vivants immobilisés

> **Statut** : **validée** (05/11/2026, AGD22), avec les réponses de l'expert-comptable :
> - Q-B1 : 7222 pour les coûts de croissance portés en en-cours, 724 pour l'animal du stock qui devient reproducteur ;
> - Q-B2 : sortie partielle d'un lot au **coût moyen** du lot ;
> - Q-B3 : dépréciation par écriture de clôture gérée, saisie par fiche avec motif ;
> - Q-B4 : mort, sinistre et abattage : valeur nette en **6571**, indemnité en **7571** ;
> - Q-B5 : durée d'amortissement saisie librement par fiche ;
> - Q-B6 : **option du profil fiscal** « reproducteurs maintenus en stock », qui coupe l'alerte.
>
> **AG5.a réalisé (05/11/2026, non commité)**. Contenu :
> - colonnes `assets.living_kind`, `species`, `age_class`, `units`, `origin` (migration `f8a0b2c4d6e7`) ; nature déduite du compte (241, 242 et 2341 reproducteurs ; 243 et 2343 service ; 246 et 2346 plantations ; 247 et 2347 autres) ; champs effacés hors 24x / 234x ;
> - lot = fiche parente, entrées = composants avec effectif ; effectif du lot = somme des composants en service ;
> - **sortie partielle au coût moyen** (`assets.split_living`, `living_exit`) : chaque composant scindé dans la proportion n ÷ effectif (coût, valeur résiduelle, reprise, dotations passées), effectifs répartis au prorata, la dernière part prenant le reste ; la partie détachée sort par la sortie existante (dotation complémentaire comprise) ;
> - **cession d'un bien vivant en 6571 / 7571** (valeur nette, prix), les autres immobilisations restant en 6578 / 7578 ;
> - API : champs sur `/assets`, filtre `?living=1`, `POST /assets/<id>/living-exit` (`units` facultatif) ;
> - écrans : champs du bien vivant dans la fiche (nature, espèce, catégorie d'âge, effectif, origine), colonne « Effectif » et case « Biens vivants » dans le registre, valeur nette par tête, effectif sorti dans la sortie.
>
> Écarts avec la conception :
> - mort, sinistre et abattage sanitaire passent pour l'instant par « mise au rebut » ; leurs types de sortie, l'indemnité en 7571 et le registre de réinvestissement viennent en AG5.c ;
> - une sortie partielle refuse un lot hors service (en attente) : la mise en service d'un en-cours vient en AG5.b.
>
> Tests : `tests/api/test_living_assets.py` (3 tests), `frontend/src/features/assets/livingAssets.test.tsx` (1 test).
>
> **AG5.b réalisé (05/11/2026, non commité)**. Contenu :
> - table `living_wip_costs` et colonne `stock_lot_movements.asset_id` (migration `a9b1c3d5e7f8`) ; source gérée `LIVING_WIP` (hors livres de TVA, non extournée) ;
> - `app/services/living_assets.py` :
>   - **en-cours** : coût de croissance de l'exercice saisi par fiche en cours (234x en attente), avec sa base ; écriture D 234x / C **7222** au dernier jour ; la valeur d'origine de la fiche augmente du coût passé ; repasser remplace, annuler retire (refusé si un bien de l'écriture est déjà mis en service) ;
>   - **mise en service** : sans compte choisi, 2341 → 241, 2343 → 243, 2346 → 246, 2347 → 247 ; le cumul (achat + en-cours) est viré en 24x par la mise en service existante ;
>   - **animal du stock devenu reproducteur** : mouvement « sortie vers les immobilisations » du lot et fiche en service à la date, à la valeur saisie, D 24x / C **724** ; nouvelle fiche (compte 241 ou 243, durée) ou composant d'un lot immobilisé (durée du lot reprise) ; supprimer le mouvement supprime la fiche et son écriture tant qu'elles n'ont pas de dotation ;
> - contrôles de clôture : bien en cours sans coût de l'exercice (information), coûts saisis sans écriture (**anomalie**) ;
> - API `/fiscal-years/<id>/closing/living-wip` (GET, POST, DELETE), `PUT …/living-wip/costs`, `POST /stock-lots/<id>/to-fixed-assets` ;
> - écrans : panneau « Biens vivants en cours » dans Clôture › Inventaire ; dans la fiche d'un lot de stock, le mouvement « Sortie vers les immobilisations » demande la valeur, le lot immobilisé ou le compte et la durée.
>
> Écarts avec la conception :
> - les coûts de croissance sont **saisis** (avec leur base) ; leur calcul depuis un barème ou l'analytique viendra avec AG8 ;
> - les coûts engagés entre la dernière clôture et la mise en service ne sont pas portés en en-cours automatiquement.
>
> Tests : `tests/api/test_living_wip.py` (3 tests), `frontend/src/features/assets/livingWip.test.tsx` (1 test).
>
> **AG5.c réalisé (05/11/2026, non commité)**. Contenu :
> - tables `asset_living_exits`, `living_reinvestments`, `asset_impairments` (migration `b0c2d4e6f8a9`) ; source gérée `LIVING_IMPAIRMENT` (hors livres de TVA, non extournée) ;
> - `app/services/living_exits.py` :
>   - **sorties typées** d'un bien vivant (cession, mort, sinistre, abattage sanitaire, rebut), totales ou partielles au coût moyen : valeur nette en 6571 ; prix réservé à la cession ; **indemnité** (mort, sinistre, abattage) en D 462 / C **7571** à la date ;
>   - **abattage sanitaire** : registre de réinvestissement (indemnité, valeur nette, date limite à 2 ans, montant et date du réinvestissement) ;
>   - **dépréciations** : montant cumulé voulu par fiche avec motif (refusé au-delà de la valeur nette) ; écriture de l'écart avec la clôture précédente, D 68164 / C 294 ou D 294 / C **78164** (compte créé sous 7816 s'il manque) ; un bien sorti voit sa dépréciation reprise ;
> - échéancier : fiche **DIV-06** « Reconstitution du cheptel après abattage sanitaire » (règle `lyvre` de source `living_reinvestments`, rappels J-180, J-60, J-15, « fait » quand le réinvestissement est daté) ; la base passe à 39 fiches ;
> - contrôles de clôture : dépréciations à passer (**anomalie**), reconstitution du cheptel à moins de 6 mois de la clôture (information) ;
> - API `POST /assets/<id>/living-exits`, `GET /living-exits`, `PUT /living-reinvestments/<id>`, `/fiscal-years/<id>/closing/living-impairments` (GET, POST, DELETE, `PUT …/values`) ;
> - écrans : sortie d'un bien vivant par type (prix ou indemnité, effectif), panneau « Dépréciation des biens vivants » dans Clôture › Inventaire, registre des abattages sanitaires sous la liste des biens vivants.
>
> Écarts avec la conception :
> - créance de l'indemnité en **462** (le plan agricole n'a pas de 4687) ;
> - l'exonération de l'art. 75-0 D n'est pas calculée : le registre la prépare pour AG6.
>
> Tests : `tests/api/test_living_exits.py` (3 tests), test d'écran des biens vivants étendu.
>
> **AG5.d réalisé (05/11/2026, non commité) — lot AG5 terminé (a à d)**. Contenu :
> - option du profil fiscal **`breeders_in_stock`** « Reproducteurs maintenus en stock (option fiscale, à vérifier) », datée, sans durée ni source tant que le texte n'est pas vérifié (Q-B6) ;
> - **reproducteur en stock** (`stock_lots.breeder_warning`) : avertissement sur la ligne d'inventaire d'un lot de destination « renouvellement » ou d'un libellé évocateur (truie, verrat, taureau, bélier, bouc, étalon, poulinière, vache allaitante, reproducteur, géniteur), sur 3112 / 3113 ; coupé quand l'option est en vigueur à la clôture ; contrôle de clôture d'information ;
> - **sortie de lot vers les immobilisations sans fiche** (mouvement saisi sans passer par « Vers les immobilisations ») : contrôle d'information ;
> - **annexe** : effectifs des biens vivants immobilisés par nature (ouverture déduite, entrées de l'exercice, sorties, clôture), ajoutés au tableau des biens vivants du Bilan (`agri_reports.living_headcount`).
>
> Écarts avec la conception :
> - la vache laitière n'est pas dans les libellés évocateurs (la doctrine citée par compta-online la tient en stock à chaque clôture) ;
> - l'effectif d'ouverture est déduit (clôture − entrées + sorties), pas lu dans l'annexe de l'exercice précédent ; les sorties passées par la sortie simple d'AG5.a (sans type) ne sont pas comptées.
>
> Tests : `tests/api/test_living_controls.py` (2 tests), test d'écran de l'annexe étendu.
>
> **Besoins** : `claudedocs/compta_agri.md`, lot AG5 :
> - AG5.1 : immobilisations biologiques et gestion par lot ;
> - AG5.2 : cycle de vie (en-cours, mise en service, amortissement, dépréciation, cession, mortalité, sinistre, abattage sanitaire) ;
> - AG5.3 : contrôle d'un reproducteur en stock.
>
> **Décisions déjà prises** :
> - AGD11 : cessions de biens vivants en 7571 / 6571, autres immobilisations en 7578 / 6578, en-tête 234 ;
> - réponses d'expert du § 8 : un reproducteur est immobilisé s'il reste durablement (plus de 12 mois), en stock sinon ; l'en-cours d'un bien vivant va en 234 ;
> - AGD21 (AG4) : lots d'animaux en stock et mouvement « sortie vers les immobilisations ».
>
> **Sources lues** :
> - Recueil PCG 2026, titre 5 : art. 618-10 (définition, coût de production, lot) et 618-11 (cession habituelle en exploitation, comptes 657 et 757 créés par l'entité), p. 240-241 ;
> - `audit_reglementation.md` § 2.4 et § 3.5 (art. 75-0 D, à vérifier sur Légifrance avant citation).

---

## 1. Constats

- **Immobilisations (lot F5)** :
  - fiches avec composants (`parent_id`) ;
  - plan linéaire ou dégressif, valeur résiduelle, statut « en attente » avec compte d'attente et mise en service ;
  - dotations de l'exercice (source `DEPRECIATION`) ;
  - sortie par cession ou mise au rebut (`dispose`).
- **Plan agricole** :
  - en-cours : 234, avec 2341 animaux reproducteurs, 2343 animaux de service, 2346 plantations pérennes, 2347 autres végétaux ;
  - immobilisations : 241, 243, 246, 247 ;
  - amortissements et dépréciations : 284, 294 ; dotations 68114, 68164 ;
  - cessions : 6571, 7571 ;
  - production immobilisée : 7222 et 724.
- **Écart actuel** : `dispose` sort la valeur nette par le rôle `disposal_book_value`, qui donne **6578** pour le plan agricole, et le prix par `disposal_proceeds`, qui donne 7578. Un bien vivant devrait passer en 6571 / 7571. Le contrôle de clôture d'AG1.d le signale déjà.
- **Annexe des biens vivants** : `agri_reports.living_assets_table` existe déjà (AG1.c).
- **Lots de stock** (AG4.b) : le mouvement « sortie vers les immobilisations » existe, mais il ne crée rien.

---

## 2. Choix structurants

1. **Un bien vivant est une immobilisation** dont le compte commence par 24 (ou 234 tant qu'il est en cours). Il porte en plus :
   - sa nature : reproducteur, animal de service, plantation pérenne, autre végétal ;
   - son espèce, sa catégorie d'âge et son effectif (nombre de têtes ou de plants).
2. **Un lot est une fiche parente** : chaque entrée d'animaux (achat, mise en service, transfert depuis le stock) devient un composant avec sa valeur et son plan. On réutilise les composants existants, chacun avec son amortissement.
3. **Sortie partielle d'un lot** (n têtes sur N), **au coût moyen** (Q-B2) : chaque composant du lot est scindé dans la proportion n ÷ N.
   - La partie scindée reprend la même proportion du coût, des amortissements passés et de la valeur résiduelle de chaque composant.
   - Valeur sortie = n × valeur nette moyenne par tête.
   - Elle sort par cession, mort ou abattage ; le reste du lot garde son plan.
4. **Les cessions de biens vivants** passent en **6571 / 7571** (AGD11, PCG 618-11, cession habituelle en résultat d'exploitation), les autres immobilisations restant en 6578 / 7578.
5. **L'en-cours (234x)** reçoit à la clôture les coûts de production de l'exercice des biens vivants en croissance, en contrepartie de la production immobilisée (Q-B1).
   - À la mise en service (entrée en production), l'en-cours passe en 24x.
   - L'amortissement commence à cette date.
6. **Un animal du stock qui devient reproducteur** (mouvement « sortie vers les immobilisations » d'un lot d'AG4) crée un composant immobilisé, à la valeur du stock ou à son coût de production, en contrepartie de la production immobilisée (Q-B1).
7. **Dépréciation** (294 / 68164) : saisie par fiche à la clôture, avec un motif ; reprise en 78164 (Q-B3).
8. **Mort, sinistre, abattage sanitaire** :
   - sortie à la date, valeur nette en 6571 ;
   - indemnité éventuelle (assurance, État) en **7571** (Q-B4), D 4687 (ou 462) / C 7571 ;
   - pour l'abattage sanitaire, la sortie alimente un **registre de réinvestissement** (indemnité, valeur nette, date limite de reconstitution à 2 ans), lu par AG6 pour l'exonération de l'art. 75-0 D, et rappelé dans l'échéancier.
9. **Pas de nouveau moteur d'amortissement** : celui des immobilisations sert tel quel (linéaire, prorata, valeur résiduelle de réforme). Durée **saisie librement par fiche** (Q-B5), sans durée proposée par espèce.

---

## 3. Données (base de l'instance)

- **Colonnes de `assets`** :
  - `living_kind` : breeding, service, plantation, other ; nul hors biens vivants ;
  - `species`, `age_class` ;
  - `units` : têtes ou plants ;
  - `origin` : purchase, born, from_stock, planted.
- **`asset_living_exits`** : sortie d'un bien vivant (lot ou composant).
  - Champs : `asset_id`, `on`, `kind` (sale, death, casualty, sanitary_slaughter, scrap), `units`, `price_cents`, `indemnity_cents`, `indemnity_account_id`, `entry_id`, `note`.
- **`living_reinvestments`** : abattage sanitaire.
  - Champs : `exit_id`, `indemnity_cents`, `book_value_cents`, `deadline` (sortie + 2 ans), `reinvested_cents`, `reinvested_on`, `note`.
  - AG6 le lira pour la réintégration de la part non réinvestie.
- **`living_wip_costs`** : coûts de l'exercice portés en en-cours 234x, avec `asset_id`, `fiscal_year_id`, `amount_cents`, `basis` (saisi, ou coût standard du barème d'AG4) et `entry_id`.
- **`asset_impairments`** : dépréciation de clôture par fiche et par exercice, avec `asset_id`, `fiscal_year_id`, `amount_cents`, `reason` et `entry_id`.

---

## 4. Écritures

| Événement | Écriture | Source |
|---|---|---|
| Achat d'un reproducteur | facture d'achat sur 241 (catalogue ou ligne d'achat → fiche, comme aujourd'hui) | achats |
| Coûts de croissance de l'exercice (en-cours) | D 234x / C 7222 ou 724 (Q-B1), au dernier jour | gérée `LIVING_WIP`, non extournée |
| Mise en service | D 24x / C 234x pour le cumul de l'en-cours, à la date | `ASSET` |
| Animal du stock devenu reproducteur | D 24x / C 7222 ou 724 (Q-B1), à la date ; le stock final d'AG4 ne le compte plus | `ASSET` |
| Amortissement | D 68114 / C 284x (dotations de l'exercice existantes) | `DEPRECIATION` |
| Dépréciation, reprise | D 68164 / C 294x ; D 294x / C 78164 | gérée `LIVING_IMPAIRMENT` |
| Cession | complément d'amortissement, D 284x, D **6571** (valeur nette), C 24x ; prix D 462 / C **7571** (ou facture de vente) | `ASSET` |
| Mort, sinistre, abattage | mêmes lignes de sortie (valeur nette en 6571) ; indemnité D 4687 ou 462 / C 7571 | `ASSET` |

---

## 5. Contrôles et annexe (AG5.3)

- **Reproducteur en stock** :
  - avertissement non bloquant, sur la ligne d'inventaire et à la clôture, pour un lot de stock 3112 de destination « renouvellement » ;
  - même avertissement pour une ligne libellée comme un reproducteur (truie, vache allaitante, taureau, bélier…) ;
  - le message rappelle le critère de durée (PCG 618-10) ;
  - **l'alerte est coupée** quand l'option du profil fiscal « Reproducteurs maintenus en stock » est en vigueur à la clôture (Q-B6). L'option est ajoutée aux options datées (`breeders_in_stock`), sans durée ni source officielle tant que l'article n'est pas vérifié.
- **Lot de stock « sortie vers les immobilisations »** sans fiche immobilisée liée : information.
- **Biens vivants en 24x sans fiche au registre** : existe déjà (AG1.d).
- **Abattage sanitaire avec date limite de réinvestissement à moins de 6 mois** : rappel dans l'échéancier (règle `lyvre` de source `living_reinvestments`).
- **Annexe** : le tableau des biens vivants (AG1.c) ajoute l'effectif, les entrées et les sorties de l'exercice par nature.

---

## 6. API et écrans

- **API** :
  - `/assets` accepte les champs des biens vivants ;
  - `POST /assets/<id>/living-exit` (sortie totale ou partielle, avec scission) ;
  - `/fiscal-years/<id>/closing/living` (en-cours, dépréciations : lire, passer, annuler) ;
  - `/living-reinvestments[/<id>]` ;
  - `POST /stock-lots/<id>/to-fixed-assets` (crée le composant immobilisé depuis le mouvement d'AG4).
- **Écrans** :
  - **Compta › Immobilisations**, filtre « Biens vivants » : nature, espèce, effectif ; fiche de lot avec ses composants et ses sorties ; bouton « Sortie » (cession, mort, sinistre, abattage) ;
  - **Clôture › Inventaire** : panneau « Biens vivants » (en-cours de l'exercice, dépréciations) ;
  - **Inventaire › Animaux** : action « Vers les immobilisations » sur un mouvement de lot.

---

## 7. Hors lot

- exonération 75-0 D et réintégration, abattement, provision 73 A : **AG6** (AG5 tient le registre) ;
- coût de production calculé depuis l'analytique : **AG8** (AG5 le reçoit saisi, ou depuis un barème d'AG4) ;
- amélioration des sols (217, PCG 618-12) et DPB : immobilisations ordinaires, sans traitement propre ici.

---

## 8. Sous-lots

| Sous-lot | Contenu |
|---|---|
| **AG5.a** | Champs des biens vivants, lots par composants, sortie partielle par scission, cession en 6571 / 7571, filtre et fiche dans Immobilisations |
| **AG5.b** | En-cours 234x à la clôture, mise en service, transfert d'un animal du stock (mouvement d'AG4.b) |
| **AG5.c** | Mort, sinistre, abattage sanitaire, indemnités, registre de réinvestissement et rappel dans l'échéancier ; dépréciations 294 |
| **AG5.d** | Contrôles (reproducteur en stock, sortie de stock sans fiche) et annexe enrichie |

Ordre : a → b ∥ c → d.

---

## 9. Questions (réponses du 05/11/2026 en tête du document)

- **Q-B1 Production immobilisée : 7222 ou 724 ?** Le plan agricole a les deux comptes : 7222 « Production immobilisée – immobilisations corporelles (biens vivants) » et 724 « Biens vivants immobilisés ».
  - Proposition : **7222** pour les coûts de croissance portés en en-cours (234x) ; **724** pour l'animal du stock qui devient reproducteur.
  - Ou un seul compte pour les deux ?
- **Q-B2 Sortie partielle d'un lot** : faut-il scinder au prorata des têtes en sortant d'abord les entrées les plus anciennes (proposition) ? Ou au coût moyen du lot ?
- **Q-B3 Dépréciation des biens vivants** : écriture de clôture gérée (D 68164 / C 294x, reprise en 78164), saisie par fiche avec un motif. Est-ce suffisant ?
- **Q-B4 Mort, sinistre, abattage sanitaire** :
  - valeur nette en **6571**, comme une cession ?
  - indemnité d'assurance ou de l'État en **7571**, en **791**, ou en 742 « Indemnités liées à la production agricole » ?
- **Q-B5 Durées d'amortissement** : faut-il des durées proposées par espèce (paramètres datés que tu fournirais), ou une saisie libre par fiche ?
- **Q-B6 Reproducteur en stock** : l'option fiscale de garder les reproducteurs en stock (annexe III, 38 sexdecies, à vérifier) se traite-t-elle par une **valeur fiscale** d'AG4 (écart extra-comptable) ? Ou faut-il une option dans le profil fiscal, qui coupe l'alerte ?
