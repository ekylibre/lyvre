// Lot AG9b.e : listes de contrôle guidées.
import { afterEach, describe, expect, it, vi } from "vitest";
import { fireEvent, screen } from "@testing-library/react";
import { renderWithProviders, TEST_SESSION } from "../../test/render";
import { ChecklistsPanel, type Checklist } from "./ChecklistsPanel";

const CLOSING: Checklist = { id: "closing", title: "Clôture de l'exercice", summary: "De J-30 à J+60.", period: "2026", start: "2026-12-01",
  end: "2027-03-01", status: "current", profile_incomplete: false, progress: { done: 1, total: 2 },
  steps: [{ id: "bank", label: "Rapprocher les relevés", link: "/reconciliation/", fiche: null, auto: true, auto_done: true, marked_on: null, done: true },
    { id: "aids", label: "Produits à recevoir des aides", link: "/aids/", fiche: "FIS-01", auto: false, auto_done: null, marked_on: null, done: false }] };

afterEach(() => vi.restoreAllMocks());

describe("Listes de contrôle", () => {
  it("étapes automatiques et cases à cocher", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(((url: string) => Promise.resolve(new Response(JSON.stringify(
      String(url).includes("/steps/") ? { notices: [] } : { item: { items: [CLOSING] } }), { status: 200 }))) as typeof globalThis.fetch);
    renderWithProviders(<ChecklistsPanel />, { session: { ...TEST_SESSION, role: "admin" as const, permissions: { write: true, instance_admin: true } } });
    expect(await screen.findByText("Clôture de l'exercice 2026")).toBeInTheDocument();
    expect(screen.getByLabelText("Rapprocher les relevés")).toBeDisabled();
    fireEvent.click(screen.getByLabelText("Produits à recevoir des aides"));
    await vi.waitFor(() => expect(fetchMock.mock.calls.some(([u, init]) => String(u).endsWith("/checklists/closing/2026/steps/aids")
      && (init as RequestInit)?.method === "PUT")).toBe(true));
  });
});
