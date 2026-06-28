# Spécification des besoins — Tableau de bord « Visibilité & Impact »

> **Statut : BESOINS UNIQUEMENT (sortie de `/sc:brainstorm`).**
> Ce document décrit *quoi* et *pourquoi*, pas *comment*. Aucune décision
> d'architecture, de schéma ni de code n'est prise ici.
> Étape suivante : `/sc:design` (architecture) puis `/sc:workflow` (plan d'implémentation).
>
> Association : **Seconde Nature** (réemploi / économie circulaire). Date : 2026-06-27.

---

## 1. Objectif & contexte

Doter Seconde Nature d'un tableau de bord unique agrégeant **visibilité**
(audience web + communautés) et **impact** (environnemental, social, économique),
en s'appuyant sur les outils déjà connectés à l'application de compta et sur les
plateformes externes de l'association.

**Triple usage validé (à parts égales) :**
1. **Pilotage** — suivi mensuel par le bureau / CA (tendances, alertes, décisions).
2. **Financeurs** — alimenter rapport d'activité, demandes de subvention, bilan annuel.
3. **Communication** — chiffres de notoriété et d'impact pour la transparence externe.

**Conséquence de conception :** un même socle d'indicateurs, deux restitutions
(dashboard interactif + rapport exportable), avec un vocabulaire « parlant »
(équivalents concrets) pour les usages financeurs/communication.

---

## 2. Périmètre des dimensions (4 axes validés)

| Axe | Intention | Exemples d'indicateurs |
|---|---|---|
| **Visibilité / Notoriété** | Mesurer l'audience et la communauté | Audience site, abonnés/portée réseaux, croissance |
| **Environnemental** | Cœur de mission réemploi | kg/articles détournés, CO₂ évité, eau économisée |
| **Social** | Mobilisation humaine | Bénévoles actifs, heures valorisées, adhérents |
| **Économique** | Modèle & autofinancement | CA par canal, dons/adhésions, valorisation bénévolat |

---

## 3. Sources de données & faisabilité d'automatisation

Objectif exprimé : **tout automatique**. Réalité technique ci-dessous —
2 sources ne peuvent pas l'être et nécessitent un repli.

| Source | Données visées | Auto ? | Remarque de faisabilité |
|---|---|---|---|
| **Google Analytics (GA4)** propriété `472641442` | Utilisateurs, sessions, acquisition, pages, conversions | ✅ **Oui** | GA4 Data API (compte de service OAuth2). Intégration robuste. |
| **HelloAsso** | Adhésions, dons, montants | ✅ **Oui (déjà fait)** | Déjà synchronisé dans l'outil. |
| **Interne** (POS Odoo, adhérents, bénévoles, `work_times`) | Ventes, CA, membres, heures | ✅ **Oui (déjà fait)** | Données déjà en base. |
| **Facebook Page** | Abonnés, portée, engagement | ⚠️ **Partiel** | Graph API possible mais lourde : app Meta + token page + revue d'app pour les *insights* (portée). Le nb d'abonnés est plus accessible. Token à rafraîchir. |
| **Facebook Groupe** (`assosecondenature`) | Membres, activité | ❌ **Non** | API Groupes Meta dépréciée (2024). → **saisie manuelle**. |
| **Vinted** (`secondenature17`) | Abonnés, articles en vente, ventes, note | ❌ **Non** | Aucune API publique ; scraping fragile et contraire aux CGU. → **saisie manuelle**. |
| **Facteurs environnementaux** (CO₂, eau, kg) | Conversion ventes → impact | ⚙️ **Semi-auto** | Calcul automatique une fois les **ratios paramétrés** (source ADEME / Refashion à valider). |

> **Décision à acter (cf. §8 Q1)** : pour Vinted et le groupe Facebook, soit on
> accepte une **couverture partielle** (ces blocs restent vides/automatiques
> uniquement là où c'est possible), soit on ajoute un **mini-formulaire de saisie
> mensuelle** pour ces 2 sources. Recommandation : le mini-formulaire (effort faible,
> évite des « trous » dans le rapport financeurs).

---

## 4. Catalogue d'indicateurs (par dimension)

### 4.1 Visibilité / Notoriété
- **Site (GA4)** : utilisateurs actifs, nouveaux vs récurrents, sessions, taux
  d'engagement, durée moyenne, top pages, **sources d'acquisition**, conversions
  sortantes (clics vers HelloAsso / Vinted).
- **Facebook Page** : nombre d'abonnés, croissance mensuelle, portée, engagement.
- **Facebook Groupe** : nombre de membres, croissance *(saisie manuelle)*.
- **Vinted** : abonnés, articles en vente, note moyenne, nb d'évaluations *(saisie manuelle)*.
- **Agrégat** : **« audience totale »** (site + communautés cumulées) et sa
  croissance — indicateur phare de visibilité.

### 4.2 Environnemental (impact réemploi)
- **Articles remis en circulation** (vendus + donnés) sur la période.
- **Poids détourné (kg)** du déchet — via poids moyen/article ou pesées saisies.
- **CO₂ évité (kg CO₂e)** — facteur d'émission par kg réemployé.
- **Eau économisée (L)** — facteur textile.
- **Taux de réemploi** = remis en circulation / collectés.
- **Équivalents « parlants »** (ex. km de voiture évités) pour communication.
> Les facteurs de conversion doivent être **paramétrables** et **sourcés** (ADEME
> Base Empreinte / Refashion). Valeurs à valider, pas figées dans le code.

### 4.3 Social
- **Bénévoles actifs** (≥ 1 temps saisi sur la période).
- **Heures de bénévolat** + **valorisation €** (module `work_times` existant).
- **Adhérents** : nombre, évolution, **taux de renouvellement** (réutilise le statut
  d'adhésion / « date anniversaire » déjà calculé).
- Lien possible avec les **contributions volontaires en nature (classe 86/87)** du
  plan comptable associatif → cohérence rapport financier ↔ rapport d'impact.

### 4.4 Économique
- **CA total** et **par canal** (POS Odoo, Vinted, HelloAsso).
- **Dons & adhésions** (HelloAsso).
- **Panier moyen** par canal.
- **Part d'autofinancement** (ressources propres vs subventions).
- **Valorisation du bénévolat** comme ressource non monétaire.

---

## 5. Exigences fonctionnelles (FR)

- **FR1 — Page dashboard** « Visibilité & Impact » dans l'app, avec cartes
  chiffres-clés + graphiques de tendance.
- **FR2 — Filtre de période** (mois / trimestre / année / plage personnalisée),
  cohérent avec l'exercice comptable, réutilisant les helpers de filtre existants.
- **FR3 — Comparaison** période vs période précédente (variation %, flèche tendance).
- **FR4 — Les 4 dimensions** présentées en sections distinctes + une synthèse en tête.
- **FR5 — Connecteur GA4** : récupération automatique des métriques site.
- **FR6 — Réutilisation** des données internes et HelloAsso déjà présentes.
- **FR7 — Connecteur Facebook Page** (abonnés a minima ; portée/engagement si revue d'app obtenue).
- **FR8 — Saisie manuelle périodique** pour Vinted + groupe Facebook (selon décision §8 Q1).
- **FR9 — Paramétrage des facteurs environnementaux** (poids moyen, CO₂, eau) avec source documentée.
- **FR10 — Export du rapport** (PDF/impression) périodique, mise en page « rapport d'activité ».
- **FR11 — Indicateurs agrégés** (audience totale, impact CO₂ total, valorisation globale).
- **FR12 — Équivalents pédagogiques** affichables pour communication/financeurs.
- **FR13 — Gestion des identifiants externes** (clés GA4/Facebook) via le mécanisme
  de connexions externes déjà présent dans l'app.
- **FR14 — État de fraîcheur** : afficher la date de dernière synchro par source +
  signaler une source en échec ou en attente de saisie manuelle.

---

## 6. Exigences non-fonctionnelles (NFR)

- **NFR1 — Multi-tenant** : indicateurs cloisonnés par instance (architecture actuelle).
- **NFR2 — Résilience API** : une source en panne ne casse pas le dashboard (dégradation
  gracieuse, valeurs « N/A » + message).
- **NFR3 — Quotas/coûts** : mise en cache des appels externes (GA4/Facebook ont des
  quotas) ; synchro périodique plutôt qu'à chaque affichage.
- **NFR4 — RGPD** : ne stocker que des **métriques agrégées** (pas de données
  personnelles d'audience) ; secrets chiffrés/non versionnés.
- **NFR5 — Fiabilité financeurs** : chiffres traçables (source + méthode de calcul
  visibles), surtout pour l'impact environnemental.
- **NFR6 — Cohérence visuelle** : Bootstrap 5, style aligné sur le dashboard existant.
- **NFR7 — Maintenabilité** : facteurs de conversion et seuils configurables sans redeploy.

---

## 7. User stories & critères d'acceptation

- **US1 (Bureau)** : *En tant que membre du bureau, je consulte une page mensuelle
  qui montre l'évolution de notre audience et de notre impact, pour décider où agir.*
  - ✅ Page accessible, période sélectionnable, variation vs période précédente affichée.
- **US2 (Financeur)** : *En tant que trésorier, j'exporte un rapport trimestriel chiffré
  pour une demande de subvention.*
  - ✅ Export PDF lisible incluant les 4 dimensions, période et sources/méthodes indiquées.
- **US3 (Communication)** : *En tant que chargé de com', je récupère des chiffres
  « parlants » (kg détournés, CO₂ évité, abonnés cumulés) pour un post.*
  - ✅ Indicateurs agrégés + équivalents pédagogiques disponibles et copiables.
- **US4 (Impact env.)** : *En tant qu'asso de réemploi, je veux que mes ventes/dons se
  traduisent automatiquement en kg et CO₂ évités.*
  - ✅ Calcul automatique à partir des ventes × facteurs paramétrés ; facteurs sourcés.
- **US5 (Saisie réseaux)** : *En tant qu'admin, je saisis chaque mois les chiffres Vinted
  et du groupe Facebook qu'aucune API ne fournit.*
  - ✅ Formulaire mensuel simple ; valeurs historisées et intégrées aux tendances.
- **US6 (Fraîcheur)** : *Je vois si une source est à jour, en échec, ou en attente de saisie.*
  - ✅ Date de dernière synchro + statut par source.

---

## 8. Questions ouvertes (à trancher avant `/sc:design`)

1. **Vinted & groupe Facebook** : couverture partielle assumée, ou mini-formulaire de
   saisie mensuelle ? *(reco : formulaire)*
2. **Facebook Page** : se contente-t-on des **abonnés** (simple), ou vise-t-on
   **portée + engagement** (nécessite création d'une app Meta + revue d'app, délai) ?
3. **Données de réemploi** : suit-on les **articles collectés** (entrants) en plus des
   ventes, pour calculer un vrai taux de réemploi ? Si oui, d'où viennent-elles
   (saisie, Odoo, pesées) ?
4. **Facteurs environnementaux** : quelle source de référence fait foi
   (ADEME Base Empreinte, Refashion, étude interne) et qui les valide ?
5. **Granularité Vinted** : les ventes Vinted entrent-elles aussi dans le **CA
   économique** (et comment, sans API) — saisie d'un total mensuel suffit-elle ?
6. **Cadence de synchro** automatique (quotidienne / hebdo) et **rétention** de
   l'historique (depuis quand ?).
7. **Objectifs/cibles** : veut-on afficher des **objectifs** (ex. +10 % d'abonnés)
   pour colorer les indicateurs, ou seulement le constat ?

---

## 9. Prochaines étapes

- `/sc:design` → architecture : modèle de stockage des métriques (séries temporelles
  par source/indicateur), connecteurs (GA4, Facebook), formulaire de saisie, moteur
  de calcul d'impact, rendu dashboard + export.
- `/sc:workflow` → découpage en phases implémentables (ex. socle interne+éco d'abord,
  puis GA4, puis saisie réseaux, puis environnemental, puis export).
