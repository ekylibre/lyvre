// Mot de passe oublié : demande du lien (réponse identique pour tous), lien expiré, nouveau mot de passe.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Route, Routes } from "react-router";
import { renderWithProviders } from "../../test/render";
import ForgotPasswordPage from "./ForgotPasswordPage";
import ResetPasswordPage from "./ResetPasswordPage";

type Call = { url: string; body: any }; // eslint-disable-line @typescript-eslint/no-explicit-any
let calls: Call[];
let valid: boolean;
const json = (status: number, body: unknown) => Promise.resolve(new Response(JSON.stringify(body), { status }));

beforeEach(() => {
  calls = [];
  valid = true;
  vi.spyOn(globalThis, "fetch").mockImplementation(((input: RequestInfo | URL, init: RequestInit = {}) => {
    const url = String(input);
    calls.push({ url, body: init.body ? JSON.parse(init.body as string) : undefined });
    if (url === "/api/v1/session/password-forgot") return json(200, { notices: [{ level: "success", message: "Si un compte correspond à cette adresse, un e-mail…" }] });
    if (url === "/api/v1/session/password-reset/check") return json(200, valid ? { valid: true, email: "gerante@exemple.org" } : { valid: false, email: null });
    if (url === "/api/v1/session/password-reset") return json(200, { notices: [] });
    return json(404, {});
  }) as typeof fetch);
});
afterEach(() => vi.restoreAllMocks());

describe("mot de passe oublié", () => {
  it("demande du lien", async () => {
    const user = userEvent.setup();
    renderWithProviders(<ForgotPasswordPage />);
    await user.type(screen.getByLabelText(/^Email/), "gerante@exemple.org");
    await user.click(screen.getByRole("button", { name: "Recevoir le lien" }));
    expect(await screen.findByText(/Si un compte correspond à cette adresse/)).toBeTruthy();
    expect(calls[0].body).toEqual({ email: "gerante@exemple.org" });
  });

  it("nouveau mot de passe : confirmation vérifiée, puis connexion", async () => {
    const user = userEvent.setup();
    renderWithProviders(<Routes><Route path="/password/reset" element={<ResetPasswordPage />} />
      <Route path="/login" element={<p>Page de connexion</p>} /></Routes>, { route: "/password/reset?token=abc" });
    expect(await screen.findByText("gerante@exemple.org")).toBeTruthy();
    await user.type(screen.getByLabelText(/^Nouveau mot de passe/), "nouveau-mot-de-passe");
    await user.type(screen.getByLabelText(/^Confirmation/), "autre-chose");
    await user.click(screen.getByRole("button", { name: "Enregistrer le mot de passe" }));
    expect(screen.getByText("Les deux saisies ne sont pas identiques.")).toBeTruthy();
    await user.clear(screen.getByLabelText(/^Confirmation/));
    await user.type(screen.getByLabelText(/^Confirmation/), "nouveau-mot-de-passe");
    await user.click(screen.getByRole("button", { name: "Enregistrer le mot de passe" }));
    await waitFor(() => expect(calls.find((c) => c.url === "/api/v1/session/password-reset")?.body)
      .toEqual({ token: "abc", password: "nouveau-mot-de-passe" }));
    expect(await screen.findByText("Page de connexion")).toBeTruthy();
  });

  it("lien expiré : proposer un nouveau lien", async () => {
    valid = false;
    renderWithProviders(<ResetPasswordPage />, { route: "/password/reset?token=vieux" });
    expect(await screen.findByText(/invalide, expiré ou a déjà servi/)).toBeTruthy();
    expect(screen.getByRole("link", { name: "Recevoir un nouveau lien" })).toBeTruthy();
  });
});
