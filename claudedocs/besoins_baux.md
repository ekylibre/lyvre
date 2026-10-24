# Besoins — Rédaction de bail assistée (carte, modèles, signature)

> Brainstorm du 24/10/2026 à partir de `claudedocs/spec_baux`. Spécification des besoins seulement :
> l'architecture, le schéma et les contrats d'API relèvent de `/sc:design`.

## 1. Objectif

Créer un bail dans Lyvre comme il est rédigé aujourd'hui à la main (bail ODT de la SCI : tableau des
éléments loués A, B, C…, carte aérienne des zones, loyer au m² de bâtiment et à l'hectare de terre),
puis le faire signer électroniquement. Le bail créé continue de porter la facture récurrente de loyer
et les quittances (lot S5, inchangés).

Deux cas, **un seul assistant** :

- **A — simple** : un seul élément sans carte (une maison, un local, une parcelle) ;
- **B — cartographié** : un ou plusieurs éléments (parcelles cadastrales, bâtiments, zones dessinées)
  choisis sur une carte.

## 2. Décisions prises

| # | Sujet | Décision |
|---|-------|----------|
| BX1 | Parcelles | **Lexicon** (`lexicon.osfarm.org`) : parcelle cadastrale au point cliqué (identifiant, section, numéro, surface, nombre et emprise des bâtiments, contour) |
| BX2 | Bâtiments | Contours des bâtiments de l'**IGN BD TOPO** (Géoplateforme, public, sans clé), cliquables comme les parcelles |
| BX3 | Modèle de bail | **Un modèle par type de bail et par instance**, articles avec champs à remplacer, modifiable dans les Paramètres ; le texte généré d'un bail reste **retouchable** avant PDF et signature |
| BX4 | Types de bail | Dérogatoire commercial, commercial 3-6-9, habitation, rural / prêt à usage |
| BX5 | Signataires | **Gérants de la SCI** (registre des associés) puis le **preneur**, via **Documenso** (au départ Docuseal : son édition libre n'accepte pas de PDF par l'API) ; paraphe sur chaque page |
| BX6 | Suivi de signature | Lyvre interroge Docuseal (à la demande et à l'ouverture du bail), range le PDF signé sur le bail ; webhook ajouté en production |
| BX7 | Loyer | **Annuel par ligne** : quantité × prix unitaire annuel ; loyer annuel = total, réparti selon la fréquence de facturation ; **une ligne de facture récurrente par ligne de bail** |
| BX8 | Cas A | **Même assistant**, étape 2 « Sans carte » : lignes saisies à la main |
| BX9 | Carte dans le PDF | **Image aérienne des zones lettrées + tableau** (lettre, désignation, surface, références cadastrales, dont bâtiments) |
| BX10 | Identifiants Docuseal | **Intégration** de l'instance (URL du serveur + jeton, chiffrés) ; le jeton de test reste dans le `.env` local, jamais versionné |

## 3. Parcours (assistant « Nouveau bail »)

### Étape 1 — Bail

Le formulaire actuel (locataire, date d'effet, fin, dépôt de garantie, fréquence, échéance, comptes,
TVA) **plus** : type de bail (BX4), adresse ou lieu-dit des biens. Bouton **Suivant**.
Le loyer n'y est plus saisi : il vient des lignes (étape 3).

### Étape 2 — Biens loués

Choix : **Avec carte** (cas B) ou **Sans carte** (cas A).

**Sans carte** : lignes saisies à la main : désignation, nature (bâtiment / terre / forfait),
surface, références cadastrales facultatives (une ou plusieurs).

**Avec carte** :

- carte **centrée sur l'adresse de la structure** (Paramètres › Organisation), fond **photo aérienne** ;
  test de référence : instance `sci-chenes-verts` ;
- sélecteur de couche : **Parcelles** (BX1) ou **Bâtiments** (BX2) ;
- pour chaque **ligne** du bail :
  1. cliquer une ou plusieurs parcelles (ou un ou plusieurs bâtiments) — surbrillance, surface affichée ;
  2. **Valider** la sélection ;
  3. ajuster la **zone finale** : la sélection telle quelle, ou une **zone dessinée** (polygone) qui
     peut couvrir **plusieurs parcelles** ou **une partie seulement** d'une parcelle ou d'un
     bâtiment ; la zone est qualifiée **Bâtiment** ou **Sol** ;
  4. **Valider** avec : nom (ex. « Potager »), lettre (A, B… proposée, modifiable), surface
     (calculée, modifiable — obligatoire à la main pour une partie de bâtiment), références
     cadastrales (déduites des parcelles touchées, modifiables), dont surface bâtie ;
- ainsi de suite pour les autres lignes ; une ligne se modifie ou se retire.

### Étape 3 — Récapitulatif et loyer

Tableau des lignes : lettre, désignation, nature, quantité (m² de bâtiment, ha de terre, ou 1 pour un
forfait), **prix unitaire annuel**, **montant annuel** ; total = **loyer annuel HT hors charges**,
montant par échéance selon la fréquence. Provisions sur charges et dépôt de garantie comme aujourd'hui.

Boutons :

- **Valider** : crée le bail (et sa facture récurrente : une ligne par ligne de bail, BX7) ;
- **Aperçu du bail (PDF)** : texte du modèle rempli, tableau et carte (BX9) ;
- **Envoyer à la signature** (Docuseal, BX5) — possible après validation.

## 4. Exigences fonctionnelles

### Biens et carte

- **BF1** Une ligne de bail porte : lettre, désignation, nature (bâtiment / sol / forfait), surface,
  dont surface bâtie, références cadastrales (0..n), géométrie (facultative : absente en cas A).
- **BF2** Parcelles : interrogation de Lexicon au point cliqué ; plusieurs parcelles par ligne.
- **BF3** Bâtiments : couche IGN BD TOPO, plusieurs bâtiments par ligne.
- **BF4** Zone dessinée : polygone libre, surface calculée, parcelles touchées retrouvées pour les
  références cadastrales ; qualifiée Bâtiment ou Sol.
- **BF5** Partie de bâtiment ou de zone : surface saisie à la main, la géométrie reste celle du
  bâtiment ou de la zone.
- **BF6** Carte centrée sur l'adresse de l'organisation (géocodage de l'adresse) ; à défaut, sur la
  première parcelle du bail ou la France.
- **BF7** La carte du bail (zones lettrées sur photo aérienne) est **figée en image** à la validation
  et reproduite dans le PDF.

### Modèles et document

- **BF8** Un modèle par type de bail (BX4) et par instance, livré pré-rempli (le bail dérogatoire
  reprend le bail ODT actuel de la SCI ; les autres, un texte de base à faire relire).
- **BF9** Champs disponibles : bailleur (raison sociale, SIREN, RCS, siège), preneur (nom, forme,
  identifiant, siège), lieu des biens, tableau des biens, carte, date d'effet, fin, durée, loyer
  annuel et sa décomposition, fréquence, dépôt de garantie, charges, indice de révision, lieu et date
  de signature, signataires.
- **BF10** Modèles modifiables dans les Paramètres (administrateur de l'instance).
- **BF11** Le texte d'un bail est généré depuis le modèle à la validation, puis **retouchable** pour
  ce bail seul (modifier le modèle ne change pas les baux déjà générés).
- **BF12** PDF généré comme les autres documents de Lyvre (aperçu à tout moment ; version figée
  envoyée à la signature et conservée).

### Signature (Docuseal)

- **BF13** Intégration **Docuseal** de l'instance : URL du serveur, jeton ; bouton de test de
  connexion ; désactivable comme les autres intégrations.
- **BF14** **Envoyer à la signature** : PDF figé envoyé à Docuseal, signataires = gérants (registre
  des associés, adresse e-mail obligatoire) puis preneur (e-mail de la fiche tiers) ; ordre de
  signature gérants → preneur.
- **BF15** Statut du bail : brouillon → envoyé → signé (ou refusé / expiré) ; date d'envoi, de
  signature par signataire.
- **BF16** Suivi : rafraîchi à l'ouverture du bail et par un bouton ; une fois signé, le **PDF signé**
  et le certificat Docuseal sont rangés sur le bail.
- **BF17** Un bail envoyé n'est plus modifiable dans ses termes (désignation, loyer, texte) sans
  annuler l'envoi (archivage de la soumission Docuseal).

### Facturation

- **BF18** Loyer annuel = somme des lignes ; montant de l'échéance = annuel ÷ nombre d'échéances
  par an (arrondi au centime, écart d'arrondi sur la dernière ligne).
- **BF19** La facture récurrente du bail porte une ligne par ligne de bail (« Loyer {période} —
  A Potager… ») plus la provision sur charges.
- **BF20** Les baux existants (une seule ligne `unit_label` + loyer) restent valides et sont
  présentés comme un bail à une ligne forfaitaire.

## 5. Exigences non fonctionnelles

- **NF1 Confidentialité** : jetons Docuseal chiffrés comme les autres secrets ; jamais versionnés,
  jamais dans les journaux. Les tests n'appellent jamais Docuseal ni Lexicon/IGN réels (faux clients).
- **NF2 Envois réels** : en local, aucun envoi à la signature sans accord explicite ; copies de
  bases réelles servies sans identifiants Docuseal (même règle que Qonto).
- **NF3 Disponibilité des services** : Lexicon ou l'IGN indisponible → message clair, le cas A et
  la saisie manuelle restent possibles ; les données saisies ne sont pas perdues.
- **NF4 Robustesse Lexicon** : les points `…/geolocation.geojson` répondent aujourd'hui
  `[object Object]` ; s'appuyer sur `tools/parcel-identifier.json` (contour inclus) et signaler le
  défaut à l'équipe Lexicon.
- **NF5 Accessibilité** : chaque action de la carte a un équivalent hors carte (ajout de parcelle
  par section et numéro, saisie manuelle des lignes).
- **NF6 Mobile** : consultation et signature possibles ; la composition sur carte vise l'ordinateur.
- **NF7 Licences et attributions** : mentions IGN, Lexicon (osfarm) et fond de carte affichées sur
  la carte et dans le PDF.

## 6. Récits utilisateur et critères d'acceptation

- **U1 — Bail d'une maison (cas A)** : en tant que gérant·e, je crée un bail d'habitation pour une
  maison, sans carte, en trois étapes. *Accepté si* : une ligne saisie à la main, loyer annuel calculé,
  PDF au modèle « Habitation », facture récurrente créée.
- **U2 — Bail Preneur Exemple (cas B)** : je reproduis le bail dérogatoire actuel : six éléments (A potager,
  B bureau, C salle de préparation, D et E terres, K forage) choisis sur la carte de Saint-Porchaire.
  *Accepté si* : 155 m² bâtis à 2 €/m²/an et 1,56 ha à 140 €/ha/an donnent 528,40 €/an ; le PDF
  contient le texte du modèle dérogatoire, le tableau et la carte lettrée.
- **U3 — Zone à cheval** : je dessine une zone de 500 m² de sol sur deux parcelles. *Accepté si* :
  surface calculée, les deux références cadastrales reprises.
- **U4 — Partie de bâtiment** : je loue 40 m² d'un bâtiment de 115 m². *Accepté si* : le bâtiment est
  sélectionné, la surface saisie à la main (40 m²) est celle facturée.
- **U5 — Retouche** : je modifie un article pour ce seul bail. *Accepté si* : le modèle n'est pas
  changé, l'aperçu montre la retouche.
- **U6 — Signature** : j'envoie le bail ; les deux gérants puis le preneur reçoivent l'invitation.
  *Accepté si* : statut « envoyé », puis « signé » après rafraîchissement, PDF signé sur le bail.
- **U7 — Sans service** : Lexicon ne répond pas. *Accepté si* : message, ajout manuel de lignes
  possible, rien de perdu.

## 7. Points tranchés (25/10/2026)

| # | Point | Réponse |
|---|-------|---------|
| BX11 | Relecture juridique des modèles commercial 3-6-9, habitation, rural / prêt à usage | Par l'utilisateur (gérant) ; les modèles livrés sont des bases à relire |
| BX12 | Gérant sans e-mail | Ne se produit pas : un gérant a toujours un e-mail ; l'envoi est refusé avec un message si ce n'était pas le cas |
| BX13 | Avenants | Hors périmètre |
| BX14 | Révision du loyer (ILC, IRL, fermage) | **Calculée et appliquée automatiquement** aux échéances (voir BF21–BF23) |
| BX15 | Annexes | Non jointes : diagnostics et état des lieux restent hors Lyvre |
| BX16 | Docuseal en production | Chaque instance paramètre **son** serveur dans l'intégration (URL, clé d'API…) ; le serveur peut être partagé ou non |
| BX17 | Défaut des points GeoJSON de Lexicon | Correctif proposé : osfarm/lexicon-rest-api#29 (la cause est dans `API.ts` : un objet renvoyé tel quel devient « [object Object] ») ; demande d'un point d'accès aux **contours des bâtiments** (déjà en base Lexicon, `registered_cadastral_buildings`) : osfarm/lexicon#6 — d'ici là BX2 (IGN) |

### Révision automatique du loyer (BX14)

- **BF21** Le bail porte : indice (ILC, ILAT, IRL, indice des fermages ou aucun), indice de référence
  (trimestre et valeur), périodicité de révision (annuelle, triennale) et date anniversaire.
- **BF22** À chaque date de révision, Lyvre calcule le nouveau loyer
  (loyer × nouvel indice ÷ indice de référence, chaque ligne de bail révisée dans la même proportion),
  l'applique aux échéances suivantes de la facture récurrente, garde l'historique (date, indices,
  ancien et nouveau loyer) et met à jour le dépôt de garantie si le bail le prévoit.
- **BF23** Les valeurs d'indices sont saisies dans Lyvre (table des indices publiés par l'INSEE ou
  l'arrêté préfectoral pour les fermages) ; une révision dont l'indice n'est pas encore connu est
  signalée « en attente » et appliquée dès la saisie de l'indice. Une lettre d'information au preneur
  peut être produite (PDF).
