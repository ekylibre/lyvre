// Lot AG9a.a : profil des démarches (onglet Activités et démarches).
import { afterEach, describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithProviders, TEST_SESSION } from "../../test/render";
import { AgriActivities } from "./AgriActivities";

const json = (body: unknown) => Promise.resolve(new Response(JSON.stringify(body), { status: 200 }));
const META = {
  booleans: [{ value: "pac", label: "Demandeur des aides PAC" }, { value: "employer", label: "Employeur de salariés" }],
  dates: [{ value: "certiphyto_expires_on", label: "Fin de validité du Certiphyto" }],
  productions: [{ value: "cattle", label: "Bovins" }], msa_funds: [{ value: "other", label: "Autre caisse" }],
  lease_roles: [{ value: "tenant", label: "Preneur" }],
};

afterEach(() => vi.restoreAllMocks());

describe("Activités et démarches", () => {
  it("enregistre une réponse et un bail", async () => {
    const fetch = vi.spyOn(globalThis, "fetch").mockImplementation(((_url: string, init?: RequestInit) =>
      json({ item: init?.method === "PUT" ? JSON.parse(String(init.body)) : { pac: true }, meta: META, notices: [] })) as typeof globalThis.fetch);
    renderWithProviders(<AgriActivities />, {
      session: { ...TEST_SESSION, role: "admin" as const, permissions: { write: true, instance_admin: true } } });
    expect(await screen.findByText("Demandeur des aides PAC")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Ajouter un bail" }));
    await userEvent.type(screen.getByLabelText("Bail"), "Grands Champs");
    await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
    const put = fetch.mock.calls.find(([, init]) => (init as RequestInit | undefined)?.method === "PUT");
    expect(JSON.parse(String((put![1] as RequestInit).body))).toEqual({
      pac: true, leases: [{ label: "Grands Champs", due: "11-11", role: "tenant" }] });
  });
});
