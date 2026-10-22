import { afterEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Route, Routes } from "react-router";
import { renderWithProviders } from "../test/render";
import { matchAccount, type ChartAccount } from "./accounts/AccountsPage";
import { nextFiscalYear } from "./fiscal-years/FiscalYearsPage";
import JournalsPage from "./journals/JournalsPage";
import { testRegex } from "./rules/RulesPage";

afterEach(() => vi.restoreAllMocks());

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });

describe("exercice suivant proposé", () => {
  it("suit le dernier exercice connu", () => {
    const years = [
      { id: 1, label: "2025", start_date: "2025-01-01", end_date: "2025-12-31", closed: true, vat_liable: false,
        status: "provisional" as const, status_label: "Clôture provisoire" },
      { id: 2, label: "2025-26", start_date: "2025-07-01", end_date: "2026-06-30", closed: false, vat_liable: false,
        status: "open" as const, status_label: "Ouvert" },
    ];
    expect(nextFiscalYear(years)).toEqual({ label: "2026", start_date: "2026-07-01", end_date: "2027-06-30" });
    expect(nextFiscalYear([]).start_date).toMatch(/^\d{4}-01-01$/);
  });
});

describe("recherche dans le plan comptable", () => {
  const account: ChartAccount = { id: 1, code: "6061", label: "Fournitures non stockables (eau, énergie)",
    account_type: "EXPENSE", is_header: false, parent_code: null };
  it("par début de code ou mots du libellé, sans accents", () => {
    expect(matchAccount(account, "606")).toBe(true);
    expect(matchAccount(account, "061")).toBe(false);
    expect(matchAccount(account, "energie eau")).toBe(true);
    expect(matchAccount(account, "gaz")).toBe(false);
    expect(matchAccount(account, " ")).toBe(true);
  });
});

describe("test d'expression des règles", () => {
  it("prend en charge (?i) et signale une expression invalide", () => {
    expect(testRegex("(?i)maif", "PRELEVEMENT MAIF 123")).toBe(true);
    expect(testRegex("maif", "PRELEVEMENT MAIF 123")).toBe(false);
    expect(typeof testRegex("(", "x")).toBe("string");
  });
});

describe("JournalsPage", () => {
  it("liste les journaux et ouvre la création depuis /journals/new", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (_url, init) => {
      if (init?.method === "POST") {
        return json({ error: { code: "validation_error", message: "Le journal VT existe déjà.",
          fields: { code: "Le journal VT existe déjà." } } }, 422);
      }
      return json({ items: [{ id: 1, code: "VT", label: "Ventes" }] });
    });
    renderWithProviders(
      <Routes>
        <Route path="/journals" element={<JournalsPage />} />
        <Route path="/journals/new" element={<JournalsPage />} />
      </Routes>, { route: "/journals/new" });
    expect(await screen.findByText("Ventes")).toBeInTheDocument();
    const dialog = await screen.findByRole("dialog", { name: "Créer un journal" });
    await userEvent.type(screen.getByLabelText(/Code/), "vt");
    await userEvent.type(screen.getByLabelText(/Libellé/), "Ventes bis");
    await userEvent.click(screen.getByRole("button", { name: "Créer le journal" }));
    expect(await screen.findByText("Le journal VT existe déjà.")).toBeInTheDocument();
    expect(dialog).toBeInTheDocument();
    const post = fetchMock.mock.calls.find(([, init]) => init?.method === "POST")!;
    expect(JSON.parse(String(post[1]!.body))).toEqual({ code: "vt", label: "Ventes bis" });
    await userEvent.click(screen.getByRole("button", { name: "Annuler" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });
});
