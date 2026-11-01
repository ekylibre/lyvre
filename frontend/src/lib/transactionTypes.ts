// Type d'une transaction bancaire (code Qonto `operation_type` ou TRNTYPE OFX) → libellé français et icône
// Lucide (lot TX2, claudedocs/design_ecran_transactions.md § 3.1). Le sens du montant départage les virements.
import {
  ArrowDownLeft, ArrowUpRight, Banknote, CircleDot, CreditCard, Landmark, PenLine, Repeat, type LucideIcon,
} from "lucide-react";

export interface TransactionType { label: string; icon: LucideIcon }

const FIXED: Record<string, TransactionType> = {
  card: { label: "Paiement par carte", icon: CreditCard },
  pos: { label: "Paiement par carte", icon: CreditCard },
  direct_debit: { label: "Prélèvement", icon: Repeat },
  directdebit: { label: "Prélèvement", icon: Repeat },
  qonto_fee: { label: "Frais bancaires", icon: Landmark },
  fee: { label: "Frais bancaires", icon: Landmark },
  srvchg: { label: "Frais bancaires", icon: Landmark },
  cheque: { label: "Chèque", icon: PenLine },
  check: { label: "Chèque", icon: PenLine },
  atm: { label: "Retrait d'espèces", icon: Banknote },
  cash: { label: "Retrait d'espèces", icon: Banknote },
  income: { label: "Virement reçu", icon: ArrowDownLeft },
};
const TRANSFERS = new Set(["transfer", "xfer", "debit", "credit", "swift_income", "dep"]);

export function transactionType(rawType: string | null | undefined, amountCents: number): TransactionType {
  const code = (rawType ?? "").trim().toLowerCase();
  if (FIXED[code]) return FIXED[code];
  if (TRANSFERS.has(code)) {
    return amountCents < 0 ? { label: "Virement émis", icon: ArrowUpRight } : { label: "Virement reçu", icon: ArrowDownLeft };
  }
  return { label: code ? `Autre opération (${rawType})` : "Type non précisé", icon: CircleDot };
}
