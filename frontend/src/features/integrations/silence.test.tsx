// Intégration désactivée (lot I2) : ni bandeau, ni bouton, ni colonne qui n'existent que pour elle.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import { renderWithProviders, TEST_SESSION } from "../../test/render";
import type { Session } from "../../api/session";
import { IntegrationNotice } from "../../components/IntegrationNotice";
import PurchasesPage from "../purchases/PurchasesPage";

const json = (status: number, body: unknown) => Promise.resolve(new Response(JSON.stringify(body), { status }));

function withIntegrations(enabled: string[]): Session {
  return { ...TEST_SESSION, instance: { ...TEST_SESSION.instance!, integrations: { enabled, proposed: [] } } };
}

const PURCHASES = {
  items: [{ id: 1, issue_date: "2026-09-02", invoice_number: "F-1", is_credit_note: false, source: "qonto",
    qonto_upload_status: null, qonto_upload_error: null, is_einvoice: false, has_attachment: false,
    supplier: null, supplier_name: "EDF", total_cents: 1200, state: { code: "posted", label: "Comptabilisée", reasons: [] },
    qonto_status: "paid", qonto_status_label: "Payée", review_reason: null, due_date: null }],
  meta: { counters: { to_complete: 0, to_review: 2, to_replace: 0, supplier_proposals: 0, hidden: 0, without_supplier: 0, ready: 0 },
    suppliers: [], states: [], statuses: [], months: [], sync: { from: "2026-01-01", synced_at: null, job: null },
    qonto: { enabled: false, available: false, message: null, upload: false } },
};

beforeEach(() => {
  vi.spyOn(globalThis, "fetch").mockImplementation(((input: RequestInfo | URL) =>
    String(input).startsWith("/api/v1/purchases") ? json(200, PURCHASES) : json(404, {})) as typeof fetch);
});

afterEach(() => vi.restoreAllMocks());

describe("bandeau d'intégration", () => {
  const unavailable = { available: false, message: "Intégration Qonto non configurée (Configuration › Intégrations)." };

  it("muet si l'intégration est désactivée", () => {
    renderWithProviders(<IntegrationNotice name="qonto" state={unavailable} consequence="synchronisation impossible" />,
      { session: withIntegrations([]) });
    expect(screen.queryByRole("status")).toBeNull();
  });

  it("affiché si elle est activée mais non configurée", () => {
    renderWithProviders(<IntegrationNotice name="qonto" state={{ ...unavailable, enabled: true }} consequence="synchronisation impossible" />,
      { session: withIntegrations(["qonto"]) });
    expect(screen.getByText("Qonto indisponible : synchronisation impossible.")).toBeTruthy();
  });
});

describe("factures d'achat sans Qonto", () => {
  it("ni synchronisation, ni statut Qonto ; les factures importées restent", async () => {
    renderWithProviders(<PurchasesPage />, { session: withIntegrations([]) });
    expect(await screen.findByText("F-1")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Synchroniser les factures Qonto" })).toBeNull();
    expect(screen.queryByText("Statut Qonto")).toBeNull();
    expect(screen.queryByText(/modifiée\(s\) dans Qonto/)).toBeNull();
    expect(screen.queryByText(/Qonto : factures à partir du/)).toBeNull();
    expect(screen.getByText("Factures fournisseurs saisies dans l'application.")).toBeTruthy();
  });

  it("avec Qonto activée : synchronisation et statut", async () => {
    renderWithProviders(<PurchasesPage />, { session: withIntegrations(["qonto"]) });
    expect(await screen.findByText(/Qonto : factures à partir du/)).toBeTruthy();
    expect(screen.getByRole("button", { name: "Synchroniser les factures Qonto" })).toBeTruthy();
    expect(screen.getAllByText("Statut Qonto").length).toBeGreaterThan(0);
  });
});
