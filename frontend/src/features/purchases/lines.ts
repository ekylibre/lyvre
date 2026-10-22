// Lignes d'une facture d'achat : totaux recalculés à la saisie (le serveur refait le calcul).
import type { LineRow, ProductOption } from "./types";

export const EMPTY_LINE: LineRow = { product_id: "", account_code: "", label: "", untaxed: "", vat_rate: "", vat: "" };

/** « 1 234,56 » → centimes ; vide ou invalide → null (signe accepté : remise en ligne négative). */
export function cents(value: string): number | null {
  const s = value.replace(/[\s  €]/g, "").replace(",", ".");
  if (!/^-?\d+(\.\d*)?$/.test(s)) return null;
  return Math.round(Number(s) * 100);
}

/** TTC d'une ligne : HT + TVA saisie, sinon TVA calculée depuis le taux. */
export function lineTotal(row: LineRow): number {
  const untaxed = cents(row.untaxed) ?? 0;
  let vat = cents(row.vat);
  if (vat === null) {
    const rate = Number(row.vat_rate.replace(",", "."));
    vat = row.vat_rate.trim() === "" || Number.isNaN(rate) ? 0 : Math.round((untaxed * rate) / 100);
  }
  return untaxed + vat;
}

export function linesTotal(rows: LineRow[]): number {
  return rows.reduce((sum, row) => sum + lineTotal(row), 0);
}

/**
 * Modification d'un champ : montant ou taux changé → TVA vidée (recalculée à l'enregistrement) ;
 * produit choisi → compte et taux du produit.
 */
export function updateLine(row: LineRow, field: keyof LineRow, value: string, products: ProductOption[]): LineRow {
  const next = { ...row, [field]: value };
  if (field === "untaxed" || field === "vat_rate") next.vat = "";
  if (field === "product_id") {
    const product = products.find((p) => p.value === value);
    if (product) {
      if (product.account) next.account_code = product.account;
      if (product.rate) { next.vat_rate = product.rate; next.vat = ""; }
      if (!next.label) next.label = product.label;
    }
  }
  return next;
}
