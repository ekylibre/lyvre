// Lot AG3.a : registre des aides PAC et subventions.
import { afterEach, describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithProviders, TEST_SESSION } from "../../test/render";
import AidsPage, { type Aid, type AidList } from "./AidsPage";

const json = (body: unknown) => Promise.resolve(new Response(JSON.stringify(body), { status: 200 }));
const AID: Aid = {
  id: 1, scheme: "basic_income", scheme_label: "Aide de base au revenu (DPB)", label: "Aide de base au revenu (DPB)",
  campaign: 2026, payer: "ASP", nature: "operating", nature_label: "Subvention d'exploitation",
  account: { id: 9, code: "7451", label: "Aide de base au revenu (DPB)" }, operating_account: null, investment_share_cents: null,
  trigger: "pac_deadline", trigger_label: "Date limite de la demande PAC", trigger_on: "2026-05-18", trigger_provisional: false,
  decision_on: null, requested_cents: 1800000, notified_cents: null, notified_on: null, acquired_cents: 1800000,
  paid_cents: 1200000, remaining_cents: 600000, payment_request_deadline: null, payment_requested_on: null,
  commitment_end_on: null, status: "requested", status_label: "Demandée", notes: null, warnings: [],
  payments: [{ id: 3, paid_on: "2026-10-16", amount_cents: 1200000, kind: "advance", kind_label: "Avance", note: null, bank_transaction: null }],
};
const LIST: AidList = {
  items: [AID], totals: { requested_cents: 1800000, acquired_cents: 1800000, paid_cents: 1200000, remaining_cents: 600000 },
  meta: { natures: [], triggers: [], statuses: [{ value: "requested", label: "Demandée" }, { value: "granted", label: "Attribuée" }],
    payment_kinds: [{ value: "advance", label: "Avance" }, { value: "balance", label: "Solde" }], campaigns: [2026, 2025] },
};
const admin = { ...TEST_SESSION, role: "admin" as const, permissions: { write: true, instance_admin: true } };

afterEach(() => vi.restoreAllMocks());

describe("Aides et subventions", () => {
  it("liste de la campagne et fiche du dossier", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(((url: string) =>
      json(String(url).includes("/aids/1") ? { item: AID } : LIST)) as typeof fetch);
    renderWithProviders(<AidsPage />, { route: "/aids/?campaign=2026", session: admin });
    expect(await screen.findByText("7451")).toBeInTheDocument();
    expect(screen.getByText("Demandée")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Nouvelle campagne PAC" })).toBeInTheDocument();
    await userEvent.click(screen.getByText("Aide de base au revenu (DPB)"));
    expect(await screen.findByText(/18\/05\/2026/)).toBeInTheDocument();
    expect(screen.getByRole("cell", { name: "Avance" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Ajouter" })).toBeInTheDocument();
  });

  it("campagne PAC proposée d'après le profil", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(((url: string) => json(String(url).includes("pac-campaign")
      ? { items: [{ scheme: "basic_income", label: "Aide de base au revenu (DPB)", account: "7451", checked: true, reason: "dispositif de base", exists: false },
        { scheme: "ichn", label: "ICHN", account: "7441", checked: false, reason: null, exists: false }] }
      : { ...LIST, items: [] })) as typeof fetch);
    renderWithProviders(<AidsPage />, { route: "/aids/?campaign=2026", session: admin });
    await userEvent.click(await screen.findByRole("button", { name: "Nouvelle campagne PAC" }));
    expect(await screen.findByRole("checkbox", { name: "Aide de base au revenu (DPB) (7451)" })).toBeChecked();
    expect(screen.getByRole("checkbox", { name: "ICHN (7441)" })).not.toBeChecked();
    expect(screen.getByRole("button", { name: "Créer les dossiers 2026" })).toBeEnabled();
  });

  it("lecture seule pour l'expert-comptable", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((() => json(LIST)) as typeof fetch);
    renderWithProviders(<AidsPage />, { route: "/aids/", session: { ...TEST_SESSION, role: "accountant" as const,
      permissions: { write: false, instance_admin: false } } });
    expect(await screen.findByText("7451")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Nouveau dossier" })).not.toBeInTheDocument();
  });
});
