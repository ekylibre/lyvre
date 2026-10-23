// Intégration nécessaire (lot I4) : clic sur une action courante sans l'intégration, ou réponse
// `integration_required` de l'API → fenêtre qui propose d'activer l'intégration.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MantineProvider } from "@mantine/core";
import { ModalsProvider } from "@mantine/modals";
import { QueryClientProvider, useMutation } from "@tanstack/react-query";
import { MemoryRouter } from "react-router";
import { ApiError } from "../api/client";
import { SESSION_KEY, type Session } from "../api/session";
import { createQueryClient } from "../app/providers";
import { theme } from "../app/theme";
import RemindersPage from "../features/members/RemindersPage";
import { renderWithProviders, TEST_SESSION } from "../test/render";

const calls: string[] = [];
const json = (status: number, body: unknown) => Promise.resolve(new Response(JSON.stringify(body), { status }));
const SMTP_OFF: Session = { ...TEST_SESSION, instance: { ...TEST_SESSION.instance!, integrations: { enabled: [], proposed: [] } } };
const ADMIN_SMTP_OFF: Session = { ...SMTP_OFF, role: "admin", permissions: { write: true, instance_admin: true } };

beforeEach(() => {
  calls.length = 0;
  vi.spyOn(globalThis, "fetch").mockImplementation(((input: RequestInfo | URL, init: RequestInit = {}) => {
    calls.push(`${init.method ?? "GET"} ${String(input)}`);
    return json(200, { items: [{ id: 1, name: "Ancien", email: "a@example.org", is_benevole: false }],
      meta: { helloasso_url: "", integrations: { smtp: { enabled: false, available: false, message: null },
        helloasso: { enabled: false, available: false, message: null }, odoo: { enabled: false, available: false, message: null } } } });
  }) as typeof fetch);
});

afterEach(() => vi.restoreAllMocks());

describe("intégration nécessaire", () => {
  it("relance sans SMTP : bouton actif, fenêtre, aucun envoi", async () => {
    const user = userEvent.setup();
    renderWithProviders(<RemindersPage />, { session: ADMIN_SMTP_OFF });
    await screen.findByText("Ancien");
    const button = screen.getByRole("button", { name: "Envoyer la relance" });
    expect((button as HTMLButtonElement).disabled).toBe(false);
    await user.click(button);
    expect(await screen.findByText("L'envoi des relances par email nécessite l'intégration SMTP (emails), désactivée.")).toBeTruthy();
    expect(screen.getByRole("link", { name: "Activer l'intégration" }).getAttribute("href")).toBe("/configuration/integrations/smtp");
    expect(calls.filter((c) => c.startsWith("POST"))).toEqual([]);
  });

  it("sans droit d'administration : contacter un administrateur", async () => {
    const user = userEvent.setup();
    renderWithProviders(<RemindersPage />, { session: SMTP_OFF });
    await screen.findByText("Ancien");
    await user.click(screen.getByRole("button", { name: "Envoyer la relance" }));
    expect(await screen.findByText("Contactez un administrateur de l'instance pour l'activer.")).toBeTruthy();
    expect(screen.queryByRole("link", { name: "Activer l'intégration" })).toBeNull();
  });

  it("réponse integration_required de l'API : même fenêtre", async () => {
    const client = createQueryClient();
    client.setQueryData(SESSION_KEY, ADMIN_SMTP_OFF);
    function Send() {
      const send = useMutation({ mutationFn: () => Promise.reject(new ApiError("integration_required",
        "Cette action nécessite l'intégration SMTP (emails), désactivée.", 409, {}, { service: "smtp" })) });
      return <button onClick={() => send.mutate()}>Envoyer</button>;
    }
    render(
      <QueryClientProvider client={client}>
        <MantineProvider theme={theme} env="test"><ModalsProvider><MemoryRouter><Send /></MemoryRouter></ModalsProvider></MantineProvider>
      </QueryClientProvider>,
    );
    await userEvent.setup().click(screen.getByRole("button", { name: "Envoyer" }));
    expect(await screen.findByText("Cette action nécessite l'intégration SMTP (emails), désactivée.")).toBeTruthy();
    expect(screen.getByText("Intégration SMTP (emails) désactivée")).toBeTruthy();
  });
});
