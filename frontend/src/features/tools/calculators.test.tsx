// Lot AG12.a : formulaire générique d'une calculette (préremplissage avec origine, exemple, calcul) et gabarit.
import { afterEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithProviders } from "../../test/render";
import { CalculatorForm } from "./CalculatorPage";
import type { CalcResult, CalcSpec } from "./types";

const json = (body: unknown) => Promise.resolve(new Response(JSON.stringify(body), { status: 200 }));
afterEach(() => vi.restoreAllMocks());

const SPEC: CalcSpec = {
  code: "acompte-tva", number: "25", title: "Acomptes de TVA du RSA", category: "vat", category_label: "TVA",
  summary: "", charts: ["agri"], prefillable: true, method: "Chaque acompte vaut 20 % de la TVA due.", sources: [],
  prefill_label: null,
  inputs: [
    { key: "year", label: "Année des acomptes", kind: "integer", unit: null, required: true, choices: null, help: null, default: null },
    { key: "due", label: "TVA due l'année précédente", kind: "money", unit: "€", required: true, choices: null, help: null, default: null },
  ],
  example: { year: "2027", due: "8400" },
  prefill: { year: { value: "2026", origin: "année en cours" }, due: { value: "5000.00", origin: "CA12A 2025" } },
};

const RESULT: CalcResult = {
  headline: [{ label: "Chaque acompte", value: "1 680,00 €" }], details: [{ label: "Part", value: "20 %" }],
  table: { columns: ["N°", "Échéance"], rows: [[1, "05/05/2027"]] }, warnings: [], actions: [{ label: "Déclarations de TVA", route: "/vat-returns/" }],
  params: [{ key: "vat.rsa.installment_share_bp", value: 2000, missing: false, valid_from: "2016-01-01", valid_to: null,
    source: "https://bofip.impots.gouv.fr/node/10637", source_label: "CGI art. 1693 bis I", verified_on: "2026-11-03", reliability: "R" }],
  on: "2027-12-31", text: "Acomptes de TVA du RSA…",
};

describe("Calculette", () => {
  it("préremplit avec l'origine, garde l'origine non modifiée, affiche le résultat", async () => {
    const spy = vi.spyOn(globalThis, "fetch").mockImplementation((() => json({ result: RESULT })) as typeof fetch);
    renderWithProviders(<CalculatorForm spec={SPEC} />);
    expect(screen.getByText("Origine : CA12A 2025")).toBeInTheDocument();
    const due = screen.getByLabelText(/TVA due/);
    await userEvent.clear(due);
    await userEvent.type(due, "8400");
    expect(screen.queryByText("Origine : CA12A 2025")).toBeNull();          // valeur modifiée : saisie
    await userEvent.click(screen.getByRole("button", { name: "Calculer" }));
    await waitFor(() => expect(screen.getByText("1 680,00 €")).toBeInTheDocument());
    const body = JSON.parse(String((spy.mock.calls[0][1] as RequestInit).body));
    expect(body).toEqual({ values: { year: "2026", due: "8400" }, origins: { year: "année en cours" } });
    expect(screen.getByText("recoupé")).toBeInTheDocument();
    expect(screen.getByText("Chaque acompte vaut 20 % de la TVA due.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Copier le résultat" })).toBeInTheDocument();
  });

  it("charge l'exemple et affiche l'erreur de l'API", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((() => Promise.resolve(new Response(JSON.stringify(
      { error: { code: "conflict", message: "Paramètre réglementaire absent" } }), { status: 409 }))) as typeof fetch);
    renderWithProviders(<CalculatorForm spec={SPEC} />);
    await userEvent.click(screen.getByRole("button", { name: "Charger l'exemple" }));
    expect(screen.getByLabelText(/TVA due/)).toHaveValue("8400");
    await userEvent.click(screen.getByRole("button", { name: "Calculer" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Paramètre réglementaire absent");
  });
});

// Lot AG12.d : point choisi sur la carte (carte remplacée par un bouton dans les tests).
vi.mock("./CalcMap", () => ({
  default: ({ onPick, features }: { onPick?: (lat: number, lon: number) => void; features?: { features: unknown[] } | null }) => (
    <div>{onPick && <button type="button" onClick={() => onPick(45.8295, -0.787)}>clic carte</button>}
      {features && <span>{features.features.length} parcelle(s) sur la carte</span>}</div>),
}));

const ZONES: CalcSpec = {
  ...SPEC, code: "zonages", title: "Zonages de ma parcelle", prefill: {}, method: "Zonages publiés.",
  inputs: [{ key: "point", label: "Point sur la carte", kind: "point", unit: null, required: true, choices: null, help: null, default: null }],
  example: { point: "45.8295,-0.7870" },
};

describe("Calculette géographique", () => {
  it("prend le point cliqué et affiche la carte du résultat", async () => {
    const spy = vi.spyOn(globalThis, "fetch").mockImplementation(((url: string) => json(url.includes("/geo/organization")
      ? { center: { lat: 46, lon: 0, zoom: 12 } }
      : { result: { ...RESULT, map: { center: [45.8295, -0.787], zoom: 15, features: { type: "FeatureCollection", features: [{}, {}] } } } }
    )) as typeof fetch);
    renderWithProviders(<CalculatorForm spec={ZONES} />);
    await userEvent.click(await screen.findByRole("button", { name: "clic carte" }));
    expect(screen.getByLabelText(/Point sur la carte/)).toHaveValue("45.8295,-0.787");
    await userEvent.click(screen.getByRole("button", { name: "Calculer" }));
    expect(await screen.findByText("2 parcelle(s) sur la carte")).toBeInTheDocument();
    const post = spy.mock.calls.find(([, init]) => (init as RequestInit | undefined)?.method === "POST")!;
    expect(JSON.parse(String((post[1] as RequestInit).body)).values).toEqual({ point: "45.8295,-0.787" });
  });
});
