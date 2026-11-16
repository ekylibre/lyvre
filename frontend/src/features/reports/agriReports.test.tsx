// Lot AG1.c : soldes intermédiaires de gestion et annexe « biens vivants » du bilan d'une exploitation agricole.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import { renderWithProviders, TEST_SESSION } from "../../test/render";
import type { Session } from "../../api/session";
import BilanPage from "./BilanPage";
import SigPage from "./SigPage";

const json = (body: unknown) => Promise.resolve(new Response(JSON.stringify(body), { status: 200 }));
const META = { fiscal_years: [{ value: "1", label: "2026" }], fiscal_year: { id: 1, label: "2026", start_date: "2026-01-01",
  end_date: "2026-12-31" }, previous: null };
const session = (chart: "agri" | "societe"): Session => ({ ...TEST_SESSION, instance: { ...TEST_SESSION.instance!, chart } });

beforeEach(() => {
  vi.spyOn(globalThis, "fetch").mockImplementation(((input: RequestInfo | URL) => {
    const url = String(input);
    if (url.startsWith("/api/v1/reports/sig")) return json({ items: [
      { key: "production", label: "Production de l'exercice", kind: "total", n: 525000000, p: null },
      { key: "valeur_ajoutee", label: "Valeur ajoutée", kind: "total", n: 365000000, p: null },
      { key: "ebe", label: "Excédent brut d'exploitation", kind: "total", n: 380000000, p: null },
    ], meta: { ...META, export_url: "/reports/agri-statements.xlsx?fy_id=1" } });
    if (url.startsWith("/api/v1/reports/living-assets")) return json({ item: {
      groups: [{ key: "long", label: "Biens vivants (cycle long)", rows: [{ key: "animaux", label: "Animaux", opening: 0, closing: 182000000 }],
        total: { opening: 0, closing: 182000000 } },
      { key: "court", label: "Biens vivants (cycle court)", rows: [{ key: "vegetaux", label: "Végétaux", opening: 0, closing: 30000000 }],
        total: { opening: 0, closing: 30000000 } }],
      total: { opening: 0, closing: 212000000 },
      headcount: [{ kind: "breeding", label: "Animaux reproducteurs", opening: 0, entries: 20, exits: 5, closing: 15 }] }, meta: META });
    if (url.startsWith("/api/v1/reports/bilan")) return json({ actif: [], passif: [], meta: { ...META, layout: "agri_ei" } });
    return json({ items: [] });
  }) as typeof fetch);
});
afterEach(() => vi.restoreAllMocks());

describe("états agricoles", () => {
  it("soldes intermédiaires et export", async () => {
    renderWithProviders(<SigPage />, { session: session("agri") });
    expect(await screen.findByText("Excédent brut d'exploitation")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Exporter en XLSX" })).toHaveAttribute("href", "/reports/agri-statements.xlsx?fy_id=1");
  });

  it("bilan : annexe des biens vivants pour une exploitation seulement", async () => {
    renderWithProviders(<BilanPage />, { session: session("agri") });
    expect(await screen.findByText("Annexe : biens vivants et en-cours de production")).toBeInTheDocument();
    expect(screen.getByText("TOTAL GÉNÉRAL (I + II)")).toBeInTheDocument();
    expect(screen.getByText("Effectifs des biens vivants immobilisés")).toBeInTheDocument();
    expect(screen.getByText("Animaux reproducteurs")).toBeInTheDocument();
  });

  it("pas d'annexe pour une société", async () => {
    renderWithProviders(<BilanPage />, { session: session("societe") });
    expect(await screen.findByText("Actif")).toBeInTheDocument();
    expect(screen.queryByText("Annexe : biens vivants et en-cours de production")).not.toBeInTheDocument();
  });
});
