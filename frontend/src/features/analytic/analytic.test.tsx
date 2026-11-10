// Lot AG8.b : ventilation analytique des lignes.
import { afterEach, describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import { renderWithProviders, TEST_SESSION } from "../../test/render";
import AnalyticPage, { type UnallocatedView } from "./AnalyticPage";

const json = (body: unknown) => Promise.resolve(new Response(JSON.stringify(body), { status: 200 }));
const VIEW: UnallocatedView = {
  fiscal_year: { id: 7, label: "2026" },
  coverage: { charges: { total_cents: 1200000, allocated_cents: 1000000, ratio_bp: 8333 }, products: { total_cents: 5000000, allocated_cents: 5000000, ratio_bp: 10000 } },
  groups: [{ account: "60614", label: "Carburants et lubrifiants", count: 1, amount_cents: 200000, partial: 0 }],
  lines: [{ id: 11, date: "2026-06-30", reference: null, label: "Gazole", account: "60614", amount_cents: 200000, origin: null, origin_label: null, targets: [], share_bp: 0 }],
  suggestions: [{ account_prefix: "70111", account_label: "Ventes de blé", target: { kind: "activity", id: 2, label: "Grandes cultures › Blé" } }],
};

afterEach(() => vi.restoreAllMocks());

describe("Ventilation analytique", () => {
  it("couverture, comptes à ventiler, lignes et suggestions", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(((url: string) => json(String(url).includes("/analytic/") ? { item: VIEW, meta: { targets: [{ value: "activity:2", label: "Blé", group: "Grandes cultures" }] } }
      : { items: [{ id: 7, label: "2026", status: "open" }] })) as typeof globalThis.fetch);
    renderWithProviders(<AnalyticPage />, { route: "/analytic/?fiscal_year=7&account=60614",
      session: { ...TEST_SESSION, role: "admin" as const, permissions: { write: true, instance_admin: true } } });
    expect(await screen.findByText("60614 Carburants et lubrifiants")).toBeInTheDocument();
    expect(screen.getByText("83,3 %")).toBeInTheDocument();
    expect(screen.getByText("Gazole")).toBeInTheDocument();
    expect(screen.getByText("70111 Ventes de blé → Grandes cultures › Blé")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Affecter les lignes cochées" })).toBeDisabled();
    expect(screen.getByText("1 ligne")).toBeInTheDocument();
  });

  it("sans activité : invite à créer les activités, pas de formulaire ; dotations remplacées", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(((url: string) => json(String(url).includes("/analytic/")
      ? { item: { ...VIEW, replaced: [{ account: "68112", label: "Immobilisations corporelles", count: 3, amount_cents: 120000 }] }, meta: { targets: [] } }
      : { items: [{ id: 7, label: "2026", status: "open" }] })) as typeof globalThis.fetch);
    renderWithProviders(<AnalyticPage />, { route: "/analytic/?fiscal_year=7&account=60614",
      session: { ...TEST_SESSION, role: "admin" as const, permissions: { write: true, instance_admin: true } } });
    expect(await screen.findByText(/Aucune activité ni clé de répartition/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Affecter/ })).not.toBeInTheDocument();
    expect(screen.getByText(/68112 Immobilisations corporelles \(3 lignes\)/)).toBeInTheDocument();
  });
});
