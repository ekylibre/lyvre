import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { notifications } from "@mantine/notifications";
import { renderWithProviders } from "../../test/render";
import BankAccountsPage from "./BankAccountsPage";

type Call = { method: string; url: string; body: any }; // eslint-disable-line @typescript-eslint/no-explicit-any
let calls: Call[];
const json = (status: number, body: unknown) => Promise.resolve(new Response(JSON.stringify(body), { status }));
const account = (id: number, label: string, extra: Record<string, unknown> = {}) => ({
  id, label, iban: null, kind: "bank", qonto: null, account: { id: 5, code: "512000", label: "Banque" },
  balance_cents: 0, transactions: 3, unreconciled: 0, ...extra,
});

beforeEach(() => {
  calls = [];
  vi.spyOn(notifications, "show").mockReturnValue("id");
  vi.spyOn(globalThis, "fetch").mockImplementation(((input: RequestInfo | URL, init: RequestInit = {}) => {
    const url = String(input);
    const method = init.method ?? "GET";
    calls.push({ method, url, body: init.body ? JSON.parse(init.body as string) : undefined });
    if (url === "/api/v1/bank-accounts") {
      return json(200, { items: [
        account(1, "CIC", { bank_balance: { balance_cents: 7500, at: "2026-11-02", opening_missing: true, fiscal_year: "2026" } }),
        account(2, "Qonto", { bank_balance: { balance_cents: 123456, at: "2026-11-02", opening_missing: false, fiscal_year: "2026" } }),
        account(3, "Caisse", { kind: "cash" }),
      ], meta: { gl_accounts: [], cash_accounts: [], qonto: { available: false, message: null } } });
    }
    if (url === "/api/v1/bank-accounts/1/opening" && method === "GET") {
      return json(200, { item: { amount_cents: null, date: null, proposed_date: "2026-01-01", entry: null, entry_allowed: true },
        meta: { counterparts: [{ value: "8", label: "102 — Fonds propres sans droit de reprise" },
          { value: "new:103", label: "103 — Fonds propres avec droit de reprise (à créer)" }] } });
    }
    if (url === "/api/v1/bank-accounts/1/opening" && method === "PUT") {
      return json(200, { item: {}, opening: {}, notices: [{ level: "success", message: "Solde bancaire d'ouverture enregistré." }] });
    }
    return json(404, { error: { code: "not_found", message: "?" } });
  }) as typeof fetch);
});

afterEach(() => vi.restoreAllMocks());

describe("BankAccountsPage — solde bancaire", () => {
  it("affiche le solde bancaire et signale le solde d'ouverture manquant", async () => {
    renderWithProviders(<BankAccountsPage />, { route: "/bank-accounts/" });
    expect(await screen.findByText("Solde bancaire")).toBeInTheDocument();
    expect(await screen.findByText(/234,56/)).toBeInTheDocument();
    expect(screen.getByText(/75,00/)).toBeInTheDocument();
    expect(screen.getAllByText(/Solde d'ouverture (à saisir|manquant)/)).toHaveLength(1);
  });

  it("saisit le solde d'ouverture avec l'écriture d'apport", async () => {
    const user = userEvent.setup();
    renderWithProviders(<BankAccountsPage />, { route: "/bank-accounts/" });
    await user.click(await screen.findByText(/Solde d'ouverture (à saisir|manquant)/));
    const amount = await screen.findByLabelText(/Solde d'ouverture/);
    await user.type(amount, "500");
    expect(screen.getByLabelText(/Passer l'écriture d'apport initial/)).toBeChecked();
    await user.click(screen.getByRole("button", { name: "Enregistrer" }));
    await waitFor(() => expect(calls.find((c) => c.method === "PUT")?.body).toEqual(
      { amount_cents: 50000, date: "2026-01-01", post_entry: true, counterpart: "8" }));
  });
});
