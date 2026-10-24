// Lot F1 : historique d'une écriture (différences entre états), fiche d'une écriture validée.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { notifications } from "@mantine/notifications";
import { Route, Routes } from "react-router";
import { renderWithProviders } from "../../test/render";
import EntryDetailPage from "./EntryDetailPage";
import { diff } from "./validation";

type Call = { method: string; url: string; body: any }; // eslint-disable-line @typescript-eslint/no-explicit-any
let calls: Call[];
const json = (status: number, body: unknown) => Promise.resolve(new Response(JSON.stringify(body), { status }));
const line = (account: string, debit: number, credit: number) => ({ account, label: "Vente", debit_cents: debit, credit_cents: credit, project_id: null });
const snap = (date: string, amount: number) => ({ entry_date: date, description: "Vente", journal: "BQ", validation_number: null,
  lines: [line("512100", amount, 0), line("706", 0, amount)] });

const ENTRY = {
  id: 5, reference: "BQ-2026-0005", fiscal_year: "2026", fiscal_year_id: 1, fiscal_year_closed: false, journal: "BQ — Banque",
  entry_date: "2026-03-01", description: "Vente", source: "MANUAL", source_ref: null, is_balanced: true,
  total_debit_cents: 1500, total_credit_cents: 1500, reconciled: false, editable: false, managed: false,
  validated: true, validation_number: 3, validated_at: "2026-03-05T10:00:00", reversal: null, reverses: null, reversible: true,
  lines: [{ id: 1, account_id: 1, account_code: "512100", account_label: "Banque", label: "Vente", debit_cents: 1500, credit_cents: 0,
    project_id: null, project: null, reconciled: false }],
};

beforeEach(() => {
  calls = [];
  vi.spyOn(notifications, "show").mockReturnValue("id");
  vi.spyOn(globalThis, "fetch").mockImplementation(((input: RequestInfo | URL, init: RequestInit = {}) => {
    const url = String(input);
    calls.push({ method: init.method ?? "GET", url, body: init.body ? JSON.parse(init.body as string) : undefined });
    if (url === "/api/v1/entries/5") return json(200, ENTRY);
    if (url === "/api/v1/entries/5/history") return json(200, { items: [
      { id: 1, action: "create", at: "2026-03-01T09:00:00", user: "tresorier@asso.fr", origin: "api:x", snapshot: snap("2026-03-01", 1000) },
      { id: 2, action: "update", at: "2026-03-02T09:00:00", user: "tresorier@asso.fr", origin: "api:x", snapshot: snap("2026-03-02", 1500) },
      { id: 3, action: "validate", at: "2026-03-05T10:00:00", user: null, origin: "job", snapshot: { ...snap("2026-03-02", 1500), validation_number: 3 } },
    ] });
    if (url === "/api/v1/entries/5/reverse") return json(200, { item: { id: 6 }, notices: [] });
    return json(404, {});
  }) as typeof fetch);
});
afterEach(() => vi.restoreAllMocks());

describe("validation des écritures", () => {
  it("différences entre deux états", () => {
    const { changes, added, removed } = diff(snap("2026-03-01", 1000), snap("2026-03-02", 1500));
    expect(changes).toEqual(["Date : 01/03/2026 → 02/03/2026"]);
    expect(added.map((l) => l.account)).toEqual(["512100", "706"]);
    expect(removed.map((l) => l.debit_cents + l.credit_cents)).toEqual([1000, 1000]);
    expect(diff(snap("2026-03-01", 1000), snap("2026-03-01", 1000)).added).toEqual([]);
  });

  it("écriture validée : historique, pas de modification, contrepassation avec motif", async () => {
    renderWithProviders(<Routes><Route path="/entries/:entry_id" element={<EntryDetailPage />} /></Routes>, { route: "/entries/5" });
    expect(await screen.findByText("Validée n° 3")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Modifier" })).toBeNull();
    expect(await screen.findByText("Modification")).toBeTruthy();
    expect(screen.getByText("Validation")).toBeTruthy();
    expect(screen.getByText(/tâche automatique/)).toBeTruthy();
    await userEvent.click(screen.getByRole("button", { name: "Contrepasser" }));
    await screen.findByLabelText(/Motif/);
    await userEvent.type(screen.getByLabelText(/Motif/), "Doublon");
    await userEvent.click(screen.getAllByRole("button", { name: "Contrepasser" }).at(-1)!);
    await vi.waitFor(() => expect(calls.find((c) => c.url === "/api/v1/entries/5/reverse")?.body.reason).toBe("Doublon"));
  });
});
