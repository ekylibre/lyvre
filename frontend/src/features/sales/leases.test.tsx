// Lot S5 : émission en lot des échéances préparées, création d'un bail.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { notifications } from "@mantine/notifications";
import { renderWithProviders } from "../../test/render";
import DueSalesPage from "./DueSalesPage";
import { LeaseForm } from "./LeasesPage";

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
    if (url === "/api/v1/sales/due") return json(200, { items: [{ id: 5, kind: "invoice", status: "draft", status_label: "Brouillon", number: null,
      client: { id: 2, name: "Locataire Martin" }, issue_date: "2026-10-23", due_date: "2026-11-01", total_cents: 85000 }], meta: { prepared: 1 } });
    if (url === "/api/v1/sales/issue-batch") return json(200, { result: { issued: 1, sent: 0, errors: [] }, notices: [] });
    if (url === "/api/v1/leases" && method === "POST") return json(201, { item: { id: 3 }, notices: [] });
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

describe("bail", () => {
  it("création : loyer, charges, dépôt", async () => {
    const user = userEvent.setup();
    const done = vi.fn();
    renderWithProviders(<LeaseForm lease={null} onDone={done}
      meta={{ tenants: [{ value: "2", label: "Locataire Martin" }], accounts: [], bank_accounts: [], qonto: false }} />);
    await user.click(screen.getByRole("combobox", { name: "Locataire" }));
    await user.click(await screen.findByRole("option", { name: "Locataire Martin" }));
    await user.type(screen.getByLabelText(/^Lot/), "Appartement 2B");
    await user.type(screen.getByLabelText(/^Loyer hors charges/), "800");
    await user.type(screen.getByLabelText(/^Provisions sur charges/), "50");
    await user.click(screen.getByRole("button", { name: "Créer le bail" }));
    await waitFor(() => expect(calls.find((c) => c.method === "POST")?.body).toMatchObject({
      entity_id: "2", unit_label: "Appartement 2B", rent: "800", charges: "50", due_day: "1", in_advance: true }));
    await waitFor(() => expect(done).toHaveBeenCalled());
  });
});
