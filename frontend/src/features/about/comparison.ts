// Comparatif de la page À propos, partagé avec le site lyvre.org (site/scripts/prebuild.mjs le copie) :
// critères (colonne Lyvre ici, les autres logiciels dans competitors.ts et openSourceVendors.ts), points forts, limites.
import type { Mark } from "./competitors";

export interface Row { key: string; label: string; lyvre: Mark; note?: string }

/** Une ligne par critère ; la colonne Lyvre ici, les autres dans competitors.ts. */
export const ROWS: Row[] = [
  { key: "plan_asso", label: "Plan comptable associatif", lyvre: "yes" },
  { key: "double_entry", label: "Partie double (bilan, compte de résultat)", lyvre: "yes" },
  { key: "simple_mode", label: "Comptabilité simplifiée (trésorerie)", lyvre: "yes" },
  { key: "bank_import", label: "Import bancaire, rapprochement", lyvre: "yes" },
  { key: "cash", label: "Caisse (espèces)", lyvre: "yes" },
  { key: "supplier_invoices", label: "Factures fournisseurs, justificatifs", lyvre: "yes" },
  { key: "members", label: "Adhésions, cotisations, relances", lyvre: "yes" },
  { key: "tax_receipts", label: "Reçus fiscaux des dons", lyvre: "yes" },
  { key: "budget_projects", label: "Budget, suivi par projet", lyvre: "yes" },
  { key: "cash_forecast", label: "Prévisionnel de trésorerie", lyvre: "yes" },
  { key: "fec", label: "Export FEC", lyvre: "yes" },
  { key: "closing", label: "Clôture guidée, affectation du résultat", lyvre: "yes" },
  { key: "dedicated_funds", label: "Fonds dédiés", lyvre: "yes" },
  { key: "ag_report", label: "Rapport pour l'assemblée générale", lyvre: "yes" },
  { key: "multi_users", label: "Plusieurs utilisateurs, rôles", lyvre: "yes" },
  { key: "multi_entities", label: "Plusieurs structures", lyvre: "yes" },
  { key: "sales_invoices", label: "Factures clients, devis", lyvre: "yes" },
  { key: "cheques_ticketing", label: "Remise de chèques, billetterie", lyvre: "no" },
  { key: "website_crm", label: "Site web, CRM, communication", lyvre: "no" },
  { key: "mobile_app", label: "Application mobile", lyvre: "partial", note: "Lyvre : interface lisible sur mobile" },
  { key: "free_software", label: "Logiciel libre, auto-hébergeable", lyvre: "yes" },
  { key: "free_tier", label: "Gratuit", lyvre: "yes" },
];

/** Critères ajoutés pour les logiciels open source, documentés chez eux (pas chez les éditeurs du premier tableau). */
export const OSS_ROWS: Row[] = [
  ...ROWS,
  { key: "sci", label: "SCI : associés, baux, quittances", lyvre: "yes" },
  { key: "lettering", label: "Lettrage des comptes de tiers", lyvre: "yes" },
  { key: "entry_lock", label: "Écritures validées intangibles", lyvre: "yes" },
  { key: "fixed_assets", label: "Immobilisations, amortissements", lyvre: "yes" },
  { key: "vat_return", label: "Déclaration de TVA préparée", lyvre: "yes", note: "Lyvre : CA3 mensuelle ou trimestrielle, CA12A agricole, saisies en ligne" },
  { key: "einvoicing", label: "Facture électronique, plateforme agréée", lyvre: "yes", note: "Lyvre : Factur-X émis et lu, SuperPDP ou Qonto" },
  { key: "sepa_online", label: "Prélèvement SEPA, paiement en ligne", lyvre: "no" },
];

export const LIMITS = [
  "Pas d'application mobile native : l'interface s'adapte au téléphone.",
  "Pas de remise de chèques ni de billetterie ; la facture électronique (réforme 2026-2027) passe par une plateforme agréée, SuperPDP ou Qonto.",
  "Déclarations de TVA préparées mais pas transmises : la CA3 et la CA12A agricole se saisissent sur l'espace professionnel (pas d'envoi EDI) ; pas de CA12 hors régime agricole.",
  "Pas de paiement en ligne propre : les adhésions et dons en ligne passent par HelloAsso.",
  "Modèles de reçus fiscaux à faire relire face aux formulaires Cerfa en vigueur avant usage.",
];

/** Ce qui distingue Lyvre. */
export const STRENGTHS = [
  "Libre et auto-hébergé : vos données restent chez vous, sans abonnement.",
  "Clôture complète guidée et FEC, comme un logiciel d'expert-comptable.",
  "Rapprochement bancaire au clavier, lecture des factures, règles automatiques.",
  "Plusieurs structures et rôles par structure, dont l'expert-comptable en lecture seule.",
  "Pour une SCI : baux, carte des parcelles, signature électronique et révision des loyers.",
  "Tiers pré-remplis depuis Sirene, adhérents synchronisés vers Brevo.",
  "Partie double ou simplifiée, avec passage de l'une à l'autre sans ressaisie.",
  "Pour une exploitation : échéancier fiscal, MSA et PAC, inventaire, marges par activité et assistant.",
  "Arrivée depuis Ekylibre en une restauration contrôlée, soldes vérifiés compte par compte.",
];
