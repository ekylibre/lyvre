import { afterEach, describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithProviders, TEST_SESSION } from "../../test/render";
import ChangePasswordPage from "./ChangePasswordPage";

const FLAGGED = { ...TEST_SESSION, user: { ...TEST_SESSION.user!, must_change_password: true } };

afterEach(() => vi.restoreAllMocks());

describe("ChangePasswordPage", () => {
  it("explique le changement imposé et contrôle la saisie avant l'envoi", async () => {
    const fetch = vi.spyOn(globalThis, "fetch");
    renderWithProviders(<ChangePasswordPage />, { session: FLAGGED, route: "/password" });
    expect(screen.getByText(/choisissez le vôtre pour continuer/)).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText(/Mot de passe actuel/), "initial");
    await userEvent.type(screen.getByLabelText(/Nouveau mot de passe/), "court");
    await userEvent.type(screen.getByLabelText(/Confirmation/), "autre");
    await userEvent.click(screen.getByRole("button", { name: "Enregistrer le mot de passe" }));
    expect(await screen.findByText("8 caractères au moins.")).toBeInTheDocument();
    expect(screen.getByText("Les deux saisies diffèrent.")).toBeInTheDocument();
    expect(fetch).not.toHaveBeenCalled();
  });

  it("affiche l'erreur du serveur sur le champ", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify({ error: {
      code: "validation_error", message: "Mot de passe actuel incorrect.",
      fields: { current_password: "Mot de passe actuel incorrect." } } }), { status: 422 }));
    renderWithProviders(<ChangePasswordPage />, { session: FLAGGED, route: "/password" });
    await userEvent.type(screen.getByLabelText(/Mot de passe actuel/), "faux");
    await userEvent.type(screen.getByLabelText(/Nouveau mot de passe/), "nouveau-mdp");
    await userEvent.type(screen.getByLabelText(/Confirmation/), "nouveau-mdp");
    await userEvent.click(screen.getByRole("button", { name: "Enregistrer le mot de passe" }));
    expect(await screen.findByText("Mot de passe actuel incorrect.")).toBeInTheDocument();
  });

  it("propose d'annuler quand le changement est volontaire", () => {
    renderWithProviders(<ChangePasswordPage />, { session: TEST_SESSION, route: "/password" });
    expect(screen.getByRole("button", { name: "Annuler" })).toBeInTheDocument();
  });
});
