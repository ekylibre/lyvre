// Lot AG1.b : création d'une instance « Exploitation agricole » (forme, impôt et régime, premier exercice).
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithProviders, TEST_SESSION } from "../../test/render";
import InstancesPage from "./InstancesPage";

const json = (body: unknown) => Promise.resolve(new Response(JSON.stringify(body), { status: 200 }));
const META = {
  charts: [{ value: "asso", label: "Association (loi 1901)" }, { value: "agri", label: "Exploitation agricole (EI, EARL, GAEC, SCEA…)" }],
  default_chart: "asso", integrations_by_chart: { asso: [], agri: [] },
  agri: { legal_forms: [{ value: "EI", label: "Entreprise individuelle" }, { value: "GAEC", label: "GAEC" }],
    is_only_forms: ["SAS", "SA"], income_tax: [{ value: "IR", label: "Impôt sur le revenu" }, { value: "IS", label: "Impôt sur les sociétés" }],
    ba_regimes: [{ value: "micro", label: "Micro-BA" }, { value: "simplified", label: "Réel simplifié" }, { value: "normal", label: "Réel normal" }] },
};
const posted: unknown[] = [];

beforeEach(() => {
  posted.length = 0;
  vi.spyOn(globalThis, "fetch").mockImplementation(((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (init?.method === "POST") { posted.push(JSON.parse(String(init.body))); return json({ item: {}, notices: [] }); }
    if (url.startsWith("/api/v1/instances")) return json({ items: [], meta: META });
    return json({ items: [], meta: { roles: [] } });
  }) as typeof fetch);
});
afterEach(() => vi.restoreAllMocks());

describe("création d'une exploitation", () => {
  it("trois étapes ; micro-BA : exercice civil", async () => {
    const user = userEvent.setup();
    renderWithProviders(<InstancesPage />, { session: { ...TEST_SESSION, user: { ...TEST_SESSION.user!, is_admin: true } },
      route: "/instances/new" });
    await user.click(await screen.findByRole("combobox", { name: /Plan comptable/ }));
    await user.click(await screen.findByRole("option", { name: /Exploitation agricole/ }));
    expect(screen.getByText("1. Forme juridique")).toBeInTheDocument();
    expect(screen.getByText("3. Premier exercice")).toBeInTheDocument();
    await user.click(screen.getByRole("combobox", { name: /^Forme/ }));
    await user.click(await screen.findByRole("option", { name: "Entreprise individuelle" }));
    await user.click(screen.getByRole("combobox", { name: /Régime des bénéfices agricoles/ }));
    await user.click(await screen.findByRole("option", { name: "Micro-BA" }));
    expect(screen.getByText(/comptabilité simplifiée \(recettes et dépenses\), exercice civil/)).toBeInTheDocument();
    await user.type(screen.getByLabelText(/^Slug/), "ferme-micro");
    await user.type(screen.getByLabelText(/^Libellé/), "Ferme");
    await user.click(screen.getByRole("button", { name: "Créer l'instance" }));
    const year = new Date().getFullYear();
    await waitFor(() => expect(posted[0]).toMatchObject({ chart: "agri", legal_form_code: "EI", ba_regime: "micro",
      income_tax: "IR", fy_start: `${year}-01-01`, fy_end: `${year}-12-31` }));
  });
});
