// Brevo sur l'écran Adhérents (lot B3) : menu (aperçu d'abord), rapport d'un aperçu avec validation,
// conflits, désinscrits, adhérents sans e-mail.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Route, Routes } from "react-router";
import { renderWithProviders, TEST_SESSION } from "../../test/render";
import type { Session } from "../../api/session";
import BrevoReportPage from "./BrevoReportPage";
import { BrevoMenu } from "./BrevoMenu";

const SESSION: Session = { ...TEST_SESSION,
  instance: { ...TEST_SESSION.instance!, integrations: { enabled: ["brevo"], proposed: [] } } };
const REPORT = {
  dry_run: true, created: 12, linked: 319, updated: 0, unchanged: 0, unlinked: 0, conflicts: 1, skipped: 1,
  blacklisted: 1, orphans: 30, errors: [],
  conflict_items: [{ entity_id: 4, name: "Chloé Durand", reason: "Nouvel e-mail déjà utilisé dans Brevo par un autre contact." }],
  blacklisted_items: [{ entity_id: 2, name: "Bruno Petit" }], skipped_items: [{ entity_id: 9, name: "Sans E-mail" }],
};

let posted: unknown[];
let firstPending = true;
beforeEach(() => {
  posted = [];
  firstPending = true;
  vi.spyOn(globalThis, "fetch").mockImplementation(((input: RequestInfo | URL, init: RequestInit = {}) => {
    const url = String(input);
    const json = (body: unknown, status = 200) => Promise.resolve(new Response(JSON.stringify(body), { status }));
    if (init.method === "POST") { posted.push(JSON.parse(String(init.body))); return json({ job: { id: 8 } }, 202); }
    if (url === "/api/v1/brevo/status") return json({ enabled: true, configured: true, first_sync_pending: firstPending,
      links: firstPending ? 0 : 331, conflicts: 0, last_job: null });
    return json({ job: { id: 7, status: "done", message: "Synchronisation terminée.", progress_done: 0, progress_total: null },
      result: REPORT, first_sync_pending: false });
  }) as typeof fetch);
});
afterEach(() => vi.restoreAllMocks());

describe("menu Brevo", () => {
  it("absent si l'intégration est désactivée", () => {
    renderWithProviders(<BrevoMenu />);
    expect(screen.queryByRole("button", { name: "Brevo" })).not.toBeInTheDocument();
  });

  it("première fois : synchronisation bloquée, aperçu lancé", async () => {
    renderWithProviders(<BrevoMenu />, { session: SESSION });
    await userEvent.click(await screen.findByRole("button", { name: "Brevo" }));
    expect(screen.getByText("Première synchronisation : lancez d'abord l'aperçu.")).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: "Synchroniser avec Brevo" })).toBeDisabled();
    await userEvent.click(screen.getByRole("menuitem", { name: "Aperçu (sans rien écrire)" }));
    await waitFor(() => expect(posted).toEqual([{ dry_run: true }]));
  });

  it("ensuite : synchronisation directe", async () => {
    firstPending = false;
    renderWithProviders(<BrevoMenu />, { session: SESSION });
    await userEvent.click(await screen.findByRole("button", { name: "Brevo" }));
    expect(screen.getByText("331 adhérent(s) lié(s)")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("menuitem", { name: "Synchroniser avec Brevo" }));
    await waitFor(() => expect(posted).toEqual([{ dry_run: false }]));
  });
});

describe("rapport", () => {
  it("aperçu : compteurs, conflits, désinscrits, validation", async () => {
    renderWithProviders(<Routes><Route path="/entities/members/brevo/:job_id" element={<BrevoReportPage />} /></Routes>,
      { session: SESSION, route: "/entities/members/brevo/7" });
    expect(await screen.findByText("Aperçu de la synchronisation Brevo")).toBeInTheDocument();
    expect(screen.getByText("319")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Chloé Durand" })).toHaveAttribute("href", "/entities/4");
    expect(screen.getByText(/déjà utilisé dans Brevo/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Bruno Petit" })).toBeInTheDocument();
    expect(screen.getByText(/30 contact\(s\) de la liste Brevo/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Synchroniser" }));
    await waitFor(() => expect(posted).toEqual([{ dry_run: false }]));
  });
});
