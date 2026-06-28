# Spécification des besoins — Rapport d'activité Seconde Nature

> **Statut : BESOINS UNIQUEMENT (sortie de `/sc:brainstorm`).**
> Décrit *quoi* et *pourquoi*, pas *comment*. Pas d'architecture, de schéma ni de
> code. Étape suivante : `/sc:design` (avec le skill **frontend-design** pour
> traduire l'identité Seconde Nature) puis `/sc:workflow` / `/sc:implement`.
> Modèle de structure : `La_Matière_Rapport_Activités_2025.pdf`. Date : 2026-06-28.

---

## 1. Objectif

Produire un **rapport d'activité** de l'association Seconde Nature, **généré dans
l'application de compta** (page dédiée, HTML imprimable → PDF), reprenant la
**structure** du rapport La Matière mais avec l'**identité visuelle du site
seconde-nature.net** (palette kraft / vert réemploi).

**Décisions actées (questions de cadrage) :**
| Sujet | Décision |
|---|---|
| Livrable | **Page dans l'app compta** (route dédiée, HTML print → PDF, stylée Seconde Nature) |
| Période | **Exercice comptable** de l'association |
| Données | **Hybride** : chiffres calculés live + textes narratifs éditables + tonnages éco saisis/importés |
| Audience | **Polyvalente** : AG/adhérents + financeurs/éco-organismes + grand public |

---

## 2. Identité visuelle (cible)

Reprendre les **tokens du site** (`assets/css/custom.scss` du repo
`seconde-nature.github.io`) — esthétique « papier recyclé / kraft » :

| Rôle | Couleur |
|---|---|
| Fond papier kraft | `#e7dcc4` |
| Surfaces / cartes | `#f4eee0` |
| Texte (encre chaude) | `#26231d` · secondaire `#5b5446` |
| **Primaire** vert réemploi | `#1c7a33` · vert profond logo `#0f3d1c` |
| Accent (parcimonie) | rouge ficelle `#c2452d` |
| Filets | `#cdbf9f` |

Typo : familles `--display` / `--body` / `--mono` (échelle fluide du site).
→ **Différent du modèle La Matière** (teal/orange) : on garde sa *mise en page*
(gros chiffres, frises, cartes, QR), pas ses couleurs.

---

## 3. Sources de contenu → sections

| # | Section | Source(s) | Nature |
|---|---|---|---|
| 0 | **Couverture** (titre, exercice, visuel, logo) | — | éditable + photo |
| 1 | **Édito / Avant-propos** (mot du CA, citation) | rédigé | éditable |
| 2 | **Sommaire** | auto | live |
| 3 | **Rapport moral** | rédigé | éditable |
| 4 | **Qui sommes-nous / Gouvernance** (mission, CA, équipe) | site `_data/missions.yml`, `infos.yml` | éditable |
| 5 | **Vie associative — Adhérents & bénévoles** | app : adhérents (`is_member` + évolution), bénévoles & heures valorisées (`work_times`), HelloAsso | **live** + graphe |
| 6 | **Réemploi & impact environnemental** ⭐ | `Declaration Ecoorganismes.xlsx` (tonnages Entrant/Sortant Ecomaison + Ecologic) + facteurs ADEME (`impact_engine`) | **live/calculé** |
| 7 | **Boutique & ventes** | app : CA POS Odoo + **Vinted** (articles vendus/abonnés, saisie manuelle) | **live** + graphe |
| 8 | **Collecte & éco-organismes** (partenariats, points de collecte, **financement** Ecomaison/Ecologic) | xlsx (facturation éco-orga) + site | **live** + éditable |
| 9 | **Repair Café & ateliers** | site `repair_cafe.md`, `_data/services.yml` | éditable |
| 10 | **Communication & visibilité** (web GA4, **groupe Facebook**, **Vinted**, HelloAsso) | module **Visibilité & Impact** existant | **live** |
| 11 | **Partenaires & coopération** | site `_data/partners.yml` | éditable |
| 12 | **Bilan financier** (exercice) | app : compte de résultat + bilan (`services/reports.py`) | **live** |
| 13 | **Perspectives / frise** (historique + objectifs N+1) | rédigé | éditable |

> Les sources externes (Vinted, groupe Facebook) restent **sans API** → données
> issues de la saisie manuelle déjà en place dans le module Visibilité & Impact.

---

## 4. Données éco-organismes (cœur de l'impact)

Le fichier `Declaration Ecoorganismes.xlsx` fournit, par **trimestre** (T2 2025 →
T1 2026) et par matière :
- **Ecomaison** : Meubles, Jouets, Brico-Jardin (tonnages **Entrant** vs **Sortant/réemploi**).
- **Ecologic** : D3E, Sports (codes GEF/GHF/PAM/ECR/ASL…, quantités LIV vs DEC_REE).
- **Volumes** totaux Entrant/Sortant, bennes déchets.
- **Facturation éco-organismes** (financement : ~1 220 €/trimestre).

Exploitation pour le rapport :
- **Tonnage collecté** (entrant) et **tonnage réemployé** (sortant) sur l'exercice.
- **Taux de réemploi** = sortant / entrant.
- **CO₂ évité / eau économisée** via les facteurs ADEME déjà paramétrés (`impact_factors`).
- **Financement éco-organismes** dans le bilan financier / section collecte.

> Le rapprochement **exercice comptable ↔ trimestres calendaires** de l'éco-déclaration
> est un point à clarifier (cf. §7).

---

## 5. Exigences fonctionnelles (FR)

- **FR1** — Page « Rapport d'activité » dans l'app, période = **exercice comptable**
  (sélecteur d'exercice), rendu HTML **imprimable** (A4, sauts de page) → PDF navigateur.
- **FR2** — **Modèle hybride** : chaque section combine chiffres **live** (app) et
  **blocs narratifs éditables** (persistés), comme le gabarit d'email de relance existant.
- **FR3** — **Contenus narratifs éditables** (admin) et historisés par exercice :
  édito, rapport moral, intros de section, légendes, perspectives.
- **FR4** — **Ingestion des tonnages éco-organismes** : import du format
  `Declaration Ecoorganismes.xlsx` **ou** saisie (organisme, matière, trimestre,
  entrant_t, sortant_t, financement €).
- **FR5** — **Impact environnemental calculé** : tonnage réemployé, taux de réemploi,
  CO₂/eau évités (réutiliser `impact_engine` + facteurs ADEME), **équivalents parlants**.
- **FR6** — **Graphiques** : évolution adhérents, tonnages entrant/sortant par matière,
  CA par canal (réutiliser ECharts déjà en place sur le dashboard).
- **FR7** — **Identité visuelle Seconde Nature** appliquée au rapport (override des
  tokens Bootstrap par la palette kraft/vert), cohérente avec le site.
- **FR8** — **Couverture + sommaire + sections** numérotées façon La Matière ;
  **QR codes** (adhésion HelloAsso, site) ; **photos** (upload ou réutilisées du site).
- **FR9** — **Bilan financier de l'exercice** depuis les rapports comptables existants
  (compte de résultat + bilan), incluant le financement éco-organismes.
- **FR10** — **Réutilisation** du module Visibilité & Impact pour la section
  communication (audience web, réseaux).

---

## 6. Exigences non-fonctionnelles (NFR)

- **NFR1 — Multi-tenant** : contenu et données cloisonnés par instance.
- **NFR2 — Impression fidèle** : mise en page A4, sauts de page maîtrisés, `@media print`.
- **NFR3 — Réutilisation** : s'appuyer sur l'existant (`impact_engine`, `reports.py`,
  `work_times`, module Visibilité & Impact, ECharts) plutôt que réimplémenter.
- **NFR4 — Cohérence de marque** : fidélité aux tokens du site (couleurs, typo, ton).
- **NFR5 — Éditabilité sans redeploy** : textes et tonnages modifiables via l'UI.
- **NFR6 — Traçabilité** : chiffres sourcés (app / éco-déclaration / ADEME) pour les financeurs.
- **NFR7 — RGPD** : uniquement des agrégats (pas de données personnelles d'adhérents/audience).

---

## 7. User stories & critères d'acceptation

- **US1 (AG)** : *présenter le rapport à l'assemblée générale.*
  - ✅ Sections gouvernance, vie associative, bilan moral et financier de l'exercice présentes et imprimables.
- **US2 (Financeur / éco-organisme)** : *justifier l'impact et le financement.*
  - ✅ Tonnages réemployés, taux de réemploi, CO₂ évité, financement Ecomaison/Ecologic, sources tracées.
- **US3 (Communication)** : *diffuser un récit illustré.*
  - ✅ Récit éditable, photos, chiffres parlants, identité visuelle Seconde Nature.
- **US4 (Trésorier)** : *intégrer le bilan financier de l'exercice.*
  - ✅ Compte de résultat + bilan de l'exercice repris automatiquement.
- **US5 (Admin)** : *éditer les textes, importer les tonnages, générer le rapport.*
  - ✅ Formulaires d'édition narrative + ingestion xlsx ; génération/impression en un clic.

---

## 8. Questions ouvertes (à trancher avant `/sc:design`)

1. **Exercice ↔ trimestres éco** : quelles dates d'exercice comptable, et comment
   mapper les trimestres calendaires de l'éco-déclaration sur l'exercice ?
2. **Ingestion tonnages** : import automatique du `Declaration Ecoorganismes.xlsx`
   (format figé) **ou** saisie manuelle trimestrielle ? *(reco : import + correction manuelle)*
3. **Contenu « identité/services/partenaires »** : ressaisi/édité dans l'app
   (découplé du site) **ou** lu depuis les `_data/*.yml` du repo Jekyll (couplage) ?
   *(reco : édité dans l'app)*
4. **Photos** : upload dans l'app, ou réutilisation des visuels `assets/img/` du site ?
5. **Fidélité de mise en page** : répliquer la maquette La Matière (frises, blocs
   colorés) **ou** une mise en page « native site » plus sobre ?
6. **Bilan financier** : compte de résultat complet (PCA) ou version synthétique grand public ?
7. **Versionnage** : un rapport par exercice, archivé/consultable a posteriori ?

---

## 9. Prochaines étapes

- `/sc:design` (skill **frontend-design**) — traduire les tokens Seconde Nature en
  système de mise en page « rapport » (couverture, sommaire, sections, cartes KPI,
  frises, print A4), modèle de données contenus narratifs + tonnages éco, et structure
  de la page/route dans l'app.
- `/sc:workflow` puis `/sc:implement` — découpage phasé (socle + sections live d'abord,
  puis éco-organismes, puis narratif/édition, puis impression/finitions).
