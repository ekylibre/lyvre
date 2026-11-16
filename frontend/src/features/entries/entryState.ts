import { parseAmount, toInput } from "../../lib/money";
import type { Account, EntryPayload } from "../../lib/types";

export interface Line {
  key: number;
  account: Account | null;
  label: string;
  debit: string; // saisie brute en euros
  credit: string;
  projectId: string | null;
  /** Lot AG8.c : affectation analytique (« activity:ID » ou « key:ID »), instances agricoles. */
  analytic: string | null;
  /** Lot T2 : code de TVA et base HT (saisie en euros) d'une ligne 445… */
  vatCode: string | null;
  vatBase: string;
}

export interface EntryState {
  fiscalYearId: number | null;
  journalId: number | null;
  date: string;
  description: string;
  lines: Line[];
}

export interface InitialLine {
  account: Account | null;
  label?: string;
  debit_cents?: number;
  credit_cents?: number;
  project_id?: string | null;
  analytic?: string | null;
  vat_code?: string | null;
  vat_base_cents?: number | null;
}

let nextKey = 1;

export function newLine(init: Partial<InitialLine> = {}): Line {
  return {
    key: nextKey++,
    account: init.account ?? null,
    label: init.label ?? "",
    debit: toInput(init.debit_cents ?? 0),
    credit: toInput(init.credit_cents ?? 0),
    projectId: init.project_id ?? null,
    analytic: init.analytic ?? null,
    vatCode: init.vat_code ?? null,
    vatBase: init.vat_base_cents != null ? toInput(init.vat_base_cents) : "",
  };
}

/** Au moins deux lignes, pour que la saisie démarre directement. */
export function withMinimumLines(lines: Line[]): Line[] {
  const out = [...lines];
  while (out.length < 2) out.push(newLine());
  return out;
}

export type Action =
  | { type: "field"; field: "fiscalYearId" | "journalId" | "date" | "description"; value: string | number | null }
  | { type: "line"; index: number; patch: Partial<Line> }
  | { type: "addLine"; line: Line }
  | { type: "removeLine"; index: number }
  | { type: "reset" };

export function reducer(state: EntryState, action: Action): EntryState {
  switch (action.type) {
    case "field":
      return { ...state, [action.field]: action.value };
    case "line":
      return {
        ...state,
        lines: state.lines.map((l, i) => (i === action.index ? { ...l, ...action.patch } : l)),
      };
    case "addLine":
      return { ...state, lines: [...state.lines, action.line] };
    case "removeLine":
      return { ...state, lines: withMinimumLines(state.lines.filter((_, i) => i !== action.index)) };
    case "reset":
      // Enregistrer et enchaîner : exercice, journal et date conservés.
      return { ...state, description: "", lines: withMinimumLines([]) };
  }
}

export interface Totals {
  debit: number;
  credit: number;
  /** debit - credit, en centimes */
  gap: number;
  /** index des lignes dont un montant est mal saisi */
  invalidAmounts: number[];
}

export function lineCents(line: Line): { debit: number | null; credit: number | null } {
  return { debit: parseAmount(line.debit), credit: parseAmount(line.credit) };
}

export function isEmptyLine(line: Line): boolean {
  return !line.account && !line.debit.trim() && !line.credit.trim();
}

export function computeTotals(lines: Line[]): Totals {
  let debit = 0;
  let credit = 0;
  const invalidAmounts: number[] = [];
  lines.forEach((line, i) => {
    const c = lineCents(line);
    if (c.debit === null || c.credit === null) invalidAmounts.push(i);
    debit += c.debit ?? 0;
    credit += c.credit ?? 0;
  });
  return { debit, credit, gap: debit - credit, invalidAmounts };
}

/** Montant qui équilibre l'écriture, dans la colonne voulue (0 si aucun). */
export function balancingAmount(lines: Line[], index: number, column: "debit" | "credit"): number {
  const others = computeTotals(lines.filter((_, i) => i !== index));
  const otherSide = column === "debit" ? others.credit : others.debit;
  const sameSide = column === "debit" ? others.debit : others.credit;
  return Math.max(otherSide - sameSide, 0);
}

/** Ligne préremplie avec l'écart restant (colonne qui équilibre). */
export function balancingLine(lines: Line[], description: string): Line {
  const { gap } = computeTotals(lines);
  return newLine({
    label: description,
    debit_cents: gap < 0 ? -gap : 0,
    credit_cents: gap > 0 ? gap : 0,
  });
}

/**
 * Lignes complètes : chaque ligne non vide a un compte et un montant, et il y
 * en a au moins deux. Sert à décider quand interroger la validation serveur.
 */
export function isComplete(state: EntryState): boolean {
  const filled = state.lines.filter((l) => !isEmptyLine(l));
  return filled.length >= 2 && filled.every((l) => {
    const c = lineCents(l);
    return l.account && ((c.debit ?? 0) > 0 || (c.credit ?? 0) > 0);
  });
}

/** Ligne de TVA (comptes 445…) ou ligne déjà codée : la saisie montre son code et sa base. */
export function hasVatFields(line: Line): boolean {
  return !!line.vatCode || (line.account?.code ?? "").startsWith("445");
}

/** Base HT proposée d'après le montant de la ligne et le taux du code (vide sans taux). */
export function proposedBase(line: Line, rateBp: number): string {
  const c = lineCents(line);
  const amount = (c.debit ?? 0) || (c.credit ?? 0);
  return rateBp && amount ? toInput(Math.round((amount * 10000) / rateBp)) : "";
}

export function toPayload(state: EntryState, bankTransactionId?: number): EntryPayload {
  const payload: EntryPayload = {
    fiscal_year_id: state.fiscalYearId,
    journal_id: state.journalId,
    entry_date: state.date,
    description: state.description.trim(),
    // Toutes les lignes, dans l'ordre : les erreurs « lines[i] » du serveur
    // désignent la ligne affichée i (les lignes vides sont ignorées côté serveur).
    lines: state.lines.map((l) => {
      const c = lineCents(l);
      return {
        account_id: l.account?.id ?? null,
        label: l.label.trim() || state.description.trim(),
        debit_cents: c.debit ?? 0,
        credit_cents: c.credit ?? 0,
        project_id: l.projectId ? Number(l.projectId) : null,
        ...(l.analytic ? { analytic: l.analytic } : {}),
        vat_code: l.vatCode,
        vat_base_cents: l.vatCode && l.vatBase.trim() ? parseAmount(l.vatBase) : null,
      };
    }),
  };
  if (bankTransactionId !== undefined) payload.bank_transaction_id = bankTransactionId;
  return payload;
}
