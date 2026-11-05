// Lot AG7.a : assiette sociale MSA par exploitant.
import { afterEach, describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import { renderWithProviders, TEST_SESSION } from "../../test/render";
import MsaPage, { type MsaView } from "./MsaPage";

const json = (body: unknown) => Promise.resolve(new Response(JSON.stringify(body), { status: 200 }));
const VIEW: MsaView = {
  fiscal_year: { id: 7, label: "2026", status: "open" }, year: 2026, reason: null, tax_frozen: false,
  warnings: ["Option de déduction de la rente du sol (D.731-24 CRPM) : demande avant le 30 juin."],
  people: [{ person: { id: 1, name: "Exploitant (Ferme)", status: "principal", base_option: "triennial", option_since: null },
    share_bp: 10000, fiscal_result_cents: 3270000, income_cents: 4000000, base_cents: 2960000,
    lines: [{ key: "contributions", label: "Cotisations sociales personnelles (646)", amount_cents: 730000, basis: "assiette hors cotisations sociales" }],
    abatement: { amount_cents: 1040000, raw_cents: 1040000, floor_cents: 84586, ceiling_cents: 6247800, pass_cents: 4806000, bound: null },
    history: [{ id: 3, year: 2025, source: "entered", income_cents: null, abatement_cents: null, base_cents: 1500000, note: "avis MSA" }],
    comparison: { contribution_year: 2027, span: [2026, 2025, 2024], bases: { "2026": 2960000, "2025": 1500000, "2024": 1460000 }, missing: [],
      annual_cents: 2960000, triennial_cents: 1973333, difference_cents: 986667, best: "triennial", retained_cents: 1973333, notes: [],
      option: { current: "triennial", since: null, deadline: "2027-06-30", deadline_label: "Option pour l'assiette annuelle des cotisations 2027 à demander avant le 30/06/2027." } },
    estimate: { available: true, year: 2027, base_cents: 1973333, warnings: [], notes: ["Estimation indicative."],
      lines: [{ key: "rco", label: "Retraite complémentaire (RCO)", amount_cents: 87506, detail: "4 %", group: "cotisations", deductible: true }],
      totals: { total_cents: 87506, contributions_cents: 87506, csg_crds_cents: 0, non_deductible_cents: 0, third_party_cents: 0 } } }],
};
const META = { statuses: [{ value: "principal", label: "Chef d'exploitation à titre exclusif ou principal" }],
  base_options: [{ value: "triennial", label: "Moyenne triennale (droit commun)" }], adjustment_kinds: [{ value: "avaloir", label: "À-valoir social (art. 72 F) déduit" }] };

const CALLS = { year: 2026, warnings: ["Exploitant (Ferme) : modulation possible du solde du 08/12/2026."], monthly: false,
  kinds: [{ value: "first", label: "1er appel provisionnel" }],
  people: [{ person: { id: 1, name: "Exploitant (Ferme)" }, retained_base_cents: 2000000, retained_base_label: "moyenne des revenus 2023 à 2025",
    totals: { amount_cents: 300000, paid_cents: 0, contributions_cents: 0, csg_deductible_cents: 0, csg_crds_non_deductible_cents: 0 },
    calls: [{ id: 9, person_id: 1, year: 2026, kind: "first", kind_label: "1er appel provisionnel", due_on: "2026-04-28", amount_cents: 300000,
      base_cents: null, contributions_cents: null, csg_deductible_cents: null, csg_crds_non_deductible_cents: null, third_party_cents: null,
      estimated: false, note: null, payment: null, proposal: { available: true, basis: "moyenne" } }] }] };

const VENT = { mode: "ei", tax_lines: [{ key: "msa_csg", label: "CSG", amount_cents: 51750 }], checks: [], associates: [],
  accrual: { amount_cents: 500000, calls: [{ id: 2, due_on: "2026-12-08", amount_cents: 500000 }], entry: null } };

afterEach(() => vi.restoreAllMocks());

describe("Cotisations MSA", () => {
  it("assiette par exploitant et abattement borné", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(((url: string) => json(String(url).includes("/ventilation") ? { item: VENT } : String(url).includes("/msa/calls") ? { item: CALLS } : String(url).includes("/msa") ? { item: VIEW, meta: META }
      : { items: [{ id: 7, label: "2026", status: "open" }] })) as typeof globalThis.fetch);
    renderWithProviders(<MsaPage />, { route: "/msa/", session: { ...TEST_SESSION, role: "admin" as const, permissions: { write: true, instance_admin: true } } });
    expect(await screen.findByText("Exploitant (Ferme)")).toBeInTheDocument();
    expect(screen.getByText(/Abattement forfaitaire de 26 %/)).toBeInTheDocument();
    expect(screen.getByText("Assiette sociale 2026")).toBeInTheDocument();
    expect(screen.getByText(/rente du sol \(D\.731-24/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Ajouter" })).toBeInTheDocument();
    expect(screen.getByText("Assiette des cotisations 2027")).toBeInTheDocument();
    expect(screen.getByText(/moyenne triennale est plus basse/)).toBeInTheDocument();
    expect(screen.getByText("avis MSA")).toBeInTheDocument();
    expect(screen.getByText("Estimation des cotisations 2027 (indicative)")).toBeInTheDocument();
    expect(screen.getByText("Retraite complémentaire (RCO)")).toBeInTheDocument();
    expect((await screen.findAllByText("1er appel provisionnel")).length).toBeGreaterThan(0);
    expect(screen.getByRole("button", { name: "Estimer" })).toBeInTheDocument();
    expect(screen.getByText(/modulation possible/)).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: "Passer la charge à payer" })).toBeInTheDocument();
  });
});
