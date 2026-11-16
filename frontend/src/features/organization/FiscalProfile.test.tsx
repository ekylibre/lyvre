// Lot AG1.a : onglet Fiscalité de la Structure (régimes datés, options et date de renonciation) et page des
// paramètres réglementaires (valeurs lisibles, fiabilité).
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import { renderWithProviders, TEST_SESSION } from "../../test/render";
import type { Session } from "../../api/session";
import OrganizationPage from "./OrganizationPage";
import RegulatoryValuesPage, { formatParam } from "../regulatory/RegulatoryValuesPage";

const json = (body: unknown) => Promise.resolve(new Response(JSON.stringify(body), { status: 200 }));
const session = (chart: "asso" | "societe"): Session => ({ ...TEST_SESSION, role: "admin",
  permissions: { write: true, instance_admin: true }, instance: { ...TEST_SESSION.instance!, chart } });

const PROFILE = {
  item: {
    legal_form_code: "GAEC", created_on: "1995-04-01", current: { income_tax: "IR", ba_regime: "simplified", vat_regime: null },
    warnings: ["GAEC : 2 à 10 associé(s) attendu(s), 1 enregistré(s)."],
    periods: [{ id: 1, kind: "ba_regime", kind_label: "Régime des bénéfices agricoles", value: "simplified",
      value_label: "Réel simplifié", start_date: "2026-01-01", end_date: null, origin: "law", origin_label: "De plein droit", note: null }],
    options: [{ id: 2, code: "vat_quarterly", label: "Option CA3 trimestrielle (RSA)", start_date: "2024-01-01",
      duration_years: 5, tacit_renewal: true, renounced_on: null, current_period: { first_year: 2024, last_year: 2028 },
      renounce_by: { date: "2029-02-05", reliability: "R", note: "" }, note: null }],
  },
  meta: { legal_forms: [{ value: "GAEC", label: "GAEC" }], origins: [], options: [], kinds: [] },
};
const ORGANIZATION = { name: "GAEC des Prés", siren: null, legal_form_code: "GAEC", created_on: "1995-04-01",
  fec_ready: false, has_associates: true, associate_interest_rate: "0", jei_since: null, vat_due_day: "" };

beforeEach(() => {
  vi.spyOn(globalThis, "fetch").mockImplementation(((input: RequestInfo | URL) => {
    const url = String(input);
    if (url === "/api/v1/organization") return json({ item: ORGANIZATION });
    if (url === "/api/v1/tax-profile") return json(PROFILE);
    if (url.startsWith("/api/v1/regulatory-values")) return json({ items: [{ key: "ba.micro.threshold_cents", domain: "ba",
      current: { key: "ba.micro.threshold_cents", value: 12920000, valid_from: "2026-01-01", valid_to: null, source: "https://x.fr",
        source_label: "CGI art. 69", verified_on: "2026-11-03", reliability: "I", reliability_label: "Incertaine", note: "",
        origin: "file", id: null }, history: [] }], meta: { reliabilities: [], on: "2026-11-03" } });
    return json({ items: [] });
  }) as typeof fetch);
});
afterEach(() => vi.restoreAllMocks());

describe("onglet Fiscalité", () => {
  it("régimes, option avec date de renonciation et alertes", async () => {
    renderWithProviders(<OrganizationPage />, { session: session("societe"), route: "/organization?tab=tax" });
    expect(await screen.findByText("Réel simplifié")).toBeInTheDocument();
    expect(screen.getByText("Option CA3 trimestrielle (RSA)")).toBeInTheDocument();
    expect(screen.getByText("05/02/2029")).toBeInTheDocument();
    expect(screen.getByText("2024–2028 (tacite)")).toBeInTheDocument();
    expect(screen.getByText(/2 à 10 associé/)).toBeInTheDocument();
  });

  it("absent pour une association", async () => {
    renderWithProviders(<OrganizationPage />, { session: session("asso") });
    expect(await screen.findByRole("tab", { name: "Identité" })).toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: "Fiscalité" })).not.toBeInTheDocument();
  });
});

describe("paramètres réglementaires", () => {
  it("valeurs lisibles", () => {
    expect(formatParam("ba.micro.threshold_cents", 12920000)).toMatch(/129\s?200 €/);
    expect(formatParam("ba.micro.allowance_bp", 8700)).toBe("87 %");
    expect(formatParam("ba.micro.company_cutoff_date", "1997-01-01")).toBe("01/01/1997");
    expect(formatParam("option.x.renounce", null)).toBe("—");
  });

  it("liste avec fiabilité", async () => {
    renderWithProviders(<RegulatoryValuesPage />);
    expect(await screen.findByText("ba.micro.threshold_cents")).toBeInTheDocument();
    expect(screen.getByText("Incertaine")).toBeInTheDocument();
  });
});
