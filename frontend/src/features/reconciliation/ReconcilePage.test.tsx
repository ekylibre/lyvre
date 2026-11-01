import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { notifications } from "@mantine/notifications";
import { renderWithProviders } from "../../test/render";
import type { BankTransaction, Suggestion } from "../../lib/types";
import ReconcilePage from "./ReconcilePage";

const tx = (id: number, label: string, amount: number, extra: Partial<BankTransaction> = {}): BankTransaction => ({
  id, date: "2026-03-10", label, amount_cents: amount, reconciled: false, is_reversed: false,
  attachment_status: null, category: null, entity: null, entry: null, new_entry_url: `/entries/new?bt_id=${id}`, ...extra,
});
const sugg = (line: number, score: number, amount: number): Suggestion => ({
  journal_line_id: line, entry_id: line, reference: `BQ-${line}`, entry_date: "2026-03-10",
  label: "E", account_code: "5121", amount_cents: amount, score,
});

let server: { transactions: BankTransaction[]; suggestions: Record<number, Suggestion[]>; reconcileFails: Set<number> };
type Call = { method: string; url: string; body: any }; // eslint-disable-line @typescript-eslint/no-explicit-any
let calls: Call[];
let show: { mock: { calls: unknown[][] } };

const json = (status: number, body: unknown) => Promise.resolve(new Response(JSON.stringify(body), { status }));

beforeEach(() => {
  calls = [];
  localStorage.clear();
  show = vi.spyOn(notifications, "show").mockReturnValue("id");
  server = {
    transactions: [tx(1, "PRLV EDF", -100), tx(2, "CB LEROY", -250), tx(3, "VIR HELLOASSO", 900)],
    suggestions: { 1: [sugg(11, 2, -100)], 2: [sugg(21, 2, -250), sugg(22, 2, -250)], 3: [sugg(31, 1, 900)] },
    reconcileFails: new Set(),
  };
  vi.spyOn(globalThis, "fetch").mockImplementation(((input: RequestInfo | URL, init: RequestInit = {}) => {
    const url = String(input);
    const method = init.method ?? "GET";
    const body = init.body ? JSON.parse(init.body as string) : undefined;
    calls.push({ method, url, body });
    const counters = () => ({ unreconciled: server.transactions.length, total: 3 });
    if (url === "/api/v1/reconciliation/context") {
      return json(200, { bank_accounts: [{ id: 1, label: "CA Courant", iban: null, qonto: null, account: { id: 5, code: "5121", label: "CA" } }],
        months: [{ value: "2026-03", label: "mars 2026" }], default_journal_id: 2 });
    }
    if (url.startsWith("/api/v1/bank-accounts/1/transactions")) return json(200, { transactions: server.transactions, counters: counters() });
    const m = url.match(/bank-transactions\/(\d+)\/suggestions/);
    if (m) return json(200, { suggestions: server.suggestions[Number(m[1])] ?? [] });
    if (url.startsWith("/api/v1/entries/form?bt_id=")) {
      return json(200, { mode: "create", options: { fiscalYears: [{ id: 1, label: "2026", start_date: "2026-01-01", end_date: "2026-12-31" }],
        journals: [{ id: 2, code: "BQ", label: "Banque" }], recentsScope: "test" },
        initial: { fiscal_year_id: 1, journal_id: 2, entry_date: "2026-03-10", description: "PRLV EDF",
          lines: [{ account: { id: 5, code: "5121", label: "CA" }, label: "PRLV EDF", debit_cents: 0, credit_cents: 100 }] },
        bank_transaction: { id: 1, date: "2026-03-10", label: "PRLV EDF", amount_cents: -100, return_url: "/reconciliation/" } });
    }
    if (url === "/api/v1/entries/validate") return json(200, { errors: {} });
    if (url === "/api/v1/reconciliations") {
      const results = body.items.map((i: { bank_transaction_id: number }) => server.reconcileFails.has(i.bank_transaction_id)
        ? { bank_transaction_id: i.bank_transaction_id, status: "error", message: "Montant différent de celui de la transaction." }
        : { bank_transaction_id: i.bank_transaction_id, status: "ok" });
      const done = results.filter((r: { status: string }) => r.status === "ok").map((r: { bank_transaction_id: number }) => r.bank_transaction_id);
      server.transactions = server.transactions.filter((t) => !done.includes(t.id));
      return json(200, { results, counters: counters(),
        undo: done.length ? { method: "POST", url: "/api/v1/reconciliations/delete", body: { bank_transaction_ids: done } } : null });
    }
    if (url === "/api/v1/reconciliations/delete") {
      server.transactions = [tx(1, "PRLV EDF", -100), tx(2, "CB LEROY", -250), tx(3, "VIR HELLOASSO", 900)];
      return json(200, { results: [], counters: counters(), undo: null });
    }
    return json(404, { error: { code: "not_found", message: "?" } });
  }) as typeof fetch);
});

