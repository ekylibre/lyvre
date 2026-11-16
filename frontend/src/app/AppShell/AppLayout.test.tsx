import { afterEach, describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithProviders, TEST_SESSION } from "../../test/render";
import { AppLayout } from "./AppLayout";

const SESSION = {
  ...TEST_SESSION,
  user: { ...TEST_SESSION.user!, is_admin: true },
  instances: [{ id: 1, label: "Test" }, { id: 2, label: "SCI" }],
  nav: [
    { key: "dashboard", label: "Tableau de bord", url: "/" },
    { key: "compta", label: "Compta", items: [
      { key: "entries", label: "Écritures", url: "/entries/" },
      { divider: true as const },
      { key: "journals", label: "Journaux", url: "/journals/" },
    ] },
  ],
  admin_links: [{ label: "Utilisateurs", url: "/users/" }],
};

afterEach(() => vi.restoreAllMocks());

describe("AppLayout", () => {
  it("affiche instance, menus de la session et contenu", async () => {
    renderWithProviders(<AppLayout><p>Contenu</p></AppLayout>, { session: SESSION, route: "/entries/" });
    expect(screen.getByText("Contenu")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Changer d'instance" })).toHaveTextContent("Test");
    expect(screen.getByRole("link", { name: "Tableau de bord" })).toHaveAttribute("href", "/");
    // Menu de la page courante ouvert, lien actif.
    expect(screen.getByRole("link", { name: "Écritures" })).toHaveAttribute("data-active", "true");
    await userEvent.click(screen.getByRole("button", { name: "Menu utilisateur" }));
    expect(await screen.findByRole("menuitem", { name: "Utilisateurs" })).toHaveAttribute("href", "/users/");
  });

  it("change de thème et l'enregistre dans le compte", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response("{}", { status: 200 }));
    renderWithProviders(<AppLayout><p /></AppLayout>, { session: SESSION });
    await userEvent.click(screen.getByRole("button", { name: "Changer de thème" }));
    await vi.advanceTimersByTimeAsync(600);
    const patch = fetchMock.mock.calls.find(([url]) => String(url) === "/api/v1/me/preferences");
    expect(JSON.parse(String(patch?.[1]?.body))).toEqual({ color_scheme: "dark" });
    vi.useRealTimers();
  });
});

describe("menu en rail (lot NV4)", () => {
  const desktop = () => vi.spyOn(window, "matchMedia").mockImplementation((query: string) => ({
    matches: query.includes("min-width"), media: query, onchange: null, addListener: () => undefined,
    removeListener: () => undefined, addEventListener: () => undefined, removeEventListener: () => undefined,
    dispatchEvent: () => false,
  }) as MediaQueryList);

  it("replie le menu en icônes, sous-menus flottants, et mémorise le choix", async () => {
    desktop();
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response("{}", { status: 200 }));
    renderWithProviders(<AppLayout><p /></AppLayout>,
      { session: { ...SESSION, preferences: { nav_rail: true } }, route: "/entries/" });
    expect(screen.queryByText("Journaux")).toBeNull();
    const compta = screen.getByRole("button", { name: "Compta" });
    expect(compta).toHaveAttribute("data-active", "true");
    await userEvent.click(compta);
    expect(await screen.findByRole("menuitem", { name: "Écritures" })).toHaveAttribute("aria-current", "page");
    await userEvent.keyboard("{Escape}");
    await userEvent.click(screen.getByRole("button", { name: "Déplier le menu" }));
    await vi.advanceTimersByTimeAsync(600);
    const patch = fetchMock.mock.calls.find(([url]) => String(url) === "/api/v1/me/preferences");
    expect(JSON.parse(String(patch?.[1]?.body))).toEqual({ nav_rail: false });
    vi.useRealTimers();
  });

  it("sur mobile, le tiroir reste déplié malgré la préférence", () => {
    renderWithProviders(<AppLayout><p /></AppLayout>,
      { session: { ...SESSION, preferences: { nav_rail: true } }, route: "/entries/" });
    expect(screen.getByRole("link", { name: "Écritures" })).toBeInTheDocument();
  });
});

describe("menu actif", () => {
  it("retient l'entrée la plus précise", async () => {
    const { activeUrl } = await import("./AppLayout");
    const menus = [{ key: "tiers", label: "Tiers", items: [
      { key: "entities", label: "Entités", url: "/entities/" },
      { key: "members", label: "Adhérents", url: "/entities/members" },
    ] }, { key: "dashboard", label: "Tableau de bord", url: "/" }];
    expect(activeUrl(menus, "/entities/members")).toBe("/entities/members");
    expect(activeUrl(menus, "/entities/12")).toBe("/entities/");
    expect(activeUrl(menus, "/entities-x")).toBeNull();
    expect(activeUrl(menus, "/")).toBe("/");
  });
});

describe("sous-menus de 3e niveau (lot NV1)", () => {
  it("ouvre le sous-menu de la page active et retient son entrée", async () => {
    const nav = [{ key: "compta", label: "Compta", icon: "calculator", items: [
      { key: "entries", label: "Écritures", url: "/entries/", icon: "notebook-pen" },
      { key: "editions", label: "Éditions comptables", icon: "file-chart-column", items: [
        { key: "balance", label: "Balance", url: "/reports/balance", icon: "scale" },
        { key: "bilan", label: "Bilan", url: "/reports/bilan", icon: "landmark" },
      ] },
    ] }];
    renderWithProviders(<AppLayout><p /></AppLayout>, { session: { ...SESSION, nav }, route: "/reports/bilan" });
    expect(screen.getByRole("link", { name: "Bilan" })).toHaveAttribute("data-active", "true");
    expect(screen.getByRole("link", { name: "Balance" })).toBeInTheDocument();     // sous-menu ouvert d'office
    const { activeUrl } = await import("./AppLayout");
    expect(activeUrl(nav, "/reports/balance")).toBe("/reports/balance");
  });
});
