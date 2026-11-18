import { afterEach, describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithProviders, TEST_SESSION } from "../../test/render";
import LoginPage, { afterLogin } from "./LoginPage";

const ANONYMOUS = { ...TEST_SESSION, user: null, instance: null, instances: [] };

afterEach(() => {
  vi.restoreAllMocks();
  document.querySelector('meta[name="lyvre-demo"]')?.remove();
});

describe("LoginPage", () => {
  it("affiche l'erreur de connexion une seule fois", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify(
      { error: { code: "validation_error", message: "Email ou mot de passe incorrect." } }), { status: 422 }));
    renderWithProviders(<LoginPage />, { session: ANONYMOUS, route: "/login" });
    await userEvent.type(screen.getByLabelText(/Email/), "a@b.c");
    await userEvent.type(screen.getByLabelText(/Mot de passe/), "x");
    await userEvent.click(screen.getByRole("button", { name: "Se connecter" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Email ou mot de passe incorrect.");
  });

  it("envoie vers le choix d'instance s'il n'y en a pas", () => {
    expect(afterLogin(TEST_SESSION, "/entries/")).toBe("/entries/");
    expect(afterLogin(ANONYMOUS, "/entries/")).toBe("/select-instance?next=%2Fentries%2F");
  });

  it("impose le choix du mot de passe avant tout", () => {
    const flagged = { ...TEST_SESSION, user: { ...TEST_SESSION.user!, must_change_password: true } };
    expect(afterLogin(flagged, "/entries/")).toBe("/password?next=%2Fentries%2F");
  });

  it("démonstration : affiche les identifiants et les remplit", async () => {
    const meta = document.createElement("meta");
    meta.name = "lyvre-demo";
    meta.dataset.email = "demo@lyvre.org";
    meta.dataset.password = "demo-lyvre";
    document.head.append(meta);
    renderWithProviders(<LoginPage />, { session: ANONYMOUS, route: "/login" });
    expect(screen.getByText("demo-lyvre")).toBeInTheDocument();
    expect(screen.queryByText("Mot de passe oublié ?")).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Remplir les identifiants" }));
    expect(screen.getByLabelText(/Email/)).toHaveValue("demo@lyvre.org");
  });
});
