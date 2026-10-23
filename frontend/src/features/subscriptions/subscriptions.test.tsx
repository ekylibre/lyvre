// Lot S6 : liste des abonnements (coûts, manquantes, préavis), création d'un abonnement.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { notifications } from "@mantine/notifications";
import { renderWithProviders } from "../../test/render";
import SubscriptionsPage, { SubscriptionForm } from "./SubscriptionsPage";
import type { SubscriptionsMeta } from "./types";

type Call = { method: string; url: string; body: any }; // eslint-disable-line @typescript-eslint/no-explicit-any
let calls: Call[];
const json = (status: number, body: unknown) => Promise.resolve(new Response(JSON.stringify(body), { status }));
const META: SubscriptionsMeta = {
  summary: { monthly_cents: 9500, yearly_cents: 114000, by_category: [{ category: "insurance", label: "Assurance", monthly_cents: 5000 }],
    missing: 2, notice_alerts: 1 },
  categories: [{ value: "internet", label: "Internet" }], frequencies: [{ value: "monthly", label: "Mensuel" }],
  suppliers: [{ value: "3", label: "Orange SA" }], products: [], bank_accounts: [],
};

beforeEach(() => {
  calls = [];
  vi.spyOn(notifications, "show").mockReturnValue("id");
  vi.spyOn(globalThis, "fetch").mockImplementation(((input: RequestInfo | URL, init: RequestInit = {}) => {
    const url = String(input);
    calls.push({ method: init.method ?? "GET", url, body: init.body ? JSON.parse(init.body as string) : undefined });
    if (url === "/api/v1/subscriptions" && (init.method ?? "GET") === "GET") return json(200, { items: [{ id: 1, label: "Assurance", category: "insurance",
      category_label: "Assurance", supplier: { id: 3, name: "Orange SA" }, amount_cents: 60000, amount_fixed: true, frequency: "yearly",
      frequency_label: "Annuel", due_day: 1, monthly_cents: 5000, start_date: "2026-01-01", end_date: null, renewal_date: "2026-12-01",
      notice_days: 30, next_renewal: "2026-12-01", notice_deadline: "2026-11-01", notice_alert: true, active: true, notes: "",
      product_id: "", bank_account_id: "", last_period: null, missing: 2 }], meta: META });
    if (url === "/api/v1/subscriptions") return json(201, { item: { id: 9 }, notices: [] });
    return json(404, {});
  }) as typeof fetch);
});
afterEach(() => vi.restoreAllMocks());

describe("abonnements", () => {
  it("coûts, échéances manquantes, préavis", async () => {
    renderWithProviders(<SubscriptionsPage />);
    expect(await screen.findByText(/2 échéance\(s\) passée\(s\) sans facture/)).toBeTruthy();
    expect(screen.getByText("préavis avant le 01/11/2026")).toBeTruthy();
    expect(screen.getByText(/1 contrat\(s\) arrivent à la date limite/)).toBeTruthy();
  });

  it("création", async () => {
    const user = userEvent.setup();
    const done = vi.fn();
    renderWithProviders(<SubscriptionForm sub={null} meta={META} onDone={done} />);
    await user.type(screen.getByLabelText(/^Désignation/), "Box internet");
    await user.click(screen.getByRole("combobox", { name: "Fournisseur" }));
    await user.click(await screen.findByRole("option", { name: "Orange SA" }));
    await user.type(screen.getByLabelText(/^Montant TTC/), "45");
    await user.click(screen.getByRole("button", { name: "Créer l'abonnement" }));
    await waitFor(() => expect(calls.find((c) => c.method === "POST")?.body).toMatchObject({
      label: "Box internet", entity_id: "3", amount: "45", frequency: "monthly", amount_fixed: true, end_date: null }));
  });
});
