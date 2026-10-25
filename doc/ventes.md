# Ventes

Devis, factures et avoirs émis par l'application, encaissements, relances, factures récurrentes,
baux et quittances — avec ou sans Qonto. Menu **Ventes** : Factures, avoirs et devis ; À émettre ;
Factures récurrentes ; Baux et quittances. (Les abonnements d'achat sont dans
[Factures d'achat](achats.md#abonnements).)

## Avant la première facture

Configuration › Structure :

- onglet **Identité** : dénomination, SIREN, adresse (obligatoires sur une facture) et **mentions
  légales** — forme juridique, capital, greffe du RCS, n° de TVA intracommunautaire (obligatoire si
  l'exercice est soumis à la TVA). Ce sont les seules : factures et baux les reprennent (« 840 968 499
  RCS Saintes », `organization.rcs_mention`) ;
- onglet **Facturation** : IBAN / BIC, délai de paiement (30 jours par défaut), pénalités de retard,
  indemnité de 40 € (clients professionnels), escompte, logo, pied de page, messages d'envoi et de
  relance. Les mentions légales y sont rappelées en lecture.

Exercices : **TVA** soumis ou non ; pour les prestations de services, TVA exigible **à
l'encaissement** (par défaut) ou **d'après les débits** (bouton « Option TVA sur les débits »).
Non soumis : les factures portent « TVA non applicable, art. 293 B du CGI ».

Catalogue (Compta › Catalogue) : un produit de vente porte son compte (7…), sa TVA, son prix HT,
son unité, sa description et sa nature (biens ou services).

## Facture

1. **Ventes › Nouvelle facture** : client (ou nouveau client, à compléter ensuite sur sa fiche —
   l'adresse est obligatoire), date, échéance (vide : délai par défaut), période de prestation,
   référence client, nature de l'opération ; lignes du catalogue ou libres (quantité, unité, prix
   HT, remise, TVA, compte de vente — 706 par défaut). Totaux estimés pendant la saisie.
2. Le **brouillon** se modifie, se supprime, a un **aperçu PDF** ; la fiche liste ce qui manque
   avant l'émission (mentions, adresse du client, exercice…).
3. **Émettre** : numéro définitif `F-AAAA-NNNN` (continu, par année), écriture au journal **VE**
   (411NNN du client / 7… / TVA), **PDF Factur-X** conservé. La facture ne se modifie ni ne se
   supprime plus ; son écriture non plus (écran Écritures).
4. **Envoyer** : email au client (destinataires, copie, objet et message modifiables), PDF joint —
   par l'intégration SMTP (ou par Qonto pour une facture Qonto). Aussi par sélection dans la liste.

**Avoir** : depuis une facture émise, toutes ou certaines lignes, avec un motif ; brouillon
modifiable puis émis `AV-AAAA-NNNN` (écriture inverse). Quand les avoirs atteignent le montant de
la facture, elle est **annulée**.

## Comptabilisation

| Opération | Écriture |
|---|---|
| Facture | 411NNN débit TTC ; 7… crédit HT ; 44571 (biens, ou TVA sur les débits) / 44574 (services, TVA à l'encaissement) crédit TVA |
| Avoir | Inverse |
| Encaissement | Banque (BQ) ou caisse (CA) débit ; 411NNN crédit ; TVA encaissée virée de 44574 à 44571 au prorata |

Le compte client 411NNN est créé à la première facture et noté sur la fiche du tiers ; 44571 et
44574 sont créés sous 4457 s'ils manquent.

## Encaissements et relances

- **Encaisser** (fiche d'une facture) :
  - **Transaction bancaire** : crédits proposés autour de la facture (montant exact et même client
    d'abord) ; les écritures de règle de catégorisation (pièce 411000 / 7… et règlement) sont
    remplacées ;
  - **Chèque, espèces…** : montant, date, banque ou caisse.
- **Rapprocher les encaissements** (liste) : une facture dont le restant dû est égal à un seul
  crédit bancaire, candidat d'elle seule, est encaissée — aussi après chaque import OFX et
  synchronisation Qonto.
- La facture passe **Payée en partie** puis **Payée** ; « Défaire » supprime l'encaissement et son
  écriture.
- **Relancer** : facture échue non soldée, depuis sa fiche ou une sélection (filtre « Échues ») ;
  message de relance (restant dû, échéance) et PDF joint ; nombre et date des relances suivis.

Tableau de bord : facturé de l'exercice (HT, avoirs déduits), encours clients, factures échues.

## Devis

**Nouveau devis** (onglet Devis) : comme une facture, avec une date de validité (30 jours par
défaut). Émis `D-AAAA-NNNN`, PDF avec « Bon pour accord » ; pas d'écriture. **Accepté** ou
**Refusé** ; « Expiré » quand la validité est passée. **Transformer en facture** : brouillon de
facture reprenant le devis (« Devis D-… » en référence) ; le devis devient **Facturé** (de nouveau
Accepté si ce brouillon est supprimé).

## Factures récurrentes

Ventes › Factures récurrentes : client, lignes, **périodicité** (mensuelle, trimestrielle,
annuelle), **jour d'échéance** (1 à 28), début, fin, terme **à échoir** ou **échu**.
`{periode}` dans une désignation devient la période (« octobre 2026 », « T4 2026 », « 2026 »).

**À émettre** : à l'ouverture, chaque échéance arrivée est préparée en brouillon — jamais deux fois
— datée du jour et payable à l'échéance. On les vérifie, puis **Émettre** (ou **Émettre et
envoyer**) en lot.

## Baux et quittances

**Nouveau bail** : un assistant en trois étapes, enregistré en **brouillon** à chaque étape (un
brouillon se reprend depuis la liste des baux, il se supprime tant qu'il n'est pas validé).

1. **Bail** : locataire (preneur), **type** (dérogatoire commercial, commercial 3-6-9, habitation,
   rural / prêt à usage), désignation (reprise sur les avis d'échéance), lieu-dit et adresse des
   biens, date d'effet, fin, dépôt de garantie, **révision** (indice ILC, ILAT, IRL ou fermages,
   indice de référence, annuelle ou triennale — appliquée automatiquement dans un lot à venir),
   lieu de signature.
2. **Biens loués** : une ligne par élément (parcelle, bâtiment, zone) : **lettre** (A, B… proposée),
   désignation, nature (bâtiment, sol, forfait), surface louée, dont surface bâtie, références
   cadastrales, « partie seulement ». **Avec carte** : photo aérienne IGN centrée sur l'adresse de
   la structure ;
   - **Parcelles** (cadastre IGN, à partir du zoom 16) : cliquer une ou plusieurs parcelles ; la
     fiche **Lexicon** de chacune donne sa surface et l'emprise de ses bâtiments ;
   - **Bâtiments** (BD TOPO de l'IGN) : cliquer un ou plusieurs bâtiments ;
   - **Dessiner** : une zone libre (Sol ou Bâtiment), à cheval sur plusieurs parcelles ou sur une
     partie seulement ; surface calculée, parcelles touchées reprises ;
   - « Ajouter une parcelle par référence » (AH 248) sans cliquer la carte.

   **Valider la sélection** ouvre la ligne pré-remplie (surface, dont bâti, références, contour) :
   nom, lettre, « partie seulement » (surface saisie à la main) à compléter. Les biens déjà saisis
   sont dessinés en bleu avec leur lettre. Services indisponibles : message, saisie **Sans carte**
   toujours possible.
3. **Loyer** : **prix annuel HT** par ligne — au m² (bâtiments), à l'hectare (sols, surface
   arrondie à l'are : 4 940 m² → 0,49 ha) ou au forfait ; **loyer annuel** = somme des lignes ;
   périodicité, jour d'échéance, provisions sur charges, TVA, comptes des loyers et des charges
   (706 / 708 par défaut — à valider avec l'expert-comptable). **Valider le bail** crée la facture
   récurrente : **une ligne « Loyer {période} — A Potager » par ligne de bail** (montant annuel
   divisé par le nombre d'échéances, écart d'arrondi sur la dernière ligne ; une ligne à 0 € n'est
   pas facturée) et la provision sur charges ; les avis d'échéance arrivent dans « À émettre ».

La **carte du bail** (photo aérienne IGN, zones lettrées, « © IGN ») est rendue par le serveur et
placée dans le texte (`{{ biens.carte }}`) ; elle n'est refaite que si les zones changent.

**Texte du bail** : à la validation, le texte est **rédigé depuis le modèle** du type de bail
(Configuration › **Modèles de bail**) et **figé** dans le bail : modifier ensuite le modèle ne change
pas les baux déjà rédigés. Sur la fiche : **Aperçu (PDF)** (tableau des biens, décomposition du loyer,
pied de page « Page x / y — paraphes »), **Retoucher** (pour ce bail seul ; un texte contenant un
tableau se retouche en source HTML), **Régénérer** (depuis le modèle et les données actuelles ; les
retouches sont perdues). L'étape 3 de l'assistant propose aussi l'aperçu avant validation.

**Signature électronique** (intégration **Documenso**, voir [serveur Documenso](signature_documenso.md)) :
sur la fiche d'un bail validé, **Envoyer à la signature** — les **gérants** (Associés, case « Gérant », e-mail de leur fiche tiers), dans
l'ordre du registre, puis le **preneur** (e-mail de sa fiche, sinon de facturation) reçoivent
l'invitation de Documenso, l'un après l'autre. Le PDF envoyé est conservé ; chaque case du bloc de
signatures porte le champ de signature (un texte rédigé avant cette version reçoit une page de
signatures en fin de document) et chaque page a, en bas à droite, une case de **paraphe** par
signataire. Statut relu à l'ouverture de la fiche (au plus une fois par
minute) ou par **Actualiser** ; signé, le **PDF signé** et le **journal d'audit** sont rangés avec le
bail. Un bail envoyé ou signé **n'est plus modifiable** (termes, biens, loyer, texte) ; **Annuler
l'envoi** l'annule chez Documenso et rend le bail modifiable ; après un refus, le bail se corrige et
se renvoie. Fin du bail et dépôt de garantie restent possibles.

**Modèles de bail** (administrateur de l'instance) : un modèle par type, livré pré-rempli — le bail
dérogatoire reprend le bail de la SCI ; commercial 3-6-9, habitation et rural sont des **bases à
relire** (bandeau « à relire » tant que le modèle n'a pas été enregistré une fois, mentions entre
crochets à compléter). Les champs `{{ … }}` (menu « Insérer un champ ») : `bailleur.identite`,
`preneur.identite`, `biens.situation`, `biens.tableau`, `biens.lettres`, `bail.debut`, `bail.fin`,
`bail.duree`, `loyer.annuel`, `loyer.annuel_lettres`, `loyer.detail`, `loyer.echeance`,
`loyer.frequence`, `charges.montant`, `depot.montant`, `indice.nom`, `indice.reference`,
`indice.periodicite`, `signature.lieu`, `signature.date`, `signatures`… ; conditions possibles
(`{% if depot.montant %}…{% else %}…{% endif %}`). Un champ inconnu est signalé à l'aperçu. Aperçu
d'un modèle (même non enregistré) sur un bail existant ; **Rétablir le modèle livré**.

**Révision du loyer** (indice choisi à l'étape 1 : ILC, ILAT, IRL ou fermages, indice de
référence, annuelle ou triennale) : à la date prévue, Lyvre prend l'indice de la **même période**
un ou trois ans plus tard (2025-T2 → 2028-T2 en triennal), multiplie le prix de chaque ligne par
nouvel indice ÷ indice de référence (au centime), met à jour la facture récurrente pour les
échéances **pas encore préparées**, révise le dépôt de garantie si la case est cochée, et prend le
nouvel indice comme référence. La révision se fait avant la préparation des échéances (page « À
émettre ») ; un bail signé est révisé aussi. Indice pas encore publié : révision **en attente**,
appliquée dès qu'il est connu. Fiche du bail › **Révision du loyer** : historique et **courrier** au
preneur (PDF : indices, ancien et nouveau loyer, date d'effet).

**Ventes › Indices de loyer** : ILC, ILAT et IRL lus à l'**INSEE** (séries publiques ; bouton
« Mettre à jour depuis l'INSEE », et relecture automatique au plus une fois par jour quand une
révision attend) ; **indice national des fermages** saisi chaque année (arrêté) ; une valeur saisie
corrige celle de l'INSEE.

**Modifier** (fiche du bail) rouvre l'assistant : un changement de lignes ou de prix met à jour la
facture récurrente pour les échéances suivantes. Les baux créés avant l'assistant ont une ligne
forfaitaire (loyer d'échéance × nombre d'échéances par an).

Les **gérants** (Associés › case « Gérant ») et la **forme juridique** et le **greffe du RCS**
(Configuration › Structure) serviront à la rédaction et à la signature des baux.

- **Dépôt de garantie** : « Encaisser le dépôt » — banque ou caisse au débit, **165** au crédit.
- **Quittance** : sur un avis d'échéance **payé**, bouton « Quittance » — loyer et charges
  distingués, période, montant reçu ; paiement partiel : **reçu** (ne vaut pas quittance). PDF
  conservé sur la fiche du bail, **Envoyer** au locataire.

Hors périmètre pour l'instant : régularisation annuelle des charges. À venir (conception
`claudedocs/design_baux.md`) : avenants, régularisation annuelle des charges.

## Avec Qonto

Configuration › Intégrations › Qonto : cocher **Ventes** dans le périmètre. Une case **Émettre avec
Qonto** (décochée par défaut) apparaît sur la facture, le devis, la facture récurrente et le bail :

- la pièce est créée dans Qonto (client cherché par SIREN, TVA, email ou nom, sinon créé), puis
  finalisée : **Qonto donne le numéro** et produit le PDF Factur-X, récupéré dès qu'il est prêt ;
  l'écriture est passée ici avec ce numéro (la série de l'application n'avance pas) ;
- l'avoir d'une facture Qonto est émis par Qonto ; l'envoi passe par Qonto ;
- un encaissement qui solde une facture Qonto la **marque payée dans Qonto** ;
- **Synchroniser Qonto** (liste) lit Qonto : clients et produits, devis et factures créés dans
  Qonto (factures comptabilisées), statuts, PDF.

Qonto limite le libellé d'une ligne à 40 caractères (la suite passe en description) ; une remise
est incluse dans le prix unitaire.

## Droits

Administrateur et trésorier saisissent, émettent, encaissent, envoient ; l'expert-comptable
consulte. Réglages de facturation et périmètre Qonto : administrateur de l'instance.
