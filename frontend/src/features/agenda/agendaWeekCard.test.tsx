// Lots AG9a.d, AG9a.e : résumé du lundi (carte du tableau de bord), abonnement à l'e-mail, adresse iCal.
import { afterEach, describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithProviders, TEST_SESSION } from "../../test/render";
import { AgendaWeekCard } from "./AgendaWeekCard";
import AgendaPage from "./AgendaPage";
import type { WeeklySummary } from "./types";

const json = (body: unknown) => Promise.resolve(new Response(JSON.stringify(body), { status: 200 }));
const SUMMARY: WeeklySummary = {
  day: "2026-11-02", week: "2026-W45", monday: "2026-11-02", counts: { late: 1, this_week: 1, to_prepare: 0, to_check: 1 },
  empty: false, to_prepare: [],
  late: [{ key: "a", label: "Taxe foncière non bâtie", title: "TFNB", organism: "SIP", date: "2026-10-15", period: "2026",
    status: "late", amount_cents: null, amount_proposed: false, link: "/agenda/", action_label: null, penalties: "10 %", missing: [] }],
  this_week: [{ key: "b", label: "Acompte de TVA", title: "Acomptes", organism: "SIE", date: "2026-11-05", period: "acompte n° 3 2026",
    status: "this_week", amount_cents: 100100, amount_proposed: true, link: "/vat-returns/", action_label: "Préparer le 3525 bis",
    penalties: null, missing: ["montant calculé par Lyvre, à valider"] }],
  to_check: [{ id: "unreconciled", level: "warning", title: "Relevés non rapprochés", detail: "…", link: "/reconciliation/",
    link_label: "Rapprocher" }],
};
const SESSION = { ...TEST_SESSION, role: "admin" as const, permissions: { write: true, instance_admin: true } };

afterEach(() => vi.restoreAllMocks());

describe("Résumé du lundi", () => {
  it("carte du tableau de bord", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((() => json({ item: SUMMARY })) as typeof fetch);
    renderWithProviders(<AgendaWeekCard />, { route: "/", session: SESSION });
    expect(await screen.findByText(/semaine du 02\/11\/2026/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Acompte de TVA" })).toHaveAttribute("href", "/vat-returns/");
    expect(screen.getByText("Relevés non rapprochés")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Tout l'échéancier" })).toBeInTheDocument();
  });

  it("désabonnement depuis l'échéancier", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(((url: string) => json(String(url).includes("subscription")
      ? { item: { subscribed: true, email: "user@example.org", available: true, last_sent_week: null }, notices: [] }
      : { items: [], questions: [], detections: [], today: "2026-11-02", start: "2026-08-04", end: "2027-12-07", fiches: {},
        statuses: [], domains: [] })) as typeof fetch);
    renderWithProviders(<AgendaPage />, { route: "/agenda/", session: SESSION });
    const toggle = await screen.findByRole("switch", { name: /Résumé du lundi/ });
    expect(toggle).toBeChecked();
    await userEvent.click(toggle);
    const put = fetchMock.mock.calls.find(([, init]) => (init as RequestInit | undefined)?.method === "PUT");
    expect(JSON.parse(String((put![1] as RequestInit).body))).toEqual({ subscribed: false });
  });

  it("crée l'adresse iCal", async () => {
    let url: string | null = null;
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(((input: string, init?: RequestInit) => {
      const path = String(input);
      if (path.includes("/agenda/ical")) {
        if (init?.method === "POST") url = "https://lyvre.example/agenda/ical/test/abc.ics";
        return json({ item: { url }, notices: [] });
      }
      if (path.includes("subscription")) return json({ item: null });
      return json({ items: [], questions: [], detections: [], today: "2026-11-02", start: "2026-08-04", end: "2027-12-07",
        fiches: {}, statuses: [], domains: [] });
    }) as typeof fetch);
    renderWithProviders(<AgendaPage />, { route: "/agenda/", session: SESSION });
    await userEvent.click(await screen.findByRole("button", { name: "Agenda (iCal)" }));
    await userEvent.click(await screen.findByRole("button", { name: "Créer l'adresse du calendrier" }));
    expect(await screen.findByDisplayValue("https://lyvre.example/agenda/ical/test/abc.ics")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Révoquer" })).toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([, i]) => (i as RequestInit | undefined)?.method === "POST")).toBe(true);
  });
});
