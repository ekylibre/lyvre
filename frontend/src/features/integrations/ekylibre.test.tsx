// Lot AG11.a : connexion Ekylibre (mot de passe à usage unique), état des données lues.
import { afterEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithProviders } from "../../test/render";
import { EkylibreConnection, type EkylibreState } from "./EkylibreConnection";

const json = (body: unknown) => Promise.resolve(new Response(JSON.stringify(body), { status: 200 }));
afterEach(() => vi.restoreAllMocks());

const STATE: EkylibreState = {
  enabled: true, configured: false, url: "", email: "", job: null,
  snapshots: {
    productions: { label: "cultures", count: 12, synced_at: "2026-11-07T10:00:00" },
    interventions: { label: "interventions", count: null, synced_at: null },
    matters: { label: "matières", count: null, synced_at: null },
  },
};

describe("Connexion Ekylibre", () => {
  it("envoie le mot de passe une fois et affiche les données lues", async () => {
    const spy = vi.spyOn(globalThis, "fetch").mockImplementation(((_url: string, init?: RequestInit) =>
      json(init?.method === "POST" ? { ...STATE, configured: true, notices: [] } : STATE)) as typeof fetch);
    renderWithProviders(<EkylibreConnection />);
    expect(await screen.findByText("cultures")).toBeInTheDocument();
    expect(screen.getByText("12")).toBeInTheDocument();
    expect(screen.getAllByText("jamais")).toHaveLength(2);
    expect(screen.getByRole("button", { name: "Lire Ekylibre" })).toBeDisabled();
    await userEvent.type(screen.getByLabelText(/Adresse de l'instance/), "https://demo.ekylibre.test");
    await userEvent.type(screen.getByLabelText(/Email Ekylibre/), "camille@example.org");
    await userEvent.type(screen.getByLabelText(/Mot de passe/), "secret");
    await userEvent.click(screen.getByRole("button", { name: "Se connecter" }));
    await waitFor(() => expect(spy.mock.calls.some(([, i]) => (i as RequestInit | undefined)?.method === "POST")).toBe(true));
    const post = spy.mock.calls.find(([, i]) => (i as RequestInit | undefined)?.method === "POST")!;
    expect(post[0]).toBe("/api/v1/ekylibre/connect");
    expect(JSON.parse(String((post[1] as RequestInit).body))).toEqual(
      { url: "https://demo.ekylibre.test", email: "camille@example.org", password: "secret" });
  });
});
