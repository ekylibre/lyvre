// Brevo (lot B1) : liste des adhérents choisie parmi les listes du compte (saisie du numéro sans clé
// ou en cas d'erreur), attributs présents / à créer et création explicite.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithProviders } from "../../test/render";
import { BrevoAttributes, BrevoListField } from "./BrevoSettings";

let calls: string[];
let listsStatus = 200;
beforeEach(() => {
  calls = [];
  listsStatus = 200;
  vi.spyOn(globalThis, "fetch").mockImplementation(((input: RequestInfo | URL, init: RequestInit = {}) => {
    const url = String(input);
    calls.push(`${init.method ?? "GET"} ${url}`);
    const json = (status: number, body: unknown) => Promise.resolve(new Response(JSON.stringify(body), { status }));
    if (url === "/api/v1/brevo/lists") return listsStatus === 200
      ? json(200, { items: [{ value: "12", label: "Adhérents (Lyvre)", contacts: 3 }], selected: null })
      : json(409, { error: { code: "brevo_ip_not_allowed", message: "L'adresse IP du serveur n'est pas autorisée dans Brevo" } });
    const items = [{ name: "PRENOM", type: "text", label: "Prénom", shared: true, present: true },
      { name: "LYVRE_STATUT", type: "text", label: "Statut d'adhésion", shared: false, present: init.method === "POST" }];
    return json(200, { items, notices: [] });
  }) as typeof fetch);
});
afterEach(() => vi.restoreAllMocks());

describe("liste des adhérents", () => {
  it("choisie parmi les listes du compte", async () => {
    const onChange = vi.fn();
    renderWithProviders(<BrevoListField label="Liste des adhérents" value="" onChange={onChange} keySaved />);
    const input = await screen.findByPlaceholderText("Choisir");
    await userEvent.click(input);
    await userEvent.click(await screen.findByText("Adhérents (Lyvre) (3 contacts)"));
    expect(onChange).toHaveBeenCalledWith("12");
  });

  it("sans clé enregistrée : saisie du numéro, sans appel", () => {
    renderWithProviders(<BrevoListField label="Liste des adhérents" value="" onChange={() => undefined} keySaved={false} />);
    expect(screen.getByPlaceholderText("N° de la liste")).toBeInTheDocument();
    expect(calls).toEqual([]);
  });

  it("IP non autorisée : message et saisie du numéro", async () => {
    listsStatus = 409;
    renderWithProviders(<BrevoListField label="Liste des adhérents" value="" onChange={() => undefined} keySaved />);
    expect(await screen.findByText(/n'est pas autorisée dans Brevo/)).toBeInTheDocument();
    expect(screen.getByPlaceholderText("N° de la liste")).toBeInTheDocument();
  });
});

describe("attributs", () => {
  it("présents, à créer, création explicite", async () => {
    renderWithProviders(<BrevoAttributes admin />);
    expect(await screen.findByText("à créer")).toBeInTheDocument();
    expect(screen.getByText("complété s'il est vide")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Créer les attributs manquants (1)" }));
    await waitFor(() => expect(calls).toContain("POST /api/v1/brevo/attributes"));
    await waitFor(() => expect(screen.queryByText("à créer")).not.toBeInTheDocument());
  });
});
