# Conception — rédaction de bail assistée (carte, modèles, signature, révision)

> Statut : **L1 à L3 réalisés** (25/10/2026). L3 : `geodata` (IGN parcelles et bâtiments par emprise, fiche Lexicon au clic et à l'ajout par référence, géocodage), routes `/geo`, carte de l'assistant (Leaflet 1.9.4, Geoman 2.20.2, Turf 7.4.0, morceau chargé à la demande), zone dessinée Sol / Bâtiment, image figée (WMS IGN + Pillow) dans le texte et le PDF. Écarts L3 : pas de colonnes `organization.latitude/longitude` ni `leases.map_path` — le géocodage est mis en cache en mémoire et l'image est nommée par l'empreinte des zones (`lease-map:carte-<empreinte>.png` dans le texte, seule image admise par l'assainissement et le PDF) ; hectares de la fiche Lexicon utilisés pour « dont bâti » d'une sélection de parcelles. L2 : modèles (dérogatoire repris du bail ODT, trois bases à relire), Configuration › Modèles de bail (éditeur, champs, aperçu, rétablir), texte figé à la validation, retouche et régénération, PDF (pied de page, paraphes). Écarts L2 : champs composés `bailleur.identite`, `preneur.identite`, `biens.situation` (modèles lisibles sans conditions) ; l'assainissement garde les classes (styles du PDF) ; un texte contenant un tableau se retouche en source HTML (l'éditeur riche ne gère pas les tableaux) ; le bloc `signatures` n'a pas encore les balises Docuseal (L4). L1 : lignes de bail, brouillon, assistant en trois étapes sans
> carte, facture récurrente à une ligne par ligne de bail, gérants, forme juridique et greffe. Écarts :
> la facturation (périodicité, échéance, charges, TVA, comptes) est saisie à l'**étape 3** (un brouillon
> n'a pas de facture récurrente qui la porterait) ; surfaces à l'hectare **arrondies à l'are** (0,01 ha)
> par ligne, comme le bail actuel (1,56 ha → 528,40 €) ; colonnes `document_html`, `map_path`,
> `organization.latitude/longitude` et tables des lots suivants créées avec leur lot. Suite : L2. Besoins : `claudedocs/besoins_baux.md`
> (BX1–BX17, BF1–BF23, NF1–NF7, U1–U7). Suite : `/sc:implement L1`.

## 1. Choix structurants

| # | Choix | Raison |
|---|---|---|
| L-C1 | **Bail brouillon dès l'étape 1** : « Suivant » enregistre le bail (`status = draft`, sans facture récurrente) ; chaque ligne validée à l'étape 2 est enregistrée ; « Valider » (étape 3) **active** le bail (document, carte figée, facture récurrente) | La composition sur carte est longue : rien n'est perdu (NF3), un brouillon se reprend plus tard |
| L-C2 | **Lignes de bail** (`lease_items`) : lettre, désignation, nature, surfaces, unité de facturation, prix annuel, références cadastrales, géométrie GeoJSON | BF1 ; le loyer se déduit des lignes (BX7), la carte et le tableau du PDF aussi |
| L-C3 | **Sources géographiques** : contours des parcelles affichées et des bâtiments par l'**IGN Géoplateforme** (WFS, par emprise) ; **fiche de la parcelle choisie par Lexicon** (`tools/parcel-identifier.json` : surface officielle, nombre et emprise des bâtiments, commune) ; géocodage IGN | Lexicon ne répond qu'à un point (pas de couche) ; même identifiant de parcelle des deux côtés (`17387000AH0248`) ; quand osfarm/lexicon-rest-api#29 et osfarm/lexicon#6 seront livrés, la couche des parcelles et les bâtiments pourront passer par Lexicon (fournisseur interchangeable) |
| L-C4 | **Appels géographiques par le serveur Lyvre** (`/api/v1/geo/...`, délai borné, petit cache) ; seules les **tuiles de la photo aérienne** sont chargées directement par le navigateur (WMTS IGN) | Un seul endroit pour les délais, erreurs et fournisseurs ; les tests remplacent un client Python |
| L-C5 | Carte : **Leaflet** + **Leaflet-Geoman** (sélection, dessin, édition de polygones) + **Turf** (surface, intersection zone ↔ parcelles), chargés seulement par l'assistant (morceau séparé) | Bibliothèques libres, légères, éprouvées ; l'outil Lexicon utilise Leaflet |
| L-C6 | **Image de la carte rendue par le serveur** à l'activation : photo aérienne IGN (WMS, emprise des lignes + marge, Web Mercator) + zones et lettres dessinées avec Pillow ; PNG rangé avec le bail | Pas de capture d'écran du navigateur (CORS, résolution) ; image reproductible pour le PDF (BF7, BX9) |
| L-C7 | **Modèles en HTML** (éditeur Tiptap déjà utilisé) avec champs **Jinja en bac à sable** (`SandboxedEnvironment`, échappement, champ inconnu = erreur lisible) ; texte du bail **figé** dans le bail à l'activation, retouchable ensuite | BX3, BF8–BF11 ; même rendu PDF que les autres documents (WeasyPrint) |
| L-C8 | **Docuseal** = intégration de l'instance (`url`, `api_key`) ; envoi par `POST {url}/api/submissions/pdf` (PDF en base64, **balises de champ** `{{…;role=…;type=signature}}` dans le bloc de signature, ordre `preserved`) ; suivi par `GET /api/submissions/{id}` | BX5, BX6, BX10, BX16 ; aucun modèle à gérer côté Docuseal |
| L-C9 | **Révision appliquée au moment où les échéances sont préparées** (`recurrence.prepare_due`) ; indices **ILC, ILAT, IRL lus à l'INSEE** (série BDM publique, sans clé) et **indice des fermages saisi** ; une révision sans indice connu reste **en attente** | BX14, BF21–BF23 ; même déclencheur que la facturation, rien de planifié en plus |
| L-C10 | Les **baux existants** deviennent des baux actifs à **une ligne forfaitaire** (migration) | BF20 : rien ne casse (quittances, factures, dépôt) |

## 2. Flux

```
Étape 1  POST /leases (status=draft) ─────────────────────────────┐
Étape 2  carte : WMTS IGN (tuiles)                                 │
         /geo/parcels?bbox  ─► IGN WFS parcellaire express         │
         /geo/buildings?bbox ─► IGN WFS BD TOPO bâtiment           │  lease_items
         /geo/parcel?lat,lon ─► Lexicon parcel-identifier          │  (une ligne
         Turf : surface, parcelles touchées par une zone            │   à la fois)
         POST/PATCH/DELETE /leases/<id>/items ─────────────────────┤
Étape 3  PATCH items (prix) ; GET /leases/<id>/preview.pdf          │
         POST /leases/<id>/activate ─► carte figée (WMS + Pillow)   │
                                     ─► texte généré (modèle)        │
                                     ─► facture récurrente (lignes) ─┘
Signature POST /leases/<id>/signature ─► PDF figé ─► Docuseal /api/submissions/pdf
          GET  /leases/<id>  (statut actualisé si envoyé, ≥ 1 min)  ─► GET /api/submissions/{id}
          signé ─► PDF signé + journal d'audit rangés
Révision  GET /sales/due ─► leases.revise_due() ─► recurrence.prepare_due()
```

## 3. Données

### 3.1 `leases` (colonnes ajoutées)

| Colonne | Type | Rôle |
|---|---|---|
| `status` | `draft` \| `active` | L-C1 ; les baux existants : `active` |
| `kind` | `derogatory` \| `commercial` \| `residential` \| `rural` \| NULL | Type (BX4) ; NULL pour les baux repris |
| `premises_label` | texte | Lieu-dit, adresse des biens (« La Vauzelle ») — l'adresse existante reste |
| `signed_on_place` | texte | « Fait à … » (défaut : ville de l'organisation) |
| `document_html` | texte | Texte du bail généré puis retouché (BF11) |
| `document_kind_version` | entier | Version du modèle utilisé (information) |
| `map_path` | texte | Image de la carte (L-C6) |
| `index_code` | `ILC` \| `ILAT` \| `IRL` \| `FERMAGES` \| NULL | Indice de révision (BF21) |
| `index_reference_period` | texte | « 2025-Q2 » ou « 2025 » (fermages) |
| `index_reference_value` | décimal (2) | Valeur de l'indice de référence |
| `revision_months` | entier | 12 ou 36 |
| `next_revision_date` | date | Prochaine révision (date d'effet + périodicité) |
| `revise_deposit` | booléen | Dépôt de garantie révisé dans la même proportion |

`unit_label` reste (désignation courte, libellé des factures) ; `rent_cents` reste le **loyer d'une
échéance**, recalculé depuis les lignes.

### 3.2 `lease_items` (nouvelle)

| Colonne | Type | Rôle |
|---|---|---|
| `id`, `lease_id` (CASCADE), `position` | | |
| `letter` | texte (3) | A, B… (proposée, modifiable, unique par bail) |
| `label` | texte | « Potager » |
| `nature` | `building` \| `land` \| `flat` | Bâtiment, sol, forfait |
| `area_m2` | entier | Surface louée (calculée ou saisie, BF5) |
| `built_m2` | entier | Dont surface bâtie |
| `billing_unit` | `m2` \| `ha` \| `flat` | Unité du prix |
| `unit_price_cents` | entier | Prix annuel HT par unité |
| `annual_cents` | entier | Montant annuel (calculé : m² × prix, ha = m² / 10 000 × prix, forfait) |
| `cadastral_refs` | JSON | `["17387000AH0248", …]` (affichés « AH 248 ») |
| `geometry` | JSON | GeoJSON (Polygon / MultiPolygon, WGS84) ; NULL en cas A |
| `source` | `parcels` \| `buildings` \| `drawn` \| `manual` | Origine de la géométrie |
| `partial` | booléen | Partie seulement du bâtiment ou de la zone (surface saisie) |

### 3.3 Autres tables

- **`lease_templates`** : `kind` (unique), `title`, `body_html`, `version`, `updated_at`,
  `updated_by_id`. Rempli au premier usage depuis les modèles livrés
  (`app/templates/leases/defaults/<kind>.html`) ; « Rétablir le modèle livré ».
- **`lease_signatures`** : `lease_id`, `provider` (`docuseal`), `submission_id`, `status`
  (`sent` \| `completed` \| `declined` \| `expired` \| `cancelled`), `sent_at`, `completed_at`,
  `sent_pdf_path`, `signed_pdf_path`, `audit_pdf_path`, `checked_at`, `error`.
- **`lease_signers`** : `signature_id`, `position`, `role` (« Bailleur 1 », « Preneur »), `name`,
  `email`, `associate_id` / `entity_id`, `submitter_id`, `status`, `signed_at`, `declined_at`.
- **`rent_indices`** : `code`, `period`, `value` (décimal 2), `source` (`insee` \| `manual`),
  `fetched_at` ; unique (`code`, `period`).
- **`lease_revisions`** : `lease_id`, `due_date`, `index_code`, `old_period`, `old_value`,
  `new_period`, `new_value`, `old_annual_cents`, `new_annual_cents`, `old_deposit_cents`,
  `new_deposit_cents`, `status` (`pending` \| `applied`), `applied_at`, `letter_pdf_path`.
- **`associates.is_manager`** (booléen) : gérant, signataire côté bailleur (BX5) ; e-mail lu sur la
  fiche tiers de l'associé (BX12 : refus clair s'il manque).
- **`organization`** : `latitude`, `longitude` (géocodage mis en cache, effacé si l'adresse change),
  `legal_form` (« Société civile immobilière »), `rcs_city` (« Saintes ») — champs du bailleur.

### 3.4 Migration

Une migration Alembic : colonnes et tables ci-dessus ; chaque bail existant reçoit `status = active`
et une ligne `flat` « {unit_label} » dont `annual_cents = rent_cents × échéances par an`.
Rien n'est touché aux factures récurrentes existantes (leurs lignes restent jusqu'à une modification).

## 4. Services

### 4.1 `leases` (étendu)

| Fonction | Rôle |
|---|---|
| `create_draft(data)` | Étape 1 : bail `draft` (contrôles actuels, sans loyer ni récurrence) |
| `save_item(lease, data)` / `delete_item(item)` | Ligne : lettre unique, nature, surfaces ≥ 0, unité ; `annual_cents` recalculé |
| `annual_total(lease)` / `period_amounts(lease, frequency)` | Loyer annuel ; montant d'échéance par ligne (annuel ÷ échéances par an, **écart d'arrondi sur la dernière ligne**, BF18) |
| `activate(lease, data)` | Contrôles (≥ 1 ligne, prix saisis, type), carte figée (`lease_map.render`), texte (`lease_documents.generate`), récurrence avec **une ligne par ligne de bail** + provision sur charges (BF19), `rent_cents`, `next_revision_date` ; `status = active` |
| `update(lease, data)` | Bail actif : termes modifiables tant qu'**aucune signature n'est envoyée** (BF17) ; lignes de la facture récurrente reconstruites |

Les lignes de la facture récurrente : « Loyer {periode} — A Potager » (prix d'échéance de la ligne),
compte de loyer du bail.

### 4.2 `geodata` (nouveau) — fournisseurs géographiques

| Fonction | Source | Retour |
|---|---|---|
| `geocode(address)` | IGN `data.geopf.fr/geocodage/search` | `(lat, lon, label, score)` |
| `parcels(bbox)` | IGN WFS `CADASTRALPARCELS.PARCELLAIRE_EXPRESS:parcelle` | FeatureCollection (`idu`, section, numéro, contenance) |
| `buildings(bbox)` | IGN WFS `BDTOPO_V3:batiment` | FeatureCollection (`cleabs`, nature, usage, surface calculée) |
| `parcel_at(lat, lon)` | Lexicon `tools/parcel-identifier.json` | `idu`, surface, nombre et emprise des bâtiments, commune, contour |
| `parcel_by_ref(insee, section, number)` | Lexicon `cadastral-parcels.json` puis `parcel_at` (centre) | idem (ajout hors carte, NF5) |

- `requests` avec délai (10 s), emprise limitée (≤ 2 km de côté), **cache mémoire** 15 min par
  requête arrondie ; erreurs → `GeoUnavailable("Lexicon ne répond pas…")` traduite en 503 lisible.
- `PROVIDERS` remplaçable dans les tests (faux clients) ; aucun test n'appelle l'IGN ni Lexicon (NF1).

### 4.3 `lease_map` (nouveau) — image figée

- Emprise = union des géométries + 15 % ; projection Web Mercator (EPSG:3857, formule directe, sans
  dépendance) ; image 1600 px de large, hauteur selon l'emprise (≤ 1100 px).
- `GET https://data.geopf.fr/wms-r?…LAYERS=ORTHOIMAGERY.ORTHOPHOTOS&CRS=EPSG:3857&BBOX=…` ;
  Pillow : zones remplies (bleu translucide comme le bail actuel, contour plein), lettre au centre
  de chaque zone, mention « © IGN » en bas (NF7).
- Fichier `instance_dir()/baux/<lease_id>/carte.png` ; refaite à chaque activation ou modification
  des lignes d'un bail non envoyé. Sans géométrie (cas A) : pas d'image, le PDF n'a que le tableau.
- Photo indisponible : image des seules zones sur fond neutre + avertissement (NF3).

### 4.4 `lease_documents` (nouveau) — modèles et PDF

- `template_for(kind)` : modèle de l'instance (créé depuis le modèle livré au premier usage).
- `context(lease)` : champs du modèle (BF9) :

| Champ | Contenu |
|---|---|
| `bailleur.*` | `nom`, `forme`, `siren`, `rcs`, `adresse`, `gerants` (liste nom) |
| `preneur.*` | `nom`, `siret`, `adresse`, `email`, `particulier` (booléen) |
| `biens.lieu`, `biens.adresse` | Lieu-dit, adresse |
| `biens.tableau` | Tableau HTML (lettre, désignation, surface, références cadastrales, dont bâti) — BX9 |
| `biens.carte` | `<img>` de la carte figée (vide en cas A) |
| `biens.lettres` | « A, B, C, D, E et K » |
| `bail.debut`, `bail.fin`, `bail.duree` | Dates longues (« 1er octobre 2025 »), durée en années / mois |
| `loyer.annuel`, `loyer.echeance`, `loyer.frequence`, `loyer.detail` | Montants en toutes lettres et chiffres ; détail par ligne (« 155 m² × 2 €/m²/an = 310 € ») |
| `depot`, `charges` | Montants |
| `indice.nom`, `indice.reference`, `indice.periodicite` | « indice des loyers commerciaux (ILC) », « 2025-T2 : 135,30 » |
| `signature.lieu`, `signature.date` | « Fait à … le … » |
| `signatures` | Bloc des signataires avec les **balises Docuseal** (L-C8), invisible tant que non envoyé |

- `generate(lease)` → `document_html` (rendu Jinja bac à sable, autoescape, `StrictUndefined` :
  « Champ inconnu dans le modèle : {{ loyer.mensuel }} »).
- `render_pdf(lease, for_signature=False)` : gabarit `leases/document.html` (en-tête, styles, numéros de
  page) + `document_html` ; WeasyPrint. `for_signature` : balises Docuseal en clair dans le bloc
  de signature (petites, couleur du fond) — à vérifier sur le serveur de test (L4).
- Modèles livrés : **dérogatoire** repris du bail ODT de la SCI (articles 1 à 16, spécificités
  Preneur Exemple remplacées par des champs) ; commercial 3-6-9, habitation (loi du 6 juillet 1989,
  mentions obligatoires), rural / prêt à usage : textes de base **à relire** (BX11), bandeau
  « Modèle à relire » tant qu'ils n'ont pas été enregistrés une fois.

### 4.5 `docuseal` (nouveau) — signature

- Intégration `docuseal` dans `external_config` : clés `url`, `api_key` (secret), requises toutes
  deux ; repli `.env` en développement : `DOCUSEAL_URL`, `DOCUSEAL_API_KEY` (les deux lignes du
  `.env` local seront renommées) ; sonde : `GET {url}/api/templates?limit=1` (lecture seule ; point 10.2).
- `send(lease)` : PDF `for_signature` figé (`sent_pdf_path`) ; signataires = gérants
  (`is_manager`, ordre du registre) puis preneur (e-mail de la fiche, sinon premier e-mail de
  facturation) ; `POST /api/submissions/pdf` (`order: preserved`, `send_email: true`,
  `external_id: lease-<id>`) ; `lease_signatures` + `lease_signers`.
- `refresh(signature)` : `GET /api/submissions/{id}` ; statuts des signataires ; `completed` →
  `GET /api/submissions/{id}/documents` + `audit_log_url` → fichiers rangés ; `declined` /
  `expired` → statut et message.
- `cancel(signature)` : `DELETE /api/submissions/{id}` (archivage) ; le bail redevient modifiable.
- Webhook (production, plus tard) : `POST /api/v1/webhooks/docuseal/<instance>` avec secret partagé,
  appelle `refresh`.
- NF2 : copies de bases servies **sans** identifiants Docuseal ; en local, aucun envoi sans accord
  explicite ; tests avec un faux client.

### 4.6 `rent_indices` et `lease_revisions` (nouveaux) — révision

- `fetch_insee(codes)` : séries BDM publiques (ILC `001532540`, ILAT `001617112`, IRL `001515333`),
  `https://bdm.insee.fr/series/sdmx/data/SERIES_BDM/<id>?lastNObservations=12` ; enregistre les
  périodes manquantes (`source = insee`). Déclenché par le bouton « Mettre à jour les indices » et,
  au plus une fois par jour, quand une révision est en attente.
- Fermages : saisie manuelle (année, valeur de l'arrêté).
- `revise_due(today)` (appelé avant `prepare_due`) : pour chaque bail actif dont
  `next_revision_date ≤ today` : période cible = période de référence + `revision_months` ;
  indice connu → nouveau prix de chaque ligne = prix × nouveau ÷ référence (arrondi au centime),
  lignes de la facture récurrente mises à jour pour les échéances **non encore préparées**, dépôt
  révisé si prévu, référence = nouvel indice, `next_revision_date += revision_months`, ligne
  `applied` ; indice inconnu → ligne `pending` (une seule), réessayée au passage suivant.
- Courrier au preneur (PDF) : ancien et nouveau loyer, indices, date d'effet.

## 5. API (ajouts, `/api/v1`)

| Méthode | Chemin | Rôle |
|---|---|---|
| POST | `/leases` | `status: draft` si `draft: true` (assistant), sinon comportement actuel |
| GET / PATCH | `/leases/<id>` | Bail + `items`, `signature`, `revisions` ; statut de signature actualisé si envoyé (≥ 1 min) |
| POST / PATCH / DELETE | `/leases/<id>/items[/<item_id>]` | Lignes |
| POST | `/leases/<id>/activate` | Étape 3 « Valider » |
| GET | `/leases/<id>/preview.pdf` | Aperçu (brouillon ou actif) |
| PUT | `/leases/<id>/document` | Texte retouché ; `POST …/document/regenerate` depuis le modèle |
| GET | `/leases/<id>/map.png` | Image figée |
| POST / DELETE | `/leases/<id>/signature` | Envoyer à la signature / annuler l'envoi |
| POST | `/leases/<id>/signature/refresh` | Actualiser le statut |
| GET | `/lease-signatures/<id>/signed.pdf`, `/audit.pdf` | Documents signés |
| GET / PUT | `/lease-templates`, `/lease-templates/<kind>` | Modèles (admin d'instance) ; `POST …/reset` |
| POST | `/lease-templates/<kind>/preview` | Aperçu d'un modèle sur un bail choisi |
| GET | `/geo/geocode?q=`, `/geo/organization` | Centre de la carte (BF6) |
| GET | `/geo/parcels?bbox=`, `/geo/buildings?bbox=` | Couches (GeoJSON) |
| GET | `/geo/parcel?lat=&lon=`, `/geo/parcel?ref=` | Fiche Lexicon |
| GET / POST | `/rent-indices`, `/rent-indices/fetch` | Indices (liste, saisie, mise à jour INSEE) |
| POST | `/lease-revisions/<id>/letter` | Courrier de révision |

Écritures refusées à l'expert-comptable (lecture seule, règle existante).

## 6. Interface

- **Ventes › Baux › Nouveau bail** → assistant `/leases/new` (Mantine `Stepper`) ; un brouillon se
  reprend depuis la liste (`/leases/<id>/edit`, badge « Brouillon »).
  1. **Bail** : formulaire actuel sans loyer + type, lieu-dit, indice et périodicité de révision.
  2. **Biens loués** : choix « Avec carte » / « Sans carte ».
     - *Sans carte* : tableau éditable des lignes.
     - *Avec carte* : carte plein écran (photo aérienne IGN, centrée sur l'organisation), sélecteur
       **Parcelles / Bâtiments / Dessiner une zone (Bâtiment ou Sol)** ; panneau latéral : ligne en cours
       (éléments choisis, surface cumulée, parcelles touchées) → **Valider la sélection** → zone finale
       (telle quelle ou dessinée / ajustée) → **Valider la ligne** (lettre, nom, nature, surface,
       dont bâti, références, « partie seulement ») ; liste des lignes (survol = zone en
       surbrillance, modifier, retirer) ; « Ajouter une parcelle par référence » (NF5).
  3. **Récapitulatif** : tableau (lettre, désignation, quantité, unité, prix annuel, montant), total
     annuel et par échéance ; **Valider**, **Aperçu du bail (PDF)**, **Envoyer à la signature**
     (actif après validation).
- **Fiche du bail** : onglets *Bail* (actuel), *Biens* (tableau + carte), *Document* (aperçu, retouche
  Tiptap, régénérer), *Signature* (signataires, statuts, actualiser, annuler, PDF signé),
  *Révisions* (historique, en attente, courrier).
- **Paramètres › Modèles de bail** : un modèle par type, éditeur Tiptap + liste des champs
  insérables, aperçu sur un bail.
- **Paramètres › Indices de loyer** : valeurs par indice, « Mettre à jour depuis l'INSEE », saisie
  des fermages.
- **Registre des associés** : case « Gérant ».
- **Intégrations** : fiche Docuseal (URL, clé, tester).

## 7. Sécurité et confidentialité

- Clé Docuseal chiffrée comme les autres secrets, masquée dans l'interface et les messages ; jamais
  dans les journaux ni le dépôt (le jeton de test reste dans `.env`).
- IGN, Lexicon, INSEE : données publiques ; seules des coordonnées, emprises et références
  cadastrales sortent de Lyvre. Docuseal reçoit le bail (données personnelles) : serveur choisi
  par l'instance (BX16).
- Modèles : Jinja en bac à sable (pas d'accès aux objets Python), HTML assaini à l'enregistrement
  (balises et attributs de Tiptap seulement).
- Fichiers des baux sous `instance_dir()/baux/<id>/`, servis seulement par les routes du bail.

## 8. Tests

- **Services** : montants (m², ha, forfait, arrondi sur la dernière ligne), activation (récurrence à
  une ligne par ligne de bail), migration des baux existants, rendu des modèles (champs, champ
  inconnu), image de la carte (projection : coin et centre d'une zone connue ; faux WMS), Docuseal
  (envoi, statuts, documents, annulation ; faux client, aucun appel réel), révision (formule,
  attente puis application, échéances déjà préparées inchangées, dépôt), lecture INSEE (réponse SDMX
  enregistrée).
- **Récit U2** (référence) : six lignes du bail actuel → 528,40 €/an ; PDF contenant le tableau et la
  carte.
- **API** : droits (expert-comptable en lecture), brouillon → actif, verrou après envoi.
- **Vitest** : assistant (étapes, cas A), tableau des montants, carte remplacée par un double (pas de
  Leaflet en jsdom).
- **E2E** : cas A complet ; cas B avec les routes `/api/v1/geo/*` et les tuiles interceptées
  (Playwright `route`) ; aucun appel réseau externe.

## 9. Lots

| Lot | Contenu | Besoins couverts |
|---|---|---|
| **L1** | Données (§3), migration, `leases` étendu, assistant étapes 1-3 **sans carte**, facture récurrente par ligne, associés « gérant », champs de l'organisation | BF1 (hors géométrie), BF18–BF20, U1 |
| **L2** | Modèles (4 livrés, dont le dérogatoire), Paramètres › Modèles, texte figé et retouche, aperçu et PDF (tableau) | BF8–BF12, U5 |
| **L3** | `geodata`, routes `/geo`, carte de l'assistant (Leaflet, Geoman, Turf), image figée, carte dans le PDF | BF2–BF7, BX9, NF3–NF5, NF7, U2–U4, U7 |
| **L4** | Intégration Docuseal, envoi, suivi, annulation, documents signés ; essai sur `docuseal.seconde-nature.net` en mode test **avec accord** | BF13–BF17, U6 |
| **L5** | Indices (INSEE, fermages), révision automatique, historique, courrier | BF21–BF23 |

## 10. Points à vérifier en cours de réalisation

1. Balises de champ Docuseal dans un PDF WeasyPrint (détection, rendu de la balise) — essai sur le
   serveur de test (L4), sinon placement par coordonnées (`fields.areas`).
2. Sonde Docuseal la plus légère disponible sur la version auto-hébergée.
3. Versions exactes de Leaflet, Leaflet-Geoman et Turf (épinglées, publiées depuis au moins deux
   semaines) et poids du morceau de carte.
4. Formule de révision triennale du bail actuel (« par rapport à l'année précédente ») : la
   conception applique la règle usuelle (indice du même trimestre, `revision_months` plus tard) —
   à confirmer à la relecture du modèle dérogatoire.
