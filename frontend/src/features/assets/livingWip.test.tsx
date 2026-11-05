// Lot AG5.b : biens vivants en cours à la clôture.
import { afterEach, describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import { renderWithProviders, TEST_SESSION } from "../../test/render";
import { LivingWipPanel } from "./LivingWipPanel";

const json = (body: unknown) => Promise.resolve(new Response(JSON.stringify(body), { status: 200 }));

afterEach(() => vi.restoreAllMocks());

describe("Biens vivants en cours", () => {
  it("coût de croissance à saisir puis à passer", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((() => json({ enabled: true, entry: null, items: [
      { asset_id: 4, label: "Génisses de renouvellement", account_code: "2341", status: "waiting", acquisition_cents: 200000,
        units: 10, species: "Bovin", amount_cents: 150000, basis: "barème", posted: false }] })) as typeof globalThis.fetch);
    renderWithProviders(<LivingWipPanel fyId={3} editable />,
      { session: { ...TEST_SESSION, role: "admin" as const, permissions: { write: true, instance_admin: true } } });
    expect(await screen.findByText("Génisses de renouvellement")).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "Base Génisses de renouvellement" })).toHaveValue("barème");
    expect(screen.getByRole("button", { name: "Passer les en-cours" })).toBeEnabled();
  });
});
