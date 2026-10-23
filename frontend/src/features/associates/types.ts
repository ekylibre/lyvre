// Associés d'une société (module « Associés », claudedocs/design_associes.md) : types de l'API
// /api/v1/associates et libellés partagés par les écrans.
import type { Option } from "../purchases/types";

export const ASSOCIATES_KEY = ["associates"];

export type Nature = "full" | "usufruct" | "bare";
export const NATURES: { value: Nature; label: string; short: string }[] = [
  { value: "full", label: "Pleine propriété", short: "PP" },
  { value: "usufruct", label: "Usufruit", short: "Usufruit" },
  { value: "bare", label: "Nue-propriété", short: "NP" },
];

export interface Associate {
  id: number; name: string; entity_id: number; account_code: string; account_label: string;
  parts: Record<Nature, number>; percent: Record<Nature, number>;
  /** Solde du compte courant, créditeur positif : la société doit à l'associé. */
  balance_cents: number;
  interest_rate: string; notes: string | null; is_out: boolean;
}

export interface AssociatesMeta {
  at: string; total_parts: number; balances_total_cents: number;
  next_account_code: string | null; entities: Option[];
}

/** Sens du solde d'un compte courant, en clair. */
export function balanceLabel(cents: number): string {
  if (cents > 0) return "dû à l'associé";
  if (cents < 0) return "dû par l'associé";
  return "soldé";
}
