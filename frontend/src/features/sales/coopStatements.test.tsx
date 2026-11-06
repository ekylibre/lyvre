// Lot AG10.d : saisie d'un décompte de coopérative (lignes typées) et totaux.
import { afterEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithProviders } from "../../test/render";
import { CoopForm, CoopTotals } from "./CoopStatementsPage";

const json = (body: unknown) => Promise.resolve(new Response(JSON.stringify(body), { status: 201 }));
afterEach(() => vi.restoreAllMocks());

const OPTIONS = {
  entities: [{ value: "4", label: "Coopérative Fictive" }],
  kinds: [{ value: "delivery" as const, label: "Apport" }, { value: "shares" as const, label: "Parts sociales retenues" }],
  accounts: [{ value: "7011", label: "7011 — Ventes de produits végétaux" }], activities: [{ value: "2", label: "Blé tendre" }],
};

describe("Décomptes de coopérative", () => {
  it("affiche les totaux", () => {
    renderWithProviders(<CoopTotals t={{ sales_cents: 650000, sales_vat_cents: 35750, advances_cents: 200000, shares_cents: 15000,
      fees_cents: 20000, fees_vat_cents: 4000, customer_cents: 646750, net_cents: 446750 }} />);
    expect(screen.getByText("Net à payer")).toBeInTheDocument();
    expect(screen.getByText("Acomptes déjà versés")).toBeInTheDocument();
  });

  it("enregistre un brouillon avec ses lignes", async () => {
    const spy = vi.spyOn(globalThis, "fetch").mockImplementation((() => json({ item: { id: 9 }, notices: [] })) as typeof fetch);
    const onDone = vi.fn();
    renderWithProviders(<CoopForm options={OPTIONS} onDone={onDone} />);
    await userEvent.click(screen.getByRole("combobox", { name: /Coopérative/ }));
    await userEvent.click(await screen.findByRole("option", { name: "Coopérative Fictive" }));
    await userEvent.type(screen.getByLabelText(/N° du décompte/), "DEC-7");
    await userEvent.type(screen.getByLabelText(/^Date/), "2026-09-30");
    await userEvent.type(screen.getByLabelText("Désignation de la ligne 1"), "Blé tendre");
    await userEvent.type(screen.getByLabelText("Montant de la ligne 1"), "6000");
    await userEvent.click(screen.getByRole("button", { name: "Enregistrer le brouillon" }));
    await waitFor(() => expect(onDone).toHaveBeenCalled());
    const [url, init] = spy.mock.calls[0];
    expect(url).toBe("/api/v1/coop-statements");
    const body = JSON.parse(String((init as RequestInit).body));
    expect([body.entity_id, body.number, body.statement_date]).toEqual(["4", "DEC-7", "2026-09-30"]);
    expect(body.lines).toEqual([{ kind: "delivery", label: "Blé tendre", quantity: "", unit: "", amount: "6000", vat_rate: "",
      account_code: "", activity_id: "", campaign_year: "" }]);
  });
});
