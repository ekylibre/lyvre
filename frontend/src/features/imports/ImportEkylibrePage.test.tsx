// Lot RE6 : Imports › Sauvegarde Ekylibre (analyse affichée, restauration bloquée ou permise).
import { afterEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithProviders } from "../../test/render";
import ImportEkylibrePage from "./ImportEkylibrePage";

const json = (body: unknown, status = 200) => Promise.resolve(new Response(JSON.stringify(body), { status }));
const ANALYSIS = {
  profile: ["Profil : **standard**, référentiel `agri`", "TVA déductible des achats conservée en 4456x"],
  chart: "agri", detected_chart: "agri", period: { start: "2024-01-01", until: "2025-12-31" }, years: [2020, 2024, 2025],
  volumes: { entries: 4668, purchases: 666, sales: 1299, statement_items: 730, fixed_assets: 11, entities: 1054, accounts: 1153, activities: 5 },
  checks: [{ label: "Écritures de la période équilibrées (4668)", ok: true, blocking: true, details: [], more: 0 },
    { label: "Solde 51210000 au 31/12/2025 = relevés", ok: false, blocking: false, details: ["Comptabilité 1256.56 €, relevés 1257.53 €"], more: 0 }],
  blocking: 0, warnings: 1, options: { from_year: null, all_history: false, attachments: true },
};
const overview = (extra: Record<string, unknown> = {}) => ({
  item: { archive: { name: "entredeuxterres.zip", size: 1575464127, uploaded_at: "2026-11-08T10:00:00" }, analysis: ANALYSIS,
    imported: null, report: true, blockers: [], max_upload: 4294967296, ...extra }, job: null,
});

afterEach(() => vi.restoreAllMocks());

describe("Sauvegarde Ekylibre", () => {
  it("affiche l'analyse et lance la restauration", async () => {
    const spy = vi.spyOn(globalThis, "fetch").mockImplementation(((url: string, init?: RequestInit) =>
      init?.method === "POST"
        ? json({ job: { id: 9, kind: "ekylibre_restore", status: "running", message: "Restauration en cours…", progress_done: 0,
          progress_total: null, result: null, finished_at: null } }, 202)
        : String(url).includes("/jobs/") ? json({ job: { id: 9, kind: "ekylibre_restore", status: "running", message: null,
          progress_done: 0, progress_total: null, result: null, finished_at: null } }) : json(overview())) as typeof fetch);
    renderWithProviders(<ImportEkylibrePage />);
    expect(await screen.findByText("entredeuxterres.zip")).toBeInTheDocument();
    expect(screen.getByText("1.5 Go, déposée le 08/11/2026", { exact: false })).toBeInTheDocument();
    expect(screen.getByText("Contrôles bloquants passés")).toBeInTheDocument();
    expect(screen.getByText("1 anomalie(s)")).toBeInTheDocument();
    expect(screen.getByText("Profil : standard, référentiel agri")).toBeInTheDocument();
    expect(screen.getByText("Comptabilité 1256.56 €, relevés 1257.53 €")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Restaurer dans cette instance" }));
    await waitFor(() => expect(spy.mock.calls.some(([u, i]) => String(u).endsWith("/imports/ekylibre/run") && (i as RequestInit)?.method === "POST")).toBe(true));
    const post = spy.mock.calls.find(([u]) => String(u).endsWith("/run"))!;
    expect(JSON.parse(String((post[1] as RequestInit).body))).toEqual({ all_history: false, from_year: null, attachments: true });
    expect(await screen.findByText("Restauration en cours…", { selector: "div,span,p" })).toBeInTheDocument();
  });

  it("instance non vide : restauration désactivée, motif affiché", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((() => json(overview({ blockers: ["L'instance contient déjà 3 écriture(s) : restaurez dans une instance vide."] }))) as typeof fetch);
    renderWithProviders(<ImportEkylibrePage />);
    expect(await screen.findByText("Restauration impossible dans cette instance")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Restaurer dans cette instance" })).toBeDisabled();
  });

  it("sans sauvegarde : zone de dépôt", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((() => json(overview({ archive: null, analysis: null, report: false }))) as typeof fetch);
    renderWithProviders(<ImportEkylibrePage />);
    expect(await screen.findByText("Déposez la sauvegarde Ekylibre (.zip)")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Analyser" })).toBeNull();
  });
});
