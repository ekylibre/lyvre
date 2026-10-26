// Nouveautés (lot R2) : pastille dans le menu tant que la version courante n'a pas été vue, page avec
// actions requises en tête et étiquettes de structure, ouverture qui enregistre la version vue.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithProviders, TEST_SESSION } from "../../test/render";
import type { Session } from "../../api/session";
import { AppLayout } from "../../app/AppShell/AppLayout";
import ChangelogPage from "./ChangelogPage";

const session = (seen: string): Session => ({ ...TEST_SESSION, app: { version: "2026.10.19", commit: "a1b2c3d4e5f6" },
  preferences: { changelog_seen: seen } });

let patches: unknown[];
beforeEach(() => {
  patches = [];
  vi.spyOn(globalThis, "fetch").mockImplementation(((input: RequestInfo | URL, init: RequestInit = {}) => {
    const url = String(input);
    if (init.method === "PATCH") patches.push(JSON.parse(String(init.body)));
    const body = url === "/api/v1/changelog" ? { version: "2026.10.19", items: [
      { version: "2026.10.19", date: "2026-10-27", title: "Version et nouveautés", entries: [
        { kind: "new", text: "Page Nouveautés." },
        { kind: "action", structure: "asso", text: "Autoriser l'IP du serveur dans Brevo." },
        { kind: "new", structure: "sci", text: "Carte du bail." }] },
      { version: "2026.10.18", date: "2026-10-26", title: "Brevo", entries: [{ kind: "fixed", text: "Correctif." }] },
    ] } : { items: [], unread: 0, preferences: {} };
    return Promise.resolve(new Response(JSON.stringify(body), { status: 200 }));
  }) as typeof fetch);
});
afterEach(() => vi.restoreAllMocks());

describe("menu utilisateur", () => {
  it("pastille et « nouveau » tant que la version n'a pas été vue, version en bas du menu", async () => {
    renderWithProviders(<AppLayout><div /></AppLayout>, { session: session("2026.10.18") });
    await userEvent.click(screen.getByRole("button", { name: "Menu utilisateur (nouveautés)" }));
    expect(await screen.findByText("nouveau")).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: /Nouveautés/ })).toHaveAttribute("href", "/changelog");
    expect(screen.getByText("Lyvre 2026.10.19 · a1b2c3d")).toBeInTheDocument();
  });

  it("rien de nouveau une fois vue", async () => {
    renderWithProviders(<AppLayout><div /></AppLayout>, { session: session("2026.10.19") });
    await userEvent.click(screen.getByRole("button", { name: "Menu utilisateur" }));
    expect(await screen.findByRole("menuitem", { name: /Nouveautés/ })).toBeInTheDocument();
    expect(screen.queryByText("nouveau")).not.toBeInTheDocument();
  });
});

describe("page Nouveautés", () => {
  it("actions requises en tête, étiquettes, version enregistrée comme vue", async () => {
    renderWithProviders(<ChangelogPage />, { session: session("2026.10.18") });
    expect(await screen.findByText("Version et nouveautés")).toBeInTheDocument();
    expect(screen.getByText("Version actuelle")).toBeInTheDocument();
    expect(screen.getByText("Action requise")).toBeInTheDocument();
    expect(screen.getByText("Associations")).toBeInTheDocument();
    expect(screen.getByText("SCI")).toBeInTheDocument();
    expect(screen.getByText("Corrections")).toBeInTheDocument();
    await waitFor(() => expect(patches).toContainEqual({ changelog_seen: "2026.10.19" }), { timeout: 2000 });
  });
});
