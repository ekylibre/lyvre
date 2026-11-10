// Lots AG9a.b, AG9a.c : échéancier (liste, fiche, questions, paiements, détections).
import { afterEach, describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithProviders, TEST_SESSION } from "../../test/render";
import AgendaPage from "./AgendaPage";
import type { AgendaResponse, Occurrence } from "./types";

const json = (body: unknown) => Promise.resolve(new Response(JSON.stringify(body), { status: 200 }));
const occ = (over: Partial<Occurrence>): Occurrence => ({
  key: "k", deadline_id: "TVA-02#1", fiche_id: "TVA-02", label: "Acompte de TVA", title: "Acomptes trimestriels de TVA (3525 bis)",
  domain: "tva", organism: "SIE", date: "2026-11-05", period: "acompte n° 3 2026", status: "this_week", timing: "this_week",
  to_confirm: false, note: null, edi_date: null, amount_cents: 100100, amount_proposed: true, managed: true, link: "/vat-returns/",
  action: { label: "Préparer le 3525 bis", route: "/vat-returns/" }, quiet: false, reminder_only: false, reliability: "R",
  reminder_from: "2026-10-21", state: null, payment: true, unlinked: false, ...over,
});
const DATA: AgendaResponse = {
  today: "2026-11-02", start: "2026-08-04", end: "2027-12-07", questions: ["PAC-01"],
  detections: [{ id: "unreconciled", level: "warning", title: "Relevés non rapprochés", detail: "3 transactions de plus de 30 jours.",
    link: "/reconciliation/", link_label: "Rapprocher" }],
  items: [occ({}), occ({ key: "k2", deadline_id: "FIS-06#1", fiche_id: "FIS-06", label: "Taxe foncière non bâtie", domain: "fiscal",
    organism: "SIP", date: "2026-10-15", period: "2026", status: "late", amount_cents: null, managed: false, action: null })],
  fiches: {
    "TVA-02": { id: "TVA-02", title: "Acomptes trimestriels de TVA (3525 bis)", domain: "tva", domain_label: "TVA", organism: "SIE",
      summary: "Au moins 1/5 de la TVA due l'année précédente.", prepare: ["TVA due de la dernière CA12A (ligne 23)"],
      lyvre_data: null, penalties: "Intérêt de retard de 0,20 % par mois.", links: ["https://bofip.impots.gouv.fr/node/10637"],
      reliability: "R", reminder_only: false },
    "FIS-06": { id: "FIS-06", title: "Taxe foncière sur les propriétés non bâties (TFNB)", domain: "fiscal", domain_label: "Fiscal",
      organism: "SIP", summary: "Paiement le 15/10.", prepare: null, lyvre_data: null, penalties: null, links: null, reliability: "A",
      reminder_only: false },
    "PAC-01": { id: "PAC-01", title: "Demande d'aides PAC (telepac)", domain: "pac", domain_label: "PAC et aides", organism: "DDT(M)",
      summary: "", prepare: null, lyvre_data: null, penalties: null, links: null, reliability: "A", reminder_only: true },
  },
  statuses: [{ value: "late", label: "En retard" }, { value: "this_week", label: "Cette semaine" }],
  domains: [{ value: "tva", label: "TVA" }, { value: "fiscal", label: "Fiscal" }],
};

afterEach(() => vi.restoreAllMocks());

describe("Échéancier", () => {
  it("blocs, montant, question et fiche", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((() => json(DATA)) as typeof fetch);
    renderWithProviders(<AgendaPage />, { route: "/agenda/",
      session: { ...TEST_SESSION, role: "admin" as const, permissions: { write: true, instance_admin: true } } });
    expect(await screen.findByText(/En retard/, { selector: "h4" })).toBeInTheDocument();
    expect(screen.getByText(/Cette semaine/, { selector: "h4" })).toBeInTheDocument();
    expect(screen.getByText(/Demande d'aides PAC/)).toBeInTheDocument();
    await userEvent.click(screen.getByText("Acompte de TVA"));
    expect(await screen.findByText(/Montant calculé par Lyvre/)).toBeInTheDocument();
    expect(screen.getByText(/suivie par Lyvre/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Préparer le 3525 bis" })).toBeInTheDocument();
  });

  it("détections et paiement reconnu", async () => {
    const bankState = { id: 7, status: "done" as const, done_on: "2026-11-05", origin: "bank" as const, note: null,
      transaction: { id: 3, bank_account_id: 1, date: "2026-11-05", label: "PRLV DGFIP", amount_cents: -100100 } };
    const data = { ...DATA, items: [occ({ status: "done", state: bankState }), DATA.items[1]] };
    vi.spyOn(globalThis, "fetch").mockImplementation((() => json(data)) as typeof fetch);
    renderWithProviders(<AgendaPage />, { route: "/agenda/",
      session: { ...TEST_SESSION, role: "admin" as const, permissions: { write: true, instance_admin: true } } });
    expect(await screen.findByText("Relevés non rapprochés")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Rapprocher" })).toBeInTheDocument();
    await userEvent.click(screen.getByText("Acompte de TVA"));
    expect(await screen.findByText(/Paiement reconnu/)).toBeInTheDocument();
    expect(screen.getByText(/PRLV DGFIP/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Détacher le paiement" })).toBeInTheDocument();
  });

  it("un rappel silencieux passé ne s'affiche ni en retard ni parmi les faites", async () => {
    const data = { ...DATA, items: [...DATA.items, occ({ key: "k3", fiche_id: "FIS-06", label: "Acompte du prélèvement à la source",
      date: "2026-10-15", status: "done", quiet: true, state: null, managed: false })] };
    vi.spyOn(globalThis, "fetch").mockImplementation((() => json(data)) as typeof fetch);
    renderWithProviders(<AgendaPage />, { route: "/agenda/",
      session: { ...TEST_SESSION, role: "admin" as const, permissions: { write: true, instance_admin: true } } });
    expect(await screen.findByText("Taxe foncière non bâtie")).toBeInTheDocument();
    expect(screen.queryByText("Acompte du prélèvement à la source")).not.toBeInTheDocument();
  });

  it("rattache un débit à la main", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(((url: string) => json(String(url).includes("candidates")
      ? { items: [{ id: 9, bank_account_id: 1, date: "2026-10-16", label: "PRLV SIP TFNB", amount_cents: -45000, amount_matches: false }] }
      : DATA)) as typeof fetch);
    renderWithProviders(<AgendaPage />, { route: "/agenda/",
      session: { ...TEST_SESSION, role: "admin" as const, permissions: { write: true, instance_admin: true } } });
    await userEvent.click(await screen.findByText("Taxe foncière non bâtie"));
    expect(await screen.findByText(/PRLV SIP TFNB/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Rattacher" }));
    const post = fetchMock.mock.calls.find(([, init]) => (init as RequestInit | undefined)?.method === "POST");
    expect(JSON.parse(String((post![1] as RequestInit).body))).toMatchObject({ bank_transaction_id: 9, status: "done" });
  });
});
