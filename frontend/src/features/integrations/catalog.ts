// Catalogue des intégrations côté écran : libellé (comme external_config.SERVICE_LABELS) et texte
// de la proposition d'activation (tableau de bord).
export const INTEGRATION_LABELS: Record<string, string> = {
  stancer: "Stancer", odoo: "Odoo", helloasso: "HelloAsso", smtp: "SMTP (emails)",
  ga4: "Google Analytics (GA4)", facebook: "Facebook (Page)", qonto: "Qonto",
};

export function integrationLabel(slug: string): string {
  return INTEGRATION_LABELS[slug] ?? slug;
}

/** Proposition d'une intégration recommandée : ce qu'elle apporte à la structure. */
export const INTEGRATION_PITCHES: Record<string, string> = {
  qonto: "Synchronisez vos comptes bancaires et vos factures d'achat Qonto.",
  helloasso: "Importez les adhésions et les formulaires HelloAsso de vos adhérents.",
};
