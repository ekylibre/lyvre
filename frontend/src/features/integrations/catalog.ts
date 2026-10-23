// Catalogue des intégrations côté écran : libellé (comme external_config.SERVICE_LABELS).
export const INTEGRATION_LABELS: Record<string, string> = {
  stancer: "Stancer", odoo: "Odoo", helloasso: "HelloAsso", smtp: "SMTP (emails)",
  ga4: "Google Analytics (GA4)", facebook: "Facebook (Page)", qonto: "Qonto",
};

export function integrationLabel(slug: string): string {
  return INTEGRATION_LABELS[slug] ?? slug;
}
