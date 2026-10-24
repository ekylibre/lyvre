// Lot L4 : fiche du bail — envoi à la signature (confirmation, signataires), bail envoyé verrouillé.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { notifications } from "@mantine/notifications";
import { Route, Routes } from "react-router";
import { renderWithProviders } from "../../test/render";
import LeaseDetailPage from "./LeaseDetailPage";

type Call = { method: string; url: string };
let calls: Call[];
const json = (status: number, body: unknown) => Promise.resolve(new Response(JSON.stringify(body), { status }));
const SIGNERS = [{ role: "Bailleur 1", name: "Gérante Dupont", email: "dupont@exemple.org" },
  { role: "Preneur", name: "Association Preneuse", email: "preneur@exemple.org" }];
const base = {
  id: 3, status: "active", unit_label: "La Vauzelle", tenant: { id: 2, name: "Association Preneuse" }, kind: "derogatory",
  kind_label: "Bail dérogatoire commercial", premises_label: "", address_line1: "", address_line2: "", postal_code: "", city: "",
  start_date: "2026-10-01", end_date: null, rent_cents: 52840, annual_cents: 52840, charges_cents: 0, deposit_cents: 0,
  deposit_entry: null, due_day: 1, in_advance: true, next_date: "2027-10-01", items: [], invoices: [], receipts: [],
  document: { generated_at: "2026-10-25T09:00:00", edited: false, frozen: true, preview_url: "/api/v1/leases/3/preview.pdf" },
  signers_planned: SIGNERS, signature_problems: [] as string[], locked: false, signature: null as unknown, notes: "",
};
const SENT = { id: 7, status: "sent", status_label: "Envoyé à la signature", sent_at: "2026-10-25T10:00:00", completed_at: null,
  checked_at: null, error: null, files: { sent: "/api/v1/lease-signatures/7/sent.pdf" },
  signers: SIGNERS.map((s, i) => ({ ...s, status: i ? "awaiting" : "sent", status_label: i ? "En attente" : "Invitation envoyée", signed_at: null, declined_at: null })) };
let lease: typeof base;

beforeEach(() => {
  calls = [];
  lease = base;
  vi.spyOn(notifications, "show").mockReturnValue("id");
  vi.spyOn(globalThis, "fetch").mockImplementation(((input: RequestInfo | URL, init: RequestInit = {}) => {
    const url = String(input);
    const method = init.method ?? "GET";
    calls.push({ method, url });
    if (url === "/api/v1/leases/3" && method === "GET") return json(200, { item: lease });
    if (url === "/api/v1/leases") return json(200, { items: [], meta: { tenants: [], accounts: [], bank_accounts: [] } });
    if (url === "/api/v1/leases/3/signature" && method === "POST") {
      lease = { ...base, locked: true, signature: SENT };
      return json(200, { item: lease, notices: [] });
    }
    return json(404, {});
  }) as typeof fetch);
});
afterEach(() => vi.restoreAllMocks());

describe("signature du bail", () => {
  it("envoi confirmé, puis bail verrouillé avec le suivi des signataires", async () => {
    const user = userEvent.setup();
    renderWithProviders(<Routes><Route path="/leases/:lease_id" element={<LeaseDetailPage />} /></Routes>, { route: "/leases/3" });
    expect(await screen.findByRole("link", { name: "Modifier" })).toBeTruthy();
    await user.click(screen.getByRole("button", { name: "Envoyer à la signature" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText(/Gérante Dupont \(dupont@exemple.org\), puis Association Preneuse/)).toBeTruthy();
    await user.click(within(dialog).getByRole("button", { name: "Envoyer" }));
    await waitFor(() => expect(calls.some((c) => c.method === "POST" && c.url === "/api/v1/leases/3/signature")).toBe(true));
    expect(await screen.findByText("Envoyé à la signature")).toBeTruthy();
    expect(screen.getByText("Invitation envoyée")).toBeTruthy();
    expect(screen.queryByRole("link", { name: "Modifier" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Retoucher" })).toBeNull();
    expect(screen.getByRole("button", { name: "Annuler l'envoi" })).toBeTruthy();
  });

  it("envoi impossible tant qu'il manque un e-mail", async () => {
    lease = { ...base, signature_problems: ["E-mail manquant sur la fiche du preneur Association Preneuse."] };
    renderWithProviders(<Routes><Route path="/leases/:lease_id" element={<LeaseDetailPage />} /></Routes>, { route: "/leases/3" });
    expect(await screen.findByText("Envoi impossible")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Envoyer à la signature" })).toHaveProperty("disabled", true);
  });
});
