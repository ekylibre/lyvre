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

  it("indice de la comptabilité, réponse proposée et compteur d'échéances", async () => {
    const fetch = vi.spyOn(globalThis, "fetch").mockImplementation(((_url: string, init?: RequestInit) =>
      json({ item: init?.method === "PUT" ? JSON.parse(String(init.body)) : { pac: false }, meta: META, notices: [],
        hints: { pac: { text: "Compte 742 mouvementé : 10 000 €.", suggested: true, conflict: true },
          employer: { text: "Compte 641 mouvementé : 500 €.", suggested: true, conflict: false } },
        uses: { pac: ["PAC-01 Demande d'aides PAC (telepac)", "PAC-02 Aides animales couplées"] } })) as typeof globalThis.fetch);
    renderWithProviders(<AgriActivities />, {
      session: { ...TEST_SESSION, role: "admin" as const, permissions: { write: true, instance_admin: true } } });
    expect(await screen.findByText("2 échéances")).toBeInTheDocument();
    expect(screen.getByText(/la comptabilité indique le contraire : Compte 742/)).toBeInTheDocument();
    expect(screen.getByText(/Indice dans la comptabilité : Compte 641/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Répondre oui" }));   // seulement pour la question sans réponse
    await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
    const put = fetch.mock.calls.find(([, init]) => (init as RequestInit | undefined)?.method === "PUT");
    expect(JSON.parse(String((put![1] as RequestInit).body))).toEqual({ pac: false, employer: true });
  });
});
