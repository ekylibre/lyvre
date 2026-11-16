// Lot AG2.c : acomptes du RSA (3525 bis) affichés sous la CA12A annuelle.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import { renderWithProviders, TEST_SESSION } from "../../test/render";
import { InstallmentsPanel } from "./InstallmentsPanel";
import type { InstallmentSchedule } from "./types";

const json = (body: unknown) => Promise.resolve(new Response(JSON.stringify(body), { status: 200 }));
const item = (number: number, deadline: string, extra = {}) => ({
  number, label: `T${number}`, start: "2026-01-01", end: "2026-03-31", deadline, status: "to_prepare" as const,
  status_label: "À préparer", late: false, amount_cents: null, motive: null, can_validate: number === 2, return: null, ...extra,
});
const SCHEDULE: InstallmentSchedule = {
  period: "2026-A", label: "2026", start: "2026-01-01", end: "2026-12-31", dispensed: false, proposed_cents: 100100,
  planned_cents: 300300, exemption_cents: 100000, share_bp: 2000,
  reference: { source: "ca12a", due_cents: 500300, assets_cents: 50000, before_assets_cents: 550300, label: "2025" },
  estimate: null, annual_return: null, warnings: [],
  items: [item(1, "2026-05-05", { status: "validated", status_label: "Enregistré", amount_cents: 0, motive: "Suspension",
    return: { id: 7, status: "validated", status_label: "Enregistré", due_cents: 0, credit_cents: 0, refund_cents: 0,
      credit_carried_cents: 0, declared_on: null, declared_reference: null, validated_at: null, liquidation_entry: null } }),
    item(2, "2026-08-05"), item(3, "2026-11-05"), item(4, "2027-02-05")],
};

let body: InstallmentSchedule = SCHEDULE;
beforeEach(() => { vi.spyOn(globalThis, "fetch").mockImplementation((() => json(body)) as typeof fetch); });
afterEach(() => vi.restoreAllMocks());
const session = { ...TEST_SESSION, role: "admin" as const, permissions: { write: true, instance_admin: true } };

describe("Acomptes de TVA", () => {
  it("échéancier, acompte calculé et actions", async () => {
    body = SCHEDULE;
    renderWithProviders(<InstallmentsPanel period="2026-A" />, { session });
    expect(await screen.findByText(/Acomptes 2026 \(3525 bis\)/)).toBeInTheDocument();
    expect(screen.getByText("05/08/2026")).toBeInTheDocument();
    expect(screen.getByText("Suspension")).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "Enregistrer" })).toHaveLength(1);
    expect(screen.getByRole("button", { name: "Payé" })).toBeInTheDocument();
  });

  it("dispense", async () => {
    body = { ...SCHEDULE, dispensed: true, proposed_cents: null,
      items: SCHEDULE.items.map((i) => ({ ...i, status: "dispensed" as const, status_label: "Dispensé", return: null,
        amount_cents: null, can_validate: false, motive: null })) };
    renderWithProviders(<InstallmentsPanel period="2026-A" />, { session });
    expect(await screen.findByText(/Dispensé d'acomptes/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Enregistrer" })).toBeNull();
  });
});
