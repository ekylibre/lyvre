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
  interest_rate: string; notes: string | null; is_out: boolean; is_manager: boolean; email: string | null;
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

// ------------------------------------------------------------------ registre des parts

export const REGISTER_KEY = [...ASSOCIATES_KEY, "register"];

export type MovementKind = "opening" | "subscription" | "transfer" | "donation" | "succession" | "reunion" | "reduction";
/** Types qui changent le capital et portent la valeur nominale d'une part. */
export const CAPITAL_KINDS: MovementKind[] = ["opening", "subscription", "reduction"];

export const KIND_HELP: Record<MovementKind, string> = {
  opening: "Situation reprise à une date (bilan d'ouverture) : parts reçues par chaque associé, valeur nominale.",
  subscription: "Constitution ou augmentation de capital : parts reçues, valeur nominale.",
  transfer: "Cession : autant de parts cédées que reçues, nature par nature.",
  donation: "Donation : le capital ne change pas. Avec réserve d'usufruit, le donateur cède N parts en pleine propriété et reçoit N parts en usufruit ; les donataires reçoivent la nue-propriété (N parts au total).",
  succession: "Succession : autant de parts cédées que reçues, nature par nature.",
  reunion: "Réunion de l'usufruit et de la nue-propriété (décès de l'usufruitier, fin d'usufruit) : l'usufruitier cède N parts en usufruit, le nu-propriétaire cède N parts en nue-propriété et reçoit N parts en pleine propriété.",
  reduction: "Réduction de capital : parts cédées (annulées), valeur nominale.",
};

export interface MovementLine { associate_id: number; associate: string; nature: Nature; nature_label: string; parts: number }

export interface Movement {
  id: number; movement_date: string; kind: MovementKind; kind_label: string;
  nominal_cents: number | null; price_cents: number | null; description: string | null;
  attachment: { name: string; url: string } | null; lines: MovementLine[];
}

export interface Capital {
  parts: number; nominal_cents: number | null; capital_cents: number | null; ledger_cents: number; warnings: string[];
}

export interface RegisterMeta {
  at: string; capital: Capital; situation: Associate[];
  kinds: Option[]; natures: Option[]; associates: Option[];
}
