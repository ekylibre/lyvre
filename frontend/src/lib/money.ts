// Montants : toujours en centimes entiers (comme côté serveur).

const SPACES = /[\s  €]/g;
const AMOUNT = /^\d+(\.\d{0,2})?$/;

/**
 * Montant saisi en euros (« 1 234,56 », « 12.5 », « 3 ») → centimes.
 * Chaîne vide → 0. Format invalide ou négatif → null.
 */
export function parseAmount(input: string): number | null {
  const s = input.replace(SPACES, "").replace(",", ".");
  if (s === "") return 0;
  if (!AMOUNT.test(s)) return null;
  const [units, decimals = ""] = s.split(".");
  return Number(units) * 100 + Number((decimals + "00").slice(0, 2));
}

/** Centimes → valeur d'un champ de saisie (« 1234,56 »), vide pour 0. */
export function toInput(cents: number): string {
  return cents ? (cents / 100).toFixed(2).replace(".", ",") : "";
}

const EUROS = new Intl.NumberFormat("fr-FR", { style: "currency", currency: "EUR" });

/** Centimes → affichage (« 1 234,56 € »). */
export function formatEuros(cents: number): string {
  return EUROS.format(cents / 100);
}
