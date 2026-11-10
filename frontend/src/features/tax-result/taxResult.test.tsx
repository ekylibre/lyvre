// Lot AG6.a : résultat fiscal et tableau de passage.
import { afterEach, describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import { renderWithProviders, TEST_SESSION } from "../../test/render";
import TaxResultPage, { type TaxResultView } from "./TaxResultPage";

const json = (body: unknown) => Promise.resolve(new Response(JSON.stringify(body), { status: 200 }));
const VIEW: TaxResultView = {
  fiscal_year: { id: 7, label: "2026", end_date: "2026-12-31", status: "open" }, accounting_result_cents: 4000000,
  lines: [{ key: "stock_gap", label: "Écart de valeur fiscale des stocks", amount_cents: 20000, source: "inventory", link: "/inventory/" },
    { key: "manual_1", id: 1, kind: "csg", label: "Part de la CSG non déductible", amount_cents: 50000, source: "manual", reason: "appel MSA" }],
  additions_cents: 70000, deductions_cents: 0, fiscal_result_cents: 4070000, company_is: false, warnings: [], frozen: false, frozen_at: null,
  associates: [{ associate_id: 1, name: "Paul", share_bp: 6000, basis: "parts (pleine propriété et usufruit)", is_operator: true, fiscal_result_cents: 642000, ja_cents: 1800000 }],
};

const DEP = {
  base_cents: 4000000, deduction_cents: 3000000, ceiling: { ceiling_cents: 3530090, operators: 1 },
  register: [{ id: 1, kind_label: "DEP", origin: "2026", amount_cents: 3000000, outstanding_cents: 3000000, deadline: "2036", deadline_now: false, movements: [] }],
  savings: { accounts: [], at_close_cents: 0, at_deadline_cents: 0, deadline: "2027-06-30", substitutes_cents: 0, substitutes: [],
    savings_cents: 0, pending_cents: 3000000, minimum_cents: 1500000, ratio_bp: 0, below: true, above: false, deadline_passed: false },
  hazard: { value_added_cents: 4000000, average3_cents: null, drop3_bp: null, hazard: false }, movements: [], hazards: [],
};

const COW = {
  proposal: { eligible: true, reason: null, increase_cents: 1050000, cap_cents: 1500000, operators: 1, egalim_contract: false, minoration_bp: 2000,
    amount_cents: 840000, heads: 63, value_cents: 7650000, warnings: [],
    categories: [{ category: "dairy", label: "Vaches laitières", opening_cents: 4800000, closing_cents: 5850000, heads: 45, increase_cents: 1050000 },
      { category: "suckler", label: "Vaches allaitantes", opening_cents: 2000000, closing_cents: 1800000, heads: 18, increase_cents: 0 }] },
  plan: [], register: [], constituted: false, entry: null,
};

const SPREADS = {
  proposal: { base_cents: 10000000, average_cents: 2000000, floor_cents: 2500000, exceptional_cents: 7500000, reason: null,
    previous: [{ year: 2025, label: "2025", fiscal_result_cents: 2000000, source: "entered" }] },
  register: [{ id: 1, origin: "2026", fiscal_year_id: 7, kind_label: "Bénéfice exceptionnel (art. 75-0 A, 1-a)", amount_cents: 7500000, reason: null,
    schedule: [{ rank: 1, label: "2026", amount_cents: 1071429 }] }],
  kinds: [{ value: "profit", label: "Bénéfice exceptionnel (art. 75-0 A, 1-a)" }],
  averaging: { labels: ["2024", "2025", "2026"], totals: [2000000, 2000000, 3571429], average_cents: 2523810, option: false,
    associates: [{ associate_id: 1, name: "Paul", values: [null, null, 2142857], average_cents: null }] },
};

const LIASSE = { form: "2139", millesime: 2026, title: "BA réel simplifié", reliability: "I", warnings: [], not_covered: ["2139-C-SD"],
  tables: [{ code: "2139-B-SD", title: "Compte de résultat simplifié", checks: [{ label: "FJ = CE", ok: true, difference_cents: 0 }],
    rows: [{ case: "EA", label: "Produits végétaux", kind: "accounts", amount_cents: 10000000, detail: false, note: null, unit: null, accounts: ["7011"], exclude: null }] }] };

const GAINS = { disposals: [{ asset_id: 1, label: "Parcelle", account: "2111", acquired_on: "2015-01-01", disposed_on: "2026-06-30", net_cents: 1000000,
  price_cents: 2500000, gain_cents: 1500000, short_cents: 0, long_cents: 1500000, long_held: true, excluded: false, excluded_reason: null }],
  short_cents: 0, long_cents: 1500000, long_exempt_cents: 0, long_taxable_cents: 1500000, short_exempt_cents: 0,
  septies: { activity_since: "2010-01-01", young_farmer_buyer: false, average_cents: 20000000, rate_bp: 10000, detail: "exonération totale", reason: null, applied: false, associates: [],
    receipts: [{ year: 2024, threshold_cents: null }, { year: 2025, threshold_cents: 40000000 }] } };
const CREDITS = { items: [{ id: 1, kind: "hve", label: "Crédit d'impôt certification HVE", data: {}, amount_cents: 250000, detail: "certification", associates: [] }],
  total_cents: 250000, kinds: [{ value: "hve", label: "HVE" }], notes: [] };

afterEach(() => vi.restoreAllMocks());

describe("Résultat fiscal", () => {
  it("tableau de passage et répartition", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(((url: string) => json(String(url).endsWith("/dep") ? { item: DEP } : String(url).endsWith("/cow-provision") ? { item: COW } : String(url).endsWith("/income-spreads") ? { item: SPREADS } : String(url).endsWith("/liasse") ? { item: LIASSE } : String(url).endsWith("/capital-gains") ? { item: GAINS } : String(url).endsWith("/tax-credits") ? { item: CREDITS } : String(url).includes("tax-result")
      ? { item: VIEW, meta: { kinds: [{ value: "csg", label: "Part de la CSG non déductible" }] } }
      : { items: [{ id: 7, label: "2026", status: "open", start_date: "2026-01-01", end_date: "2026-12-31" }] })) as typeof globalThis.fetch);
    renderWithProviders(<TaxResultPage />, { route: "/tax-result/",
      session: { ...TEST_SESSION, role: "admin" as const, permissions: { write: true, instance_admin: true } } });
    expect(await screen.findByText("Écart de valeur fiscale des stocks")).toBeInTheDocument();
    expect(screen.getByText("Répartition par associé")).toBeInTheDocument();
    expect(screen.getByText("60 %")).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Abattement JA" })).toBeInTheDocument();
    expect(await screen.findByText("Déduction pour épargne de précaution (DEP)")).toBeInTheDocument();
    expect(screen.getByText("2036")).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "Ajouter" }).length).toBeGreaterThan(0);
    expect(await screen.findByText("Provision pour augmentation du stock de vaches (art. 73 A)")).toBeInTheDocument();
    expect(screen.getByText("Vaches allaitantes")).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: /EGALIM/ })).not.toBeChecked();
    expect(screen.getByRole("button", { name: "Passer l'écriture" })).toBeInTheDocument();
    expect(await screen.findByText("Étalement des revenus exceptionnels (art. 75-0 A)")).toBeInTheDocument();
    expect(screen.getByText(/Historique pour la moyenne triennale/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Étaler" })).toBeInTheDocument();
    expect(await screen.findByText("Aide à la liasse 2139 (millésime 2026)")).toBeInTheDocument();
    expect(screen.getByText("équilibré")).toBeInTheDocument();
    expect(await screen.findByText("Plus-values professionnelles")).toBeInTheDocument();
    expect(screen.getByText("2111 Parcelle")).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: "Appliquer l'exonération" })).not.toBeChecked();
    expect(screen.getByText(/2024 inconnues/)).toBeInTheDocument();
  });
});
