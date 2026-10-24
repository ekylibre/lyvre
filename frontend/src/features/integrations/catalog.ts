// Catalogue des intégrations côté écran : libellé (comme external_config.SERVICE_LABELS), logo et
// texte de la proposition d'activation (tableau de bord). Logos officiels des marques (kits presse
// ou fichiers des marques), servis par l'application ; SMTP n'a pas de marque (icône d'enveloppe).
import facebook from "../../assets/integrations/facebook.png";
import ga4 from "../../assets/integrations/ga4.png";
import helloasso from "../../assets/integrations/helloasso.png";
import odoo from "../../assets/integrations/odoo.svg";
import qonto from "../../assets/integrations/qonto.png";
import stancer from "../../assets/integrations/stancer.png";

export const INTEGRATION_LOGOS: Record<string, string> = { facebook, ga4, helloasso, odoo, qonto, stancer };
export const INTEGRATION_LABELS: Record<string, string> = {
  stancer: "Stancer", odoo: "Odoo", helloasso: "HelloAsso", smtp: "SMTP (emails)",
  ga4: "Google Analytics (GA4)", facebook: "Facebook (Page)", qonto: "Qonto", documenso: "Documenso",
};

export function integrationLabel(slug: string): string {
  return INTEGRATION_LABELS[slug] ?? slug;
}

/** Proposition d'une intégration recommandée : ce qu'elle apporte à la structure. */
export const INTEGRATION_PITCHES: Record<string, string> = {
  qonto: "Synchronisez vos comptes bancaires et vos factures d'achat Qonto.",
  helloasso: "Importez les adhésions et les formulaires HelloAsso de vos adhérents.",
};
