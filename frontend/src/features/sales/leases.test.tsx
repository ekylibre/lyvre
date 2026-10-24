// Lot S5 : émission en lot des échéances préparées ; lot L1 : assistant de bail (brouillon, biens, loyer).
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { notifications } from "@mantine/notifications";
import { Route, Routes } from "react-router";
import { renderWithProviders } from "../../test/render";
import DueSalesPage from "./DueSalesPage";
import LeaseWizardPage, { annualOf, hectares } from "./LeaseWizardPage";

type Call = { method: string; url: string; body: any }; // eslint-disable-line @typescript-eslint/no-explicit-any
let calls: Call[];
const META = { tenants: [{ value: "2", label: "Association Preneuse" }], accounts: [], bank_accounts: [], qonto: false,
  kinds: [{ value: "derogatory", label: "Bail dérogatoire commercial" }],
  natures: [{ value: "building", label: "Bâtiment" }, { value: "land", label: "Sol" }, { value: "flat", label: "Forfait" }],
  units: [{ value: "m2", label: "€ / m² / an" }, { value: "ha", label: "€ / ha / an" }, { value: "flat", label: "€ / an" }],
  indexes: [{ value: "ILC", label: "Indice des loyers commerciaux (ILC)" }],
  frequencies: [{ value: "monthly", label: "Mensuelle" }, { value: "yearly", label: "Annuelle" }] };
const ITEM = { id: 9, position: 0, letter: "A", label: "Bureau", nature: "building", area_m2: 40, built_m2: 40, billing_unit: "m2",
  unit_price_cents: 0, annual_cents: 0, cadastral_refs: ["AH 248"], source: "manual", partial: false, has_geometry: false };
let lease: Record<string, unknown>;
const json = (status: number, body: unknown) => Promise.resolve(new Response(JSON.stringify(body), { status }));

beforeEach(() => {
  calls = [];
  lease = { id: 3, status: "draft", unit_label: "La Vauzelle", tenant: { id: 2, name: "Association Preneuse" }, kind: "derogatory",
    kind_label: "", premises_label: "", address_line1: "", address_line2: "", postal_code: "", city: "", start_date: "2026-10-01",
    end_date: null, deposit_cents: 0, index_code: "", index_reference_period: "", index_reference_value: "", revision_months: "",
    revise_deposit: false, signed_on_place: "", notes: "", items: [], frequency: "monthly", due_day: 1, in_advance: true,
    vat_rate: "0", charges_cents: 0, rent_account_code: "", charges_account_code: "", qonto_emit: false, rent_cents: 0, annual_cents: 0 };
  vi.spyOn(notifications, "show").mockReturnValue("id");
  vi.spyOn(globalThis, "fetch").mockImplementation(((input: RequestInfo | URL, init: RequestInit = {}) => {
    const url = String(input);
    const method = init.method ?? "GET";
    calls.push({ method, url, body: init.body ? JSON.parse(init.body as string) : undefined });
    if (url === "/api/v1/sales/due") return json(200, { items: [{ id: 5, kind: "invoice", status: "draft", status_label: "Brouillon", number: null,
      client: { id: 2, name: "Locataire Martin" }, issue_date: "2026-10-23", due_date: "2026-11-01", total_cents: 85000 }], meta: { prepared: 1 } });
    if (url === "/api/v1/sales/issue-batch") return json(200, { result: { issued: 1, sent: 0, errors: [] }, notices: [] });
    if (url === "/api/v1/leases" && method === "GET") return json(200, { items: [], meta: META });
    if (url === "/api/v1/leases" && method === "POST") return json(201, { item: lease, notices: [] });
    if (url === "/api/v1/leases/3" && method === "GET") return json(200, { item: lease });
    if (url === "/api/v1/leases/3/items" && method === "POST") {
      lease = { ...lease, items: [ITEM] };
      return json(201, { item: ITEM, lease });
    }
    if (url === "/api/v1/leases/3/items/9" && method === "PATCH") return json(200, { item: ITEM, lease });
    if (url === "/api/v1/leases/3/activate") return json(200, { item: { ...lease, status: "active" }, notices: [] });
    return json(404, {});
  }) as typeof fetch);
});
afterEach(() => vi.restoreAllMocks());

describe("échéances à émettre", () => {
  it("préparées puis émises en lot", async () => {
    const user = userEvent.setup();
    renderWithProviders(<DueSalesPage />);
    expect(await screen.findByText("1 échéance(s) préparée(s) à l'instant.")).toBeTruthy();
    await user.click(screen.getAllByRole("checkbox")[1]);
    await user.click(screen.getByRole("button", { name: "Émettre (1)" }));
    await waitFor(() => expect(calls.find((c) => c.url === "/api/v1/sales/issue-batch")?.body).toEqual({ ids: [5], send: false }));
  });
});

describe("assistant de bail", () => {
  it("montants : m², hectares à l'are, forfait", () => {
    expect(hectares(4940)).toBe(0.49);
    expect(annualOf("ha", 10323, 14000)).toBe(14420);
    expect(annualOf("m2", 155, 200)).toBe(31000);
    expect(annualOf("flat", 0, 5000)).toBe(5000);
  });

  it("brouillon, bien loué, prix puis validation", async () => {
    const user = userEvent.setup();
    renderWithProviders(<Routes>
      <Route path="/leases/new" element={<LeaseWizardPage />} />
      <Route path="/leases/:lease_id/edit" element={<LeaseWizardPage />} />
      <Route path="/leases/:lease_id" element={<p>Fiche du bail</p>} />
    </Routes>, { route: "/leases/new" });
    await user.click(await screen.findByRole("combobox", { name: "Locataire (preneur)" }));
    await user.click(await screen.findByRole("option", { name: "Association Preneuse" }));
    await user.click(screen.getByRole("combobox", { name: "Type de bail" }));
    await user.click(await screen.findByRole("option", { name: "Bail dérogatoire commercial" }));
    await user.type(screen.getByLabelText(/^Désignation/), "La Vauzelle");
    await user.click(screen.getByRole("button", { name: "Suivant" }));
    await waitFor(() => expect(calls.find((c) => c.method === "POST")?.body).toMatchObject({
      draft: true, entity_id: "2", kind: "derogatory", unit_label: "La Vauzelle" }));

    await user.click(await screen.findByRole("button", { name: "Ajouter un bien" }));
    const dialog = await screen.findByRole("dialog");
    await user.type(within(dialog).getByLabelText(/^Désignation/), "Bureau");
    await user.type(within(dialog).getByLabelText(/^Surface louée/), "40");
    await user.click(within(dialog).getByRole("button", { name: "Ajouter" }));
    await waitFor(() => expect(calls.find((c) => c.url === "/api/v1/leases/3/items")?.body).toMatchObject({
      label: "Bureau", nature: "building", area_m2: "40" }));
    await user.click(await screen.findByRole("button", { name: "Suivant" }));

    await user.type(await screen.findByLabelText("Prix Bureau"), "2");
    expect(screen.getAllByText("80,00 €").length).toBeGreaterThan(0);
    await user.click(screen.getByRole("button", { name: "Valider le bail" }));
    await waitFor(() => expect(calls.find((c) => c.url === "/api/v1/leases/3/items/9")?.body).toEqual({ billing_unit: "m2", unit_price: "2" }));
    await waitFor(() => expect(calls.find((c) => c.url === "/api/v1/leases/3/activate")?.body).toMatchObject({ frequency: "monthly" }));
    expect(await screen.findByText("Fiche du bail")).toBeTruthy();
  });
});
