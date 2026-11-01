import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { notifications } from "@mantine/notifications";
import { Route, Routes } from "react-router";
import { renderWithProviders } from "../../test/render";
import TransactionsPage from "./TransactionsPage";

const row = (id: number, label: string, extra: Record<string, unknown> = {}) => ({
  id, date: "2026-03-10", label, amount_cents: -5000, reconciled: true, is_reversed: false, attachment_status: null,
  category: "Énergie", entity: null, entity_id: null, raw_type: null, note: null, invoices: [], entry: null,
  new_entry_url: "", rule_tiers: false, ...extra,
});

type Call = { method: string; url: string; body: any }; // eslint-disable-line @typescript-eslint/no-explicit-any
let calls: Call[];
const json = (status: number, body: unknown) => Promise.resolve(new Response(JSON.stringify(body), { status }));

beforeEach(() => {
  calls = [];
  vi.spyOn(notifications, "show").mockReturnValue("id");
  vi.spyOn(globalThis, "fetch").mockImplementation(((input: RequestInfo | URL, init: RequestInit = {}) => {
    const url = String(input);
    const method = init.method ?? "GET";
    calls.push({ method, url, body: init.body ? JSON.parse(init.body as string) : undefined });
    if (url === "/api/v1/bank-accounts/1") {
      return json(200, { item: { id: 1, label: "Crédit Agricole", kind: "bank", iban: null, qonto: null,
        account: { id: 5, code: "512", label: "Banque" } }, qonto_job: null, proposal_count: 0, reversed_reconciled: [],
        meta: { months: [], qonto: { available: false, message: null } } });
    }
    if (url.startsWith("/api/v1/bank-accounts/1/transactions")) {
      return json(200, { transactions: [row(1, "PRLV EDF", { rule_tiers: true }), row(2, "CB DIVERS"),
        row(3, "BZIIIT — EKYLIBRE-SIA-26", { amount_cents: 360000, reconciled: false, category: null,
          sale_proposals: [{ id: 9, number: "F-2026-0001", client: "bziiit", due_date: "2026-08-20" }] })] });
    }
    if (url.startsWith("/api/v1/entities?")) return json(200, { results: [{ id: 7, name: "EDF", type: "FOURNISSEUR", email: null }] });
    if (url === "/api/v1/bank-transactions/1/entity") {
      return json(200, { item: row(1, "PRLV EDF", { rule_tiers: true, entity: "EDF", entity_id: 7 }),
        notices: [{ level: "success", message: "Transaction attribuée à EDF." }] });
    }
    if (url === "/api/v1/sales/match") {
      return json(200, { items: [], notices: [{ level: "success", message: "Encaissement rapproché (1 facture(s))." }] });
    }
    return json(404, { error: { code: "not_found", message: "?" } });
  }) as typeof fetch);
});

afterEach(() => vi.restoreAllMocks());

describe("TransactionsPage — attribuer un tiers", () => {
  it("propose l'attribution aux seules transactions passées par une règle et l'envoie", async () => {
    renderWithProviders(<Routes><Route path="/bank-accounts/:ba_id/transactions" element={<TransactionsPage />} /></Routes>,
      { route: "/bank-accounts/1/transactions" });
    await screen.findByText("PRLV EDF");
    expect(screen.getByText("Tiers par défaut")).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "Attribuer" })).toHaveLength(1);

    await userEvent.click(screen.getByRole("button", { name: "Attribuer" }));
    const dialog = await screen.findByRole("dialog", { name: "Attribuer à un tiers" });
    await userEvent.click(within(dialog).getByRole("combobox", { name: "Tiers" }));
    await userEvent.click(await screen.findByRole("option", { name: "EDF" }));
    await userEvent.click(within(dialog).getByRole("button", { name: "Attribuer" }));

    await waitFor(() => expect(calls.some((c) => c.method === "POST" && c.url === "/api/v1/bank-transactions/1/entity")).toBe(true));
    expect(calls.find((c) => c.method === "POST")?.body).toEqual({ entity_id: 7 });
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });
});

describe("TransactionsPage — encaisser une facture de vente", () => {
  it("propose la facture ouverte de même montant et l'encaisse par la transaction après confirmation", async () => {
    renderWithProviders(<Routes><Route path="/bank-accounts/:ba_id/transactions" element={<TransactionsPage />} /></Routes>,
      { route: "/bank-accounts/1/transactions" });
    await userEvent.click(await screen.findByRole("button", { name: "Encaisser F-2026-0001" }));
    const dialog = await screen.findByRole("dialog", { name: "Encaisser la facture F-2026-0001 ?" });
    await userEvent.click(within(dialog).getByRole("button", { name: "Encaisser" }));
    await waitFor(() => expect(calls.some((c) => c.method === "POST" && c.url === "/api/v1/sales/match")).toBe(true));
    expect(calls.find((c) => c.url === "/api/v1/sales/match")?.body).toEqual(
      { bank_transaction_id: 3, allocations: [{ sale_id: 9, amount_cents: 360000 }] });
  });
});