afterEach(() => vi.restoreAllMocks());

const region = () => screen.getByRole("region", { name: /Transactions à rapprocher/ });
const rows = () => within(region()).getAllByRole("row").slice(1);
const messages = (): string[] => show.mock.calls.map((c) => (c[0] as { message: string }).message);

async function ready() {
  await waitFor(() => expect(rows()).toHaveLength(3));
  await screen.findByText("BQ-11");
}

describe("ReconcilePage", () => {
  it("rapproche la transaction active avec Entrée et passe à la suivante", async () => {
    const user = userEvent.setup();
    renderWithProviders(<ReconcilePage />, { route: "/reconciliation/" });
    await ready();
    region().focus();
    await user.keyboard("{Enter}");
    await waitFor(() => expect(rows()).toHaveLength(2));
    expect(calls.find((c) => c.url === "/api/v1/reconciliations")!.body).toEqual({ items: [{ bank_transaction_id: 1, journal_line_id: 11 }] });
    expect(screen.getByText("2 transactions à rapprocher sur 3")).toBeInTheDocument();
    expect(rows()[0]).toHaveAttribute("aria-current", "true"); // CB LEROY devient active
    expect(screen.getByText("1 transaction rapprochée.")).toBeInTheDocument();
  });

  it("refuse Entrée quand les suggestions sont à égalité, accepte le choix 1…9", async () => {
    const user = userEvent.setup();
    renderWithProviders(<ReconcilePage />, { route: "/reconciliation/" });
    await ready();
    region().focus();
    await user.keyboard("j");
    await screen.findByText("BQ-21");
    await user.keyboard("{Enter}");
    expect(messages().some((m) => m.includes("équivalentes"))).toBe(true);
    expect(calls.some((c) => c.url === "/api/v1/reconciliations")).toBe(false);
    await user.keyboard("2");
    await waitFor(() => expect(calls.find((c) => c.url === "/api/v1/reconciliations")?.body)
      .toEqual({ items: [{ bank_transaction_id: 2, journal_line_id: 22 }] }));
  });

  it("sélectionne une plage, rapproche en masse avec résultat partiel, puis annule (Ctrl+Z)", async () => {
    server.reconcileFails.add(3);
    const user = userEvent.setup();
    renderWithProviders(<ReconcilePage />, { route: "/reconciliation/" });
    await ready();
    region().focus();
    await user.keyboard("{Shift>}{ArrowDown}{ArrowDown}{/Shift}");
    expect(screen.getByText("3 sélectionnées :")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Rapprocher les suggestions ★" }));
    await waitFor(() => expect(rows()).toHaveLength(2));
    expect(calls.find((c) => c.url === "/api/v1/reconciliations")!.body.items.map((i: { bank_transaction_id: number }) => i.bank_transaction_id)).toEqual([1, 3]);
    expect(messages()).toContain("1 transaction ignorée : pas de suggestion unique.");
    expect(messages()).toContain("Montant différent de celui de la transaction.");
    region().focus();
    await user.keyboard("{Control>}z{/Control}");
    await waitFor(() => expect(rows()).toHaveLength(3));
    expect(calls.some((c) => c.url === "/api/v1/reconciliations/delete")).toBe(true);
    expect(messages()).toContain("Action annulée.");
  });

  it("ouvre le panneau de saisie avec N, prérempli par le serveur, focus sur la contrepartie", async () => {
    const user = userEvent.setup();
    renderWithProviders(<ReconcilePage />, { route: "/reconciliation/" });
    await ready();
    region().focus();
    await user.keyboard("n");
    const dialog = await screen.findByRole("dialog", { name: "Créer l'écriture" });
    expect(calls.some((c) => c.url === "/api/v1/entries/form?bt_id=1")).toBe(true);
    expect(await within(dialog).findByLabelText("Compte, ligne 1")).toHaveValue("5121 — CA");
    expect(within(dialog).getByLabelText("Crédit, ligne 1")).toHaveValue("1,00");
    await waitFor(() => expect(within(dialog).getByLabelText("Compte, ligne 2")).toHaveFocus());
    await user.keyboard("{Escape}");  // ferme la liste des comptes
    await user.keyboard("{Escape}");  // ferme le panneau
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  it("annonce la transaction active aux lecteurs d'écran", async () => {
    const user = userEvent.setup();
    renderWithProviders(<ReconcilePage />, { route: "/reconciliation/" });
    await ready();
    const live = () => document.querySelector('[aria-live="polite"][aria-atomic="true"]')!;
    await waitFor(() => expect(live()).toHaveTextContent("Transaction 10/03/2026, PRLV EDF"));
    expect(live()).toHaveTextContent("1 suggestion");
    region().focus();
    await user.keyboard("j");
    await waitFor(() => expect(live()).toHaveTextContent("CB LEROY"));
    await user.keyboard(" ");
    expect(live()).toHaveTextContent("sélectionnée");
    expect(rows()[1]).toHaveAttribute("aria-current", "true");
  });

  it("affiche une transaction annulée sans permettre de la rapprocher ni d'en créer l'écriture", async () => {
    server.transactions[0] = tx(1, "PRLV EDF", -100, { is_reversed: true });
    server.suggestions[1] = [];
    const user = userEvent.setup();
    renderWithProviders(<ReconcilePage />, { route: "/reconciliation/" });
    await waitFor(() => expect(rows()).toHaveLength(3));
    expect(within(rows()[0]).getByText("Annulée")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Créer l'écriture (N)" })).not.toBeInTheDocument();
    region().focus();
    await user.keyboard("{Enter}");
    await user.keyboard("n");
    expect(messages().some((m) => m.includes("annulée par la banque"))).toBe(true);
    expect(calls.some((c) => c.url === "/api/v1/reconciliations")).toBe(false);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("affiche le feu, le type et la pièce par des icônes nommées, avec la légende des feux", async () => {
    server.transactions[0] = tx(1, "PRLV EDF", -100, { attachment_status: "missing", raw_type: "direct_debit",
      light: "orange", light_reasons: ["À rapprocher", "Justificatif manquant"] });
    server.transactions[1] = tx(2, "CB LEROY", -250, { attachment_status: "ok", raw_type: "card", light: "orange",
      light_reasons: ["À rapprocher"] });
    renderWithProviders(<ReconcilePage />, { route: "/reconciliation/" });
    await waitFor(() => expect(rows()).toHaveLength(3));
    expect(within(rows()[0]).getByRole("img", { name: "Justificatif manquant" })).toBeInTheDocument();
    expect(within(rows()[0]).getByRole("img", { name: "Prélèvement" })).toBeInTheDocument();
    expect(within(rows()[0]).getByRole("img", { name: "À traiter : À rapprocher, Justificatif manquant" })).toBeInTheDocument();
    expect(within(rows()[1]).getByRole("img", { name: "Justificatif présent" })).toBeInTheDocument();
    expect(within(rows()[1]).getByRole("img", { name: "Paiement par carte" })).toBeInTheDocument();
    expect(within(rows()[2]).queryByRole("img", { name: /Justificatif/ })).not.toBeInTheDocument();
    expect(screen.getByLabelText("Légende des feux")).toHaveTextContent("À traiter");
  });
});
